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
            endpoint="http://vast:8080", access="ak", secret="sk", ssl_verify=True
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
    )
    store._table_metadata = MagicMock()
    mock_table = MagicMock()
    mock_transaction.table_from_metadata.return_value = mock_table
    return store


def test_adbc_filter_invalid_column_raises(adbc_vectorstore, mock_transaction):
    """P1: unknown column name in filter raises ValueError before any DB call."""
    with pytest.raises(ValueError, match="not an allowed column"):
        adbc_vectorstore._do_vector_search_adbc(
            mock_transaction,
            [0.1, 0.2, 0.3],
            k=4,
            filter_dict={"'; DROP TABLE x; --": "val"},
        )


def test_adbc_filter_none_value_raises(adbc_vectorstore, mock_transaction):
    """P7: None filter value raises ValueError before any DB call."""
    with pytest.raises(ValueError, match="is None"):
        adbc_vectorstore._do_vector_search_adbc(
            mock_transaction,
            [0.1, 0.2, 0.3],
            k=4,
            filter_dict={"id": None},
        )


def test_adbc_filter_string_value_with_single_quote_is_escaped(
    adbc_vectorstore, mock_transaction
):
    """P1: single quotes in string filter values are escaped (SQL injection prevention)."""
    mock_dbapi = MagicMock()
    _cm = mock_dbapi.connect.return_value.__enter__.return_value
    mock_cursor = _cm.cursor.return_value.__enter__.return_value
    mock_cursor.fetch_arrow_table.return_value.to_pydict.return_value = {
        "id": [],
        "distance": [],
    }

    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=mock_dbapi):
        adbc_vectorstore._do_vector_search_adbc(
            mock_transaction,
            [0.1, 0.2, 0.3],
            k=4,
            filter_dict={"id": "it's here"},
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
    )
    store._table_metadata = MagicMock()
    mock_transaction.table_from_metadata.return_value = MagicMock()

    mock_dbapi = MagicMock()
    _cm2 = mock_dbapi.connect.return_value.__enter__.return_value
    mock_cursor = _cm2.cursor.return_value.__enter__.return_value
    mock_cursor.fetch_arrow_table.return_value.to_pydict.return_value = {
        "id": [],
        "distance": [],
    }

    with patch("langchain_vastdb.vectorstores._get_adbc_dbapi", return_value=mock_dbapi):
        store._do_vector_search_adbc(mock_transaction, [0.1, 0.2, 0.3], k=4, filter_dict=None)

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


def test_retriever_with_filter_kwarg(vectorstore):
    """AC #3: as_retriever(search_kwargs={"filter": {...}}) passes filter."""
    retriever = vectorstore.as_retriever(
        search_kwargs={"filter": {"category": "news"}}
    )
    with patch.object(vectorstore, "similarity_search", return_value=[]) as mock_ss:
        retriever.invoke("query")

    mock_ss.assert_called_once()
    call_kwargs = mock_ss.call_args
    assert call_kwargs.kwargs.get("filter") == {"category": "news"} or \
        call_kwargs[1].get("filter") == {"category": "news"}


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


def test_adbc_filter_rejects_unsupported_type(adbc_vectorstore, mock_transaction):
    """DF-9: Non-scalar filter values should raise TypeError."""
    with pytest.raises(TypeError, match="unsupported type"):
        adbc_vectorstore._do_vector_search_adbc(
            mock_transaction,
            [0.1, 0.2, 0.3],
            k=4,
            filter_dict={"id": [1, 2, 3]},
        )

