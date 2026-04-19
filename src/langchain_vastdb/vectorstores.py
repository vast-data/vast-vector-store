"""VastDBVectorStore -- LangChain VectorStore backed by VAST Database."""

from __future__ import annotations

import json
import logging
import math
import types
import uuid
from collections import Counter
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
    from typing import Self

    from vastdb.table import ITable
    from vastdb.transaction import Transaction


_logger = logging.getLogger(__name__)

# Lazy-cached ADBC dbapi module (DF-f: avoid per-call import overhead).
_adbc_dbapi: types.ModuleType | None = None


def _get_adbc_dbapi() -> types.ModuleType:
    """Return the cached ``adbc_driver_manager.dbapi`` module, importing on first call."""
    global _adbc_dbapi  # noqa: PLW0603
    if _adbc_dbapi is None:
        from adbc_driver_manager import dbapi

        _adbc_dbapi = dbapi
    return _adbc_dbapi


class VastDBVectorStore(VectorStore):
    """LangChain VectorStore backed by VAST Database.

    This class implements the Template Method pattern for vector operations
    against a VAST Database table. It provides:

    - Session-first construction with a ``from_connection_params`` convenience factory.
    - Cached table metadata access via the non-interactive workflow
      (``TableRef`` / ``TableMetadata`` / ``_get_table``).
    - Configurable column names for id, text, vector, and metadata columns.
    - The ``embeddings`` property exposing the configured ``Embeddings`` model.

    Six protected hook methods are available for subclass customization:

    - ``_insert_vectors`` — customize record insertion
    - ``_vector_search`` — customize similarity search behavior
    - ``_delete_by_ids`` — customize document deletion
    - ``_get_by_ids`` — customize document retrieval by ID
    - ``_row_to_document`` — customize row-to-Document conversion
    - ``_select_columns`` — customize columns for full-row retrieval

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
        adbc_driver_path: str | None = None,
        adbc_endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
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
            adbc_driver_path: Path to ``libadbc_driver_vastdb.so``. When set
                together with ``adbc_endpoint``, ``access_key``, and
                ``secret_key``, enables native ADBC vector search via
                ``array_distance()`` SQL (no vector index required). Falls back
                to in-memory L2Sq scan when ADBC is unavailable or fails.
            adbc_endpoint: ADBC/QueryEngine endpoint (hostname or IP), e.g.
                ``"172.27.74.17"`` or ``"query-engine.platform.svc.cluster.local"``.
                This is separate from the HTTP REST endpoint.
            access_key: S3-style access key for the ADBC connection. Required
                when ``adbc_driver_path`` is set. **Retained as an instance
                attribute** for per-call ADBC connection open; callers that
                prefer not to retain credentials in memory should rotate the
                key or construct a fresh store per request.
            secret_key: S3-style secret key for the ADBC connection. Required
                when ``adbc_driver_path`` is set. **Retained as an instance
                attribute** — same caveat as ``access_key``.
        """
        self._embedding = embedding
        self._session = session

        self._id_column = id_column
        self._text_column = text_column
        self._vector_column = vector_column
        self._metadata_column = metadata_column

        self._adbc_driver_path = adbc_driver_path
        self._adbc_endpoint = adbc_endpoint
        self._access_key = access_key
        self._secret_key = secret_key

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
        adbc_driver_path: str | None = None,
        adbc_endpoint: str | None = None,
        ssl_verify: bool = True,
        **kwargs: Any,
    ) -> Self:
        """Create a VastDBVectorStore from VAST connection parameters.

        This is a convenience factory that builds a ``vastdb.Session``
        internally from the provided credentials and endpoint, then
        delegates to the primary constructor.

        Args:
            embedding: The embeddings model used to generate vectors.
            endpoint: The VAST cluster HTTP endpoint URL.
            access_key: The access key for authentication.
            secret_key: The secret key for authentication.
            bucket: The VAST bucket name containing the target table.
            schema: The schema name within the bucket.
            table_name: The table name to use for vector operations.
            adbc_driver_path: Optional path to ``libadbc_driver_vastdb.so``
                for native ADBC vector search.
            adbc_endpoint: Optional ADBC/QueryEngine endpoint (separate from
                the HTTP endpoint).
            ssl_verify: Whether to verify SSL certificates. Set to ``False``
                for self-signed certificates. Defaults to ``True``.
            **kwargs: Additional keyword arguments forwarded to ``__init__``
                (e.g., custom column names).

        Returns:
            A configured ``VastDBVectorStore`` instance.
        """
        session = vastdb.connect(
            endpoint=endpoint,
            access=access_key,
            secret=secret_key,
            ssl_verify=ssl_verify,
        )
        return cls(
            embedding=embedding,
            session=session,
            bucket=bucket,
            schema=schema,
            table_name=table_name,
            adbc_driver_path=adbc_driver_path,
            adbc_endpoint=adbc_endpoint,
            access_key=access_key,
            secret_key=secret_key,
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
    ) -> Self:
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
            # WARNING: the distance metric is hardcoded to l2sq — if the real
            # index uses a different metric (cosine, ip), search results will
            # be silently wrong.
            if self._table_metadata._vector_index is None:
                _logger.warning(
                    "VastDB cluster returned no vector index metadata for table "
                    "%s; falling back to hardcoded l2sq VectorIndex. Search "
                    "results will be incorrect if the table is actually "
                    "indexed with a different distance metric.",
                    self._table_ref,
                )
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

    def _select_columns(self) -> list[str]:
        """Return column names for full-row retrieval (excludes vectors).

        Used by ``_vector_search`` and ``_get_by_ids`` to determine which
        columns to SELECT when fetching document data. The default returns
        id, text, and metadata columns.

        Subclasses that replace the JSON metadata column with typed columns
        should override this to return their custom column names.

        Returns:
            List of column name strings.
        """
        return [self._id_column, self._text_column, self._metadata_column]

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
        if not texts_list:
            return []
        if ids is not None and len(ids) != len(texts_list):
            raise ValueError(
                f"ids length {len(ids)} != texts length {len(texts_list)}"
            )
        if metadatas is not None and len(metadatas) != len(texts_list):
            raise ValueError(
                f"metadatas length {len(metadatas)} != texts length {len(texts_list)}"
            )
        ids_provided = ids is not None
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts_list]
        else:
            # Replace per-element None with generated UUIDs (e.g. when
            # Document.id is None for some documents but not others).
            ids = [id_ if id_ is not None else str(uuid.uuid4()) for id_ in ids]
        if ids_provided:
            empties = [
                i for i, id_ in enumerate(ids)
                if isinstance(id_, str) and not id_.strip()
            ]
            if empties:
                raise ValueError(
                    f"Empty-string IDs at positions {empties}; "
                    "IDs must be non-empty, non-whitespace strings"
                )
            dupes = [id_ for id_, cnt in Counter(ids).items() if cnt > 1]
            if dupes:
                raise ValueError(f"Duplicate IDs in supplied ids: {dupes}")
        vectors = self._embedding.embed_documents(texts_list)
        if metadatas is None:
            metadatas = [{} for _ in texts_list]
        with self._session.transaction() as tx:
            # Upsert only when the caller supplied IDs — fresh UUIDs cannot
            # collide with existing rows, so the delete round-trip is skipped.
            if ids_provided:
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
        if not embeddings:
            return ids
        vector_dim = len(embeddings[0])
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
        if not isinstance(k, int) or isinstance(k, bool):
            raise TypeError(f"k must be an integer, got {type(k).__name__}")
        if k <= 0:
            raise ValueError(f"k must be a positive integer, got {k}")
        filter_dict = kwargs.get("filter")
        query_vector = self._embedding.embed_query(query)
        if not all(math.isfinite(x) for x in query_vector):
            raise ValueError("query vector contains non-finite values")
        predicate = self._build_predicate(filter_dict)
        results = self._vector_search(query_vector, k, predicate=predicate, filter_dict=filter_dict)
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
        if not isinstance(k, int) or isinstance(k, bool):
            raise TypeError(f"k must be an integer, got {type(k).__name__}")
        if k <= 0:
            raise ValueError(f"k must be a positive integer, got {k}")
        filter_dict = kwargs.get("filter")
        query_vector = self._embedding.embed_query(query)
        if not all(math.isfinite(x) for x in query_vector):
            raise ValueError("query vector contains non-finite values")
        predicate = self._build_predicate(filter_dict)
        results = self._vector_search(query_vector, k, predicate=predicate, filter_dict=filter_dict)
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
        if not isinstance(k, int) or isinstance(k, bool):
            raise TypeError(f"k must be an integer, got {type(k).__name__}")
        if k <= 0:
            raise ValueError(f"k must be a positive integer, got {k}")
        if not embedding:
            raise ValueError("query vector must be non-empty")
        if not all(math.isfinite(x) for x in embedding):
            raise ValueError("query vector contains non-finite values")
        filter_dict = kwargs.get("filter")
        predicate = self._build_predicate(filter_dict)
        results = self._vector_search(embedding, k, predicate=predicate, filter_dict=filter_dict)
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
        if not ids:
            return True
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
        columns = self._select_columns()
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

    def _adbc_available(self) -> bool:
        """Return True when all four ADBC parameters are configured and non-blank."""
        def _nonblank(val: object) -> bool:
            return isinstance(val, str) and bool(val.strip())

        return (
            _nonblank(self._adbc_driver_path)
            and _nonblank(self._adbc_endpoint)
            and _nonblank(self._access_key)
            and _nonblank(self._secret_key)
        )

    def _vector_search(
        self,
        query_vector: list[float],
        k: int,
        predicate: ibis.Expr | None = None,
        *,
        filter_dict: dict | None = None,
        tx: Transaction | None = None,
    ) -> list[tuple[dict, float]]:
        """Search VastDB for similar vectors.

        Primary path: ADBC SQL with ``array_distance()`` (server-side, no
        vector index required). Fallback: in-memory L2Sq scan. Subclasses
        can override this hook to customise search behaviour.

        Args:
            query_vector: The query embedding vector.
            k: Maximum number of results to return.
            predicate: Optional ibis predicate for in-memory fallback filtering.
            filter_dict: Optional raw filter dict used to build a SQL WHERE
                clause for the ADBC path.
            tx: Optional transaction for reuse by subclasses.

        Returns:
            List of (row_dict, distance_score) tuples.
        """
        columns = self._select_columns()
        if tx is not None:
            return self._do_vector_search(tx, query_vector, k, columns, predicate, filter_dict)

        with self._session.transaction() as new_tx:
            return self._do_vector_search(new_tx, query_vector, k, columns, predicate, filter_dict)

    def _do_vector_search(
        self,
        tx: Transaction,
        query_vector: list[float],
        k: int,
        columns: list[str],
        predicate: ibis.Expr | None,
        filter_dict: dict | None = None,
    ) -> list[tuple[dict, float]]:
        """Execute the vector search within a transaction.

        Tries ADBC ``array_distance()`` SQL first (no vector index required).
        Falls back to an in-memory L2Sq scan when ADBC is not configured or
        any ADBC error occurs.

        Args:
            tx: An active transaction.
            query_vector: The query embedding vector.
            k: Maximum number of results.
            columns: Column names to select.
            predicate: Optional ibis predicate for in-memory fallback filtering.
            filter_dict: Optional raw filter dict for ADBC SQL WHERE clause.

        Returns:
            List of (row_dict, distance_score) tuples.
        """
        if self._adbc_available():
            from vastdb.transaction import NoAdbcConnectionError

            adbc_exc_types: tuple[type[BaseException], ...] = (
                NoAdbcConnectionError,
                ImportError,
                OSError,
            )
            try:
                from adbc_driver_manager import Error as _AdbcError

                adbc_exc_types = adbc_exc_types + (_AdbcError,)
            except ImportError:
                pass

            try:
                return self._do_vector_search_adbc(tx, query_vector, k, filter_dict)
            except (TypeError, ValueError):
                # AC3 input-validation errors (bad filter type, disallowed
                # column, etc.) are caller bugs and must propagate, not be
                # masked by the in-memory fallback.
                raise
            except adbc_exc_types as exc:
                _logger.warning(
                    "ADBC vector search failed (%s: %s); falling back to in-memory L2Sq scan.",
                    type(exc).__name__,
                    exc,
                )
            except Exception as exc:
                # DF-a: step-2 SDK failure (_get_by_ids) propagates a non-ADBC
                # exception. Fall back rather than crashing the search.
                _logger.warning(
                    "ADBC vector search step-2 SDK call failed (%s: %s); "
                    "falling back to in-memory L2Sq scan.",
                    type(exc).__name__,
                    exc,
                )
        return self._do_vector_search_fallback(tx, query_vector, k, columns, predicate)

    def _do_vector_search_adbc(
        self,
        tx: Transaction,
        query_vector: list[float],
        k: int,
        filter_dict: dict | None,
    ) -> list[tuple[dict, float]]:
        """ADBC vector search using ``array_distance()`` SQL (no index needed).

        Mirrors the approach used in vast-pipelines: step 1 fetches only
        ``id + distance`` via ADBC SQL (lightweight), step 2 retrieves the
        full document columns for the top-k IDs via the VastDB SDK.

        Args:
            tx: An active VastDB transaction (used for step-2 row fetch).
            query_vector: The query embedding vector.
            k: Maximum number of results.
            filter_dict: Optional dict of equality filters applied as a SQL
                WHERE clause.

        Returns:
            List of (row_dict, distance_score) tuples ordered by distance.
        """
        adbc_dbapi = _get_adbc_dbapi()

        dim = len(query_vector)
        # Escape any embedded double-quotes in identifier components (P2).
        bucket_esc = self._table_ref.bucket.replace('"', '""')
        schema_esc = self._table_ref.schema.replace('"', '""')
        table_esc = self._table_ref.table.replace('"', '""')
        table_path = f'"{bucket_esc}/{schema_esc}"."{table_esc}"'

        # Build WHERE clause from simple equality filters (P1, P7).
        # Scalar columns only: equality on _vector_column (float[]) is nonsensical
        # and equality on _metadata_column is position-dependent on JSON bytes.
        # Derive allowed columns from _select_columns() so subclass-added typed
        # columns (e.g., category, level) are accepted when ADBC is enabled.
        _allowed_cols = set(self._select_columns())
        where_parts: list[str] = []
        if filter_dict:
            for col, val in filter_dict.items():
                if col not in _allowed_cols:
                    raise ValueError(
                        f"filter key {col!r} is not an allowed column name; "
                        f"allowed: {sorted(_allowed_cols)}"
                    )
                if val is None:
                    raise ValueError(
                        f"filter value for {col!r} is None; use IS NULL via a "
                        "predicate or omit the key"
                    )
                if isinstance(val, bool):
                    quoted = "TRUE" if val else "FALSE"
                elif isinstance(val, str):
                    escaped = val.replace("'", "''")
                    quoted = f"'{escaped}'"
                elif isinstance(val, (int, float)):
                    if isinstance(val, float) and not math.isfinite(val):
                        raise TypeError(
                            f"filter value for {col!r} is non-finite ({val!r}); "
                            "NaN and infinity are not valid SQL literals"
                        )
                    quoted = str(val)
                else:
                    raise TypeError(
                        f"filter value for {col!r} has unsupported type "
                        f"{type(val).__name__}; allowed types: str, int, float, bool"
                    )
                col_esc = col.replace('"', '""')
                quoted_col = f'"{col_esc}"'
                where_parts.append(f"{quoted_col} = {quoted}")
        where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        # Step 1: ADBC SQL — fetch id + distance only (no heavy columns).
        # Cast to plain float to avoid np.float64(...) in the SQL literal.
        float_vec = [float(x) for x in query_vector]
        # Quote all column identifiers to avoid SQL keyword conflicts.
        id_col_esc = self._id_column.replace('"', '""')
        quoted_id_col = f'"{id_col_esc}"'
        vec_col_esc = self._vector_column.replace('"', '""')
        quoted_vec_col = f'"{vec_col_esc}"'
        query = (
            f"SELECT {quoted_id_col}, "
            f"array_distance({quoted_vec_col}::FLOAT[{dim}], "
            f"ARRAY{float_vec}::FLOAT[{dim}]) AS distance "
            f"FROM {table_path} "
            f"{where_clause} "
            f"ORDER BY distance "
            f"LIMIT {k}"
        )
        with adbc_dbapi.connect(
            driver=self._adbc_driver_path,
            db_kwargs={
                "vast.db.endpoint": self._adbc_endpoint,
                "vast.db.access_key": self._access_key,
                "vast.db.secret_key": self._secret_key,
            },
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                result = cursor.fetch_arrow_table().to_pydict()

        ids: list[str] = result.get(self._id_column, [])
        distances: list[float] = result.get("distance", [])
        if not ids:
            return []

        # Step 2: SDK — fetch full rows for the top-k IDs.
        if len(ids) != len(set(ids)):
            _logger.warning(
                "ADBC step-1 returned %d IDs but only %d are unique; "
                "duplicate IDs collapsed — results may be fewer than k.",
                len(ids),
                len(set(ids)),
            )
        score_by_id = dict(zip(ids, distances))
        full_rows = self._get_by_ids(ids, tx=tx)
        row_by_id = {row[self._id_column]: row for row in full_rows}
        return [
            (row_by_id[id_], score_by_id[id_])
            for id_ in ids
            if id_ in row_by_id
        ]

    def _do_vector_search_fallback(
        self,
        tx: Transaction,
        query_vector: list[float],
        k: int,
        columns: list[str],
        predicate: ibis.Expr | None,
    ) -> list[tuple[dict, float]]:
        """In-memory L2-squared distance fallback when ADBC is unavailable.

        Reads id + vector columns, ranks by L2-squared distance (lower=better,
        matching the native path's ``$distance`` semantics), then fetches full
        rows for the top-k hits.
        """
        table = self._get_table(tx)
        scan_columns = [self._id_column, self._vector_column]
        reader = table.select(predicate=predicate, columns=scan_columns)
        all_rows = reader.read_all().to_pylist()

        qdim = len(query_vector)
        scored: list[tuple[str, float]] = []
        skipped = 0
        for row in all_rows:
            vec = row.get(self._vector_column)
            # Coerce to list for Arrow arrays/tuples (DF-j).
            if vec is not None and not isinstance(vec, list):
                vec = list(vec)
            if not isinstance(vec, list) or len(vec) != qdim:
                skipped += 1
                continue
            score = sum((a - b) * (a - b) for a, b in zip(query_vector, vec))
            scored.append((row[self._id_column], score))
        if skipped:
            _logger.warning(
                "Fallback vector search skipped %d/%d rows with missing or "
                "dimension-mismatched vectors (expected dim=%d).",
                skipped,
                len(all_rows),
                qdim,
            )

        scored.sort(key=lambda x: x[1])
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
        page_content = row.get(self._text_column) or ""
        metadata_raw = row.get(self._metadata_column)
        metadata = json.loads(metadata_raw) if metadata_raw else {}
        doc_id = row.get(self._id_column)
        return Document(page_content=page_content, metadata=metadata, id=doc_id)
