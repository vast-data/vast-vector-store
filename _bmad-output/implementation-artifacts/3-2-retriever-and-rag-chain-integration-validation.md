# Story 3.2: Retriever & RAG Chain Integration Validation

Status: ready-for-dev

## Story

As a developer,
I want to use VastDBVectorStore as a LangChain retriever and in RAG chain pipelines,
so that I can integrate VAST-backed vector search into my LangChain applications seamlessly.

## Acceptance Criteria

1. **Given** a VastDBVectorStore instance with indexed documents,
   **When** `store.as_retriever()` is called,
   **Then** a LangChain `VectorStoreRetriever` is returned that can be invoked with a query string.

2. **Given** a retriever created from VastDBVectorStore,
   **When** `retriever.invoke("search query")` is called,
   **Then** it returns a list of `Document` objects matching the query, using the store's `similarity_search` under the hood.

3. **Given** a retriever with custom search kwargs,
   **When** `store.as_retriever(search_kwargs={"k": 2, "filter": {"category": "news"}})` is called,
   **Then** the retriever uses the specified k and filter when performing searches.

4. **Given** a VastDBVectorStore retriever,
   **When** it is used in a LangChain LCEL RAG chain (`retriever | prompt | llm`),
   **Then** the chain executes successfully with the retriever providing context documents from VAST.

5. **Given** unit tests for retriever and RAG chain functionality,
   **When** `uv run pytest tests/unit_tests/` is run,
   **Then** all existing tests pass plus the new retriever/chain tests (expected: 41 existing + new tests).

6. **Given** integration tests for retriever functionality,
   **When** they run against a live VAST cluster,
   **Then** they verify `as_retriever()` returns correct documents, custom `search_kwargs` are respected, and the retriever integrates into a simple LCEL chain.

## Tasks / Subtasks

- [ ] **Task 1: Unit tests for `as_retriever()` basic functionality (AC #1, #2)**
  - [ ] Add test `test_as_retriever_returns_retriever_instance` — verify `store.as_retriever()` returns a `VectorStoreRetriever`.
  - [ ] Add test `test_retriever_invoke_returns_documents` — add docs, create retriever, call `retriever.invoke("query")`, assert returns `list[Document]` with expected content.
  - [ ] Add test `test_retriever_invoke_empty_store` — retriever on empty store returns `[]`.

- [ ] **Task 2: Unit tests for retriever with custom search_kwargs (AC #3)**
  - [ ] Add test `test_retriever_with_k_kwarg` — `as_retriever(search_kwargs={"k": 2})`, invoke, assert at most 2 results.
  - [ ] Add test `test_retriever_with_filter_kwarg` — `as_retriever(search_kwargs={"filter": {"category": "news"}})`, invoke, verify `similarity_search` called with the filter. Use mock patching on `similarity_search` to verify kwargs pass-through.

- [ ] **Task 3: Unit tests for LCEL RAG chain pattern (AC #4)**
  - [ ] Add test `test_lcel_rag_chain_executes` — build an LCEL chain: `{"context": retriever, "question": RunnablePassthrough()} | prompt | llm | StrOutputParser()`. Use `FakeListLLM` from `langchain_core.language_models` as the LLM. Assert the chain `.invoke("query")` returns a string response.
  - [ ] Verify the retriever is invoked (documents fetched) as part of the chain execution.

- [ ] **Task 4: Integration tests for `as_retriever()` (AC #1, #2, #6)**
  - [ ] Add test `test_as_retriever_returns_documents` — use the existing `vectorstore` fixture, add documents, create retriever, `retriever.invoke("query")`, assert correct `Document` objects returned.
  - [ ] Verify `Document.id` is preserved through the retriever path.

- [ ] **Task 5: Integration tests for custom search_kwargs (AC #3, #6)**
  - [ ] Add test `test_retriever_custom_k` — add 5 docs, create retriever with `search_kwargs={"k": 2}`, invoke, assert exactly 2 docs returned.
  - [ ] Add test `test_retriever_with_metadata_filter` — add docs with varying metadata, create retriever with `search_kwargs={"filter": {"category": "news"}}`, invoke, assert only docs with matching metadata returned.

- [ ] **Task 6: Integration test for LCEL RAG chain (AC #4, #6)**
  - [ ] Add test `test_lcel_rag_chain_with_live_retriever` — build LCEL chain with live retriever + `FakeListLLM`, invoke, assert chain returns a string and retriever provided real documents from VAST.

- [ ] **Task 7: Local validation (AC #5)**
  - [ ] `uv run ruff check .` exits 0 with zero warnings.
  - [ ] `uv run pytest tests/unit_tests/` — all tests pass (41 existing + new).

## Dev Notes

### Key Insight: This is a Validation Story, Not an Implementation Story

`as_retriever()` is inherited from `langchain_core.vectorstores.VectorStore`. **No production code changes should be needed.** The store already supports retriever functionality by virtue of inheriting from `VectorStore`. This story validates that the inheritance works correctly end-to-end against a live cluster and in chain compositions.

If any production code change IS needed (unlikely), it means a bug was found — treat it as a correctness fix and document it in Dev Notes, analogous to Story 3.1a.

### Available Components (all from `langchain-core`, no new deps)

- `VectorStoreRetriever` — returned by `VectorStore.as_retriever()`, has `.invoke(query: str) -> list[Document]`
- `FakeListLLM` — `from langchain_core.language_models import FakeListLLM` — deterministic fake LLM for testing. Provide `responses=["mock answer"]`.
- `ChatPromptTemplate` — `from langchain_core.prompts import ChatPromptTemplate`
- `RunnablePassthrough` — `from langchain_core.runnables import RunnablePassthrough`
- `StrOutputParser` — `from langchain_core.output_parsers import StrOutputParser`

### LCEL RAG Chain Pattern for Tests

```python
from langchain_core.language_models import FakeListLLM
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough

retriever = store.as_retriever(search_kwargs={"k": 3})

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
result = chain.invoke("test query")
# result == "This is a test answer"
```

### Integration Test Fixture Reuse

Reuse the existing `vectorstore` fixture from `TestVastDBVectorStoreSync` for integration tests. The new integration test class should either:
- Add methods to the existing `TestVastDBVectorStoreSync` class (simplest — reuses the fixture directly), OR
- Create a new test class that uses the same fixture pattern.

**Recommended: Add methods to the existing class** since they need the same fixture and the test file is already well-structured. This avoids duplicating the fixture setup/teardown.

### Metadata Filter Constraints

The `filter` dict in `search_kwargs` maps to the `filter` parameter of `similarity_search`. The store's `_do_vector_search_adbc` builds a WHERE clause from filter keys/values. Only columns in `_metadata_columns + [_id_column]` (after second-pass review tightening: `{_id_column, _text_column}`) are allowed.

For integration tests with metadata filters: insert documents with metadata like `{"category": "news"}` and `{"category": "sports"}`. The metadata is stored as a JSON string in the `metadata` column, so filter behavior depends on the store's SQL WHERE clause construction — **the metadata column itself is a single JSON string column, not individual columns per key.**

**IMPORTANT:** Verify how `filter={"category": "news"}` maps to SQL. If the store only supports top-level column filters (not JSON path extraction), metadata-key filters may not work as expected. The current `_do_vector_search_adbc` builds `WHERE "col" = 'val'` — this works for `id` and `text` columns but NOT for JSON metadata fields. Check this before writing the metadata filter test. If metadata-key filtering is not supported, the test should use a column-level filter (e.g., `filter={"text": "specific text"}`) or the test should document the limitation.

### Previous Story Intelligence (from 3-1a)

- Integration test fixture creates unique schema + table per test run via `uuid.uuid4().hex[:12]`.
- Session uses `ssl_verify=False` and `BackoffConfig(max_tries=2, max_time=15.0)`.
- ADBC env vars are optional — CI runs through fallback path.
- `VectorStoreIntegrationTests.get_embeddings()` provides deterministic fake embeddings (dimension = `EMBEDDING_SIZE` from `langchain_tests`).
- Cleanup is in a `finally` block with bare `except Exception: pass`.
- All 41 unit tests + 15 integration tests currently pass.

### Testing Standards

1. `uv run ruff check .` exits 0 with zero warnings.
2. `uv run pytest tests/unit_tests/` — all tests pass (41 existing + new).
3. Integration tests: `uv run pytest tests/integration_tests/ -v` — existing 15 pass + new retriever tests pass.

### Files to Modify

- `tests/unit_tests/test_vectorstore.py` — add retriever + LCEL chain unit tests
- `tests/integration_tests/test_vectorstore.py` — add retriever + LCEL chain integration tests

### Files NOT to Modify

- `src/langchain_vastdb/vectorstores.py` — no production code changes expected
- `pyproject.toml` — no new dependencies needed (all components from `langchain-core`)

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.2]
- [Source: _bmad-output/planning-artifacts/architecture.md#Test Patterns]
- [Source: _bmad-output/planning-artifacts/architecture.md#Project Structure]
- [Source: _bmad-output/implementation-artifacts/3-1a-live-cluster-correctness-fixes.md#Dev Notes]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
