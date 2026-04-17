"""Subclassing VastDBVectorStore with typed metadata columns.

Demonstrates the Template Method pattern by overriding the
``_insert_vectors`` and ``_row_to_document`` hooks to replace the
default JSON metadata column with typed columns (category, source).

Prerequisites:
    - A running VAST cluster with vector search support
    - Environment variables: VASTDB_ENDPOINT, VASTDB_ACCESS_KEY, VASTDB_SECRET_KEY

Usage:
    export VASTDB_ENDPOINT="http://your-vast-endpoint:443"
    export VASTDB_ACCESS_KEY="your-access-key"
    export VASTDB_SECRET_KEY="your-secret-key"
    python examples/subclassing.py
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import pyarrow as pa
from langchain_core.documents import Document
from langchain_core.embeddings import FakeEmbeddings

from langchain_vastdb import VastDBVectorStore

if TYPE_CHECKING:
    from vastdb.transaction import Transaction

# ---------------------------------------------------------------------------
# 1. Connection setup.
# ---------------------------------------------------------------------------
ENDPOINT = os.environ["VASTDB_ENDPOINT"]
ACCESS_KEY = os.environ["VASTDB_ACCESS_KEY"]
SECRET_KEY = os.environ["VASTDB_SECRET_KEY"]


# ---------------------------------------------------------------------------
# 2. Define a subclass that uses typed metadata columns.
#
#    Instead of storing metadata as a single JSON string (the default),
#    this subclass stores "category" and "source" as separate typed columns.
#    This enables efficient columnar filtering in VastDB.
#
#    Only two hooks need overriding:
#      - _insert_vectors: build a RecordBatch with typed columns
#      - _row_to_document: reconstruct Document metadata from typed columns
# ---------------------------------------------------------------------------


class TypedMetadataStore(VastDBVectorStore):
    """A VastDBVectorStore that stores metadata in typed columns."""

    # Column names for the typed metadata fields.
    CATEGORY_COLUMN = "category"
    SOURCE_COLUMN = "source"

    def _insert_vectors(
        self,
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
        ids: list[str],
        *,
        tx: Transaction | None = None,
    ) -> list[str]:
        """Insert vectors with typed metadata columns instead of JSON.

        Builds a PyArrow RecordBatch that includes separate "category" and
        "source" columns rather than packing everything into a single JSON
        metadata column.
        """
        if not embeddings:
            return ids

        vector_dim = len(embeddings[0])
        vector_type = pa.list_(
            pa.field("item", pa.float32(), nullable=False), vector_dim
        )

        # Build a RecordBatch with typed columns for category and source.
        batch = pa.RecordBatch.from_pydict(
            {
                self._id_column: ids,
                self._text_column: texts,
                self._vector_column: pa.array(embeddings, type=vector_type),
                self.CATEGORY_COLUMN: [m.get("category", "") for m in metadatas],
                self.SOURCE_COLUMN: [m.get("source", "") for m in metadatas],
            }
        )

        if tx is not None:
            table = self._get_table(tx)
            table.insert(batch)
            return ids

        with self._session.transaction() as new_tx:
            table = self._get_table(new_tx)
            table.insert(batch)
            return ids

    def _row_to_document(
        self,
        row: dict,
        score: float | None = None,
    ) -> Document:
        """Reconstruct a Document from typed metadata columns.

        Reads "category" and "source" from the row dict (instead of
        deserializing a JSON blob) and packs them into the Document's
        metadata dict.
        """
        page_content = row.get(self._text_column, "")
        metadata: dict[str, Any] = {
            "category": row.get(self.CATEGORY_COLUMN, ""),
            "source": row.get(self.SOURCE_COLUMN, ""),
        }
        doc_id = row.get(self._id_column)
        return Document(page_content=page_content, metadata=metadata, id=doc_id)


# ---------------------------------------------------------------------------
# 3. Create a TypedMetadataStore instance and add documents.
#    The table must have "category" and "source" columns pre-created
#    (or VastDB must be configured to auto-create columns on insert).
# ---------------------------------------------------------------------------
embedding = FakeEmbeddings(size=1536)

store = TypedMetadataStore.from_connection_params(
    embedding=embedding,
    endpoint=ENDPOINT,
    access_key=ACCESS_KEY,
    secret_key=SECRET_KEY,
    bucket="example-bucket",
    schema="example-schema",
    table_name="example-subclassing",
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

# ---------------------------------------------------------------------------
# 4. Search and observe that metadata comes from typed columns.
# ---------------------------------------------------------------------------
results = store.similarity_search("database analytics", k=2)
print(f"\nSearch results ({len(results)} docs):")
for doc in results:
    print(f"  - {doc.page_content!r}")
    print(f"    category={doc.metadata['category']}, source={doc.metadata['source']}")
