"""Filtered similarity search with VastDBVectorStore.

Demonstrates adding documents with varied metadata and using the
``filter`` parameter to narrow similarity search results.

The ``filter`` parameter in ``similarity_search()`` works on **table
columns**, not JSON metadata fields.  This example therefore promotes
``category`` and ``level`` to typed columns via ``_typed_metadata_columns``
so that ibis predicates can filter on them directly.

Prerequisites:
    - A running VAST cluster with vector search support
    - A ``.env`` file at the project root (loaded automatically)

Usage:
    python examples/filtered_search.py
"""

from __future__ import annotations

import os
import uuid

import pyarrow as pa
import vastdb
from dotenv import load_dotenv
from langchain_core.embeddings import FakeEmbeddings

from langchain_vastdb import TypedColumn, VastDBVectorStore

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
# 2. Define a subclass with typed columns for the filterable fields.
#    The ``filter`` dict in ``similarity_search()`` creates ibis equality
#    predicates on table columns, so the fields we want to filter on must
#    be stored as first-class columns.
#
#    ``_typed_metadata_columns`` handles everything: insert, select, and
#    document reconstruction.  Extra metadata fields are preserved in the
#    JSON column automatically.
# ---------------------------------------------------------------------------


class FilterableStore(VastDBVectorStore):
    """VastDBVectorStore with typed columns for filtered search."""

    _typed_metadata_columns = {
        "category": TypedColumn(),
        "level": TypedColumn(),
    }


# ---------------------------------------------------------------------------
# 3. Create an isolated schema and table for this example run.
#    The table includes typed "category" and "level" columns alongside
#    the default "metadata" JSON column for extra fields.
# ---------------------------------------------------------------------------
VECTOR_DIM = 1536
embedding = FakeEmbeddings(size=VECTOR_DIM)

run_id = uuid.uuid4().hex[:8]
SCHEMA = f"example_filter_{run_id}"
TABLE = f"example_filter_{run_id}"

TABLE_SCHEMA = pa.schema(
    [
        pa.field("id", pa.string()),
        pa.field("text", pa.string()),
        pa.field(
            "embedding",
            pa.list_(
                pa.field("item", pa.float32(), nullable=False), VECTOR_DIM
            ),
        ),
        pa.field("category", pa.string()),
        pa.field("level", pa.string()),
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
    # 4. Create the filterable store.
    # -------------------------------------------------------------------
    store = FilterableStore.from_connection_params(
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
    # 5. Add documents with diverse metadata.
    #    "category" and "level" are promoted to typed columns, making
    #    them filterable via the ``filter`` parameter.
    # -------------------------------------------------------------------
    store.add_texts(
        texts=[
            "Introduction to machine learning algorithms.",
            "Deep learning with neural networks.",
            "Database indexing strategies for performance.",
            "SQL query optimization techniques.",
            "Natural language processing fundamentals.",
            "Distributed systems design patterns.",
        ],
        metadatas=[
            {"category": "ml", "level": "beginner"},
            {"category": "ml", "level": "advanced"},
            {"category": "database", "level": "intermediate"},
            {"category": "database", "level": "advanced"},
            {"category": "ml", "level": "beginner"},
            {"category": "systems", "level": "advanced"},
        ],
    )
    print("Added 6 documents with typed category/level columns.")

    # -------------------------------------------------------------------
    # 6. Search WITHOUT a filter -- returns the most similar documents
    #    regardless of metadata.
    # -------------------------------------------------------------------
    print("\n--- Unfiltered search for 'data processing' ---")
    results = store.similarity_search("data processing", k=3)
    for doc in results:
        print(f"  - {doc.page_content!r}  metadata={doc.metadata}")

    # -------------------------------------------------------------------
    # 7. Search WITH a filter -- only returns documents whose typed
    #    column matches.  The filter dict is converted to ibis equality
    #    predicates and applied during the vector search.
    # -------------------------------------------------------------------
    print("\n--- Filtered search: category='ml' ---")
    results = store.similarity_search(
        "data processing", k=3, filter={"category": "ml"}
    )
    for doc in results:
        print(f"  - {doc.page_content!r}  metadata={doc.metadata}")

    # -------------------------------------------------------------------
    # 8. Filter by a different key to further narrow results.
    # -------------------------------------------------------------------
    print("\n--- Filtered search: category='database' ---")
    results = store.similarity_search(
        "performance optimization", k=3, filter={"category": "database"}
    )
    for doc in results:
        print(f"  - {doc.page_content!r}  metadata={doc.metadata}")

    # -------------------------------------------------------------------
    # 9. Filter by level to show another metadata dimension.
    # -------------------------------------------------------------------
    print("\n--- Filtered search: level='beginner' ---")
    results = store.similarity_search(
        "learning", k=3, filter={"level": "beginner"}
    )
    for doc in results:
        print(f"  - {doc.page_content!r}  metadata={doc.metadata}")

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
