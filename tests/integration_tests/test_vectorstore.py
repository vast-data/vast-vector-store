"""Integration tests for VastDBVectorStore using LangChain's standard test suite."""

import os
import uuid
import warnings
from collections.abc import Generator
from typing import Any

import pyarrow as pa
import pytest
import vastdb
from ibis import _
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.vectorstores import VectorStore
from langchain_tests.integration_tests import (
    RetrieversIntegrationTests,
    VectorStoreIntegrationTests,
)
from langchain_tests.integration_tests.vectorstores import EMBEDDING_SIZE
from vastdb.config import BackoffConfig

from langchain_vastdb import VastDBVectorStore

# ---------------------------------------------------------------------------
# Environment variable handling
# ---------------------------------------------------------------------------

REQUIRED_ENV = [
    "AWS_S3_ENDPOINT_URL",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "VASTDB_BUCKET",
]

_missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
pytestmark = pytest.mark.skipif(
    bool(_missing),
    reason=f"Missing required VAST env vars: {_missing}",
)

# Sourced from langchain_tests so a future bump is picked up automatically.
VECTOR_DIM = EMBEDDING_SIZE

_ARROW_SCHEMA = pa.schema([
    pa.field("id", pa.string()),
    pa.field("text", pa.string()),
    pa.field(
        "embedding",
        pa.list_(pa.field("item", pa.float32(), nullable=False), list_size=VECTOR_DIM),
    ),
    pa.field("metadata", pa.string()),
])


# ---------------------------------------------------------------------------
# Shared fixtures (module-scoped session + schema, function-scoped table)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _vastdb_session():
    """Single VAST session shared across all tests in this module."""
    # Note: adbc_driver is NOT passed to vastdb.connect() — the SDK would route
    # it through the HTTPS endpoint (TLS issues). VastDBVectorStore opens its own
    # ADBC connection directly to adbc_endpoint (the QueryEngine IP).
    session = vastdb.connect(
        endpoint=os.environ["AWS_S3_ENDPOINT_URL"],
        access=os.environ["AWS_ACCESS_KEY_ID"],
        secret=os.environ["AWS_SECRET_ACCESS_KEY"],
        timeout=10,
        ssl_verify=False,
        backoff_config=BackoffConfig(max_tries=2, max_time=15.0),
    )
    yield session


@pytest.fixture(scope="module")
def _vastdb_schema(_vastdb_session):
    """Single schema shared across all tests in this module; dropped on teardown."""
    bucket = os.environ["VASTDB_BUCKET"]
    schema = f"lc_vs_it_{uuid.uuid4().hex[:12]}"
    with _vastdb_session.transaction() as tx:
        tx.bucket(bucket).create_schema(schema)
    yield schema
    try:
        with _vastdb_session.transaction() as tx:
            tx.bucket(bucket).schema(schema).drop()
    except Exception:
        pass


def _build_vectorstore(session: Any, schema: str) -> Generator[VectorStore, None, None]:
    """Yield an empty VastDBVectorStore backed by a dedicated, isolated test table.

    Reuses the module-scoped session and schema; only creates/drops the table so
    each test gets a clean slate without the cost of reconnecting or recreating the
    schema on every function.

    Required env vars: AWS_S3_ENDPOINT_URL, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
    VASTDB_BUCKET. Optional: VASTDB_ADBC_DRIVER_PATH + VASTDB_ADBC_ENDPOINT
    enable native ADBC vector search via array_distance() SQL (no vector
    index required). Load env vars via your IDE's run config, `direnv`, or
    `set -a && source .env && set +a`.
    """
    bucket = os.environ["VASTDB_BUCKET"]
    access_key = os.environ["AWS_ACCESS_KEY_ID"]
    secret_key = os.environ["AWS_SECRET_ACCESS_KEY"]
    table_name = f"lc_vs_it_{uuid.uuid4().hex[:12]}"

    adbc_driver_path = os.environ.get("VASTDB_ADBC_DRIVER_PATH")
    adbc_endpoint = os.environ.get("VASTDB_ADBC_ENDPOINT")
    if not adbc_driver_path or not adbc_endpoint:
        warnings.warn(
            "VASTDB_ADBC_DRIVER_PATH / VASTDB_ADBC_ENDPOINT not set; "
            "tests will use the in-memory fallback (VASTDB_ALLOW_FALLBACK=1). "
            "Set ADBC env vars for production-representative test runs.",
            stacklevel=2,
        )
        os.environ.setdefault("VASTDB_ALLOW_FALLBACK", "1")

    with session.transaction() as tx:
        tx.bucket(bucket).schema(schema).create_table(table_name, _ARROW_SCHEMA)

    store = VastDBVectorStore(
        embedding=VectorStoreIntegrationTests.get_embeddings(),
        session=session,
        bucket=bucket,
        schema=schema,
        table_name=table_name,
        adbc_driver_path=adbc_driver_path,
        adbc_endpoint=adbc_endpoint,
        access_key=access_key,
        secret_key=secret_key,
        distance_metric="l2sq",
    )
    try:
        yield store
    finally:
        try:
            with session.transaction() as tx:
                tx.bucket(bucket).schema(schema).table(table_name).drop()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Standard test class
# ---------------------------------------------------------------------------


class TestVastDBVectorStoreSync(VectorStoreIntegrationTests):
    """LangChain standard integration test suite for VastDBVectorStore (sync only).

    Inherits all standard VectorStore integration tests from LangChain.
    Async tests are disabled because the VastDB SDK is sync-only.
    """

    @property
    def has_async(self) -> bool:
        """VastDB SDK is sync-only; async tests are not applicable."""
        return False

    @pytest.fixture()
    def vectorstore(self, _vastdb_session, _vastdb_schema) -> Generator[VectorStore, None, None]:  # type: ignore[override]
        yield from _build_vectorstore(_vastdb_session, _vastdb_schema)

    # -----------------------------------------------------------------------
    # Epic 2 deferred findings — dedicated test cases (AC: #6)
    # -----------------------------------------------------------------------

    def test_insert_with_python_float_list_does_not_fail(
        self, vectorstore: VectorStore
    ) -> None:
        """AI-1: Verify float64-inferred Python lists insert without type errors.

        pa.RecordBatch.from_pydict() infers float64 for Python float lists;
        VAST table schema uses float32. Validates SDK coercion on insert and
        successful round-trip via get_by_ids.
        """
        ids = vectorstore.add_texts(["hello world"])
        assert len(ids) == 1
        docs = vectorstore.get_by_ids(ids)
        assert len(docs) == 1
        assert docs[0].page_content == "hello world"

    def test_row_with_null_metadata_roundtrips(
        self, vectorstore: VectorStore
    ) -> None:
        """AI-2: Verify rows with NULL metadata don't raise TypeError.

        Directly inserts a row with metadata=NULL via the VAST SDK, bypassing
        VastDBVectorStore._insert_vectors. Expects _row_to_document to handle
        None gracefully. Fixed in story 4-2a.
        """
        batch = pa.RecordBatch.from_pydict(
            {
                "id": ["test-null-meta"],
                "text": ["test text"],
                "embedding": [[0.0] * VECTOR_DIM],
                "metadata": pa.array([None], type=pa.string()),
            },
            schema=_ARROW_SCHEMA,
        )
        with vectorstore._session.transaction() as tx:  # type: ignore[union-attr]
            table = vectorstore._get_table(tx)  # type: ignore[union-attr]
            table.insert(batch)

        docs = vectorstore.get_by_ids(["test-null-meta"])
        assert len(docs) == 1

    def test_similarity_search_with_score_returns_distance(
        self, vectorstore: VectorStore
    ) -> None:
        """AI-3: Confirm $distance score passthrough from table.vector_search.

        Inserts documents and asserts similarity_search_with_score returns
        non-trivial float scores (not all 0.0), confirming the $distance field
        is correctly popped from each row dict by _do_vector_search.
        """
        vectorstore.add_texts(["hello", "world", "foo bar"])
        results = vectorstore.similarity_search_with_score("hello", k=3)
        assert len(results) > 0
        scores = [score for _, score in results]
        assert all(isinstance(s, float) for s in scores)
        assert not all(s == 0.0 for s in scores), (
            "All scores are 0.0 — $distance passthrough from table.vector_search may be broken"
        )

    # -----------------------------------------------------------------------
    # Story 3.2: Retriever & RAG chain integration validation
    # -----------------------------------------------------------------------

    def test_as_retriever_returns_documents(self, vectorstore: VectorStore) -> None:
        """AC #1, #2: as_retriever().invoke() returns correct Documents from live VAST."""
        from langchain_core.vectorstores import VectorStoreRetriever

        vectorstore.add_texts(
            ["alpha document", "beta document", "gamma document"],
            ids=["r-1", "r-2", "r-3"],
        )
        retriever = vectorstore.as_retriever()
        assert isinstance(retriever, VectorStoreRetriever)

        docs = retriever.invoke("alpha")
        assert isinstance(docs, list)
        assert len(docs) > 0
        assert all(isinstance(d, Document) for d in docs)
        # The retriever should preserve Document.id
        assert all(d.id is not None for d in docs)

    def test_retriever_custom_k(self, vectorstore: VectorStore) -> None:
        """AC #3: Retriever with search_kwargs={"k": 2} returns at most 2 docs."""
        vectorstore.add_texts(
            ["one", "two", "three", "four", "five"],
            ids=["k-1", "k-2", "k-3", "k-4", "k-5"],
        )
        retriever = vectorstore.as_retriever(search_kwargs={"k": 2})
        docs = retriever.invoke("one")
        assert len(docs) == 2

    def test_retriever_with_text_filter(self, vectorstore: VectorStore) -> None:
        """AC #3: Retriever with search_kwargs={"predicate": ...} filters correctly."""
        vectorstore.add_texts(
            ["target text", "other text", "more text"],
            ids=["f-1", "f-2", "f-3"],
        )
        retriever = vectorstore.as_retriever(
            search_kwargs={"k": 10, "predicate": _["text"] == "target text"}
        )
        docs = retriever.invoke("text")
        assert len(docs) >= 1
        assert all(d.page_content == "target text" for d in docs)

    def test_lcel_rag_chain_with_live_retriever(
        self, vectorstore: VectorStore
    ) -> None:
        """AC #4: LCEL chain with live retriever + FakeListLLM executes end-to-end."""
        from langchain_core.language_models import FakeListLLM
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.runnables import RunnablePassthrough

        vectorstore.add_texts(
            ["VAST Database stores vector embeddings efficiently"],
            ids=["chain-1"],
        )
        retriever = vectorstore.as_retriever(search_kwargs={"k": 1})

        prompt = ChatPromptTemplate.from_template(
            "Answer based on context:\n{context}\n\nQuestion: {question}"
        )

        def format_docs(docs):
            return "\n".join(d.page_content for d in docs)

        llm = FakeListLLM(responses=["VAST is great for vectors"])
        chain = (
            {"context": retriever | format_docs, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )

        result = chain.invoke("What does VAST store?")
        assert isinstance(result, str)
        assert "VAST is great for vectors" in result


# ---------------------------------------------------------------------------
# Retriever standard test class
# ---------------------------------------------------------------------------


class TestVastDBRetrieverIntegration(RetrieversIntegrationTests):
    """LangChain standard integration test suite for the retriever surface.

    Exercises `store.as_retriever()` against the upstream `RetrieversIntegrationTests`
    contract so future LangChain tightenings are caught automatically — the same
    rationale we rely on for `VectorStoreIntegrationTests`. The retriever is
    `VectorStoreRetriever` (inherited from langchain-core); we wire the standard
    suite's `retriever_constructor` hook to a factory that seeds the existing
    vectorstore fixture and returns `store.as_retriever(search_kwargs={"k": k})`.
    """

    @pytest.fixture()
    def vectorstore(self, _vastdb_session, _vastdb_schema) -> Generator[VectorStore, None, None]:
        yield from _build_vectorstore(_vastdb_session, _vastdb_schema)

    @pytest.fixture(autouse=True)
    def _seed_and_bind(self, vectorstore: VectorStore) -> None:
        """Seed 5 docs and bind the store so `retriever_constructor` can reach it."""
        vectorstore.add_texts(["one", "two", "three", "four", "five"])
        self._vs = vectorstore

    @property
    def retriever_constructor(self) -> Any:  # type: ignore[override]
        """Factory that builds a VectorStoreRetriever over the seeded fixture store.

        Typed `Any` because the upstream contract expects `type[BaseRetriever]` but
        only *calls* the attribute — any callable returning a `BaseRetriever`
        satisfies the test suite. `k` maps to `search_kwargs["k"]`; all other kwargs
        pass through to `as_retriever(**kwargs)` as retriever-level params so future
        upstream additions (e.g. `search_type="mmr"`) land on the right surface.
        """
        vs = self._vs

        def factory(**kwargs: Any) -> BaseRetriever:
            k = kwargs.pop("k", 4)
            search_kwargs = {"k": k, **kwargs.pop("search_kwargs", {})}
            return vs.as_retriever(search_kwargs=search_kwargs, **kwargs)

        return factory

    @property
    def retriever_constructor_params(self) -> dict[str, Any]:
        return {"k": 3}

    @property
    def retriever_query_example(self) -> str:
        return "one"

    @pytest.mark.xfail(
        reason=(
            "VastDB SDK is sync-only; async retrieval, if it succeeds, does so via "
            "langchain-core's executor fallback (asimilarity_search -> run_in_executor). "
            "strict=False because XPASS is acceptable — we just don't commit to the surface."
        ),
        strict=False,
    )
    async def test_ainvoke_returns_documents(
        self, retriever: BaseRetriever
    ) -> None:
        await super().test_ainvoke_returns_documents(retriever)
