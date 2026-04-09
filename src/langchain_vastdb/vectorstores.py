"""VastDBVectorStore -- LangChain VectorStore backed by VAST Database."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import vastdb
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore
from vastdb.table_metadata import TableMetadata, TableRef

if TYPE_CHECKING:
    from collections.abc import Iterable

    from vastdb.table import ITable
    from vastdb.transaction import Transaction


class VastDBVectorStore(VectorStore):
    """LangChain VectorStore backed by VAST Database.

    This class implements the Template Method pattern for vector operations
    against a VAST Database table. It provides:

    - Session-first construction with a ``from_connection_params`` convenience factory.
    - Cached table metadata access via the non-interactive workflow
      (``TableRef`` / ``TableMetadata`` / ``_get_table``).
    - Configurable column names for id, text, vector, and metadata columns.
    - The ``embeddings`` property exposing the configured ``Embeddings`` model.

    Five protected hook methods are defined in later stories:

    - ``_insert_vectors`` (Story 2.2)
    - ``_vector_search`` (Story 2.3)
    - ``_delete_by_ids`` (Story 2.4)
    - ``_get_by_ids`` (Story 2.4)
    - ``_row_to_document`` (Story 2.3)

    Example:
        .. code-block:: python

            from langchain_vastdb import VastDBVectorStore

            store = VastDBVectorStore(
                embedding=my_embeddings,
                session=my_session,
                bucket="my-bucket",
                schema="my-schema",
                table_name="my-table",
            )
    """

    def __init__(
        self,
        embedding: Embeddings,
        session: vastdb.Session,
        bucket: str,
        schema: str,
        table_name: str,
        id_column: str = "id",
        text_column: str = "text",
        vector_column: str = "vector",
        metadata_column: str = "metadata",
    ) -> None:
        """Initialize VastDBVectorStore with a pre-built session.

        Args:
            embedding: The embeddings model used to generate vectors.
            session: A pre-built ``vastdb.Session`` connected to the VAST cluster.
            bucket: The VAST bucket name containing the target table.
            schema: The schema name within the bucket.
            table_name: The table name to use for vector operations.
            id_column: Column name for document IDs. Defaults to ``"id"``.
            text_column: Column name for document text. Defaults to ``"text"``.
            vector_column: Column name for embedding vectors. Defaults to ``"vector"``.
            metadata_column: Column name for document metadata. Defaults to ``"metadata"``.
        """
        self._embedding = embedding
        self._session = session

        self._id_column = id_column
        self._text_column = text_column
        self._vector_column = vector_column
        self._metadata_column = metadata_column

        self._table_ref = TableRef(bucket=bucket, schema=schema, table=table_name)
        self._table_metadata = TableMetadata(ref=self._table_ref)
        self._metadata_loaded = False

    @classmethod
    def from_connection_params(
        cls,
        embedding: Embeddings,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        schema: str,
        table_name: str,
        **kwargs: Any,
    ) -> VastDBVectorStore:
        """Create a VastDBVectorStore from VAST connection parameters.

        This is a convenience factory that builds a ``vastdb.Session``
        internally from the provided credentials and endpoint, then
        delegates to the primary constructor.

        Credentials are passed directly to ``vastdb.connect()`` and are
        **not** stored as instance attributes.

        Args:
            embedding: The embeddings model used to generate vectors.
            endpoint: The VAST cluster endpoint URL.
            access_key: The access key for authentication.
            secret_key: The secret key for authentication.
            bucket: The VAST bucket name containing the target table.
            schema: The schema name within the bucket.
            table_name: The table name to use for vector operations.
            **kwargs: Additional keyword arguments forwarded to ``__init__``
                (e.g., custom column names).

        Returns:
            A configured ``VastDBVectorStore`` instance.
        """
        session = vastdb.connect(
            endpoint=endpoint, access_key=access_key, secret_key=secret_key
        )
        return cls(
            embedding=embedding,
            session=session,
            bucket=bucket,
            schema=schema,
            table_name=table_name,
            **kwargs,
        )

    @property
    def embeddings(self) -> Embeddings:
        """Return the embeddings model provided at construction time."""
        return self._embedding

    def _get_table(self, tx: Transaction) -> ITable:
        """Get table using cached metadata (non-interactive workflow).

        First call loads metadata via ``md.load(tx)``. Subsequent calls reuse
        cached metadata via ``tx.table_from_metadata()``, skipping
        bucket -> schema -> table round trips entirely.

        Args:
            tx: An active ``vastdb`` transaction.

        Returns:
            The ``ITable`` handle for the configured table.
        """
        if not self._metadata_loaded:
            self._table_metadata.load(tx)
            self._metadata_loaded = True
        return tx.table_from_metadata(self._table_metadata)

    def invalidate_table_cache(self) -> None:
        """Invalidate cached table metadata.

        Call this after create or drop operations that change the table
        structure. The next ``_get_table()`` call will reload metadata
        from the database.
        """
        self._metadata_loaded = False
        self._table_metadata = TableMetadata(ref=self._table_ref)

    def add_texts(
        self,
        texts: Iterable[str],
        metadatas: list[dict] | None = None,
        *,
        ids: list[str] | None = None,
        **kwargs: Any,
    ) -> list[str]:
        """Add texts to the vector store.

        Placeholder stub -- full implementation lands in Story 2.2.

        Raises:
            NotImplementedError: Always, until Story 2.2 is implemented.
        """
        raise NotImplementedError("add_texts is implemented in Story 2.2")

    def similarity_search(
        self,
        query: str,
        k: int = 4,
        **kwargs: Any,
    ) -> list[Document]:
        """Search for documents similar to the query string.

        Placeholder stub -- full implementation lands in Story 2.3.

        Raises:
            NotImplementedError: Always, until Story 2.3 is implemented.
        """
        raise NotImplementedError("similarity_search is implemented in Story 2.3")
