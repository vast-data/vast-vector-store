"""Integration tests for VastDBVectorStore using LangChain's standard test suite."""

import os
import uuid
from collections.abc import Generator

import pyarrow as pa
import pytest
import vastdb
from langchain_core.vectorstores import VectorStore
from langchain_tests.integration_tests import VectorStoreIntegrationTests
from vastdb._internal import VectorIndexSpec

from langchain_vastdb import VastDBVectorStore

# ---------------------------------------------------------------------------
# Environment variable handling
# ---------------------------------------------------------------------------

REQUIRED_ENV = [
    "VASTDB_ENDPOINT",
    "VASTDB_ACCESS_KEY",
    "VASTDB_SECRET_KEY",
    "VASTDB_TEST_BUCKET",
    "VASTDB_TEST_SCHEMA",
]

_missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
pytestmark = pytest.mark.skipif(
    bool(_missing),
    reason=f"Missing required VAST env vars: {_missing}",
)

# Must match EMBEDDING_SIZE in langchain_tests.integration_tests.vectorstores
VECTOR_DIM = 6

_ARROW_SCHEMA = pa.schema([
    pa.field("id", pa.string()),
    pa.field("text", pa.string()),
    pa.field("vector", pa.list_(pa.float32(), list_size=VECTOR_DIM)),
    pa.field("metadata", pa.string()),
])


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
    def vectorstore(self) -> Generator[VectorStore, None, None]:  # type: ignore[override]
        """Yield an empty VastDBVectorStore backed by a dedicated, isolated test table.

        Creates a uniquely-named table on the test VAST cluster before yielding,
        and drops it unconditionally in the finally block.

        Required env vars: VASTDB_ENDPOINT, VASTDB_ACCESS_KEY, VASTDB_SECRET_KEY,
        VASTDB_TEST_BUCKET, VASTDB_TEST_SCHEMA.
        """
        endpoint = os.environ["VASTDB_ENDPOINT"]
        access_key = os.environ["VASTDB_ACCESS_KEY"]
        secret_key = os.environ["VASTDB_SECRET_KEY"]
        bucket = os.environ["VASTDB_TEST_BUCKET"]
        schema = os.environ["VASTDB_TEST_SCHEMA"]
        table_name = f"lc_vs_it_{uuid.uuid4().hex[:12]}"

        session = vastdb.connect(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
        )

        with session.transaction() as tx:
            tx.bucket(bucket).schema(schema).create_table(
                table_name,
                _ARROW_SCHEMA,
                vector_index=VectorIndexSpec("vector", "cosine"),
            )

        store = VastDBVectorStore(
            embedding=self.get_embeddings(),
            session=session,
            bucket=bucket,
            schema=schema,
            table_name=table_name,
        )
        try:
            yield store
        finally:
            try:
                with session.transaction() as tx:
                    tx.bucket(bucket).schema(schema).table(table_name).drop()
            except Exception:
                pass

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

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "AI-2: _row_to_document NULL metadata handling — "
            "json.loads(None) raises TypeError when metadata column is NULL. "
            "Deferred to follow-up story."
        ),
    )
    def test_row_with_null_metadata_roundtrips(
        self, vectorstore: VectorStore
    ) -> None:
        """AI-2: Verify rows with NULL metadata don't raise TypeError.

        Directly inserts a row with metadata=NULL via the VAST SDK, bypassing
        VastDBVectorStore._insert_vectors. Expects _row_to_document to handle
        None gracefully. Currently xfail: json.loads(None) raises TypeError.
        See deferred-work.md for the proposed fix.
        """
        null_vector = pa.array(
            [[0.0] * VECTOR_DIM], type=pa.list_(pa.float32(), list_size=VECTOR_DIM)
        )
        batch = pa.RecordBatch.from_pydict(
            {
                "id": ["test-null-meta"],
                "text": ["test text"],
                "vector": null_vector,
                "metadata": pa.array([None], type=pa.string()),
            }
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
