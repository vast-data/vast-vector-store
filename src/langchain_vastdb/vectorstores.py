"""VastDBVectorStore -- LangChain VectorStore backed by VAST Database."""

from __future__ import annotations

import json
import logging
import math
import os
import time
import types
import uuid
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import ibis
import pyarrow as pa
import vastdb
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore
from vastdb.table_metadata import TableMetadata, TableRef

from langchain_vastdb._ibis_sql import predicate_to_sql_where

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from typing_extensions import Self
    from vastdb.table import ITable
    from vastdb.transaction import Transaction


_logger = logging.getLogger(__name__)

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _connect(**kwargs: Any) -> Any:
    """``vastdb.connect``, pinning data_endpoints on loopback so 2.1 skips VIP discovery.

    vastdb 2.1 probes cluster-private VIPs; behind an SSH tunnel those time out.
    Direct cluster URLs still discover. # ponytail: loopback-only pin, pass SessionConfig
    """
    endpoint = kwargs.get("endpoint") or os.environ.get("AWS_S3_ENDPOINT_URL")
    if endpoint and "config" not in kwargs:
        host = urlparse(endpoint).hostname
        if host in _LOOPBACK_HOSTS:
            try:
                from vastdb.config import SessionConfig

                kwargs = {**kwargs, "config": SessionConfig(data_endpoints=[endpoint])}
            except (ImportError, TypeError):
                pass
    return vastdb.connect(**kwargs)


@dataclass(frozen=True, slots=True)
class TypedColumn:
    """Declaration for a typed metadata column.

    Attributes:
        default: Static default value when the key is absent from metadata.
        default_factory: Callable returning a fresh default (e.g. timestamps).
            Takes precedence over *default* when set.
        pa_type: Optional PyArrow type for coercion (e.g. ``pa.int64()``).
        include_in_metadata: Whether to merge this column back into metadata on read.
            Set to ``False`` for infrastructure columns (e.g. ``tenant_id``,
            ``shard_key``) that exist for DB-level filtering but should not
            appear in user-facing ``Document.metadata``.
    """

    default: Any = ""
    default_factory: Callable[[], Any] | None = None
    pa_type: pa.DataType | None = None
    include_in_metadata: bool = True

    def get_default(self) -> Any:
        if self.default_factory is not None:
            return self.default_factory()
        return self.default


# Lazy-cached ADBC dbapi module (DF-f: avoid per-call import overhead).
_adbc_dbapi: types.ModuleType | None = None

_FALLBACK_MAX_ROWS = 1000
_ADBC_ID_BATCH = 1000
_ADBC_TXID_PROPERTY = "vast.db.external_txid"
_ADBC_DISTANCE_ALIAS = "_vastdb_distance"


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _adbc_error_types() -> tuple[type[BaseException], ...]:
    from vastdb.transaction import NoAdbcConnectionError

    errors: tuple[type[BaseException], ...] = (NoAdbcConnectionError, ImportError, OSError)
    try:
        from adbc_driver_manager import Error as AdbcError

        errors += (AdbcError,)
    except ImportError:
        pass
    return errors


def _get_adbc_dbapi() -> types.ModuleType:
    """Return the cached ``adbc_driver_manager.dbapi`` module, importing on first call."""
    global _adbc_dbapi  # noqa: PLW0603
    if _adbc_dbapi is None:
        from adbc_driver_manager import dbapi

        _adbc_dbapi = dbapi
    return _adbc_dbapi


def _build_table_schema(
    vector_dim: int,
    *,
    id_column: str = "id",
    text_column: str = "text",
    vector_column: str = "embedding",
    metadata_column: str = "metadata",
    extra_columns: list[pa.Field] | None = None,
) -> pa.Schema:
    """Return the PyArrow schema used for VastDB vector-store tables."""
    fields: list[pa.Field] = [
        pa.field(id_column, pa.string()),
        pa.field(text_column, pa.string()),
        pa.field(
            vector_column,
            pa.list_(pa.field("item", pa.float32(), nullable=False), vector_dim),
        ),
        pa.field(metadata_column, pa.string()),
    ]
    if extra_columns:
        fields.extend(extra_columns)
    return pa.schema(fields)


def _check_schema_compatible(expected: pa.Schema, actual: pa.Schema) -> None:
    """Raise ``ValueError`` if *actual* is missing or mismatches any field in *expected*.

    Extra columns in *actual* are allowed — the check is one-directional.
    """
    mismatches: list[str] = []
    for expected_field in expected:
        idx = actual.get_field_index(expected_field.name)
        if idx == -1:
            mismatches.append(f"  missing column {expected_field.name!r}")
        else:
            actual_type = actual.field(idx).type
            if actual_type != expected_field.type:
                mismatches.append(
                    f"  column {expected_field.name!r}: "
                    f"expected {expected_field.type}, got {actual_type}"
                )
    if mismatches:
        raise ValueError(
            "Existing table schema is incompatible with the requested schema:\n"
            + "\n".join(mismatches)
        )


def _fallback_allowed() -> bool:
    """Return True when the VASTDB_ALLOW_FALLBACK env var is set to a truthy value."""
    return os.environ.get("VASTDB_ALLOW_FALLBACK", "").lower() in ("1", "true", "yes")


def _generate_sortable_id() -> str:
    """Generate a time-sortable UUID (v7 layout) for optimal VastDB sorted-key performance."""
    timestamp_ms = int(time.time() * 1000)
    time_bytes = timestamp_ms.to_bytes(6, "big")
    rand_bytes = os.urandom(10)
    raw = bytearray(time_bytes + rand_bytes)
    # Set version 7 and RFC 9562 variant bits.
    raw[6] = (raw[6] & 0x0F) | 0x70
    raw[8] = (raw[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(raw)))


class VastDBVectorStore(VectorStore):
    """LangChain VectorStore backed by VAST Database.

    This class implements the Template Method pattern for vector operations
    against a VAST Database table. It provides:

    - Session-first construction with a ``from_connection_params`` convenience factory.
    - Cached table metadata access via the non-interactive workflow
      (``TableRef`` / ``TableMetadata`` / ``_get_table``).
    - Configurable column names for id, text, vector, and metadata columns.
    - The ``embeddings`` property exposing the configured ``Embeddings`` model.

    For the common case of typed metadata columns (e.g., ``category``,
    ``source``), set the ``_typed_metadata_columns`` class attribute.
    This is the recommended extension point — it auto-derives
    ``_select_columns``, ``_build_metadata_columns``, and ``_row_to_document``
    without requiring any hook overrides.

    For advanced scenarios, protected hook methods are available for
    subclass customization:

    - ``_insert_vectors`` — customize record insertion
    - ``_build_metadata_columns`` — customize column layout for metadata storage
    - ``_vector_search`` — customize similarity search behavior
    - ``_delete_by_ids`` — customize document deletion
    - ``_get_by_ids`` — customize document retrieval by ID (not called by ADBC search)
    - ``_row_to_document`` — customize row-to-Document conversion
    - ``_select_columns`` — customize projected search and lookup columns
    - ``_get_table`` — customize table acquisition (e.g., create-on-first-use, table-level options)

    Overrides of ``_open_adbc_connection`` should accept ``**kwargs``: search
    forwards per-call options, and joined delete/lookups pass the SDK transaction
    ID through ``adbc_conn_kwargs_overrides``. With ADBC configured, search,
    lookup, and delete use Query Engine SQL; upsert deletes and SDK Arrow inserts
    within one transaction. Without ADBC, the existing SDK paths remain.

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

    Tuning ``k`` per call:
        ``k`` is a per-call argument, not an instance attribute. To vary it
        across calls (e.g. retrieval pipelines that compute ``k`` from the
        query), pass it to each call or use ``as_retriever``::

            store.similarity_search(query, k=12)

            retriever = store.as_retriever(search_kwargs={"k": 12})
            docs = retriever.invoke(query)

        This replaces the legacy ``store.k = N`` pattern from some other
        LangChain stores; mutating ``k`` on the instance has no effect here.
    """

    _typed_metadata_columns: dict[str, TypedColumn] = {}

    def _typed_column_names(self) -> tuple[str, ...]:
        return tuple(self._typed_metadata_columns.keys())

    def __init__(
        self,
        embedding: Embeddings,
        session: vastdb.session.Session,
        bucket: str,
        schema: str,
        table_name: str,
        id_column: str = "id",
        text_column: str = "text",
        vector_column: str = "embedding",
        metadata_column: str = "metadata",
        adbc_driver_path: str | None = None,
        adbc_endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        distance_metric: str | None = None,
        vector_dim: int | None = None,
        adbc_conn_kwargs: dict | None = None,
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
            vector_column: Column name for embedding vectors. Defaults to ``"embedding"``.
            metadata_column: Column name for document metadata. Defaults to ``"metadata"``.
            adbc_driver_path: Path to ``libadbc_driver_vastdb.so``. When set
                together with ``adbc_endpoint``, ``access_key``, and
                ``secret_key``, enables native ADBC vector search via
                ``array_distance()`` SQL (no vector index required). When ADBC
                is not configured, vector search raises ``RuntimeError`` unless
                the ``VASTDB_ALLOW_FALLBACK`` env var is set (development only).
            adbc_endpoint: Full ADBC/QueryEngine endpoint URL, e.g.
                ``"http://query-engine.example.com:80"``. This is separate
                from the HTTP REST endpoint.
            access_key: S3-style access key for the ADBC connection. Required
                when ``adbc_driver_path`` is set.
            secret_key: S3-style secret key for the ADBC connection. Required
                when ``adbc_driver_path`` is set.
            distance_metric: Distance metric to use when the cluster does not
                return vector index metadata (e.g. ``"l2sq"``, ``"cosine"``,
                ``"ip"``). When ``None`` and metadata is missing, raises
                ``ValueError`` instead of silently guessing.
            vector_dim: Dimensionality of the embedding vectors. Only required
                when calling :meth:`build_table`.
            adbc_conn_kwargs: Optional dict of ``conn_kwargs`` passed to
                ``adbc_dbapi.connect()``. Use for ADBC connection-level options
                such as timeouts or TLS settings.
        """
        self._embedding = embedding
        self._session = session

        self._id_column = id_column
        self._text_column = text_column
        self._vector_column = vector_column
        self._metadata_column = metadata_column
        self._vector_dim = vector_dim

        self._adbc_driver_path = adbc_driver_path
        self._adbc_endpoint = adbc_endpoint
        self._access_key = access_key or os.environ.get("AWS_ACCESS_KEY_ID")
        self._secret_key = secret_key or os.environ.get("AWS_SECRET_ACCESS_KEY")
        self._distance_metric = distance_metric
        self._adbc_conn_kwargs = adbc_conn_kwargs

        self._table_ref = TableRef(bucket=bucket, schema=schema, table=table_name)
        self._table_metadata = TableMetadata(ref=self._table_ref)
        self._metadata_loaded = False

        core_columns = {id_column, text_column, vector_column, metadata_column}
        conflicts = core_columns & set(self._typed_metadata_columns)
        if conflicts:
            raise ValueError(
                f"Typed column names conflict with core columns: {sorted(conflicts)}"
            )

    @classmethod
    def from_connection_params(
        cls,
        embedding: Embeddings,
        bucket: str,
        schema: str,
        table_name: str,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        adbc_driver_path: str | None = None,
        adbc_endpoint: str | None = None,
        ssl_verify: bool = True,
        session: vastdb.session.Session | None = None,
        **kwargs: Any,
    ) -> Self:
        """Create a VastDBVectorStore from VAST connection parameters.

        This is a convenience factory that builds a ``vastdb.session.Session``
        internally from the provided credentials and endpoint, then
        delegates to the primary constructor.

        Args:
            embedding: The embeddings model used to generate vectors.
            bucket: The VAST bucket name containing the target table.
            schema: The schema name within the bucket.
            table_name: The table name to use for vector operations.
            endpoint: The VAST cluster HTTP endpoint URL. When ``None``,
                ``vastdb.connect`` reads ``AWS_S3_ENDPOINT_URL`` from env.
            access_key: The access key for authentication. When ``None``,
                ``vastdb.connect`` reads ``AWS_ACCESS_KEY_ID`` from env.
            secret_key: The secret key for authentication. When ``None``,
                ``vastdb.connect`` reads ``AWS_SECRET_ACCESS_KEY`` from env.
            adbc_driver_path: Optional path to ``libadbc_driver_vastdb.so``
                for native ADBC vector search.
            adbc_endpoint: Optional ADBC/QueryEngine endpoint (separate from
                the HTTP endpoint).
            ssl_verify: Whether to verify SSL certificates. Set to ``False``
                for self-signed certificates. Defaults to ``True``.
            session: Optional pre-built ``vastdb.session.Session``. When provided,
                reused instead of opening a fresh connection — useful for
                sharing a session across multiple stores.
            **kwargs: Additional keyword arguments forwarded to ``__init__``
                (e.g., custom column names).

        Returns:
            A configured ``VastDBVectorStore`` instance.
        """
        if session is None:
            session = _connect(
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

    @staticmethod
    def create_table(
        session: vastdb.session.Session,
        bucket: str,
        vector_dim: int,
        *,
        schema: str | None = None,
        table_name: str | None = None,
        id_column: str = "id",
        text_column: str = "text",
        vector_column: str = "embedding",
        metadata_column: str = "metadata",
        extra_columns: list[pa.Field] | None = None,
    ) -> None:
        """Create a VastDB table with the expected schema for this vector store.

        Convenience helper for bootstrap/setup scripts. Does not make table
        creation implicit in the constructor — callers must invoke this
        explicitly before constructing a store against a new table.

        Args:
            session: An active ``vastdb.session.Session``.
            bucket: The VAST bucket name.
            vector_dim: Dimensionality of the embedding vectors.
            schema: The schema name within the bucket. Defaults to a
                randomly generated name prefixed with ``"vs_"``.
            table_name: The table name to create. Defaults to a randomly
                generated name prefixed with ``"vs_"``.
            id_column: Column name for document IDs.
            text_column: Column name for document text.
            vector_column: Column name for embedding vectors.
            metadata_column: Column name for document metadata.
            extra_columns: Optional additional ``pa.Field`` entries appended
                to the schema (e.g., typed metadata columns).
        """
        schema = schema or f"vs_{uuid.uuid4().hex[:12]}"
        table_name = table_name or f"vs_{uuid.uuid4().hex[:12]}"
        table_schema = _build_table_schema(
            vector_dim,
            id_column=id_column,
            text_column=text_column,
            vector_column=vector_column,
            metadata_column=metadata_column,
            extra_columns=extra_columns,
        )
        with session.transaction() as tx:
            tx.bucket(bucket).create_schema(schema, fail_if_exists=False)
            tx.bucket(bucket).schema(schema).create_table(table_name, table_schema)

    def build_table(self, *, exist_ok: bool = False) -> None:
        """Create the backing schema and table using this store's attributes.

        Use this after constructing the store when the table does not yet exist.
        Typed metadata columns declared on the class via
        ``_typed_metadata_columns`` are automatically included in the schema.

        Args:
            exist_ok: When ``True``, skip creation if the table already exists
                and verify that its schema is compatible with the requested one.
                When ``False`` (default), raises ``vastdb.errors.TableExists``.

        Raises:
            ValueError: If ``vector_dim`` was not set at construction time, or
                if ``exist_ok=True`` and the existing table's schema is
                incompatible with the requested schema.
            vastdb.errors.TableExists: If the table already exists and
                ``exist_ok`` is ``False``.
        """
        if self._vector_dim is None:
            raise ValueError(
                "vector_dim must be provided at construction time to use build_table()"
            )
        extra_columns = [
            pa.field(name, tc.pa_type if tc.pa_type is not None else pa.string())
            for name, tc in self._typed_metadata_columns.items()
        ] or None
        expected_schema = _build_table_schema(
            self._vector_dim,
            id_column=self._id_column,
            text_column=self._text_column,
            vector_column=self._vector_column,
            metadata_column=self._metadata_column,
            extra_columns=extra_columns,
        )
        _table_existed = False
        with self._session.transaction() as tx:
            sc = tx.bucket(self._table_ref.bucket)
            sc.create_schema(self._table_ref.schema, fail_if_exists=False)
            try:
                sc.schema(self._table_ref.schema).create_table(
                    self._table_ref.table, expected_schema
                )
            except vastdb.errors.TableExists:
                _table_existed = True
                if exist_ok:
                    existing = sc.schema(self._table_ref.schema).table(self._table_ref.table)
                    _check_schema_compatible(expected_schema, existing.arrow_schema)
        if _table_existed and not exist_ok:
            raise vastdb.errors.TableExists(
                self._table_ref.bucket, self._table_ref.schema, self._table_ref.table
            )

    def table_exists(self) -> bool:
        """Return ``True`` when the configured bucket/schema/table is reachable.

        Returns ``False`` if any of the bucket, schema, or table is missing.
        Other VastDB errors (auth, network) propagate.
        """
        with self._session.transaction() as tx:
            try:
                tbl = (
                    tx.bucket(self._table_ref.bucket)
                    .schema(self._table_ref.schema)
                    .table(self._table_ref.table)
                )
            except (
                vastdb.errors.MissingBucket,
                vastdb.errors.MissingSchema,
                vastdb.errors.MissingTable,
            ):
                return False
            return tbl is not None

    def drop_table(self, *, missing_ok: bool = False) -> None:
        """Drop the configured table.

        Args:
            missing_ok: When ``True``, silently succeed if the bucket, schema,
                or table does not exist. When ``False`` (default), propagate
                the underlying ``vastdb.errors.MissingTable`` /
                ``MissingSchema`` / ``MissingBucket``.
        """
        with self._session.transaction() as tx:
            try:
                bucket_obj = tx.bucket(self._table_ref.bucket)
                schema_obj = bucket_obj.schema(self._table_ref.schema)
                table_obj = schema_obj.table(self._table_ref.table)
                table_obj.drop()
            except (
                vastdb.errors.MissingBucket,
                vastdb.errors.MissingSchema,
                vastdb.errors.MissingTable,
            ):
                if not missing_ok:
                    raise
        self.invalidate_table_cache()

    @classmethod
    def build_with_table(
        cls,
        embedding: Embeddings,
        vector_dim: int,
        *,
        bucket: str | None = None,
        schema: str | None = None,
        table_name: str | None = None,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        adbc_driver_path: str | None = None,
        adbc_endpoint: str | None = None,
        ssl_verify: bool = True,
        session: vastdb.session.Session | None = None,
        id_column: str = "id",
        text_column: str = "text",
        vector_column: str = "embedding",
        metadata_column: str = "metadata",
        distance_metric: str | None = None,
    ) -> Self:
        """Create a VastDBVectorStore and provision the backing schema and table.

        Combines session construction, schema creation, table creation, and
        store construction into a single call. Use this for first-time setup
        when neither the schema nor the table exists yet.

        Typed metadata columns declared on the subclass via
        ``_typed_metadata_columns`` are automatically included in the table
        schema. To add custom columns, subclass and set ``_typed_metadata_columns``.

        Args:
            embedding: The embeddings model used to generate vectors.
            vector_dim: Dimensionality of the embedding vectors.
            bucket: The VAST bucket name. Defaults to the ``VASTDB_BUCKET``
                environment variable.
            schema: The schema name to create within the bucket. Defaults to a
                random hex string prefixed with ``"vs_"``.
            table_name: The table name to create. Defaults to a random hex
                string prefixed with ``"vs_"``.
            endpoint: The VAST cluster HTTP endpoint URL.
            access_key: The access key for authentication.
            secret_key: The secret key for authentication.
            adbc_driver_path: Optional path to ``libadbc_driver_vastdb.so``.
            adbc_endpoint: Optional ADBC/QueryEngine endpoint.
            ssl_verify: Whether to verify SSL certificates. Defaults to ``True``.
            session: Optional pre-built ``vastdb.session.Session``.
            id_column: Column name for document IDs. Defaults to ``"id"``.
            text_column: Column name for document text. Defaults to ``"text"``.
            vector_column: Column name for embedding vectors. Defaults to ``"embedding"``.
            metadata_column: Column name for document metadata. Defaults to ``"metadata"``.
            distance_metric: Distance metric for the store (e.g. ``"l2sq"``,
                ``"cosine"``, ``"ip"``). Required when the cluster does not
                return vector index metadata.

        Returns:
            A configured ``VastDBVectorStore`` instance backed by the new table.
        """
        bucket = bucket or os.environ.get("VASTDB_BUCKET")
        if not bucket:
            raise ValueError(
                "bucket must be provided or set via the VASTDB_BUCKET environment variable"
            )
        schema = schema or f"vs_{uuid.uuid4().hex[:12]}"
        table_name = table_name or f"vs_{uuid.uuid4().hex[:12]}"

        if session is None:
            session = _connect(
                endpoint=endpoint,
                access=access_key,
                secret=secret_key,
                ssl_verify=ssl_verify,
            )

        store = cls(
            embedding=embedding,
            session=session,
            bucket=bucket,
            schema=schema,
            table_name=table_name,
            id_column=id_column,
            text_column=text_column,
            vector_column=vector_column,
            metadata_column=metadata_column,
            adbc_driver_path=adbc_driver_path,
            adbc_endpoint=adbc_endpoint,
            access_key=access_key,
            secret_key=secret_key,
            distance_metric=distance_metric,
            vector_dim=vector_dim,
        )
        store.build_table()
        return store

    @classmethod
    def from_texts(
        cls,
        texts: list[str],
        embedding: Embeddings,
        metadatas: list[dict] | None = None,
        *,
        session: vastdb.session.Session,
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
            session: An active ``vastdb.session.Session``.
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
            if self._table_metadata._vector_index is None and self._distance_metric is None:
                raise ValueError(
                    f"VastDB cluster returned no vector index metadata for "
                    f"table {self._table_ref}. Pass distance_metric= to the "
                    f"constructor (e.g. 'l2sq', 'cosine', 'ip') to specify "
                    f"the metric explicitly."
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

    @contextmanager
    def _ensure_tx(self, tx: Transaction | None):
        """Yield *tx* if provided, otherwise open and yield a new transaction."""
        if tx is not None:
            yield tx
        else:
            with self._session.transaction() as new_tx:
                yield new_tx

    def _select_columns(self) -> list[str]:
        """Return column names for full-row retrieval (excludes vectors).

        Used by one-query ADBC search and ``_get_by_ids`` to determine which
        columns to SELECT when fetching document data.

        When ``_typed_metadata_columns`` is set, returns
        ``[id, text, *typed_columns, metadata]`` automatically.

        Returns:
            List of column name strings.
        """
        typed_names = self._typed_column_names()
        return [
            self._id_column,
            self._text_column,
            *typed_names,
            self._metadata_column,
        ]

    def add_texts(
        self,
        texts: Iterable[str],
        metadatas: list[dict] | None = None,
        *,
        ids: list[str] | None = None,
        upsert: bool = True,
        **kwargs: Any,
    ) -> list[str]:
        """Add texts to the vector store.

        Embeds the provided texts using the configured embedding model.
        When IDs are provided and ``upsert=True`` (the default), any existing
        rows with those IDs are deleted before inserting, ensuring upsert
        semantics. The delete and insert happen in a single transaction.

        Set ``upsert=False`` to skip the pre-delete step when you know the
        IDs are fresh (e.g. content-hashed IDs for new documents). This
        avoids a round-trip to the database but will raise on duplicate keys
        if a row with the same ID already exists.

        Per-element ``None`` values in ``ids`` are replaced with auto-generated
        UUIDs, so a mixed list (some explicit IDs, some ``None``) is supported.

        Args:
            texts: Texts to add to the store.
            metadatas: Optional metadata dicts, one per text.
                Defaults to empty dicts if not provided.
            ids: Optional document IDs. Auto-generated UUIDs for any
                element that is ``None`` or when the whole list is ``None``.
            upsert: When ``True`` (default), existing rows with matching IDs
                are deleted before insert. Set to ``False`` to skip the delete
                when IDs are known to be fresh.
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
            ids = [_generate_sortable_id() for _ in texts_list]
        else:
            # Replace per-element None with generated UUIDs (e.g. when
            # Document.id is None for some documents but not others).
            ids = [id_ if id_ is not None else _generate_sortable_id() for id_ in ids]
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
            # Upsert only when the caller supplied IDs and upsert is enabled —
            # fresh UUIDs cannot collide with existing rows, so the delete
            # round-trip is skipped.
            if ids_provided and upsert:
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

        Builds a PyArrow RecordBatch from the core columns (id, text,
        vector) plus whatever ``_build_metadata_columns`` returns, then inserts
        the batch.  Subclasses that only need to change column layout
        should override ``_build_metadata_columns`` instead of this method.

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
        columns: dict[str, Any] = {
            self._id_column: ids,
            self._text_column: texts,
            self._vector_column: pa.array(embeddings, type=vector_type),
        }
        columns.update(self._build_metadata_columns(metadatas))
        batch = pa.RecordBatch.from_pydict(columns)
        with self._ensure_tx(tx) as active_tx:
            table = self._get_table(active_tx)
            table.insert(batch)
            return ids

    def _build_metadata_columns(
        self,
        metadatas: list[dict],
    ) -> dict[str, list]:
        """Serialize metadata dicts into a column-name -> values mapping.

        Called by ``_insert_vectors`` to build the metadata portion of
        the PyArrow RecordBatch.

        When ``_typed_metadata_columns`` is set, pops those keys into
        separate typed columns and dumps the remainder as JSON.  When
        empty (default), serializes each dict to the JSON metadata column.

        Subclasses needing custom defaults or type coercion should
        override this method directly.

        Examples:
            No typed columns (default) — everything goes into the JSON blob::

                metadatas = [{"source": "a.txt", "score": 0.9},
                             {"source": "b.txt", "score": 0.4}]
                # _typed_metadata_columns = {}
                _build_metadata_columns(metadatas)
                # {
                #   "metadata": ['{"source": "a.txt", "score": 0.9}',
                #                '{"source": "b.txt", "score": 0.4}']
                # }

            With typed columns — ``source`` is promoted to its own column,
            remainder stays in the JSON blob::

                # _typed_metadata_columns = {"source": TypedColumn(pa_type=pa.string())}
                _build_metadata_columns(metadatas)
                # {
                #   "source":   ["a.txt", "b.txt"],
                #   "metadata": ['{"score": 0.9}', '{"score": 0.4}']
                # }

        Args:
            metadatas: One metadata dict per document.

        Returns:
            Dict mapping column names to lists of per-row values.
            Each list must have the same length as *metadatas*.
        """
        if not self._typed_metadata_columns:
            return {self._metadata_column: [json.dumps(m) for m in metadatas]}

        result: dict[str, list] = {col: [] for col in self._typed_metadata_columns}
        json_blobs: list[str] = []

        for m in metadatas:
            m_copy = dict(m)
            for col, tc in self._typed_metadata_columns.items():
                result[col].append(m_copy.pop(col, tc.get_default()))
            json_blobs.append(json.dumps(m_copy))

        # Second pass: pa.array() requires the complete list, so type coercion
        # must happen after all rows are collected. No-op when pa_type is None.
        for col, tc in self._typed_metadata_columns.items():
            if tc.pa_type is not None:
                result[col] = pa.array(result[col], type=tc.pa_type)

        result[self._metadata_column] = json_blobs
        return result

    def similarity_search(
        self,
        query: str,
        k: int = 4,
        *,
        predicate: ibis.Expr | None = None,
        **kwargs: Any,
    ) -> list[Document]:
        """Search for documents similar to the query string.

        Embeds the query using the configured embedding model, then delegates
        to the ``_vector_search`` hook.

        Args:
            query: The text query to search for.
            k: Number of results to return.
            predicate: Optional ibis deferred filter expression, e.g.
                ``ibis._["category"] == "news"`` or
                ``(ibis._["level"] == "advanced") & (ibis._["score"] > 0.9)``.
            **kwargs: Forwarded to ``_vector_search`` / ``_do_vector_search_adbc``
                / ``_open_adbc_connection`` / ``_build_adbc_where_clause``. The
                base ``_open_adbc_connection`` recognises
                ``adbc_db_kwargs_overrides`` and ``adbc_conn_kwargs_overrides``
                for per-call identity injection (e.g. row-level-security).
                Unknown kwargs are tolerated by all hooks in the default chain.

        Returns:
            List of Documents most similar to the query.
        """
        if "filter" in kwargs:
            raise TypeError(
                "The 'filter' keyword argument was removed. "
                "Pass an ibis predicate instead: predicate=ibis._['col'] == val"
            )
        if not isinstance(k, int) or isinstance(k, bool):
            raise TypeError(f"k must be an integer, got {type(k).__name__}")
        if k <= 0:
            raise ValueError(f"k must be a positive integer, got {k}")
        query_vector = self._embedding.embed_query(query)
        if not all(math.isfinite(x) for x in query_vector):
            raise ValueError("query vector contains non-finite values")
        results = self._vector_search(query_vector, k, predicate=predicate, **kwargs)
        return [self._row_to_document(row) for row, _ in results]

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        *,
        predicate: ibis.Expr | None = None,
        **kwargs: Any,
    ) -> list[tuple[Document, float]]:
        """Search for documents similar to the query, returning scores.

        Args:
            query: The text query to search for.
            k: Number of results to return.
            predicate: Optional ibis deferred filter expression.
            **kwargs: Forwarded to ``_vector_search`` / ``_do_vector_search_adbc``
                / ``_open_adbc_connection`` / ``_build_adbc_where_clause``. The
                base ``_open_adbc_connection`` recognises
                ``adbc_db_kwargs_overrides`` and ``adbc_conn_kwargs_overrides``
                for per-call identity injection (e.g. row-level-security).
                Unknown kwargs are tolerated by all hooks in the default chain.

        Returns:
            List of (Document, distance_score) tuples, ordered by similarity.
        """
        if "filter" in kwargs:
            raise TypeError(
                "The 'filter' keyword argument was removed. "
                "Pass an ibis predicate instead: predicate=ibis._['col'] == val"
            )
        if not isinstance(k, int) or isinstance(k, bool):
            raise TypeError(f"k must be an integer, got {type(k).__name__}")
        if k <= 0:
            raise ValueError(f"k must be a positive integer, got {k}")
        query_vector = self._embedding.embed_query(query)
        if not all(math.isfinite(x) for x in query_vector):
            raise ValueError("query vector contains non-finite values")
        results = self._vector_search(query_vector, k, predicate=predicate, **kwargs)
        return [(self._row_to_document(row, score), score) for row, score in results]

    def similarity_search_by_vector(
        self,
        embedding: list[float],
        k: int = 4,
        *,
        predicate: ibis.Expr | None = None,
        **kwargs: Any,
    ) -> list[Document]:
        """Search for documents by a pre-computed embedding vector.

        Skips the embedding step and passes the vector directly to
        the ``_vector_search`` hook.

        Args:
            embedding: The pre-computed query embedding vector.
            k: Number of results to return.
            predicate: Optional ibis deferred filter expression.
            **kwargs: Forwarded to ``_vector_search`` / ``_do_vector_search_adbc``
                / ``_open_adbc_connection`` / ``_build_adbc_where_clause``. The
                base ``_open_adbc_connection`` recognises
                ``adbc_db_kwargs_overrides`` and ``adbc_conn_kwargs_overrides``
                for per-call identity injection (e.g. row-level-security).
                Unknown kwargs are tolerated by all hooks in the default chain.

        Returns:
            List of Documents most similar to the embedding.
        """
        if "filter" in kwargs:
            raise TypeError(
                "The 'filter' keyword argument was removed. "
                "Pass an ibis predicate instead: predicate=ibis._['col'] == val"
            )
        if not isinstance(k, int) or isinstance(k, bool):
            raise TypeError(f"k must be an integer, got {type(k).__name__}")
        if k <= 0:
            raise ValueError(f"k must be a positive integer, got {k}")
        if embedding is None or len(embedding) == 0:
            raise ValueError("query vector must be non-empty")
        if not all(math.isfinite(x) for x in embedding):
            raise ValueError("query vector contains non-finite values")
        results = self._vector_search(embedding, k, predicate=predicate, **kwargs)
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

        When ADBC is configured, executes batched Query Engine DELETEs joined
        to the SDK transaction. Otherwise selects internal ``$row_id`` rows
        and passes them to the SDK ``table.delete()``.

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
        with self._ensure_tx(tx) as active_tx:
            if self._adbc_available():
                with self._open_adbc_connection(
                    adbc_conn_kwargs_overrides={_ADBC_TXID_PROPERTY: str(active_tx.txid)}
                ) as conn:
                    with conn.cursor() as cursor:
                        for start in range(0, len(ids), _ADBC_ID_BATCH):
                            predicate = ibis._[self._id_column].isin(
                                ids[start:start + _ADBC_ID_BATCH]
                            )
                            cursor.execute(
                                f"DELETE FROM {self._adbc_table_path()} "
                                f"WHERE {predicate_to_sql_where(predicate)}"
                            )
            else:
                predicate = ibis._[self._id_column].isin(ids)
                table = self._get_table(active_tx)
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

        Uses batched Query Engine SELECTs when ADBC is configured; otherwise
        uses the SDK. Both paths omit the large vector column and return row
        dicts for the selected document columns.

        Subclasses may override this to return additional columns or apply
        custom post-processing.

        Args:
            ids: Document IDs to retrieve; an empty list returns no rows.
            tx: Optional active transaction. ADBC joins it via
                ``vast.db.external_txid``; without it, ADBC opens a plain
                connection. The SDK path opens a transaction when absent.

        Returns:
            List of row dicts with ``_select_columns()`` columns for each
            match, including typed columns when configured.
        """
        columns = self._select_columns()
        if self._adbc_available():
            if not ids:
                return []
            unique_ids = list(dict.fromkeys(ids))
            conn_kwargs = (
                {"adbc_conn_kwargs_overrides": {_ADBC_TXID_PROPERTY: str(tx.txid)}}
                if tx is not None else {}
            )
            try:
                rows: list[dict] = []
                with self._open_adbc_connection(**conn_kwargs) as conn:
                    with conn.cursor() as cursor:
                        for start in range(0, len(unique_ids), _ADBC_ID_BATCH):
                            predicate = ibis._[self._id_column].isin(
                                unique_ids[start:start + _ADBC_ID_BATCH]
                            )
                            cursor.execute(
                                f"SELECT {', '.join(map(_quote_ident, columns))} "
                                f"FROM {self._adbc_table_path()} "
                                f"WHERE {predicate_to_sql_where(predicate)}"
                            )
                            rows.extend(cursor.fetch_arrow_table().to_pylist())
                return rows
            except _adbc_error_types() as exc:
                if not _fallback_allowed():
                    raise
                _logger.warning(
                    "ADBC get_by_ids failed (%s: %s); falling back to SDK select.",
                    type(exc).__name__, exc,
                )
        predicate = ibis._[self._id_column].isin(ids)
        with self._ensure_tx(tx) as active_tx:
            table = self._get_table(active_tx)
            reader = table.select(columns=columns, predicate=predicate)
            return reader.read_all().to_pylist()

    def count(
        self,
        predicate: ibis.Expr | None = None,
    ) -> int:
        """Return the number of rows matching *predicate*.

        Without a predicate, returns cached ``ITable.stats.num_rows`` rather
        than an exact count. Stats may lag writes or temporarily over-count
        while the table settles. Pass a predicate for an exact SDK SELECT count.

        .. warning::
            Supplying a predicate scans matching IDs and materialises them in
            memory (``read_all().num_rows``). Use with care on large tables.

        Args:
            predicate: Optional ``ibis._`` deferred predicate.

        Returns:
            The row count.
        """
        with self._session.transaction() as tx:
            table = self._get_table(tx)
            if predicate is None:
                if table.stats is None:
                    table.reload_stats()
                if table.stats is None:
                    raise RuntimeError(
                        "Table stats unavailable after reload — cannot determine row "
                        "count without a full scan. Pass a predicate (even an "
                        "always-true one) to perform an explicit scan."
                    )
                return table.stats.num_rows
            reader = table.select(columns=[self._id_column], predicate=predicate)
            return reader.read_all().num_rows

    def _adbc_table_path(self) -> str:
        return (
            f'{_quote_ident(self._table_ref.bucket + "/" + self._table_ref.schema)}'
            f'.{_quote_ident(self._table_ref.table)}'
        )

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
        tx: Transaction | None = None,
        **kwargs: Any,
    ) -> list[tuple[dict, float]]:
        """Search VastDB for similar vectors.

        Primary path: ADBC SQL with ``array_distance()`` (server-side, no
        vector index required). Fallback: in-memory L2Sq scan. Subclasses
        can override this hook to customise search behaviour.

        Args:
            query_vector: The query embedding vector.
            k: Maximum number of results to return.
            predicate: Optional ibis deferred predicate used for both the ADBC
                SQL WHERE clause (converted via ``predicate_to_sql_where``) and
                the in-memory fallback scan (passed directly to the VastDB SDK).
            tx: Optional transaction for reuse by subclasses.
            **kwargs: Additional keyword arguments forwarded to
                ``_do_vector_search_adbc`` and ``_build_adbc_where_clause``.

        Returns:
            List of (row_dict, distance_score) tuples.
        """
        columns = self._select_columns()
        with self._ensure_tx(tx) as active_tx:
            self._get_table(active_tx)  # loads vector index metadata once
            return self._do_vector_search(
                active_tx, query_vector, k, columns, predicate,
                **kwargs,
            )

    def _do_vector_search(
        self,
        tx: Transaction,
        query_vector: list[float],
        k: int,
        columns: list[str],
        predicate: ibis.Expr | None,
        **kwargs: Any,
    ) -> list[tuple[dict, float]]:
        """Execute the vector search within a transaction.

        Uses ADBC ``array_distance()`` SQL when configured. Falls back to an
        in-memory L2Sq scan only when ADBC is unavailable/fails AND the
        ``VASTDB_ALLOW_FALLBACK`` env var is set to a truthy value.

        Args:
            tx: An active transaction.
            query_vector: The query embedding vector.
            k: Maximum number of results.
            columns: Column names to select.
            predicate: Optional ibis deferred predicate. Converted to a SQL
                WHERE clause for the ADBC path and passed directly to the VastDB
                SDK for the fallback path.
            **kwargs: Additional keyword arguments forwarded to
                ``_do_vector_search_adbc`` and ``_build_adbc_where_clause``.
                These are **not** forwarded to ``_do_vector_search_fallback``
                because the fallback path does not use ADBC; per-call identity
                overrides (``adbc_*_overrides``) have no effect on the fallback.

        Returns:
            List of (row_dict, distance_score) tuples.

        Raises:
            RuntimeError: If ADBC is not configured and fallback is not allowed.
        """
        if self._adbc_available():
            try:
                return self._do_vector_search_adbc(tx, query_vector, k, predicate, **kwargs)
            except (TypeError, ValueError):
                raise
            except _adbc_error_types() as exc:
                if not _fallback_allowed():
                    raise
                _logger.warning(
                    "ADBC vector search failed (%s: %s); falling back to in-memory L2Sq scan.",
                    type(exc).__name__,
                    exc,
                )
        elif not _fallback_allowed():
            raise RuntimeError(
                "ADBC is not configured. Vector search requires a Query Engine "
                "(ADBC) connection. Provide adbc_driver_path, adbc_endpoint, "
                "access_key, and secret_key to enable vector search. "
                "Alternatively, set VASTDB_ALLOW_FALLBACK=1 for small-table "
                "in-memory search (development/testing only)."
            )
        return self._do_vector_search_fallback(tx, query_vector, k, columns, predicate)

    @contextmanager
    def _open_adbc_connection(self, **kwargs: Any):
        """Yield an open ADBC connection.

        Override this hook to customise driver, db_kwargs, or conn_kwargs —
        for example to inject per-request credentials or impersonation headers.

        Keyword arguments forwarded from the public search methods are made
        available here so subclasses can apply per-call identity without
        retaining mutable state on the instance. The base implementation
        recognises two reserved kwargs:

        - ``adbc_db_kwargs_overrides``: ``dict`` merged on top of the static
          ``vast.db.*`` credentials (e.g. ``{"vast.db.access_key": ...}``).
        - ``adbc_conn_kwargs_overrides``: ``dict`` merged on top of the
          per-instance ``adbc_conn_kwargs``.

        Unknown kwargs are ignored so they can be consumed by other hooks
        (e.g. ``_build_adbc_where_clause``) in the same forwarding chain.

        Args:
            **kwargs: Keyword arguments propagated from
                ``similarity_search``/``_vector_search``/``_do_vector_search_adbc``.
        """
        adbc_dbapi = _get_adbc_dbapi()

        db_kwargs: dict[str, Any] = {
            "vast.db.endpoint": self._adbc_endpoint,
            "vast.db.access_key": self._access_key,
            "vast.db.secret_key": self._secret_key,
        }
        db_overrides = kwargs.get("adbc_db_kwargs_overrides")
        if db_overrides:
            db_kwargs.update(db_overrides)

        connect_kwargs: dict[str, Any] = {
            "driver": self._adbc_driver_path,
            "db_kwargs": db_kwargs,
        }
        conn_kwargs: dict[str, Any] = dict(self._adbc_conn_kwargs or {})
        conn_overrides = kwargs.get("adbc_conn_kwargs_overrides")
        if conn_overrides:
            conn_kwargs.update(conn_overrides)
        if conn_kwargs:
            connect_kwargs["conn_kwargs"] = conn_kwargs

        with adbc_dbapi.connect(**connect_kwargs) as conn:
            yield conn

    def _build_adbc_where_clause(
        self, predicate: ibis.Expr | None, **kwargs: Any
    ) -> str:
        """Return a SQL WHERE fragment (without leading ``WHERE``) or empty string.

        Override this hook to implement filtering that ``predicate_to_sql_where``
        cannot express — for example VastDB-specific functions such as
        ``list_has_any()``, or to inject a raw SQL string directly.

        Args:
            predicate: Optional ibis deferred predicate to convert to SQL.
            **kwargs: Additional keyword arguments forwarded from the search
                chain. Subclasses may use these to pass e.g. a pre-built
                ``where`` string.

        Returns:
            A SQL fragment suitable for insertion after ``WHERE``, or ``""``
            if no filtering is needed.
        """
        if predicate is None:
            return ""
        return predicate_to_sql_where(predicate)

    def _resolve_distance_metric(self) -> str:
        """Return the active distance metric name.

        Resolution order: cluster metadata (authoritative when available),
        then the constructor ``distance_metric`` parameter as fallback.
        """
        vi = self._table_metadata._vector_index
        if vi is not None:
            return vi.distance_metric
        if self._distance_metric is not None:
            return self._distance_metric
        raise ValueError(
            "Cannot resolve distance metric: no cluster metadata and no "
            "distance_metric constructor parameter."
        )

    def _adbc_distance_expr(
        self, vec_col_sql: str, query_vec: list[float], dim: int
    ) -> str:
        """Return the SQL expression for distance computation.

        Override this hook for exotic metrics not covered by the built-in
        mapping. The returned expression must be usable as a SELECT column
        and produce a scalar float (lower = more similar).

        Args:
            vec_col_sql: The quoted column identifier for the vector column.
            query_vec: The query vector as a list of floats.
            dim: Dimensionality of the vectors.

        Returns:
            A SQL expression string computing distance.
        """
        if not all(math.isfinite(x) for x in query_vec):
            raise ValueError("query vector contains non-finite values")
        vec_literal = f"ARRAY{query_vec}::FLOAT[{dim}]"
        col_cast = f"{vec_col_sql}::FLOAT[{dim}]"
        vi = self._table_metadata._vector_index
        if vi is not None:
            metric, fn = vi.distance_metric, vi.sql_distance_function
        else:
            metric = self._resolve_distance_metric()
            fn = {"l2sq": "array_distance", "cosine": "cosine_distance",
                  "ip": "array_inner_product"}.get(metric)
            if fn is None:
                raise ValueError(
                    f"Unknown distance metric {metric!r}; supported: 'l2sq', 'cosine', 'ip'. "
                    f"Override _adbc_distance_expr() for custom metrics."
                )
        expr = f"{fn}({col_cast}, {vec_literal})"
        # array_inner_product is a similarity (higher = closer); negate so ASC ordering
        # and the returned score mean "lower = more similar" like the other metrics.
        return f"-{expr}" if metric == "ip" else expr

    def _do_vector_search_adbc(
        self,
        tx: Transaction,
        query_vector: list[float],
        k: int,
        predicate: ibis.Expr | None,
        **kwargs: Any,
    ) -> list[tuple[dict, float]]:
        """Fetch ranked document columns and distance in one ADBC query.

        Args:
            tx: Active SDK transaction retained for hook compatibility; unused by ADBC.
            query_vector: The query embedding vector.
            k: Maximum number of results.
            predicate: Optional ibis predicate converted via ``_build_adbc_where_clause``.
            **kwargs: Forwarded to the WHERE and connection hooks.

        Returns:
            List of (row_dict, distance_score) tuples ordered by distance.
        """
        where_body = self._build_adbc_where_clause(predicate, **kwargs)
        where_clause = f"WHERE {where_body}" if where_body else ""
        float_vec = [float(x) for x in query_vector]
        distance_expr = self._adbc_distance_expr(
            _quote_ident(self._vector_column), float_vec, len(query_vector)
        )
        alias = _quote_ident(_ADBC_DISTANCE_ALIAS)
        columns = ", ".join(map(_quote_ident, self._select_columns()))
        query = (
            f"SELECT {columns}, {distance_expr} AS {alias} "
            f"FROM {self._adbc_table_path()} {where_clause} "
            f"ORDER BY {alias} LIMIT {k}"
        )
        with self._open_adbc_connection(**kwargs) as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetch_arrow_table().to_pylist()

        ids = [row[self._id_column] for row in rows]
        if len(ids) != len(set(ids)):
            _logger.warning(
                "ADBC vector search returned %d IDs but only %d are unique; "
                "duplicate IDs returned as-is.",
                len(ids),
                len(set(ids)),
            )
        return [(row, float(row.pop(_ADBC_DISTANCE_ALIAS))) for row in rows]

    def _do_vector_search_fallback(
        self,
        tx: Transaction,
        query_vector: list[float],
        k: int,
        columns: list[str],
        predicate: ibis.Expr | None,
    ) -> list[tuple[dict, float]]:
        """In-memory distance fallback when ADBC is unavailable.

        Supports l2sq, cosine, and ip metrics. Reads id + vector columns,
        ranks by the configured distance metric (lower=better), then fetches
        full rows for the top-k hits.

        Only available when ``VASTDB_ALLOW_FALLBACK=1`` is set. Raises
        RuntimeError if the table exceeds ``_FALLBACK_MAX_ROWS`` rows.
        """
        table = self._get_table(tx)
        if table.stats is None:
            table.reload_stats()
        if table.stats and table.stats.num_rows > _FALLBACK_MAX_ROWS:
            raise RuntimeError(
                f"In-memory fallback search refused: table has {table.stats.num_rows} rows "
                f"(limit is {_FALLBACK_MAX_ROWS}). Configure ADBC (Query Engine) "
                f"for production workloads."
            )
        scan_columns = [self._id_column, self._vector_column]
        reader = table.select(predicate=predicate, columns=scan_columns)
        all_rows = reader.read_all().to_pylist()

        metric = self._resolve_distance_metric()
        score_fn = self._fallback_score_fn(metric)

        qdim = len(query_vector)
        scored: list[tuple[str, float]] = []
        skipped = 0
        for row in all_rows:
            vec = row.get(self._vector_column)
            if vec is not None and not isinstance(vec, list):
                vec = list(vec)
            if not isinstance(vec, list) or len(vec) != qdim:
                skipped += 1
                continue
            score = score_fn(query_vector, vec)
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

    @staticmethod
    def _fallback_score_fn(metric: str):
        """Return a scoring function for in-memory distance computation."""
        if metric == "l2sq":
            def _l2sq(a: list[float], b: list[float]) -> float:
                return sum((x - y) * (x - y) for x, y in zip(a, b))
            return _l2sq
        if metric == "cosine":
            def _cosine(a: list[float], b: list[float]) -> float:
                dot = sum(x * y for x, y in zip(a, b))
                norm_a = math.sqrt(sum(x * x for x in a))
                norm_b = math.sqrt(sum(x * x for x in b))
                if norm_a == 0 or norm_b == 0:
                    return 1.0
                return 1.0 - dot / (norm_a * norm_b)
            return _cosine
        if metric == "ip":
            def _ip(a: list[float], b: list[float]) -> float:
                return -sum(x * y for x, y in zip(a, b))
            return _ip
        raise ValueError(
            f"Fallback search does not support metric {metric!r}; "
            f"supported: 'l2sq', 'cosine', 'ip'."
        )

    def _row_to_document(
        self,
        row: dict,
        score: float | None = None,
    ) -> Document:
        """Convert a VastDB row dict to a LangChain Document.

        Extracts text from the configured text column and deserializes
        JSON metadata.  When ``_typed_metadata_columns`` is set, merges
        typed column values into the metadata dict (skipping empty-string
        defaults and keys already present in JSON).

        Args:
            row: A dict representing a single VastDB row.
            score: Optional distance score (available for subclass use).

        Returns:
            A LangChain ``Document`` with page_content and metadata.
        """
        page_content = row.get(self._text_column) or ""
        metadata_raw = row.get(self._metadata_column)
        metadata = json.loads(metadata_raw) if metadata_raw else {}
        for col, tc in self._typed_metadata_columns.items():
            if tc.include_in_metadata and col not in metadata:
                val = row.get(col)
                if val is not None and val != "":
                    metadata[col] = val
        doc_id = row.get(self._id_column)
        return Document(page_content=page_content, metadata=metadata, id=doc_id)
