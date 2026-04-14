"""Unit tests for VastDBVectorStore using mocked VastDB SDK calls."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding

from langchain_vastdb import VastDBVectorStore

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
    )
    # Replace _table_metadata with a MagicMock so load() calls are trackable
    # without needing a real VastDB cluster
    store._table_metadata = MagicMock()
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
            endpoint="http://vast:8080", access_key="ak", secret_key="sk"
        )
    assert store._session is mock_session


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


def test_credentials_not_stored_as_instance_attributes(mock_session, fake_embedding):
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


def test_similarity_search_passes_filter_as_ibis_predicate(vectorstore, mock_transaction):
    with patch.object(vectorstore, "_do_vector_search", return_value=[]) as mock_search:
        vectorstore.similarity_search("hello", filter={"category": "news"})

    args = mock_search.call_args.args  # (tx, query_vector, k, columns, predicate, filter_dict)
    predicate = args[4]
    filter_dict = args[5]
    assert predicate is not None
    assert filter_dict == {"category": "news"}


def test_row_to_document_deserializes_json_metadata(vectorstore):
    row = {"text": "hello world", "metadata": '{"source": "test", "page": 1}'}
    doc = vectorstore._row_to_document(row)
    assert doc.page_content == "hello world"
    assert doc.metadata == {"source": "test", "page": 1}


def test_build_predicate_returns_none_for_none_input(vectorstore):
    assert vectorstore._build_predicate(None) is None


def test_build_predicate_returns_none_for_empty_dict(vectorstore):
    assert vectorstore._build_predicate({}) is None


def test_build_predicate_returns_expr_for_single_key(vectorstore):
    result = vectorstore._build_predicate({"key": "val"})
    assert result is not None


def test_build_predicate_returns_combined_expr_for_multiple_keys(vectorstore):
    result = vectorstore._build_predicate({"a": 1, "b": 2})
    assert result is not None


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
