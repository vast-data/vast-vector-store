"""Subclassing VastDBVectorStore with typed metadata columns.

Demonstrates the declarative ``_typed_metadata_columns`` attribute
that automatically extracts named fields into separate VastDB columns
while preserving any extra metadata in the JSON column.

Prerequisites:
    - A running VAST cluster with vector search support
    - A ``.env`` file at the project root (loaded automatically)

Usage:
    python examples/subclassing.py
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
# 1. Connection setup.
# ---------------------------------------------------------------------------
ENDPOINT = os.environ["VASTDB__ENDPOINT"]
ACCESS_KEY = os.environ["VASTDB__ACCESS_KEY"]
SECRET_KEY = os.environ["VASTDB__SECRET_KEY"]
BUCKET = os.environ.get("VASTDB__BUCKET", "example-bucket")


# ---------------------------------------------------------------------------
# 2. Define a subclass that uses typed metadata columns.
#
#    Instead of storing metadata as a single JSON string (the default),
#    this subclass promotes "category" and "source" to separate typed
#    columns.  This enables efficient columnar filtering in VastDB.
#
#    Only one declaration is needed:
#      - _typed_metadata_columns: names of fields to promote
#
#    The base class automatically derives _select_columns,
#    _metadata_columns, and _row_to_document from this declaration.
#    Extra metadata fields (not listed) are preserved in the JSON column.
# ---------------------------------------------------------------------------


class TypedMetadataStore(VastDBVectorStore):
    """A VastDBVectorStore that promotes metadata fields to typed columns."""

    _typed_metadata_columns = ("category", "source")


# ---------------------------------------------------------------------------
# 3. Create an isolated schema and table for this example run.
#    The table includes typed "category" and "source" columns alongside
#    the default "metadata" JSON column for extra fields.
# ---------------------------------------------------------------------------
VECTOR_DIM = 1536
embedding = FakeEmbeddings(size=VECTOR_DIM)

run_id = uuid.uuid4().hex[:8]
SCHEMA = f"example_subcls_{run_id}"
TABLE = f"example_subcls_{run_id}"

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
        pa.field("category", pa.string()),
        pa.field("source", pa.string()),
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
    # 4. Create a TypedMetadataStore instance and add documents.
    #    Note the third document has an "extra" field not declared in
    #    _typed_metadata_columns — it is preserved in the JSON column.
    # -------------------------------------------------------------------
    store = TypedMetadataStore.from_connection_params(
        embedding=embedding,
        endpoint=ENDPOINT,
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        bucket=BUCKET,
        schema=SCHEMA,
        table_name=TABLE,
        ssl_verify=False,
    )

    ids = store.add_texts(
        texts=[
            "VastDB stores columnar data for analytics.",
            "LangChain enables building LLM-powered applications.",
            "Vector search uses embeddings to find similar content.",
        ],
        metadatas=[
            {"category": "database", "source": "vastdb-docs"},
            {"category": "framework", "source": "langchain-docs"},
            {"category": "search", "source": "ml-handbook", "extra": "preserved"},
        ],
    )
    print(f"Added {len(ids)} documents with typed metadata columns.")

    # -------------------------------------------------------------------
    # 5. Search and observe that metadata comes from typed columns +
    #    any extra fields from the JSON column.
    # -------------------------------------------------------------------
    results = store.similarity_search("database analytics", k=3)
    print(f"\nSearch results ({len(results)} docs):")
    for doc in results:
        print(f"  - {doc.page_content!r}")
        print(f"    metadata={doc.metadata}")

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
