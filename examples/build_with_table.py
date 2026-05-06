"""Using build_with_table / build_table for easy setup.

Demonstrates two patterns for creating the VAST schema and table without
managing those steps manually:

- ``build_with_table`` (classmethod) — one call returns a ready-to-use store.
- ``build_table`` (instance method) — construct the store first, then call
  ``build_table()`` to provision the schema and table using the object's own
  attributes.

Also shows the subclass variant (B) where typed metadata columns are
automatically added to the table schema from ``_typed_metadata_columns``.

Prerequisites:
    - A running VAST cluster with vector search support
    - A ``.env`` file at the project root (loaded automatically)

Usage:
    python examples/build_with_table.py
"""

from __future__ import annotations

import os
import uuid

from dotenv import load_dotenv
from langchain_core.embeddings import FakeEmbeddings

from langchain_vastdb import TypedColumn, VastDBVectorStore

# ---------------------------------------------------------------------------
# 0. Load environment variables from .env (same mechanism as conftest.py).
# ---------------------------------------------------------------------------
load_dotenv()

if not os.environ.get("VASTDB_ADBC_DRIVER_PATH"):
    os.environ.setdefault("VASTDB_ALLOW_FALLBACK", "1")
    print("NOTE: ADBC not configured; using in-memory fallback (dev only).")

# ---------------------------------------------------------------------------
# 1. Connection credentials.
# ---------------------------------------------------------------------------
ENDPOINT = os.environ["AWS_S3_ENDPOINT_URL"]
ACCESS_KEY = os.environ["AWS_ACCESS_KEY_ID"]
SECRET_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]
BUCKET = os.environ.get("VASTDB_BUCKET", "example-bucket")

VECTOR_DIM = 1536
embedding = FakeEmbeddings(size=VECTOR_DIM)

# ---------------------------------------------------------------------------
# Example A: minimal call — only embedding and vector_dim required.
#
# bucket reads from VASTDB_BUCKET; schema and table_name are auto-generated.
# ---------------------------------------------------------------------------
os.environ.setdefault("VASTDB_BUCKET", BUCKET)

# Pass schema= and table_name= explicitly if you need repeatable names.
store_a = VastDBVectorStore.build_with_table(
    embedding,
    VECTOR_DIM,
    endpoint=ENDPOINT,
    access_key=ACCESS_KEY,
    secret_key=SECRET_KEY,
    ssl_verify=False,
    distance_metric="l2sq",
)
print(
    f"[A] Created store: schema={store_a._table_ref.schema!r}"
    f"  table={store_a._table_ref.table!r}"
)

try:
    ids = store_a.add_texts(
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
    print(f"[A] Added {len(ids)} documents.")

    results = store_a.similarity_search("analytical database", k=2)
    print(f"[A] Similarity search results ({len(results)} docs):")
    for doc in results:
        print(f"    - {doc.page_content!r}  metadata={doc.metadata}")

finally:
    try:
        with store_a._session.transaction() as tx:
            sc = tx.bucket(BUCKET).schema(store_a._table_ref.schema)
            sc.table(store_a._table_ref.table).drop()
            sc.drop()
    except Exception:
        pass

run_id = uuid.uuid4().hex[:8]

# ---------------------------------------------------------------------------
# Example B: subclass with typed metadata columns.
#
# Typed columns declared in _typed_metadata_columns are automatically
# included in the table schema — no need to build a pa.schema manually.
# ---------------------------------------------------------------------------


class FilterableStore(VastDBVectorStore):
    """VastDBVectorStore with typed columns for filtered search."""

    _typed_metadata_columns = {
        "category": TypedColumn(),
        "level": TypedColumn(),
    }


SCHEMA_B = f"example_bwt_b_{run_id}"
TABLE_B = f"example_bwt_b_{run_id}"

store_c = FilterableStore.build_with_table(
    embedding,
    VECTOR_DIM,
    endpoint=ENDPOINT,
    access_key=ACCESS_KEY,
    secret_key=SECRET_KEY,
    bucket=BUCKET,
    schema=SCHEMA_B,
    table_name=TABLE_B,
    ssl_verify=False,
    distance_metric="l2sq",
)

try:
    store_c.add_texts(
        texts=[
            "Introduction to machine learning algorithms.",
            "Database indexing strategies for performance.",
            "SQL query optimization techniques.",
        ],
        metadatas=[
            {"category": "ml", "level": "beginner"},
            {"category": "database", "level": "intermediate"},
            {"category": "database", "level": "advanced"},
        ],
    )
    print("\n[B] Added 3 documents with typed category/level columns.")

    results = store_c.similarity_search(
        "data processing", k=2, filter={"category": "database"}
    )
    print(f"[B] Filtered search results ({len(results)} docs):")
    for doc in results:
        print(f"    - {doc.page_content!r}  metadata={doc.metadata}")

finally:
    try:
        with store_c._session.transaction() as tx:
            sc = tx.bucket(BUCKET).schema(SCHEMA_B)
            sc.table(TABLE_B).drop()
            sc.drop()
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Example C: build_table instance method — construct first, provision later.
#
# Useful when you want to keep store construction and table provisioning as
# separate steps, e.g. in dependency-injection or lazy-init patterns.
# ---------------------------------------------------------------------------
import vastdb  # noqa: E402

SCHEMA_C = f"example_bwt_c_{run_id}"
TABLE_C = f"example_bwt_c_{run_id}"

session_c = vastdb.connect(
    endpoint=ENDPOINT,
    access=ACCESS_KEY,
    secret=SECRET_KEY,
    ssl_verify=False,
)

store_d = VastDBVectorStore(
    embedding=embedding,
    session=session_c,
    bucket=BUCKET,
    schema=SCHEMA_C,
    table_name=TABLE_C,
    vector_dim=VECTOR_DIM,
    distance_metric="l2sq",
)

# Table doesn't exist yet — build_table() provisions schema + table.
store_d.build_table()
print(f"\n[C] Provisioned schema={SCHEMA_C!r}  table={TABLE_C!r}")

# Calling again with exist_ok=True is safe; without it would raise TableExists.
store_d.build_table(exist_ok=True)

try:
    store_d.add_texts(
        texts=["build_table provisions schema and table from instance attributes."],
        metadatas=[{"source": "example"}],
    )
    results = store_d.similarity_search("instance method", k=1)
    print(f"[C] Search result: {results[0].page_content!r}")

finally:
    try:
        with session_c.transaction() as tx:
            sc = tx.bucket(BUCKET).schema(SCHEMA_C)
            sc.table(TABLE_C).drop()
            sc.drop()
    except Exception:
        pass
