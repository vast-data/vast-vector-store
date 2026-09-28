"""Unit tests for VastDBVectorStore using mocked VastDB SDK calls."""

import json
import logging
import uuid
from unittest.mock import MagicMock, patch

import numpy as np
import pyarrow as pa
import pytest
from ibis import _
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding

from langchain_vastdb import TypedColumn, VastDBVectorStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_transaction():
    tx = MagicMock()
    return tx


@pytest.fixture
def mock_session(mock_transaction):
    session = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = mock_transaction
    cm.__exit__.return_value = False
    session.transaction.return_value = cm
    return session


@pytest.fixture
def fake_embedding():
    return DeterministicFakeEmbedding(size=3)


@pytest.fixture
def vectorstore(mock_session, fake_embedding, mock_transaction):
    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        distance_metric="l2sq",
    )
    # Replace _table_metadata with a MagicMock so load() calls are trackable
    # without needing a real VastDB cluster
    store._table_metadata = MagicMock()
    store._table_metadata._vector_index = None
    mock_table = MagicMock()
    mock_transaction.table_from_metadata.return_value = mock_table
    return store


@pytest.fixture
def sample_rows():
    return [
        {"id": "id-1", "text": "hello world", "metadata": '{"key": "val1"}'},
        {"id": "id-2", "text": "foo bar", "metadata": '{"key": "val2"}'},
    ]


# ---------------------------------------------------------------------------
# Task 2: Constructor and configuration tests (AC: #3)
# ---------------------------------------------------------------------------


def test_session_first_construction_stores_session(mock_session, fake_embedding):
    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
    )
    assert store._session is mock_session
    assert store._metadata_loaded is False


def test_from_connection_params_patches_vastdb_connect(mock_session, fake_embedding):
    with patch("langchain_vastdb.vectorstores.vastdb.connect") as mock_connect:
        mock_connect.return_value = mock_session
        store = VastDBVectorStore.from_connection_params(
            embedding=fake_embedding,
            endpoint="http://vast:8080",
            access_key="ak",
            secret_key="sk",
            bucket="b",
            schema="s",
            table_name="t",
        )
        mock_connect.assert_called_once_with(
            endpoint="http://vast:8080", access="ak", secret="sk", ssl_verify=True
        )
    assert store._session is mock_session


def test_connect_pins_data_endpoints_on_loopback():
    """vastdb 2.1 VIP discovery is skipped when the endpoint is loopback."""
    from vastdb.config import SessionConfig

    from langchain_vastdb.vectorstores import _connect

    with patch("langchain_vastdb.vectorstores.vastdb.connect") as mock_connect:
        _connect(endpoint="https://localhost:18151", access="ak", secret="sk")
        kwargs = mock_connect.call_args.kwargs
        assert kwargs["config"] == SessionConfig(
            data_endpoints=["https://localhost:18151"]
        )

    with patch("langchain_vastdb.vectorstores.vastdb.connect") as mock_connect:
        _connect(endpoint="http://vast:8080", access="ak", secret="sk")
        assert "config" not in mock_connect.call_args.kwargs


def test_custom_column_name_configuration(mock_session, fake_embedding):
    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        id_column="my_id",
        text_column="my_text",
        vector_column="my_vec",
        metadata_column="my_meta",
    )
    assert store._id_column == "my_id"
    assert store._text_column == "my_text"
    assert store._vector_column == "my_vec"
    assert store._metadata_column == "my_meta"


def test_embeddings_property_returns_embedding_instance(vectorstore, fake_embedding):
    assert vectorstore.embeddings is fake_embedding


def test_credentials_not_exposed_as_public_attributes(mock_session, fake_embedding):
    with patch("langchain_vastdb.vectorstores.vastdb.connect") as mock_connect:
        mock_connect.return_value = mock_session
        store = VastDBVectorStore.from_connection_params(
            embedding=fake_embedding,
            endpoint="http://vast:8080",
            access_key="ak",
            secret_key="sk",
            bucket="b",
            schema="s",
            table_name="t",
        )
    assert not hasattr(store, "access_key")
    assert not hasattr(store, "secret_key")


# ---------------------------------------------------------------------------
# Task 3: Table access and cache tests (AC: #1)
# ---------------------------------------------------------------------------


def test_get_table_loads_metadata_on_first_call(vectorstore, mock_transaction):
    vectorstore._get_table(mock_transaction)
    vectorstore._table_metadata.load.assert_called_once_with(mock_transaction)
    mock_transaction.table_from_metadata.assert_called_once()


def test_get_table_skips_load_on_subsequent_calls(vectorstore, mock_transaction):
    vectorstore._get_table(mock_transaction)
    vectorstore._get_table(mock_transaction)
    # load() should only be called once (first call), not on cache hit
    vectorstore._table_metadata.load.assert_called_once()
    assert mock_transaction.table_from_metadata.call_count == 2


def test_invalidate_table_cache_resets_metadata_loaded(vectorstore):
    vectorstore._metadata_loaded = True
    vectorstore.invalidate_table_cache()
    assert vectorstore._metadata_loaded is False


# ---------------------------------------------------------------------------
# Task 4: add_texts tests (AC: #4)
# ---------------------------------------------------------------------------


def test_add_texts_embeds_via_embed_documents(vectorstore):
    # DeterministicFakeEmbedding is a frozen Pydantic model; patch at class level
    with patch.object(vectorstore, "_insert_vectors", return_value=["id-1"]):
        with patch.object(
            DeterministicFakeEmbedding, "embed_documents", return_value=[[0.1, 0.2, 0.3]]
        ) as mock_embed:
            vectorstore.add_texts(["hello"])
            mock_embed.assert_called_once_with(["hello"])


def test_add_texts_calls_insert_vectors_with_correct_args(vectorstore):
    with patch.object(vectorstore, "_insert_vectors", return_value=["my-id"]) as mock_insert:
        vectorstore.add_texts(["hello"], metadatas=[{"k": "v"}], ids=["my-id"])
        mock_insert.assert_called_once()
        args = mock_insert.call_args.args
        assert args[0] == ["hello"]
        assert args[2] == [{"k": "v"}]
        assert args[3] == ["my-id"]
        assert len(args[1]) == 1  # one embedding vector


def test_add_texts_generates_uuids_when_no_ids_provided(vectorstore):
    ids = vectorstore.add_texts(["hello"])
    assert len(ids) == 1
    uuid.UUID(ids[0])  # raises ValueError if not a valid UUID


def test_add_texts_uses_explicit_ids_when_provided(vectorstore):
    ids = vectorstore.add_texts(["hello"], ids=["explicit-id"])
    assert ids == ["explicit-id"]


def test_add_texts_defaults_empty_metadata_when_none(vectorstore):
    with patch.object(vectorstore, "_insert_vectors", return_value=["id-1", "id-2"]) as mock_insert:
        vectorstore.add_texts(["a", "b"], metadatas=None)
        args = mock_insert.call_args.args
        assert args[2] == [{}, {}]


# ---------------------------------------------------------------------------
# Task 5: Search method tests (AC: #5)
# ---------------------------------------------------------------------------


def test_similarity_search_returns_list_of_documents(vectorstore, mock_transaction):
    row = {"id": "1", "text": "hello", "metadata": '{"k": "v"}'}
    with patch.object(vectorstore, "_do_vector_search", return_value=[(row, 0.5)]):
        results = vectorstore.similarity_search("hello")

    assert isinstance(results, list)
    assert len(results) == 1
    assert isinstance(results[0], Document)
    assert results[0].page_content == "hello"


def test_similarity_search_with_score_returns_tuples_with_float_scores(
    vectorstore, mock_transaction
):
    row = {"id": "1", "text": "hello", "metadata": "{}"}
    with patch.object(vectorstore, "_do_vector_search", return_value=[(row, 0.3)]):
        results = vectorstore.similarity_search_with_score("hello")

    assert isinstance(results, list)
    assert len(results) == 1
    doc, score = results[0]
    assert isinstance(doc, Document)
    assert isinstance(score, float)
    assert score == pytest.approx(0.3)


def test_similarity_search_by_vector_skips_embed_query(
    vectorstore, mock_transaction, fake_embedding
):
    with patch.object(vectorstore, "_do_vector_search", return_value=[]):
        # DeterministicFakeEmbedding is a frozen Pydantic model; patch at class level
        with patch.object(DeterministicFakeEmbedding, "embed_query") as mock_embed_query:
            vectorstore.similarity_search_by_vector([0.1, 0.2, 0.3])
            mock_embed_query.assert_not_called()


def test_similarity_search_passes_predicate_to_vector_search(vectorstore, mock_transaction):
    pred = _["category"] == "news"
    with patch.object(vectorstore, "_do_vector_search", return_value=[]) as mock_search:
        vectorstore.similarity_search("hello", predicate=pred)

    args = mock_search.call_args.args  # (tx, query_vector, k, columns, predicate)
    assert args[4] is pred


def test_similarity_search_filter_kwarg_raises_helpful_error(vectorstore):
    with pytest.raises(TypeError, match="'filter' keyword argument was removed"):
        vectorstore.similarity_search("hello", filter={"category": "news"})


def test_similarity_search_with_score_filter_kwarg_raises(vectorstore):
    with pytest.raises(TypeError, match="'filter' keyword argument was removed"):
        vectorstore.similarity_search_with_score("hello", filter={"category": "news"})


def test_similarity_search_by_vector_filter_kwarg_raises(vectorstore):
    with pytest.raises(TypeError, match="'filter' keyword argument was removed"):
        vectorstore.similarity_search_by_vector([0.1, 0.2, 0.3], filter={"category": "news"})


def test_row_to_document_deserializes_json_metadata(vectorstore):
    row = {"text": "hello world", "metadata": '{"source": "test", "page": 1}'}
    doc = vectorstore._row_to_document(row)
    assert doc.page_content == "hello world"
    assert doc.metadata == {"source": "test", "page": 1}



# ---------------------------------------------------------------------------
# Task 6: Delete and get_by_ids tests (AC: #6)
# ---------------------------------------------------------------------------


def test_delete_with_ids_calls_delete_by_ids_and_returns_true(
    vectorstore, mock_transaction
):
    mock_table = mock_transaction.table_from_metadata.return_value
    result = vectorstore.delete(ids=["id-1"])
    assert result is True
    mock_table.delete.assert_called_once()


def test_delete_with_none_ids_returns_none(vectorstore):
    result = vectorstore.delete(ids=None)
    assert result is None


def test_delete_with_empty_ids_returns_none(vectorstore):
    result = vectorstore.delete(ids=[])
    assert result is None


def test_sdk_get_by_ids_empty_preserves_select_path(vectorstore, mock_transaction):
    table = mock_transaction.table_from_metadata.return_value
    table.select.return_value.read_all.return_value.to_pylist.return_value = []
    assert vectorstore._get_by_ids([]) == []
    table.select.assert_called_once()


def test_get_by_ids_returns_correct_documents(vectorstore, mock_transaction, sample_rows):
    mock_table = mock_transaction.table_from_metadata.return_value
    mock_reader = MagicMock()
    mock_reader.read_all.return_value.to_pylist.return_value = sample_rows
    mock_table.select.return_value = mock_reader

    docs = vectorstore.get_by_ids(["id-1", "id-2"])

    assert len(docs) == 2
    assert isinstance(docs[0], Document)
    assert docs[0].page_content == "hello world"
    assert docs[0].metadata == {"key": "val1"}
    assert docs[1].page_content == "foo bar"
    assert docs[1].metadata == {"key": "val2"}


def test_from_texts_constructs_instance_and_calls_add_texts(mock_session, fake_embedding):
    with patch.object(VastDBVectorStore, "add_texts", return_value=["id-1"]) as mock_add:
        store = VastDBVectorStore.from_texts(
            texts=["hello"],
            embedding=fake_embedding,
            session=mock_session,
            bucket="b",
            schema="s",
            table_name="t",
        )
        mock_add.assert_called_once_with(["hello"], metadatas=None)
    assert isinstance(store, VastDBVectorStore)


# ---------------------------------------------------------------------------
# Task 7: Hook extensibility tests (AC: #7)
# ---------------------------------------------------------------------------


class TrackingVectorStore(VastDBVectorStore):
    """Test subclass that overrides _insert_vectors to track calls."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.insert_calls = []

    def _insert_vectors(self, texts, embeddings, metadatas, ids, *, tx=None):
        self.insert_calls.append((texts, embeddings, metadatas, ids))
        return ids


def test_add_texts_dispatches_to_overridden_insert_vectors(mock_session, fake_embedding):
    store = TrackingVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
    )
    store.add_texts(["hello"])
    assert len(store.insert_calls) == 1
    assert store.insert_calls[0][0] == ["hello"]


class TypedColumnStore(VastDBVectorStore):
    """Test subclass using the declarative _typed_metadata_columns attribute."""

    _typed_metadata_columns = {
        "category": TypedColumn(),
        "source": TypedColumn(),
    }


def test_metadata_columns_default_serializes_json(vectorstore):
    result = vectorstore._build_metadata_columns([{"k": "v"}, {"k2": "v2"}])
    assert list(result.keys()) == ["metadata"]
    assert result["metadata"] == ['{"k": "v"}', '{"k2": "v2"}']


def test_typed_metadata_columns_pops_fields_and_dumps_remainder(
    mock_session, fake_embedding,
):
    store = TypedColumnStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
    )
    result = store._build_metadata_columns([
        {"category": "db", "source": "docs", "extra": "val"},
    ])
    assert result["category"] == ["db"]
    assert result["source"] == ["docs"]
    assert json.loads(result["metadata"][0]) == {"extra": "val"}


def test_typed_metadata_columns_select_columns_auto_derived(
    mock_session, fake_embedding,
):
    store = TypedColumnStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
    )
    cols = store._select_columns()
    assert cols == ["id", "text", "category", "source", "metadata"]


def test_typed_metadata_columns_used_by_insert_vectors(
    mock_session, fake_embedding, mock_transaction,
):
    store = TypedColumnStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        distance_metric="l2sq",
    )
    store._table_metadata = MagicMock()
    store._table_metadata._vector_index = None
    store._metadata_loaded = False
    mock_table = MagicMock()
    mock_transaction.table_from_metadata.return_value = mock_table

    store._insert_vectors(
        ["hello"], [[0.1, 0.2, 0.3]],
        [{"category": "db", "source": "docs", "extra": "val"}],
        ["id-1"],
        tx=mock_transaction,
    )
    batch = mock_table.insert.call_args[0][0]
    assert batch.column("category").to_pylist() == ["db"]
    assert batch.column("source").to_pylist() == ["docs"]
    assert json.loads(batch.column("metadata").to_pylist()[0]) == {"extra": "val"}


def test_typed_metadata_columns_row_to_document_merges(
    mock_session, fake_embedding,
):
    store = TypedColumnStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
    )
    row = {
        "id": "1",
        "text": "hello",
        "category": "db",
        "source": "docs",
        "metadata": json.dumps({"extra": "val"}),
    }
    doc = store._row_to_document(row)
    assert doc.metadata == {"extra": "val", "category": "db", "source": "docs"}


def test_typed_metadata_columns_empty_default_skipped_on_read(
    mock_session, fake_embedding,
):
    store = TypedColumnStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
    )
    row = {
        "id": "1",
        "text": "hello",
        "category": "",
        "source": "",
        "metadata": json.dumps({"foo": "bar"}),
    }
    doc = store._row_to_document(row)
    assert doc.metadata == {"foo": "bar"}
    assert "category" not in doc.metadata


class ScoreAddingVectorStore(VastDBVectorStore):
    """Test subclass that overrides _row_to_document to embed score in metadata."""

    def _row_to_document(self, row, score=None):
        doc = super()._row_to_document(row, score)
        if score is not None:
            doc.metadata["score"] = score
        return doc


def test_similarity_search_with_score_uses_overridden_row_to_document(
    mock_session, fake_embedding, mock_transaction
):
    store = ScoreAddingVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
    )
    row = {"id": "1", "text": "hello", "metadata": "{}"}
    with patch.object(store, "_do_vector_search", return_value=[(row, 0.7)]):
        results = store.similarity_search_with_score("hello")
    doc, score = results[0]
    assert score == pytest.approx(0.7)
    assert doc.metadata.get("score") == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# Task 13b: Code-review patch backlog P1–P7 tests
# ---------------------------------------------------------------------------

# --- P3: len(ids) == len(texts) guard ---


def test_add_texts_ids_length_mismatch_raises(vectorstore):
    with pytest.raises(ValueError, match="ids length 1 != texts length 2"):
        vectorstore.add_texts(["a", "b"], ids=["x"])


# --- P4: k <= 0 guard ---


def test_similarity_search_k_zero_raises(vectorstore):
    with pytest.raises(ValueError, match="k must be a positive integer"):
        vectorstore.similarity_search("q", k=0)


def test_similarity_search_k_negative_raises(vectorstore):
    with pytest.raises(ValueError, match="k must be a positive integer"):
        vectorstore.similarity_search("q", k=-1)


def test_similarity_search_by_vector_k_zero_raises(vectorstore):
    with pytest.raises(ValueError, match="k must be a positive integer"):
        vectorstore.similarity_search_by_vector([0.1, 0.2, 0.3], k=0)


# --- P5: NaN / inf guard ---


def test_similarity_search_by_vector_nan_raises(vectorstore):
    with pytest.raises(ValueError, match="non-finite"):
        vectorstore.similarity_search_by_vector([float("nan"), 0.2, 0.3])


def test_similarity_search_by_vector_inf_raises(vectorstore):
    with pytest.raises(ValueError, match="non-finite"):
        vectorstore.similarity_search_by_vector([0.1, float("inf"), 0.3])


def test_similarity_search_by_vector_numpy_array_does_not_raise_truth_value_error(
    vectorstore, mock_transaction
):
    """numpy.ndarray raises 'truth value of array is ambiguous' on `if not arr`."""
    embedding = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    mock_transaction.__enter__.return_value.execute.return_value = []
    vectorstore._vector_search = MagicMock(return_value=[])
    result = vectorstore.similarity_search_by_vector(embedding)
    assert result == []


def test_similarity_search_by_vector_empty_numpy_raises(vectorstore):
    with pytest.raises(ValueError, match="non-empty"):
        vectorstore.similarity_search_by_vector(np.array([]))


# --- P6: Duplicate IDs ---


def test_add_texts_duplicate_ids_raises(vectorstore):
    with pytest.raises(ValueError, match="Duplicate IDs"):
        vectorstore.add_texts(["a", "b"], ids=["x", "x"])


def test_add_texts_duplicate_ids_message_includes_dupe(vectorstore):
    with pytest.raises(ValueError, match="x"):
        vectorstore.add_texts(["a", "b", "c"], ids=["x", "y", "x"])


# --- P1 + P7: _do_vector_search_adbc filter validation ---
# These tests exercise validation that fires *before* any ADBC connection
# is opened, so no mocking of adbc_driver_manager is needed.


@pytest.fixture
def adbc_vectorstore(mock_session, fake_embedding, mock_transaction):
    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        adbc_driver_path="/path/to/driver.so",
        adbc_endpoint="localhost:8080",
        access_key="ak",
        secret_key="sk",
        distance_metric="l2sq",
    )
    store._table_metadata = MagicMock()
    store._table_metadata._vector_index = None
    mock_table = MagicMock()
    mock_transaction.table_from_metadata.return_value = mock_table
    return store


def test_adbc_delete_joins_tx_and_closes_before_commit(
    adbc_vectorstore, mock_transaction, mock_session
):
    mock_transaction.txid = 123
    events = []
    dbapi = MagicMock()
    conn_cm = dbapi.connect.return_value
    conn_cm.__exit__.side_effect = lambda *args: events.append("connection closed")
    mock_session.transaction.return_value.__exit__.side_effect = (
        lambda *args: events.append("transaction closed")
    )
    cursor = conn_cm.__enter__.return_value.cursor.return_value.__enter__.return_value
    sdk_table = mock_transaction.table_from_metadata.return_value
    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=dbapi):
        assert adbc_vectorstore._delete_by_ids(["a", "it's"]) is True
    assert cursor.execute.call_args.args[0] == (
        'DELETE FROM "b/s"."t" WHERE ("id" = \'a\' OR "id" = \'it\'\'s\')'
    )
    assert dbapi.connect.call_args.kwargs["conn_kwargs"] == {"vast.db.external_txid": "123"}
    assert events == ["connection closed", "transaction closed"]
    mock_transaction.table_from_metadata.assert_not_called()
    sdk_table.select.assert_not_called()
    sdk_table.delete.assert_not_called()


def test_adbc_delete_batches_and_empty_skips_connection(adbc_vectorstore, mock_transaction):
    mock_transaction.txid = 123
    dbapi = MagicMock()
    conn = dbapi.connect.return_value.__enter__.return_value
    cursor = conn.cursor.return_value.__enter__.return_value
    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=dbapi):
        assert adbc_vectorstore._delete_by_ids([]) is True
        dbapi.connect.assert_not_called()
        assert adbc_vectorstore._delete_by_ids([str(i) for i in range(2500)]) is True
    assert dbapi.connect.call_count == 1
    assert cursor.execute.call_count == 3
    assert all(" IN (" not in call.args[0] for call in cursor.execute.call_args_list)


@pytest.mark.parametrize("fallback", [True, False])
def test_adbc_delete_error_falls_back_only_when_allowed(
    adbc_vectorstore, mock_transaction, fallback
):
    mock_transaction.txid = 123
    dbapi = MagicMock()
    dbapi.connect.side_effect = OSError("offline")
    sdk_table = mock_transaction.table_from_metadata.return_value
    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=dbapi), patch(
        "langchain_vastdb.vectorstores._fallback_allowed", return_value=fallback
    ):
        if fallback:
            assert adbc_vectorstore._delete_by_ids(["a"]) is True
            sdk_table.delete.assert_called_once()
        else:
            with pytest.raises(OSError, match="offline"):
                adbc_vectorstore._delete_by_ids(["a"])
            sdk_table.delete.assert_not_called()


@pytest.mark.parametrize(
    ("version", "qe_lookup", "qe_delete"),
    [((5, 3, 2), False, False), ((5, 4, 0), True, False), ((5, 5, 1), True, True)],
)
def test_adbc_paths_gated_by_cluster_version(
    adbc_vectorstore, mock_session, mock_transaction, version, qe_lookup, qe_delete
):
    mock_session.features.vast_version = version
    mock_transaction.txid = 123
    dbapi = MagicMock()
    conn = dbapi.connect.return_value.__enter__.return_value
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetch_arrow_table.return_value.to_pylist.return_value = []
    sdk_table = mock_transaction.table_from_metadata.return_value
    sdk_table.select.return_value.read_all.return_value.to_pylist.return_value = []
    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=dbapi):
        adbc_vectorstore._get_by_ids(["a"])
        assert (cursor.execute.call_count == 1) is qe_lookup
        assert (sdk_table.select.call_count == 1) is (not qe_lookup)
        cursor.execute.reset_mock()
        adbc_vectorstore._delete_by_ids(["a"])
        assert (cursor.execute.call_count == 1) is qe_delete
        assert (sdk_table.delete.call_count == 1) is (not qe_delete)


def test_select_columns_must_include_id_column(mock_session, fake_embedding):
    class NoId(VastDBVectorStore):
        def _select_columns(self):
            return [self._text_column, self._metadata_column]

    with pytest.raises(ValueError, match="must include the id column 'id'"):
        NoId(embedding=fake_embedding, session=mock_session, bucket="b", schema="s", table_name="t")


def test_adbc_search_uses_index_sql_distance_function(adbc_vectorstore):
    adbc_vectorstore._table_metadata._vector_index = MagicMock(
        distance_metric="ip", sql_distance_function="array_inner_product"
    )
    dbapi = MagicMock()
    conn = dbapi.connect.return_value.__enter__.return_value
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetch_arrow_table.return_value.to_pylist.return_value = []
    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=dbapi):
        adbc_vectorstore.similarity_search_by_vector([0.1, 0.2, 0.3])
    assert '-array_inner_product("embedding"::FLOAT[3], ' in cursor.execute.call_args.args[0]


def test_adbc_search_skips_null_distance_rows(adbc_vectorstore):
    dbapi = MagicMock()
    conn = dbapi.connect.return_value.__enter__.return_value
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetch_arrow_table.return_value.to_pylist.return_value = [
        {"id": "n", "text": "null vec", "metadata": "{}", "_vastdb_distance": None},
        {"id": "x", "text": "hello", "metadata": "{}", "_vastdb_distance": 0.5},
    ]
    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=dbapi):
        results = adbc_vectorstore._vector_search([0.1, 0.2, 0.3], 4)
    assert [(row["id"], s) for row, s in results] == [("x", 0.5)]


def test_adbc_upsert_delete_and_sdk_insert_share_transaction(
    adbc_vectorstore, mock_transaction, mock_session
):
    mock_transaction.txid = 123
    dbapi = MagicMock()
    conn = dbapi.connect.return_value.__enter__.return_value
    cursor = conn.cursor.return_value.__enter__.return_value
    sdk_table = mock_transaction.table_from_metadata.return_value
    calls = MagicMock()
    calls.attach_mock(cursor.execute, "delete_sql")
    calls.attach_mock(sdk_table.insert, "insert_arrow")
    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=dbapi):
        assert adbc_vectorstore.add_texts(["hello"], ids=["a"]) == ["a"]
    assert [call[0] for call in calls.mock_calls] == ["delete_sql", "insert_arrow"]
    mock_session.transaction.assert_called_once()
    assert 'DELETE FROM "b/s"."t" WHERE ("id" = \'a\')' == cursor.execute.call_args.args[0]
    assert dbapi.connect.call_args.kwargs["conn_kwargs"]["vast.db.external_txid"] == "123"
    sdk_table.insert.assert_called_once()
    mock_transaction.table_from_metadata.assert_called_once()


def test_adbc_get_by_ids_batches_dedupes_and_uses_one_connection(adbc_vectorstore):
    dbapi = MagicMock()
    conn = dbapi.connect.return_value.__enter__.return_value
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetch_arrow_table.return_value.to_pylist.return_value = []
    ids = [f"id-{i}" for i in range(2500)] + ["id-0"]
    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=dbapi):
        assert adbc_vectorstore._get_by_ids(ids) == []
    dbapi.connect.assert_called_once()
    assert "conn_kwargs" not in dbapi.connect.call_args.kwargs
    assert cursor.execute.call_count == 3
    queries = [call.args[0] for call in cursor.execute.call_args_list]
    assert all(query.startswith('SELECT "id", "text", "metadata" FROM "b/s"."t" WHERE (')
               for query in queries)
    assert all(" IN (" not in query for query in queries)
    assert queries[0].count("\"id\" = 'id-0'") == 1
    assert "id-999" in queries[0] and "id-1000" in queries[1]
    assert "id-1999" in queries[1] and "id-2000" in queries[2]


def test_adbc_get_by_ids_empty_and_tx_join(adbc_vectorstore, mock_transaction):
    mock_transaction.txid = 123
    dbapi = MagicMock()
    conn = dbapi.connect.return_value.__enter__.return_value
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetch_arrow_table.return_value.to_pylist.return_value = [
        {"id": "it's", "text": "yes", "metadata": "{}"}
    ]
    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=dbapi):
        assert adbc_vectorstore._get_by_ids([]) == []
        dbapi.connect.assert_not_called()
        rows = adbc_vectorstore._get_by_ids(["it's"], tx=mock_transaction)
    assert rows == [{"id": "it's", "text": "yes", "metadata": "{}"}]
    assert "'it''s'" in cursor.execute.call_args.args[0]
    assert dbapi.connect.call_args.kwargs["conn_kwargs"] == {"vast.db.external_txid": "123"}


@pytest.mark.parametrize("allow_fallback", [False, True])
def test_adbc_get_by_ids_error_fallback(adbc_vectorstore, mock_transaction, allow_fallback):
    dbapi = MagicMock()
    dbapi.connect.side_effect = OSError("offline")
    sdk_table = mock_transaction.table_from_metadata.return_value
    sdk_table.select.return_value.read_all.return_value.to_pylist.return_value = [
        {"id": "a", "text": "sdk", "metadata": "{}"}
    ]
    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=dbapi), patch(
        "langchain_vastdb.vectorstores._fallback_allowed", return_value=allow_fallback
    ):
        if allow_fallback:
            assert adbc_vectorstore._get_by_ids(["a"])[0]["text"] == "sdk"
            sdk_table.select.assert_called_once()
        else:
            with pytest.raises(OSError, match="offline"):
                adbc_vectorstore._get_by_ids(["a"])
            sdk_table.select.assert_not_called()


@pytest.mark.parametrize(
    "method",
    [
        "similarity_search", "similarity_search_with_score",
        "similarity_search_by_vector", "retriever",
    ],
)
def test_adbc_search_projects_document_in_one_query(adbc_vectorstore, mock_transaction, method):
    adbc_vectorstore._typed_metadata_columns = {
        "distance": TypedColumn(), "category": TypedColumn(),
    }
    cursor = MagicMock()
    cursor.fetch_arrow_table.return_value.to_pylist.return_value = [
        {"id": "x", "text": "hello", "distance": 7, "category": "news",
         "metadata": "{}", "_vastdb_distance": 0.25}
    ]
    dbapi = MagicMock()
    conn = dbapi.connect.return_value.__enter__.return_value
    conn.cursor.return_value.__enter__.return_value = cursor
    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=dbapi), patch.object(
        adbc_vectorstore, "_get_by_ids"
    ) as get_rows:
        if method == "retriever":
            results = adbc_vectorstore.as_retriever().invoke("hello")
        elif method == "similarity_search_by_vector":
            results = adbc_vectorstore.similarity_search_by_vector([0.1, 0.2, 0.3])
        else:
            results = getattr(adbc_vectorstore, method)("hello")
    cursor.execute.assert_called_once()
    sql = cursor.execute.call_args.args[0]
    assert 'SELECT "id", "text", "distance", "category", "metadata", ' in sql
    assert ' AS "_vastdb_distance" FROM "b/s"."t"' in sql
    assert 'ORDER BY "_vastdb_distance" LIMIT 4' in sql
    mock_transaction.table_from_metadata.return_value.select.assert_not_called()
    get_rows.assert_not_called()
    doc, score = results[0] if method == "similarity_search_with_score" else (results[0], None)
    assert doc.id == "x" and doc.metadata == {"distance": 7, "category": "news"}
    if score is not None:
        assert score == 0.25 and isinstance(score, float)


def test_adbc_search_isin_filter_uses_or_chain(adbc_vectorstore):
    dbapi = MagicMock()
    conn = dbapi.connect.return_value.__enter__.return_value
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetch_arrow_table.return_value.to_pylist.return_value = []
    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=dbapi):
        assert adbc_vectorstore.similarity_search_by_vector(
            [0.1, 0.2, 0.3], predicate=_["category"].isin(["news", "it's"])
        ) == []
    sql = cursor.execute.call_args.args[0]
    assert 'WHERE ("category" = \'news\' OR "category" = \'it\'\'s\')' in sql
    assert " IN (" not in sql


def test_adbc_filter_sql_injection_col_is_quoted(adbc_vectorstore, mock_transaction):
    """P1: double-quotes in column names are escaped (doubled), preventing SQL injection."""
    mock_dbapi = MagicMock()
    _cm = mock_dbapi.connect.return_value.__enter__.return_value
    mock_cursor = _cm.cursor.return_value.__enter__.return_value
    mock_cursor.fetch_arrow_table.return_value.to_pylist.return_value = []
    predicate = _['"evil"'] == "val"
    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=mock_dbapi):
        adbc_vectorstore._do_vector_search_adbc(
            mock_transaction, [0.1, 0.2, 0.3], k=4, predicate=predicate
        )
    executed_sql = mock_cursor.execute.call_args[0][0]
    # The double-quote inside the column name must be doubled, not left bare
    assert '""evil""' in executed_sql


def test_adbc_filter_string_value_with_single_quote_is_escaped(
    adbc_vectorstore, mock_transaction
):
    """P1: single quotes in string filter values are escaped (SQL injection prevention)."""
    mock_dbapi = MagicMock()
    _cm = mock_dbapi.connect.return_value.__enter__.return_value
    mock_cursor = _cm.cursor.return_value.__enter__.return_value
    mock_cursor.fetch_arrow_table.return_value.to_pylist.return_value = []

    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=mock_dbapi):
        adbc_vectorstore._do_vector_search_adbc(
            mock_transaction,
            [0.1, 0.2, 0.3],
            k=4,
            predicate=_["id"] == "it's here",
        )

    executed_sql = mock_cursor.execute.call_args[0][0]
    assert "it''s here" in executed_sql


# --- P2: table path escaping ---


def test_adbc_table_path_double_quotes_in_bucket_are_escaped(
    mock_session, fake_embedding, mock_transaction
):
    """P2: double-quotes in bucket/schema/table names are doubled in the SQL path."""
    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket='b"ucket',
        schema="s",
        table_name="t",
        adbc_driver_path="/path/to/driver.so",
        adbc_endpoint="localhost:8080",
        access_key="ak",
        secret_key="sk",
        distance_metric="l2sq",
    )
    store._table_metadata = MagicMock()
    store._table_metadata._vector_index = None
    mock_transaction.table_from_metadata.return_value = MagicMock()

    mock_dbapi = MagicMock()
    _cm2 = mock_dbapi.connect.return_value.__enter__.return_value
    mock_cursor = _cm2.cursor.return_value.__enter__.return_value
    mock_cursor.fetch_arrow_table.return_value.to_pylist.return_value = []

    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=mock_dbapi):
        store._do_vector_search_adbc(mock_transaction, [0.1, 0.2, 0.3], k=4, predicate=None)

    executed_sql = mock_cursor.execute.call_args[0][0]
    assert 'b""ucket' in executed_sql


# ---------------------------------------------------------------------------
# Story 3.2: Retriever & RAG chain integration validation (unit tests)
# ---------------------------------------------------------------------------


def test_as_retriever_returns_retriever_instance(vectorstore):
    """AC #1: as_retriever() returns a VectorStoreRetriever."""
    from langchain_core.vectorstores import VectorStoreRetriever

    retriever = vectorstore.as_retriever()
    assert isinstance(retriever, VectorStoreRetriever)


def test_retriever_invoke_returns_documents(vectorstore):
    """AC #2: retriever.invoke() returns list[Document] via similarity_search."""
    rows = [
        ({"id": "1", "text": "hello world", "metadata": '{"k": "v"}'}, 0.1),
        ({"id": "2", "text": "foo bar", "metadata": "{}"}, 0.5),
    ]
    retriever = vectorstore.as_retriever()
    with patch.object(vectorstore, "_do_vector_search", return_value=rows):
        docs = retriever.invoke("hello")

    assert isinstance(docs, list)
    assert len(docs) == 2
    assert all(isinstance(d, Document) for d in docs)
    assert docs[0].page_content == "hello world"
    assert docs[1].page_content == "foo bar"


def test_retriever_invoke_empty_store(vectorstore):
    """AC #2: retriever on empty store returns []."""
    retriever = vectorstore.as_retriever()
    with patch.object(vectorstore, "_do_vector_search", return_value=[]):
        docs = retriever.invoke("anything")

    assert docs == []


def test_retriever_with_k_kwarg(vectorstore):
    """AC #3: as_retriever(search_kwargs={"k": 2}) passes k to similarity_search."""
    retriever = vectorstore.as_retriever(search_kwargs={"k": 2})
    with patch.object(vectorstore, "similarity_search", return_value=[]) as mock_ss:
        retriever.invoke("query")

    mock_ss.assert_called_once()
    call_kwargs = mock_ss.call_args
    assert call_kwargs.kwargs.get("k") == 2 or call_kwargs[1].get("k") == 2


def test_retriever_with_predicate_kwarg(vectorstore):
    """AC #3: as_retriever(search_kwargs={"predicate": ...}) passes ibis predicate."""
    pred = _["category"] == "news"
    retriever = vectorstore.as_retriever(
        search_kwargs={"predicate": pred}
    )
    with patch.object(vectorstore, "similarity_search", return_value=[]) as mock_ss:
        retriever.invoke("query")

    mock_ss.assert_called_once()
    call_kwargs = mock_ss.call_args
    passed = (
        call_kwargs.kwargs.get("predicate")
        if "predicate" in call_kwargs.kwargs
        else call_kwargs[1].get("predicate")
    )
    assert passed is pred


def test_lcel_rag_chain_executes(vectorstore):
    """AC #4: LCEL chain retriever | prompt | llm executes successfully."""
    from langchain_core.language_models import FakeListLLM
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnablePassthrough

    rows = [
        ({"id": "1", "text": "VAST is a database", "metadata": "{}"}, 0.1),
    ]
    retriever = vectorstore.as_retriever()

    prompt = ChatPromptTemplate.from_template(
        "Answer based on context:\n{context}\n\nQuestion: {question}"
    )

    def format_docs(docs):
        return "\n".join(d.page_content for d in docs)

    llm = FakeListLLM(responses=["This is a test answer"])
    chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    with patch.object(vectorstore, "_do_vector_search", return_value=rows):
        result = chain.invoke("What is VAST?")

    assert isinstance(result, str)
    assert "This is a test answer" in result


# ---------------------------------------------------------------------------
# Story 4-2a: Pre-publication hardening tests
# ---------------------------------------------------------------------------

# --- AC1: NULL-safe _row_to_document ---


def test_row_to_document_none_metadata_returns_empty_dict(vectorstore):
    """AI-2: None metadata column should produce empty dict, not raise TypeError."""
    row = {"id": "1", "text": "hello", "metadata": None}
    doc = vectorstore._row_to_document(row)
    assert doc.page_content == "hello"
    assert doc.metadata == {}


def test_row_to_document_missing_metadata_key_returns_empty_dict(vectorstore):
    """Missing metadata key should produce empty dict."""
    row = {"id": "1", "text": "hello"}
    doc = vectorstore._row_to_document(row)
    assert doc.metadata == {}


def test_row_to_document_none_text_returns_empty_string(vectorstore):
    """DF-k: None text column should produce empty string, not Document(page_content=None)."""
    row = {"id": "1", "text": None, "metadata": "{}"}
    doc = vectorstore._row_to_document(row)
    assert doc.page_content == ""


def test_row_to_document_missing_text_key_returns_empty_string(vectorstore):
    """Missing text key should produce empty string."""
    row = {"id": "1", "metadata": "{}"}
    doc = vectorstore._row_to_document(row)
    assert doc.page_content == ""


# --- AC2: Input validation ---


def test_add_texts_empty_string_id_raises(vectorstore):
    """DF-l: Empty-string IDs should be rejected."""
    with pytest.raises(ValueError, match="Empty-string IDs"):
        vectorstore.add_texts(["hello"], ids=[""])


def test_add_texts_mixed_empty_and_valid_ids_raises(vectorstore):
    """DF-l: Empty string among valid IDs should be rejected."""
    with pytest.raises(ValueError, match="Empty-string IDs"):
        vectorstore.add_texts(["a", "b", "c"], ids=["x", "", "y"])


def test_similarity_search_k_float_raises(vectorstore):
    """DF-g: Float k should raise TypeError."""
    with pytest.raises(TypeError, match="k must be an integer"):
        vectorstore.similarity_search("q", k=4.0)


def test_similarity_search_k_bool_raises(vectorstore):
    """DF-g: Bool k should raise TypeError."""
    with pytest.raises(TypeError, match="k must be an integer"):
        vectorstore.similarity_search("q", k=True)


def test_similarity_search_with_score_k_float_raises(vectorstore):
    """DF-g: Float k in similarity_search_with_score."""
    with pytest.raises(TypeError, match="k must be an integer"):
        vectorstore.similarity_search_with_score("q", k=4.0)


def test_similarity_search_by_vector_k_bool_raises(vectorstore):
    """DF-g: Bool k in similarity_search_by_vector."""
    with pytest.raises(TypeError, match="k must be an integer"):
        vectorstore.similarity_search_by_vector([0.1, 0.2, 0.3], k=True)


def test_adbc_available_rejects_whitespace_only_strings(mock_session, fake_embedding):
    """DF-e: Whitespace-only credentials should not pass _adbc_available."""
    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        adbc_driver_path=" ",
        adbc_endpoint="localhost",
        access_key="ak",
        secret_key="sk",
    )
    assert store._adbc_available() is False


def test_adbc_available_rejects_whitespace_endpoint(mock_session, fake_embedding):
    """DF-e: Whitespace-only endpoint should not pass _adbc_available."""
    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        adbc_driver_path="/path/to/driver.so",
        adbc_endpoint="  ",
        access_key="ak",
        secret_key="sk",
    )
    assert store._adbc_available() is False


# --- AC3: ADBC SQL type whitelist ---


def test_predicate_to_sql_where_rejects_unsupported_literal_type():
    """DF-9: Passing a list as an equality literal raises TypeError (use .isin() instead)."""
    from langchain_vastdb._ibis_sql import predicate_to_sql_where
    with pytest.raises(TypeError, match="Unsupported ibis resolver node type"):
        predicate_to_sql_where(_["id"] == [1, 2, 3])


def test_predicate_to_sql_where_rejects_non_finite_float():
    """Review-P4: NaN / Inf must not be spliced into SQL literals."""
    from langchain_vastdb._ibis_sql import predicate_to_sql_where
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="Non-finite"):
            predicate_to_sql_where(_["id"] > bad)


def test_predicate_to_sql_where_rejects_non_deferred_expr():
    """P1: passing a concrete ibis expression raises TypeError with a helpful message."""
    import ibis

    from langchain_vastdb._ibis_sql import predicate_to_sql_where
    table = ibis.table({"col": "string"}, name="t")
    with pytest.raises(TypeError, match="deferred ibis expression"):
        predicate_to_sql_where(table.col == "x")


def test_predicate_to_sql_where_isin_empty_list():
    """P2: isin([]) generates 1=0 (always false) rather than invalid IN ()."""
    from langchain_vastdb._ibis_sql import predicate_to_sql_where
    sql = predicate_to_sql_where(_["col"].isin([]))
    assert sql == "1=0"


def test_predicate_to_sql_where_notin_empty_list():
    """P2: notin([]) generates 1=1 (always true) rather than invalid NOT IN ()."""
    from langchain_vastdb._ibis_sql import predicate_to_sql_where
    sql = predicate_to_sql_where(_["col"].notin([]))
    assert sql == "1=1"


@pytest.mark.parametrize(
    ("predicate", "expected"),
    [
        (_["col"].isin(["a", "b"]), '("col" = \'a\' OR "col" = \'b\')'),
        (_["col"].notin(["a", "b"]), '("col" != \'a\' AND "col" != \'b\')'),
        (_["col"].isin(["it's"]), '("col" = \'it\'\'s\')'),
    ],
)
def test_predicate_membership_uses_escaped_comparisons(predicate, expected):
    from langchain_vastdb._ibis_sql import predicate_to_sql_where

    sql = predicate_to_sql_where(predicate)
    assert sql == expected
    assert " IN (" not in sql


def test_adbc_distance_expr_rejects_non_finite_vector(
    mock_session, fake_embedding, mock_transaction
):
    """P3: _adbc_distance_expr raises ValueError for non-finite query vectors."""
    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        distance_metric="l2sq",
    )
    store._table_metadata = MagicMock()
    store._table_metadata._vector_index = None
    with pytest.raises(ValueError, match="non-finite"):
        store._adbc_distance_expr('"embedding"', [float("nan"), 0.1], 2)


# --- AC3: quoted column identifiers in ADBC SQL ---


def test_adbc_column_identifiers_are_quoted_in_sql(
    mock_session, fake_embedding, mock_transaction
):
    """AC3: id/text/metadata/vector columns must be `"`-quoted in SELECT to
    survive SQL keyword collisions and odd characters."""
    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        id_column="select",       # SQL reserved word
        text_column="from",       # SQL reserved word
        metadata_column="where",  # SQL reserved word
        vector_column="order",    # SQL reserved word
        adbc_driver_path="/path/to/driver.so",
        adbc_endpoint="localhost:8080",
        access_key="ak",
        secret_key="sk",
        distance_metric="l2sq",
    )
    store._table_metadata = MagicMock()
    store._table_metadata._vector_index = None
    mock_transaction.table_from_metadata.return_value = MagicMock()

    mock_dbapi = MagicMock()
    cm = mock_dbapi.connect.return_value.__enter__.return_value
    mock_cursor = cm.cursor.return_value.__enter__.return_value
    mock_cursor.fetch_arrow_table.return_value.to_pylist.return_value = []

    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=mock_dbapi):
        store._do_vector_search_adbc(
            mock_transaction, [0.1, 0.2, 0.3], k=4, predicate=_["select"] == "x",
        )

    executed_sql = mock_cursor.execute.call_args[0][0]
    assert '"select"' in executed_sql
    assert '"order"' in executed_sql  # vector column in distance expression
    # Bare keyword (without quotes) must not appear as an identifier — check
    # there are no unquoted occurrences in SELECT/WHERE positions.
    assert " select " not in f" {executed_sql} ".replace('"select"', "")


# --- AC4: warning log emission ---


def test_fallback_warns_on_dimension_mismatch(vectorstore, mock_transaction, caplog):
    """AC4: in-memory fallback emits a WARNING with the count of skipped rows."""
    mock_table = mock_transaction.table_from_metadata.return_value
    mock_stats = MagicMock()
    mock_stats.num_rows = 3
    mock_table.stats = mock_stats
    reader = MagicMock()
    reader.read_all.return_value.to_pylist.return_value = [
        {"id": "a", "embedding": [0.1, 0.2, 0.3]},
        {"id": "b", "embedding": [0.1, 0.2]},   # wrong dim
        {"id": "c", "embedding": None},          # missing
    ]
    mock_table.select.return_value = reader

    with patch(
        "langchain_vastdb.vectorstores._fallback_allowed", return_value=True
    ), caplog.at_level(logging.WARNING, logger="langchain_vastdb.vectorstores"):
        vectorstore._do_vector_search_fallback(
            mock_transaction, [0.0, 0.0, 0.0], k=4, columns=["id"], predicate=None,
        )

    assert any(
        "skipped 2/3 rows" in rec.message and "dim=3" in rec.message
        for rec in caplog.records
    ), caplog.text


def test_adbc_duplicate_ids_preserve_rows_and_warn(adbc_vectorstore, mock_transaction, caplog):
    rows = [
        {"id": "x", "text": "first", "metadata": "{}", "_vastdb_distance": 0.1},
        {"id": "x", "text": "second", "metadata": "{}", "_vastdb_distance": 0.2},
    ]
    mock_dbapi = MagicMock()
    conn = mock_dbapi.connect.return_value.__enter__.return_value
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetch_arrow_table.return_value.to_pylist.return_value = rows
    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=mock_dbapi), (
        caplog.at_level(logging.WARNING, logger="langchain_vastdb.vectorstores")
    ):
        results = adbc_vectorstore._do_vector_search_adbc(
            mock_transaction, [0.1, 0.2, 0.3], k=2, predicate=None
        )
    assert [row["text"] for row, _ in results] == ["first", "second"]
    assert [score for _, score in results] == [0.1, 0.2]
    assert all("_vastdb_distance" not in row for row, _ in results)
    assert "duplicate IDs" in caplog.text


def test_adbc_error_falls_back_only_when_allowed(adbc_vectorstore, mock_transaction, caplog):
    fallback_rows = [({"id": "fallback", "text": "x", "metadata": "{}"}, 0.0)]
    with patch.object(
        adbc_vectorstore, "_open_adbc_connection", side_effect=OSError("offline")
    ), patch("langchain_vastdb.vectorstores._fallback_allowed", return_value=True), patch.object(
        adbc_vectorstore, "_do_vector_search_fallback", return_value=fallback_rows
    ) as fallback, caplog.at_level(logging.WARNING, logger="langchain_vastdb.vectorstores"):
        assert adbc_vectorstore._vector_search([0.1, 0.2, 0.3], k=4) == fallback_rows
    fallback.assert_called_once()
    assert "ADBC vector search failed" in caplog.text


def test_vector_search_does_not_swallow_filter_validation_errors(
    adbc_vectorstore, mock_transaction
):
    """Review-P1: TypeError/ValueError from predicate-to-SQL conversion must propagate
    rather than triggering the in-memory fallback."""
    with patch.object(
        adbc_vectorstore, "_do_vector_search_fallback"
    ) as mock_fallback:
        with pytest.raises(TypeError, match="Unsupported ibis resolver node type"):
            adbc_vectorstore._vector_search(
                [0.1, 0.2, 0.3], k=4, predicate=_["id"] == [1, 2, 3],
            )
    mock_fallback.assert_not_called()


# ---------------------------------------------------------------------------
# TypedColumn (dict-form) tests
# ---------------------------------------------------------------------------


class DictTypedColumnStore(VastDBVectorStore):
    _typed_metadata_columns = {
        "chunk_id": TypedColumn(),
        "agent_id": TypedColumn(),
        "status": TypedColumn(default="completed", include_in_metadata=False),
        "created_at": TypedColumn(
            default_factory=lambda: 9999,
            pa_type=__import__("pyarrow").int64(),
            include_in_metadata=False,
        ),
        "updated_at": TypedColumn(
            default_factory=lambda: 8888,
            pa_type=__import__("pyarrow").int64(),
            include_in_metadata=False,
        ),
    }


@pytest.fixture
def dict_typed_store(mock_session, fake_embedding, mock_transaction):
    store = DictTypedColumnStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        distance_metric="l2sq",
    )
    store._table_metadata = MagicMock()
    store._table_metadata._vector_index = None
    mock_table = MagicMock()
    mock_transaction.table_from_metadata.return_value = mock_table
    return store


def test_dict_typed_columns_with_custom_defaults(dict_typed_store):
    cols = dict_typed_store._build_metadata_columns([{"foo": "bar"}])
    assert cols["chunk_id"] == [""]
    assert cols["agent_id"] == [""]
    assert cols["status"] == ["completed"]
    assert cols["created_at"].to_pylist() == [9999]
    assert cols["updated_at"].to_pylist() == [8888]


def test_dict_typed_columns_with_pa_type_coercion(dict_typed_store):
    import pyarrow as pa

    cols = dict_typed_store._build_metadata_columns([{"created_at": 1000, "updated_at": 2000}])
    assert isinstance(cols["created_at"], pa.Array)
    assert cols["created_at"].type == pa.int64()
    assert cols["created_at"].to_pylist() == [1000]


def test_dict_typed_columns_include_in_metadata_false_not_merged(dict_typed_store):
    row = {
        "id": "1",
        "text": "hello",
        "chunk_id": "",
        "agent_id": "",
        "status": "completed",
        "created_at": 9999,
        "updated_at": 8888,
        "metadata": json.dumps({"foo": "bar"}),
    }
    doc = dict_typed_store._row_to_document(row)
    assert doc.metadata == {"foo": "bar"}
    assert "status" not in doc.metadata
    assert "created_at" not in doc.metadata
    assert "updated_at" not in doc.metadata


def test_dict_typed_columns_include_in_metadata_true_merged(dict_typed_store):
    row = {
        "id": "1",
        "text": "hello",
        "chunk_id": "c1",
        "agent_id": "a1",
        "status": "completed",
        "created_at": 9999,
        "updated_at": 8888,
        "metadata": json.dumps({"extra": "val"}),
    }
    doc = dict_typed_store._row_to_document(row)
    assert doc.metadata["chunk_id"] == "c1"
    assert doc.metadata["agent_id"] == "a1"
    assert doc.metadata["extra"] == "val"
    assert "status" not in doc.metadata
    assert "created_at" not in doc.metadata


def test_dict_typed_columns_select_columns_auto_derived(dict_typed_store):
    cols = dict_typed_store._select_columns()
    assert cols == [
        "id", "text", "chunk_id", "agent_id", "status",
        "created_at", "updated_at", "metadata",
    ]


def test_dict_typed_columns_used_by_insert_vectors(
    mock_session, fake_embedding, mock_transaction,
):
    store = DictTypedColumnStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        distance_metric="l2sq",
    )
    store._table_metadata = MagicMock()
    store._table_metadata._vector_index = None
    store._metadata_loaded = False
    mock_table = MagicMock()
    mock_transaction.table_from_metadata.return_value = mock_table

    store._insert_vectors(
        ["hello"], [[0.1, 0.2, 0.3]],
        [{"chunk_id": "c1", "agent_id": "a1", "model_used": "test"}],
        ["id-1"],
        tx=mock_transaction,
    )
    batch = mock_table.insert.call_args[0][0]
    assert batch.column("chunk_id").to_pylist() == ["c1"]
    assert batch.column("agent_id").to_pylist() == ["a1"]
    assert batch.column("status").to_pylist() == ["completed"]
    stored = json.loads(batch.column("metadata").to_pylist()[0])
    assert stored == {"model_used": "test"}


# --- Fallback gating via VASTDB_ALLOW_FALLBACK ---


def test_vector_search_raises_when_adbc_not_configured_and_fallback_disabled(
    vectorstore, mock_transaction
):
    """Vector search raises RuntimeError when ADBC is not configured and fallback is off."""
    with patch(
        "langchain_vastdb.vectorstores._fallback_allowed", return_value=False
    ):
        with pytest.raises(RuntimeError, match="ADBC is not configured"):
            vectorstore._do_vector_search(
                mock_transaction, [0.1, 0.2, 0.3], k=4,
                columns=["id"], predicate=None,
            )


def test_adbc_error_raises_when_fallback_disabled(adbc_vectorstore):
    with patch.object(
        adbc_vectorstore, "_open_adbc_connection", side_effect=OSError("offline")
    ), patch("langchain_vastdb.vectorstores._fallback_allowed", return_value=False), pytest.raises(
        OSError, match="offline"
    ):
        adbc_vectorstore._vector_search([0.1, 0.2, 0.3], k=4)


def test_adbc_unexpected_error_propagates_even_with_fallback(adbc_vectorstore):
    with patch.object(
        adbc_vectorstore, "_open_adbc_connection", side_effect=RuntimeError("unexpected")
    ), patch("langchain_vastdb.vectorstores._fallback_allowed", return_value=True), pytest.raises(
        RuntimeError, match="unexpected"
    ):
        adbc_vectorstore._vector_search([0.1, 0.2, 0.3], k=4)


def test_fallback_raises_when_table_exceeds_max_rows(
    vectorstore, mock_transaction
):
    """Fallback refuses to run when row count exceeds _FALLBACK_MAX_ROWS."""
    mock_table = mock_transaction.table_from_metadata.return_value
    mock_stats = MagicMock()
    mock_stats.num_rows = 1001
    mock_table.stats = mock_stats

    with patch(
        "langchain_vastdb.vectorstores._fallback_allowed", return_value=True
    ), pytest.raises(RuntimeError, match="table has 1001 rows"):
        vectorstore._do_vector_search_fallback(
            mock_transaction, [0.0, 0.0, 0.0], k=4, columns=["id"], predicate=None,
        )


# ---------------------------------------------------------------------------
# build_with_table tests
# ---------------------------------------------------------------------------


def test_build_with_table_creates_schema_and_table(mock_session, fake_embedding):
    """build_with_table provisions schema and table and returns the store."""
    mock_tx, mock_schema_obj = _make_tx_mock(mock_session, table_exists=False)

    with patch("langchain_vastdb.vectorstores.vastdb.connect", return_value=mock_session):
        store = VastDBVectorStore.build_with_table(
            embedding=fake_embedding,
            endpoint="http://vast:8080",
            access_key="ak",
            secret_key="sk",
            bucket="b",
            schema="s",
            table_name="t",
            vector_dim=64,
        )

    mock_tx.bucket.return_value.create_schema.assert_called_once_with("s", fail_if_exists=False)
    mock_schema_obj.create_table.assert_called_once()
    assert store._session is mock_session


def test_build_with_table_reuses_provided_session(mock_session, fake_embedding):
    """build_with_table skips vastdb.connect when a session is passed."""
    _make_tx_mock(mock_session, table_exists=False)

    with patch("langchain_vastdb.vectorstores.vastdb.connect") as mock_connect:
        store = VastDBVectorStore.build_with_table(
            embedding=fake_embedding,
            bucket="b",
            schema="s",
            table_name="t",
            vector_dim=32,
            session=mock_session,
        )
        mock_connect.assert_not_called()

    assert store._session is mock_session


def test_build_with_table_derives_extra_columns_from_typed_metadata(
    mock_session, fake_embedding
):
    """build_with_table auto-derives extra_columns from _typed_metadata_columns."""
    class TypedStore(VastDBVectorStore):
        _typed_metadata_columns = {
            "category": TypedColumn(pa_type=pa.string()),
            "score": TypedColumn(pa_type=pa.float32()),
        }

    _, mock_schema_obj = _make_tx_mock(mock_session, table_exists=False)

    with patch("langchain_vastdb.vectorstores.vastdb.connect", return_value=mock_session):
        TypedStore.build_with_table(
            embedding=fake_embedding,
            endpoint="http://vast:8080",
            access_key="ak",
            secret_key="sk",
            bucket="b",
            schema="s",
            table_name="t",
            vector_dim=8,
        )

    _, actual_schema = mock_schema_obj.create_table.call_args[0]
    assert actual_schema.get_field_index("category") != -1
    assert actual_schema.field("category").type == pa.string()
    assert actual_schema.get_field_index("score") != -1
    assert actual_schema.field("score").type == pa.float32()


def test_build_with_table_typed_column_without_pa_type_defaults_to_string(
    mock_session, fake_embedding
):
    """TypedColumn with pa_type=None falls back to pa.string() in extra_columns."""
    class UntypedStore(VastDBVectorStore):
        _typed_metadata_columns = {"tag": TypedColumn()}

    _, mock_schema_obj = _make_tx_mock(mock_session, table_exists=False)

    with patch("langchain_vastdb.vectorstores.vastdb.connect", return_value=mock_session):
        UntypedStore.build_with_table(
            embedding=fake_embedding,
            endpoint="http://vast:8080",
            access_key="ak",
            secret_key="sk",
            bucket="b",
            schema="s",
            table_name="t",
            vector_dim=4,
        )

    _, actual_schema = mock_schema_obj.create_table.call_args[0]
    assert actual_schema.get_field_index("tag") != -1
    assert actual_schema.field("tag").type == pa.string()



def test_build_with_table_forwards_custom_column_names(mock_session, fake_embedding):
    """Custom column names are stored on the returned store instance."""
    _make_tx_mock(mock_session, table_exists=False)

    with patch("langchain_vastdb.vectorstores.vastdb.connect", return_value=mock_session):
        store = VastDBVectorStore.build_with_table(
            embedding=fake_embedding,
            endpoint="http://vast:8080",
            access_key="ak",
            secret_key="sk",
            bucket="b",
            schema="s",
            table_name="t",
            vector_dim=16,
            id_column="my_id",
            text_column="my_text",
        )

    assert store._id_column == "my_id"
    assert store._text_column == "my_text"


def test_build_with_table_defaults_bucket_schema_table(mock_session, fake_embedding, monkeypatch):
    """bucket defaults to VASTDB_BUCKET; schema and table_name are auto-generated."""
    monkeypatch.setenv("VASTDB_BUCKET", "env-bucket")
    _make_tx_mock(mock_session, table_exists=False)

    with patch("langchain_vastdb.vectorstores.vastdb.connect", return_value=mock_session):
        store = VastDBVectorStore.build_with_table(
            fake_embedding,
            32,
            endpoint="http://vast:8080",
            access_key="ak",
            secret_key="sk",
        )

    assert store._table_ref.bucket == "env-bucket"
    assert store._table_ref.schema.startswith("vs_")
    assert store._table_ref.table.startswith("vs_")


def test_build_with_table_raises_without_bucket(fake_embedding):
    """build_with_table raises ValueError when bucket is not set."""
    import os
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("VASTDB_BUCKET", None)
        with pytest.raises(ValueError, match="bucket"):
            VastDBVectorStore.build_with_table(fake_embedding, 32)


# ---------------------------------------------------------------------------
# build_table tests
# ---------------------------------------------------------------------------


def _make_tx_mock(mock_session, *, table_exists: bool = False, arrow_schema=None):
    """Return a (mock_tx, mock_schema_obj) pair wired into mock_session.

    When table_exists=False, schema.create_table() succeeds (no side effect).
    When table_exists=True, schema.create_table() raises TableExists and
    schema.table() returns a mock with arrow_schema set for the compat check.
    """
    import vastdb.errors

    mock_tx = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_tx
    mock_cm.__exit__.return_value = False
    mock_session.transaction.return_value = mock_cm

    mock_schema_obj = mock_tx.bucket.return_value.schema.return_value
    if table_exists:
        mock_schema_obj.create_table.side_effect = vastdb.errors.TableExists("b", "s", "t")
        mock_table = MagicMock()
        mock_table.arrow_schema = arrow_schema
        mock_schema_obj.table.return_value = mock_table

    return mock_tx, mock_schema_obj


def test_build_table_creates_schema_and_table(mock_session, fake_embedding):
    """build_table provisions schema and table when the table does not yet exist."""
    mock_tx, mock_schema_obj = _make_tx_mock(mock_session, table_exists=False)

    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        vector_dim=64,
    )
    store.build_table()

    mock_tx.bucket.return_value.create_schema.assert_called_once_with("s", fail_if_exists=False)
    mock_schema_obj.create_table.assert_called_once()
    table_name_arg, schema_arg = mock_schema_obj.create_table.call_args[0]
    assert table_name_arg == "t"
    assert schema_arg.field("id").type == pa.string()
    assert schema_arg.field("embedding").type == pa.list_(
        pa.field("item", pa.float32(), nullable=False), 64
    )


def test_build_table_exist_ok_compatible_schema(mock_session, fake_embedding):
    """build_table with exist_ok=True passes when existing schema matches."""
    compatible_schema = pa.schema([
        pa.field("id", pa.string()),
        pa.field("text", pa.string()),
        pa.field("embedding", pa.list_(pa.field("item", pa.float32(), nullable=False), 32)),
        pa.field("metadata", pa.string()),
    ])
    _make_tx_mock(mock_session, table_exists=True, arrow_schema=compatible_schema)

    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        vector_dim=32,
    )
    store.build_table(exist_ok=True)  # must not raise


def test_build_table_exist_ok_incompatible_schema_raises(mock_session, fake_embedding):
    """build_table with exist_ok=True raises ValueError on schema mismatch."""
    incompatible_schema = pa.schema([
        pa.field("id", pa.string()),
        pa.field("text", pa.string()),
        pa.field("embedding", pa.list_(pa.field("item", pa.float32(), nullable=False), 64)),
        # metadata column missing
    ])
    _make_tx_mock(mock_session, table_exists=True, arrow_schema=incompatible_schema)

    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        vector_dim=32,
    )
    with pytest.raises(ValueError, match="incompatible"):
        store.build_table(exist_ok=True)


def test_build_table_reraises_table_exists_when_not_ok(mock_session, fake_embedding):
    """build_table with exist_ok=False (default) raises TableExists when table is present."""
    import vastdb.errors

    _make_tx_mock(mock_session, table_exists=True)

    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        vector_dim=32,
    )
    with pytest.raises(vastdb.errors.TableExists):
        store.build_table()


def test_build_table_raises_without_vector_dim(mock_session, fake_embedding):
    """build_table raises ValueError when vector_dim was not set."""
    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
    )
    with pytest.raises(ValueError, match="vector_dim"):
        store.build_table()


def test_build_table_derives_extra_columns_from_typed_metadata(mock_session, fake_embedding):
    """build_table auto-derives extra_columns from _typed_metadata_columns."""
    class TypedStore(VastDBVectorStore):
        _typed_metadata_columns = {
            "tag": TypedColumn(pa_type=pa.string()),
            "score": TypedColumn(pa_type=pa.float32()),
        }

    mock_tx, mock_schema_obj = _make_tx_mock(mock_session, table_exists=False)

    store = TypedStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        vector_dim=8,
    )
    store.build_table()

    _, schema_arg = mock_schema_obj.create_table.call_args[0]
    assert schema_arg.get_field_index("tag") != -1
    assert schema_arg.field("tag").type == pa.string()
    assert schema_arg.get_field_index("score") != -1
    assert schema_arg.field("score").type == pa.float32()


# ---------------------------------------------------------------------------
# _check_schema_compatible tests
# ---------------------------------------------------------------------------

from langchain_vastdb.vectorstores import _check_schema_compatible  # noqa: E402


def test_check_schema_compatible_identical_schemas_pass():
    schema = pa.schema([pa.field("a", pa.string()), pa.field("b", pa.int32())])
    _check_schema_compatible(schema, schema)  # must not raise


def test_check_schema_compatible_extra_actual_columns_allowed():
    expected = pa.schema([pa.field("a", pa.string())])
    actual = pa.schema([pa.field("a", pa.string()), pa.field("extra", pa.int64())])
    _check_schema_compatible(expected, actual)  # extra column is fine


def test_check_schema_compatible_missing_column_raises():
    expected = pa.schema([pa.field("a", pa.string()), pa.field("b", pa.int32())])
    actual = pa.schema([pa.field("a", pa.string())])
    with pytest.raises(ValueError, match="missing column 'b'"):
        _check_schema_compatible(expected, actual)


def test_check_schema_compatible_wrong_type_raises():
    expected = pa.schema([pa.field("a", pa.string())])
    actual = pa.schema([pa.field("a", pa.int32())])
    with pytest.raises(ValueError, match="column 'a'"):
        _check_schema_compatible(expected, actual)


def test_check_schema_compatible_multiple_mismatches_all_reported():
    expected = pa.schema([
        pa.field("a", pa.string()),
        pa.field("b", pa.float32()),
        pa.field("c", pa.int64()),
    ])
    actual = pa.schema([
        pa.field("a", pa.int32()),   # wrong type
        pa.field("b", pa.float32()), # ok
        # "c" missing
    ])
    with pytest.raises(ValueError) as exc_info:
        _check_schema_compatible(expected, actual)
    msg = str(exc_info.value)
    assert "column 'a'" in msg
    assert "missing column 'c'" in msg
    assert "column 'b'" not in msg  # b is fine — shouldn't appear


def test_check_schema_compatible_vector_column_dim_mismatch_raises():
    """Fixed-size list type with different vector dim must be caught."""
    expected = pa.schema([
        pa.field("v", pa.list_(pa.field("item", pa.float32(), nullable=False), 128)),
    ])
    actual = pa.schema([
        pa.field("v", pa.list_(pa.field("item", pa.float32(), nullable=False), 64)),
    ])
    with pytest.raises(ValueError, match="column 'v'"):
        _check_schema_compatible(expected, actual)


def test_check_schema_compatible_empty_expected_always_passes():
    _check_schema_compatible(pa.schema([]), pa.schema([pa.field("x", pa.int8())]))


# ---------------------------------------------------------------------------
# Item D: upsert opt-in
# ---------------------------------------------------------------------------


def test_add_texts_upsert_false_skips_delete(vectorstore, mock_transaction):
    """When upsert=False the pre-delete step is skipped."""
    with patch.object(vectorstore, "_delete_by_ids") as mock_del:
        vectorstore.add_texts(["hello"], ids=["id-1"], upsert=False)
    mock_del.assert_not_called()


def test_add_texts_upsert_true_calls_delete(vectorstore, mock_transaction):
    """Default upsert=True still deletes before insert."""
    with patch.object(vectorstore, "_delete_by_ids") as mock_del:
        vectorstore.add_texts(["hello"], ids=["id-1"])
    mock_del.assert_called_once()


# ---------------------------------------------------------------------------
# Item B: _build_adbc_where_clause hook
# ---------------------------------------------------------------------------


def test_build_adbc_where_clause_override(
    mock_session, fake_embedding, mock_transaction
):
    """Subclass can override _build_adbc_where_clause to return custom SQL."""

    class CustomWhereStore(VastDBVectorStore):
        def _build_adbc_where_clause(self, predicate, **kwargs):
            return "category IN ('a','b')"

    store = CustomWhereStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        adbc_driver_path="/path/to/driver.so",
        adbc_endpoint="localhost:8080",
        access_key="ak",
        secret_key="sk",
        distance_metric="l2sq",
    )
    store._table_metadata = MagicMock()
    store._table_metadata._vector_index = None
    mock_transaction.table_from_metadata.return_value = MagicMock()

    mock_dbapi = MagicMock()
    cm = mock_dbapi.connect.return_value.__enter__.return_value
    mock_cursor = cm.cursor.return_value.__enter__.return_value
    mock_cursor.fetch_arrow_table.return_value.to_pylist.return_value = []

    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=mock_dbapi):
        store._do_vector_search_adbc(
            mock_transaction, [0.1, 0.2, 0.3], k=4, predicate=None
        )

    executed_sql = mock_cursor.execute.call_args[0][0]
    assert "category IN ('a','b')" in executed_sql


# ---------------------------------------------------------------------------
# Item A: _open_adbc_connection hook + credentials_provider
# ---------------------------------------------------------------------------


def test_open_adbc_connection_override(
    mock_session, fake_embedding, mock_transaction
):
    """Subclass can override _open_adbc_connection to return custom conn."""
    mock_conn = MagicMock()
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetch_arrow_table.return_value.to_pylist.return_value = [
        {"id": "doc1", "text": "hello", "metadata": "{}", "_vastdb_distance": 0.5}
    ]

    class CustomConnStore(VastDBVectorStore):
        @__import__("contextlib").contextmanager
        def _open_adbc_connection(self):
            yield mock_conn

    store = CustomConnStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        adbc_driver_path="/path/to/driver.so",
        adbc_endpoint="localhost:8080",
        access_key="ak",
        secret_key="sk",
        distance_metric="l2sq",
    )
    store._table_metadata = MagicMock()
    store._table_metadata._vector_index = None
    mock_transaction.table_from_metadata.return_value = MagicMock()

    store._do_vector_search_adbc(
        mock_transaction, [0.1, 0.2, 0.3], k=4, predicate=None
    )

    mock_cursor.execute.assert_called_once()


def test_adbc_conn_kwargs_passed_to_connect(
    mock_session, fake_embedding, mock_transaction
):
    """adbc_conn_kwargs are forwarded to adbc_dbapi.connect()."""
    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        adbc_driver_path="/path/to/driver.so",
        adbc_endpoint="localhost:8080",
        access_key="ak",
        secret_key="sk",
        distance_metric="l2sq",
        adbc_conn_kwargs={"timeout": 30},
    )
    store._table_metadata = MagicMock()
    store._table_metadata._vector_index = None
    mock_transaction.table_from_metadata.return_value = MagicMock()

    mock_dbapi = MagicMock()
    cm = mock_dbapi.connect.return_value.__enter__.return_value
    mock_cursor = cm.cursor.return_value.__enter__.return_value
    mock_cursor.fetch_arrow_table.return_value.to_pylist.return_value = []

    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=mock_dbapi):
        store._do_vector_search_adbc(
            mock_transaction, [0.1, 0.2, 0.3], k=4, predicate=None
        )

    assert mock_dbapi.connect.call_args[1]["conn_kwargs"] == {"timeout": 30}


# ---------------------------------------------------------------------------
# Item C: SQL distance-metric plumbing
# ---------------------------------------------------------------------------


def test_adbc_cosine_metric_uses_cosine_distance_sql(
    mock_session, fake_embedding, mock_transaction
):
    """distance_metric='cosine' produces cosine_distance() in the SQL."""
    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        adbc_driver_path="/path/to/driver.so",
        adbc_endpoint="localhost:8080",
        access_key="ak",
        secret_key="sk",
        distance_metric="cosine",
    )
    store._table_metadata = MagicMock()
    store._table_metadata._vector_index = None
    mock_transaction.table_from_metadata.return_value = MagicMock()

    mock_dbapi = MagicMock()
    cm = mock_dbapi.connect.return_value.__enter__.return_value
    mock_cursor = cm.cursor.return_value.__enter__.return_value
    mock_cursor.fetch_arrow_table.return_value.to_pylist.return_value = []

    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=mock_dbapi):
        store._do_vector_search_adbc(
            mock_transaction, [0.1, 0.2, 0.3], k=4, predicate=None
        )

    executed_sql = mock_cursor.execute.call_args[0][0]
    assert "cosine_distance(" in executed_sql
    assert "array_distance(" not in executed_sql


def test_adbc_ip_metric_uses_inner_product_sql(
    mock_session, fake_embedding, mock_transaction
):
    """distance_metric='ip' produces inner_product() in the SQL."""
    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        adbc_driver_path="/path/to/driver.so",
        adbc_endpoint="localhost:8080",
        access_key="ak",
        secret_key="sk",
        distance_metric="ip",
    )
    store._table_metadata = MagicMock()
    store._table_metadata._vector_index = None
    mock_transaction.table_from_metadata.return_value = MagicMock()

    mock_dbapi = MagicMock()
    cm = mock_dbapi.connect.return_value.__enter__.return_value
    mock_cursor = cm.cursor.return_value.__enter__.return_value
    mock_cursor.fetch_arrow_table.return_value.to_pylist.return_value = []

    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=mock_dbapi):
        store._do_vector_search_adbc(
            mock_transaction, [0.1, 0.2, 0.3], k=4, predicate=None
        )

    executed_sql = mock_cursor.execute.call_args[0][0]
    assert "inner_product(" in executed_sql
    assert "array_distance(" not in executed_sql


def test_adbc_l2sq_metric_uses_array_distance_sql(
    mock_session, fake_embedding, mock_transaction
):
    """distance_metric='l2sq' produces array_distance() (default) in the SQL."""
    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b",
        schema="s",
        table_name="t",
        adbc_driver_path="/path/to/driver.so",
        adbc_endpoint="localhost:8080",
        access_key="ak",
        secret_key="sk",
        distance_metric="l2sq",
    )
    store._table_metadata = MagicMock()
    store._table_metadata._vector_index = None
    mock_transaction.table_from_metadata.return_value = MagicMock()

    mock_dbapi = MagicMock()
    cm = mock_dbapi.connect.return_value.__enter__.return_value
    mock_cursor = cm.cursor.return_value.__enter__.return_value
    mock_cursor.fetch_arrow_table.return_value.to_pylist.return_value = []

    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=mock_dbapi):
        store._do_vector_search_adbc(
            mock_transaction, [0.1, 0.2, 0.3], k=4, predicate=None
        )

    executed_sql = mock_cursor.execute.call_args[0][0]
    assert "array_distance(" in executed_sql


def test_unknown_distance_metric_raises():
    """ValueError for an unrecognized distance metric string."""
    from langchain_core.embeddings import DeterministicFakeEmbedding

    store = VastDBVectorStore(
        embedding=DeterministicFakeEmbedding(size=3),
        session=MagicMock(),
        bucket="b",
        schema="s",
        table_name="t",
        distance_metric="hamming",
    )
    store._table_metadata = MagicMock()
    store._table_metadata._vector_index = None

    with pytest.raises(ValueError, match="Unknown distance metric"):
        store._adbc_distance_expr('"embedding"', [0.1, 0.2, 0.3], 3)


def test_fallback_cosine_distance_computation(vectorstore, mock_transaction):
    """Fallback uses cosine distance when metric is 'cosine'."""
    vectorstore._distance_metric = "cosine"
    score_fn = VastDBVectorStore._fallback_score_fn("cosine")
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert abs(score_fn(a, b) - 1.0) < 1e-9
    assert abs(score_fn(a, a) - 0.0) < 1e-9


def test_fallback_ip_distance_computation():
    """Fallback uses negative inner product when metric is 'ip'."""
    score_fn = VastDBVectorStore._fallback_score_fn("ip")
    a = [1.0, 2.0, 3.0]
    b = [4.0, 5.0, 6.0]
    assert abs(score_fn(a, b) - (-32.0)) < 1e-9


# ---------------------------------------------------------------------------
# Issue 3 remainder: drop_table / table_exists
# ---------------------------------------------------------------------------


def test_table_exists_returns_true_when_table_reachable(mock_session, fake_embedding):
    """table_exists() returns True when bucket/schema/table all resolve."""
    mock_tx = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = mock_tx
    cm.__exit__.return_value = False
    mock_session.transaction.return_value = cm

    mock_tx.bucket.return_value.schema.return_value.table.return_value = MagicMock()

    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b", schema="s", table_name="t",
    )
    assert store.table_exists() is True


def test_table_exists_returns_false_when_table_missing(mock_session, fake_embedding):
    """table_exists() returns False when schema.table(fail_if_missing=False) returns None."""
    mock_tx = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = mock_tx
    cm.__exit__.return_value = False
    mock_session.transaction.return_value = cm

    mock_tx.bucket.return_value.schema.return_value.table.return_value = None

    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b", schema="s", table_name="t",
    )
    assert store.table_exists() is False


def test_table_exists_returns_false_when_bucket_missing(mock_session, fake_embedding):
    """table_exists() returns False when bucket is missing."""
    import vastdb.errors

    mock_tx = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = mock_tx
    cm.__exit__.return_value = False
    mock_session.transaction.return_value = cm

    mock_tx.bucket.side_effect = vastdb.errors.MissingBucket("b")

    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b", schema="s", table_name="t",
    )
    assert store.table_exists() is False


def test_drop_table_calls_drop_on_table(mock_session, fake_embedding):
    """drop_table() resolves the table and invokes .drop()."""
    mock_tx = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = mock_tx
    cm.__exit__.return_value = False
    mock_session.transaction.return_value = cm

    mock_table = MagicMock()
    mock_tx.bucket.return_value.schema.return_value.table.return_value = mock_table

    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b", schema="s", table_name="t",
    )
    store.drop_table()
    mock_table.drop.assert_called_once()


def test_drop_table_missing_ok_swallows_missing_table(mock_session, fake_embedding):
    """drop_table(missing_ok=True) swallows MissingTable / MissingSchema / MissingBucket."""
    import vastdb.errors

    mock_tx = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = mock_tx
    cm.__exit__.return_value = False
    mock_session.transaction.return_value = cm

    mock_tx.bucket.return_value.schema.return_value.table.side_effect = (
        vastdb.errors.MissingTable("b", "s", "t")
    )

    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b", schema="s", table_name="t",
    )
    store.drop_table(missing_ok=True)  # must not raise


def test_drop_table_propagates_missing_when_not_ok(mock_session, fake_embedding):
    """drop_table(missing_ok=False) re-raises MissingTable."""
    import vastdb.errors

    mock_tx = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = mock_tx
    cm.__exit__.return_value = False
    mock_session.transaction.return_value = cm

    mock_tx.bucket.return_value.schema.return_value.table.side_effect = (
        vastdb.errors.MissingTable("b", "s", "t")
    )

    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b", schema="s", table_name="t",
    )
    with pytest.raises(vastdb.errors.MissingTable):
        store.drop_table()


def test_drop_table_invalidates_metadata_cache(mock_session, fake_embedding):
    """drop_table clears the cached table metadata so subsequent ops reload."""
    mock_tx = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = mock_tx
    cm.__exit__.return_value = False
    mock_session.transaction.return_value = cm
    mock_tx.bucket.return_value.schema.return_value.table.return_value = MagicMock()

    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b", schema="s", table_name="t",
    )
    store._metadata_loaded = True
    store.drop_table()
    assert store._metadata_loaded is False


# ---------------------------------------------------------------------------
# Issue 5: count()
# ---------------------------------------------------------------------------


def test_count_without_predicate_uses_table_stats(vectorstore):
    """count() with no predicate returns table.stats.num_rows directly."""
    tx = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = tx
    cm.__exit__.return_value = False
    vectorstore._session.transaction.return_value = cm

    table = MagicMock()
    table.stats.num_rows = 42
    tx.table_from_metadata.return_value = table

    assert vectorstore.count() == 42
    table.select.assert_not_called()


def test_count_with_predicate_runs_select(vectorstore):
    """count(predicate) selects id with predicate and returns the read_all().num_rows."""
    tx = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = tx
    cm.__exit__.return_value = False
    vectorstore._session.transaction.return_value = cm

    table = MagicMock()
    tx.table_from_metadata.return_value = table
    rb = pa.RecordBatch.from_pydict({"id": ["a", "b"]})
    table.select.return_value.read_all.return_value = rb

    assert vectorstore.count(_["id"].isin(["a", "b"])) == 2
    assert table.select.call_args[1]["columns"] == ["id"]


def test_count_reload_stats_when_stats_none(vectorstore):
    """count() calls reload_stats() when table.stats starts as None."""
    tx = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = tx
    cm.__exit__.return_value = False
    vectorstore._session.transaction.return_value = cm

    table = MagicMock()

    state = {"stats": None}
    type(table).stats = property(
        lambda _self: MagicMock(num_rows=17) if state["stats"] is not None else None
    )

    def _reload():
        state["stats"] = MagicMock(num_rows=17)
    table.reload_stats.side_effect = _reload

    tx.table_from_metadata.return_value = table

    assert vectorstore.count() == 17
    table.reload_stats.assert_called_once()


# ---------------------------------------------------------------------------
# Issue 2 remainder: per-call ADBC connection overrides
# ---------------------------------------------------------------------------


def test_adbc_db_kwargs_overrides_merged_per_call(
    mock_session, fake_embedding, mock_transaction
):
    """Per-call adbc_db_kwargs_overrides shadow instance-level credentials."""
    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b", schema="s", table_name="t",
        adbc_driver_path="/path/to/driver.so",
        adbc_endpoint="localhost:8080",
        access_key="ak",
        secret_key="sk",
        distance_metric="l2sq",
    )
    store._table_metadata = MagicMock()
    store._table_metadata._vector_index = None
    mock_transaction.table_from_metadata.return_value = MagicMock()

    mock_dbapi = MagicMock()
    cm_conn = mock_dbapi.connect.return_value.__enter__.return_value
    mock_cursor = cm_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetch_arrow_table.return_value.to_pylist.return_value = []

    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=mock_dbapi):
        store.similarity_search_by_vector(
            [0.1, 0.2, 0.3],
            k=4,
            adbc_db_kwargs_overrides={"vast.db.access_key": "user-ak"},
        )

    called_db_kwargs = mock_dbapi.connect.call_args[1]["db_kwargs"]
    assert called_db_kwargs["vast.db.access_key"] == "user-ak"
    # Other values fall through from the instance.
    assert called_db_kwargs["vast.db.secret_key"] == "sk"
    assert called_db_kwargs["vast.db.endpoint"] == "localhost:8080"


def test_adbc_conn_kwargs_overrides_merged_per_call(
    mock_session, fake_embedding, mock_transaction
):
    """Per-call adbc_conn_kwargs_overrides merge over instance adbc_conn_kwargs."""
    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b", schema="s", table_name="t",
        adbc_driver_path="/path/to/driver.so",
        adbc_endpoint="localhost:8080",
        access_key="ak",
        secret_key="sk",
        distance_metric="l2sq",
        adbc_conn_kwargs={"timeout": 30, "tls": True},
    )
    store._table_metadata = MagicMock()
    store._table_metadata._vector_index = None
    mock_transaction.table_from_metadata.return_value = MagicMock()

    mock_dbapi = MagicMock()
    cm_conn = mock_dbapi.connect.return_value.__enter__.return_value
    mock_cursor = cm_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetch_arrow_table.return_value.to_pylist.return_value = []

    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=mock_dbapi):
        store.similarity_search_by_vector(
            [0.1, 0.2, 0.3],
            k=4,
            adbc_conn_kwargs_overrides={"timeout": 5},
        )

    conn_kwargs = mock_dbapi.connect.call_args[1]["conn_kwargs"]
    assert conn_kwargs == {"timeout": 5, "tls": True}


def test_unknown_search_kwargs_are_tolerated(
    mock_session, fake_embedding, mock_transaction
):
    """Unknown kwargs on the public search API don't crash; they pass through quietly."""
    store = VastDBVectorStore(
        embedding=fake_embedding,
        session=mock_session,
        bucket="b", schema="s", table_name="t",
        adbc_driver_path="/path/to/driver.so",
        adbc_endpoint="localhost:8080",
        access_key="ak",
        secret_key="sk",
        distance_metric="l2sq",
    )
    store._table_metadata = MagicMock()
    store._table_metadata._vector_index = None
    mock_transaction.table_from_metadata.return_value = MagicMock()

    mock_dbapi = MagicMock()
    cm_conn = mock_dbapi.connect.return_value.__enter__.return_value
    mock_cursor = cm_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetch_arrow_table.return_value.to_pylist.return_value = []

    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=mock_dbapi):
        store.similarity_search_by_vector(
            [0.1, 0.2, 0.3], k=2, some_unknown_kwarg="ignored",
        )
    mock_cursor.execute.assert_called_once()


# ---------------------------------------------------------------------------
