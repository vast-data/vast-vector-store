"""VastDBVectorStore -- LangChain VectorStore backed by VAST Database."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any

import ibis
import pyarrow as pa
import vastdb
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore
from vastdb.table_metadata import TableMetadata, TableRef, VectorIndex

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

    Five protected hook methods are available for subclass customization:

    - ``_insert_vectors`` — customize record insertion
    - ``_vector_search`` — customize similarity search behavior
    - ``_delete_by_ids`` — customize document deletion
    - ``_get_by_ids`` — customize document retrieval by ID
    - ``_row_to_document`` — customize row-to-Document conversion

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

    @classmethod
    def from_texts(
        cls,
        texts: list[str],
        embedding: Embeddings,
        metadatas: list[dict] | None = None,
        *,
        session: vastdb.Session,
        bucket: str,
        schema: str,
        table_name: str,
        **kwargs: Any,
    ) -> VastDBVectorStore:
        """Create a VastDBVectorStore and add texts in a single call.

        Convenience factory that constructs a ``VastDBVectorStore`` instance
        and immediately populates it with the provided texts (and optional
        metadata). Subclasses inherit this method for free.

        Args:
            texts: Texts to embed and insert.
            embedding: The embeddings model used to generate vectors.
            metadatas: Optional list of metadata dicts, one per text. If
                omitted, each document is stored with an empty metadata dict.
            session: An active ``vastdb.Session``.
            bucket: The VAST bucket name containing the target table.
            schema: The schema name within the bucket.
            table_name: The table name to use for vector operations.
            **kwargs: Additional keyword arguments forwarded to ``__init__``
                (e.g., custom column names).

        Returns:
            A populated ``VastDBVectorStore`` instance.
        """
        store = cls(
            embedding=embedding,
            session=session,
            bucket=bucket,
            schema=schema,
            table_name=table_name,
            **kwargs,
        )
        store.add_texts(texts, metadatas=metadatas)
        return store

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
            # Some cluster versions do not return vector index metadata in table
            # stats. Fall back to constructing VectorIndex from known column config
            # so that table.vector_search() can proceed (uses array_distance SQL).
            if self._table_metadata._vector_index is None:
                self._table_metadata._vector_index = VectorIndex(
                    column=self._vector_column,
                    distance_metric="l2sq",
                    sql_distance_function="array_distance",
                )
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
        """Add texts to the vector store with upsert semantics.

        Embeds the provided texts using the configured embedding model.
        When IDs are provided (either via the ``ids`` argument or from
        ``Document.id`` fields), any existing rows with those IDs are deleted
        before inserting, ensuring upsert semantics. The delete and insert
        happen in a single transaction.

        Per-element ``None`` values in ``ids`` are replaced with auto-generated
        UUIDs, so a mixed list (some explicit IDs, some ``None``) is supported.

        Args:
            texts: Texts to add to the store.
            metadatas: Optional metadata dicts, one per text.
                Defaults to empty dicts if not provided.
            ids: Optional document IDs. Auto-generated UUIDs for any
                element that is ``None`` or when the whole list is ``None``.
            **kwargs: Additional keyword arguments (unused by default).

        Returns:
            List of IDs for the added texts.
        """
        texts_list = list(texts)
        vectors = self._embedding.embed_documents(texts_list)
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts_list]
        else:
            # Replace per-element None with generated UUIDs (e.g. when
            # Document.id is None for some documents but not others).
            ids = [id_ if id_ is not None else str(uuid.uuid4()) for id_ in ids]
        if metadatas is None:
            metadatas = [{} for _ in texts_list]
        # Upsert: delete existing rows with these IDs, then insert — atomic.
        with self._session.transaction() as tx:
            self._delete_by_ids(ids, tx=tx)
            self._insert_vectors(texts_list, vectors, metadatas, ids, tx=tx)
        return ids

    def _insert_vectors(
        self,
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
        ids: list[str],
        *,
        tx: Transaction | None = None,
    ) -> list[str]:
        """Insert vectors into VastDB.

        Default hook implementation that builds a PyArrow RecordBatch
        and inserts it into the configured table. Subclasses can override
        this to customize insertion behavior (e.g., typed metadata columns).

        Args:
            texts: The original text strings.
            embeddings: Embedding vectors, one per text.
            metadatas: Metadata dicts, one per text.
            ids: Document IDs, one per text.
            tx: Optional transaction for reuse by subclasses.

        Returns:
            The list of document IDs that were inserted.
        """
        vector_dim = len(embeddings[0]) if embeddings else 0
        vector_type = pa.list_(pa.field("item", pa.float32(), nullable=False), vector_dim)
        batch = pa.RecordBatch.from_pydict(
            {
                self._id_column: ids,
                self._text_column: texts,
                self._vector_column: pa.array(embeddings, type=vector_type),
                self._metadata_column: [json.dumps(m) for m in metadatas],
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

    def similarity_search(
        self,
        query: str,
        k: int = 4,
        **kwargs: Any,
    ) -> list[Document]:
        """Search for documents similar to the query string.

        Embeds the query using the configured embedding model, converts
        an optional ``filter`` dict to an ibis predicate, then delegates
        to the ``_vector_search`` hook.

        Args:
            query: The text query to search for.
            k: Number of results to return.
            **kwargs: Additional arguments. Supports ``filter`` (dict) for
                metadata filtering.

        Returns:
            List of Documents most similar to the query.
        """
        query_vector = self._embedding.embed_query(query)
        predicate = self._build_predicate(kwargs.get("filter"))
        results = self._vector_search(query_vector, k, predicate=predicate)
        return [self._row_to_document(row) for row, _ in results]

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        **kwargs: Any,
    ) -> list[tuple[Document, float]]:
        """Search for documents similar to the query, returning scores.

        Args:
            query: The text query to search for.
            k: Number of results to return.
            **kwargs: Additional arguments. Supports ``filter`` (dict) for
                metadata filtering.

        Returns:
            List of (Document, distance_score) tuples, ordered by similarity.
        """
        query_vector = self._embedding.embed_query(query)
        predicate = self._build_predicate(kwargs.get("filter"))
        results = self._vector_search(query_vector, k, predicate=predicate)
        return [(self._row_to_document(row, score), score) for row, score in results]

    def similarity_search_by_vector(
        self,
        embedding: list[float],
        k: int = 4,
        **kwargs: Any,
    ) -> list[Document]:
        """Search for documents by a pre-computed embedding vector.

        Skips the embedding step and passes the vector directly to
        the ``_vector_search`` hook.

        Args:
            embedding: The pre-computed query embedding vector.
            k: Number of results to return.
            **kwargs: Additional arguments. Supports ``filter`` (dict) for
                metadata filtering.

        Returns:
            List of Documents most similar to the embedding.
        """
        predicate = self._build_predicate(kwargs.get("filter"))
        results = self._vector_search(embedding, k, predicate=predicate)
        return [self._row_to_document(row) for row, _ in results]

    def delete(self, ids: list[str] | None = None, **kwargs: Any) -> bool | None:
        """Delete documents by ID.

        Template method that delegates to the ``_delete_by_ids`` hook.
        Returns ``None`` (no-op) when ``ids`` is ``None`` or empty.

        Args:
            ids: List of document IDs to delete. If ``None`` or empty,
                the method is a no-op and returns ``None``.
            **kwargs: Additional keyword arguments (unused; present for
                compatibility with the base class signature).

        Returns:
            ``True`` on successful deletion, or ``None`` if no IDs were
            provided.
        """
        if not ids:
            return None
        return self._delete_by_ids(ids)

    def _delete_by_ids(
        self,
        ids: list[str],
        *,
        tx: Transaction | None = None,
    ) -> bool:
        """Delete documents matching the given IDs from VastDB.

        Default hook implementation. Opens a transaction if one is not
        provided, selects matching rows with their internal ``$row_id``
        column, then passes that RecordBatch to ``table.delete()``.

        ``table.delete()`` requires a RecordBatch containing the internal
        ``$row_id`` field — it does not accept ibis predicates directly.

        Subclasses may override this method to customise deletion behaviour
        while keeping the ``delete`` template method intact.

        Args:
            ids: Non-empty list of document IDs to delete.
            tx: Optional active transaction. If provided it is reused;
                otherwise a new transaction is opened.

        Returns:
            ``True`` on success.
        """
        predicate = ibis._[self._id_column].isin(ids)
        if tx is not None:
            table = self._get_table(tx)
            rows = table.select(
                columns=[self._id_column], predicate=predicate, internal_row_id=True
            ).read_all()
            table.delete(rows)
            return True

        with self._session.transaction() as new_tx:
            table = self._get_table(new_tx)
            rows = table.select(
                columns=[self._id_column], predicate=predicate, internal_row_id=True
            ).read_all()
            table.delete(rows)
            return True

    def get_by_ids(self, ids: list[str], /) -> list[Document]:
        """Retrieve documents by their IDs without performing a search.

        Template method that delegates to the ``_get_by_ids`` hook and
        converts each returned row dict to a ``Document`` via
        ``_row_to_document``.

        Args:
            ids: Positional-only list of document IDs to retrieve.

        Returns:
            List of ``Document`` objects corresponding to the given IDs.
            Documents not found in the table are silently omitted.
        """
        rows = self._get_by_ids(ids)
        return [self._row_to_document(row) for row in rows]

    def _get_by_ids(
        self,
        ids: list[str],
        *,
        tx: Transaction | None = None,
    ) -> list[dict]:
        """Retrieve raw row dicts for the given document IDs from VastDB.

        Default hook implementation. Opens a transaction if one is not
        provided, selects only the id, text, and metadata columns (omitting
        the large vector column), and returns the results as plain Python
        dicts via ``read_all().to_pylist()``.

        Subclasses may override this to return additional columns or apply
        custom post-processing.

        Args:
            ids: Non-empty list of document IDs to retrieve.
            tx: Optional active transaction. If provided it is reused;
                otherwise a new transaction is opened.

        Returns:
            List of row dicts. Each dict contains the id, text, and metadata
            columns for a matched document.
        """
        predicate = ibis._[self._id_column].isin(ids)
        columns = [self._id_column, self._text_column, self._metadata_column]
        if tx is not None:
            table = self._get_table(tx)
            reader = table.select(columns=columns, predicate=predicate)
            return reader.read_all().to_pylist()

        with self._session.transaction() as new_tx:
            table = self._get_table(new_tx)
            reader = table.select(columns=columns, predicate=predicate)
            return reader.read_all().to_pylist()

    def _build_predicate(
        self, filter_dict: dict | None
    ) -> ibis.Expr | None:
        """Convert a filter dict to an ibis predicate expression.

        Builds equality predicates for each key-value pair and combines
        them with logical AND. Filter keys are interpreted as table column
        names.

        Args:
            filter_dict: Optional dict of column-name to value mappings.

        Returns:
            An ibis predicate expression, or ``None`` if no filter provided.
        """
        if not filter_dict:
            return None
        predicates = [ibis._[key] == value for key, value in filter_dict.items()]
        result = predicates[0]
        for pred in predicates[1:]:
            result = result & pred
        return result

    def _vector_search(
        self,
        query_vector: list[float],
        k: int,
        predicate: ibis.Expr | None = None,
        *,
        tx: Transaction | None = None,
    ) -> list[tuple[dict, float]]:
        """Search VastDB for similar vectors.

        Default hook implementation that calls ``table.vector_search()``
        and returns row dicts with distance scores. Subclasses can override
        this to customize search behavior (e.g., add collection filters).

        Args:
            query_vector: The query embedding vector.
            k: Maximum number of results to return.
            predicate: Optional ibis predicate for filtering.
            tx: Optional transaction for reuse by subclasses.

        Returns:
            List of (row_dict, distance_score) tuples.
        """
        columns = [self._id_column, self._text_column, self._metadata_column]
        if tx is not None:
            return self._do_vector_search(tx, query_vector, k, columns, predicate)

        with self._session.transaction() as new_tx:
            return self._do_vector_search(new_tx, query_vector, k, columns, predicate)

    def _do_vector_search(
        self,
        tx: Transaction,
        query_vector: list[float],
        k: int,
        columns: list[str],
        predicate: ibis.Expr | None,
    ) -> list[tuple[dict, float]]:
        """Execute the vector search within a transaction.

        Attempts native ``table.vector_search()`` via ADBC. Falls back to an
        in-memory dot-product scan when ADBC is not available (e.g. on macOS
        without the VAST ADBC shared library).

        Args:
            tx: An active transaction.
            query_vector: The query embedding vector.
            k: Maximum number of results.
            columns: Column names to select.
            predicate: Optional ibis predicate for filtering.

        Returns:
            List of (row_dict, distance_score) tuples.
        """
        from vastdb.transaction import NoAdbcConnectionError

        table = self._get_table(tx)
        try:
            reader = table.vector_search(
                vec=query_vector,
                columns=columns,
                limit=k,
                predicate=predicate,
            )
            rows = reader.read_all().to_pylist()
            results: list[tuple[dict, float]] = []
            for row in rows:
                score = row.pop("$distance", 0.0)
                results.append((row, score))
            return results
        except NoAdbcConnectionError:
            return self._do_vector_search_fallback(tx, query_vector, k, columns, predicate)

    def _do_vector_search_fallback(
        self,
        tx: Transaction,
        query_vector: list[float],
        k: int,
        columns: list[str],
        predicate: ibis.Expr | None,
    ) -> list[tuple[dict, float]]:
        """In-memory dot-product fallback when ADBC is unavailable.

        Reads id + vector columns, ranks by dot product, then fetches full rows
        for the top-k hits. Same two-phase pattern used in vast-pipelines.
        """
        table = self._get_table(tx)
        scan_columns = [self._id_column, self._vector_column]
        reader = table.select(predicate=predicate, columns=scan_columns)
        all_rows = reader.read_all().to_pylist()

        scored: list[tuple[str, float]] = []
        for row in all_rows:
            vec = row.get(self._vector_column)
            if isinstance(vec, list):
                score = sum(a * b for a, b in zip(query_vector, vec))
                scored.append((row[self._id_column], score))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_ids = [id_ for id_, _ in scored[:k]]
        top_scores = {id_: score for id_, score in scored[:k]}

        if not top_ids:
            return []

        id_predicate = ibis._[self._id_column].isin(top_ids)
        combined = id_predicate if predicate is None else (predicate & id_predicate)
        reader = table.select(predicate=combined, columns=columns)
        full_rows = reader.read_all().to_pylist()

        row_by_id = {row[self._id_column]: row for row in full_rows}
        return [
            (row_by_id[id_], top_scores[id_])
            for id_ in top_ids
            if id_ in row_by_id
        ]

    def _row_to_document(
        self,
        row: dict,
        score: float | None = None,
    ) -> Document:
        """Convert a VastDB row dict to a LangChain Document.

        Default hook implementation that extracts text from the configured
        text column and deserializes JSON metadata. Subclasses can override
        this to handle typed metadata columns or include score in metadata.

        Args:
            row: A dict representing a single VastDB row.
            score: Optional distance score (available for subclass use).

        Returns:
            A LangChain ``Document`` with page_content and metadata.
        """
        page_content = row.get(self._text_column, "")
        metadata = json.loads(row.get(self._metadata_column, "{}"))
        doc_id = row.get(self._id_column)
        return Document(page_content=page_content, metadata=metadata, id=doc_id)
