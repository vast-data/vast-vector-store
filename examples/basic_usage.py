"""Basic usage of VastDBVectorStore.

Demonstrates creating a store, adding texts with metadata,
performing similarity search, and retrieving documents by ID.

Prerequisites:
    - A running VAST cluster with vector search support
    - A ``.env`` file at the project root (loaded automatically)

Usage:
    python examples/basic_usage.py
"""

from __future__ import annotations

import os
import uuid

import pyarrow as pa
import vastdb
from dotenv import load_dotenv
from langchain_core.embeddings import FakeEmbeddings

from langchain_vastdb import VastDBVectorStore

# ---------------------------------------------------------------------------
# 0. Load environment variables from .env (same mechanism as conftest.py).
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# 1. Read connection credentials from environment variables.
#    Never hardcode credentials in scripts.
# ---------------------------------------------------------------------------
ENDPOINT = os.environ["VASTDB__ENDPOINT"]
ACCESS_KEY = os.environ["VASTDB__ACCESS_KEY"]
SECRET_KEY = os.environ["VASTDB__SECRET_KEY"]
BUCKET = os.environ.get("VASTDB__BUCKET", "example-bucket")

# ---------------------------------------------------------------------------
# 2. Choose an embedding model.
#    FakeEmbeddings is used here so the script runs without an external model.
#    Replace with your actual model, e.g.:
#        from langchain_openai import OpenAIEmbeddings
#        embedding = OpenAIEmbeddings()
# ---------------------------------------------------------------------------
VECTOR_DIM = 1536
embedding = FakeEmbeddings(size=VECTOR_DIM)

# ---------------------------------------------------------------------------
# 3. Create an isolated schema and table for this example run.
#    A unique suffix avoids collisions with concurrent runs.
# ---------------------------------------------------------------------------
run_id = uuid.uuid4().hex[:8]
SCHEMA = f"example_basic_{run_id}"
TABLE = f"example_basic_{run_id}"

TABLE_SCHEMA = pa.schema(
    [
        pa.field("id", pa.string()),
        pa.field("text", pa.string()),
        pa.field(
            "vector",
            pa.list_(
                pa.field("item", pa.float32(), nullable=False), VECTOR_DIM
            ),
        ),
        pa.field("metadata", pa.string()),
    ]
)

session = vastdb.connect(
    endpoint=ENDPOINT, access=ACCESS_KEY, secret=SECRET_KEY, ssl_verify=False
)
with session.transaction() as tx:
    b = tx.bucket(BUCKET)
    b.create_schema(SCHEMA)
    b.schema(SCHEMA).create_table(TABLE, TABLE_SCHEMA)

try:
    # -------------------------------------------------------------------
    # 4. Create a VastDBVectorStore using the convenience factory.
    #    This builds a vastdb.Session internally from the provided
    #    credentials.  ssl_verify=False is needed for self-signed certs.
    # -------------------------------------------------------------------
    store = VastDBVectorStore.from_connection_params(
        embedding=embedding,
        endpoint=ENDPOINT,
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        bucket=BUCKET,
        schema=SCHEMA,
        table_name=TABLE,
        ssl_verify=False,
    )

    # -------------------------------------------------------------------
    # 5. Add texts with metadata.
    #    Each text is embedded automatically by the configured embedding
    #    model.  Metadata is stored as JSON in the metadata column.
    # -------------------------------------------------------------------
    ids = store.add_texts(
        texts=[
            "VastDB is a high-performance analytical database.",
            "LangChain provides tools for building LLM applications.",
            "Vector search finds semantically similar documents.",
        ],
        metadatas=[
            {"source": "docs", "topic": "database"},
            {"source": "docs", "topic": "framework"},
            {"source": "docs", "topic": "search"},
        ],
    )
    print(f"Added {len(ids)} documents with IDs: {ids}")

    # -------------------------------------------------------------------
    # 6. Perform a similarity search.
    #    Returns the k most similar documents to the query text.
    # -------------------------------------------------------------------
    results = store.similarity_search("analytical database", k=2)
    print(f"\nSimilarity search results ({len(results)} docs):")
    for doc in results:
        print(f"  - {doc.page_content!r}  metadata={doc.metadata}")

    # -------------------------------------------------------------------
    # 7. Retrieve documents by ID.
    #    Fetches specific documents without performing a vector search.
    # -------------------------------------------------------------------
    retrieved = store.get_by_ids(ids[:2])
    print(f"\nRetrieved {len(retrieved)} documents by ID:")
    for doc in retrieved:
        print(f"  - [{doc.id}] {doc.page_content!r}")

finally:
    # -------------------------------------------------------------------
    # Cleanup: drop the table and schema created for this run.
    # -------------------------------------------------------------------
    try:
        with session.transaction() as tx:
            sc = tx.bucket(BUCKET).schema(SCHEMA)
            sc.table(TABLE).drop()
            sc.drop()
    except Exception:
        pass
