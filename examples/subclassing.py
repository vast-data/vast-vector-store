"""Subclassing VastDBVectorStore with typed metadata columns.

Demonstrates the Template Method pattern by overriding
``_metadata_columns`` and ``_row_to_document`` to replace the
default JSON metadata column with typed columns (category, source).

Prerequisites:
    - A running VAST cluster with vector search support
    - A ``.env`` file at the project root (loaded automatically)

Usage:
    python examples/subclassing.py
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pyarrow as pa
import vastdb
from dotenv import load_dotenv
from langchain_core.documents import Document
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
#    this subclass stores "category" and "source" as separate typed columns.
#    This enables efficient columnar filtering in VastDB.
#
#    Only three hooks need overriding:
#      - _metadata_columns: define typed column layout (replaces JSON)
#      - _row_to_document: reconstruct Document metadata from typed columns
#      - _select_columns: tell the base class which columns to SELECT
# ---------------------------------------------------------------------------


class TypedMetadataStore(VastDBVectorStore):
    """A VastDBVectorStore that stores metadata in typed columns.

    Only two hooks need overriding:
      - _metadata_columns: define the column layout for inserts
      - _row_to_document: reconstruct Document metadata from typed columns
      - _select_columns: tell the base class which columns to SELECT
    """

    CATEGORY_COLUMN = "category"
    SOURCE_COLUMN = "source"

    def _select_columns(self) -> list[str]:
        return [
            self._id_column,
            self._text_column,
            self.CATEGORY_COLUMN,
            self.SOURCE_COLUMN,
        ]

    def _metadata_columns(self, metadatas: list[dict]) -> dict[str, list]:
        """Store category and source as typed columns instead of JSON."""
        return {
            self.CATEGORY_COLUMN: [m.get("category", "") for m in metadatas],
            self.SOURCE_COLUMN: [m.get("source", "") for m in metadatas],
        }

    def _row_to_document(
        self,
        row: dict,
        score: float | None = None,
    ) -> Document:
        page_content = row.get(self._text_column, "")
        metadata: dict[str, Any] = {
            "category": row.get(self.CATEGORY_COLUMN, ""),
            "source": row.get(self.SOURCE_COLUMN, ""),
        }
        doc_id = row.get(self._id_column)
        return Document(page_content=page_content, metadata=metadata, id=doc_id)


# ---------------------------------------------------------------------------
# 3. Create an isolated schema and table for this example run.
#    The table includes typed "category" and "source" columns instead of
#    the default "metadata" JSON column.
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
            {"category": "search", "source": "ml-handbook"},
        ],
    )
    print(f"Added {len(ids)} documents with typed metadata columns.")

    # -------------------------------------------------------------------
    # 5. Search and observe that metadata comes from typed columns.
    # -------------------------------------------------------------------
    results = store.similarity_search("database analytics", k=2)
    print(f"\nSearch results ({len(results)} docs):")
    for doc in results:
        print(f"  - {doc.page_content!r}")
        print(
            f"    category={doc.metadata['category']}, source={doc.metadata['source']}"
        )

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
