# Story 2.5: Unit Tests for VastDBVectorStore

Status: done

## Story

As a developer,
I want comprehensive unit tests with mocked VastDB SDK calls covering all public methods and hook defaults,
so that I can confidently refactor and extend the class without regressions.

## Acceptance Criteria

1. **Given** the unit test file `tests/unit_tests/test_vectorstore.py`
   **When** `uv run pytest tests/unit_tests/` is run
   **Then** all tests pass with mocked VastDB SDK (no cluster needed)

2. **Given** unit test fixtures
   **When** the test module is set up
   **Then** it provides: `mock_session` (mocked `vastdb.Session`), `mock_transaction` (mocked `Transaction`), `vectorstore` (instance with mocked session and `DeterministicFakeEmbedding`), and `sample_documents` (list of test `Document` objects)

3. **Given** unit tests for constructor
   **When** tests execute
   **Then** they verify: session-first construction, `from_connection_params` classmethod, custom column name configuration, embeddings property, and that credentials are not exposed

4. **Given** unit tests for `add_texts`
   **When** tests execute
   **Then** they verify: texts are embedded, `_insert_vectors` is called with correct args, UUIDs are generated when no IDs provided, explicit IDs are used when provided, empty metadata defaults work

5. **Given** unit tests for search methods
   **When** tests execute
   **Then** they verify: `similarity_search` returns `list[Document]`, `similarity_search_with_score` returns `list[tuple[Document, float]]`, `similarity_search_by_vector` skips embedding, filter dict is converted to ibis predicate, `_row_to_document` correctly deserializes JSON metadata

6. **Given** unit tests for delete and get_by_ids
   **When** tests execute
   **Then** they verify: `delete` calls `_delete_by_ids` with correct IDs, `delete(ids=None)` returns `None`, `get_by_ids` returns correct documents, `from_texts` creates store and calls `add_texts`

7. **Given** unit tests for hook extensibility
   **When** a test subclass overrides a hook method
   **Then** the template methods correctly call the overridden hook instead of the default, verifying FR24 (domain-specific methods don't conflict)

## Tasks / Subtasks

- [x] **Task 1: Create test file with imports and fixtures (AC: #1, #2)**
  - [x] Create `tests/unit_tests/test_vectorstore.py`
  - [x] Import `unittest.mock` (MagicMock, patch, PropertyMock), `pytest`, `json`, `uuid`
  - [x] Import `Document` from `langchain_core.documents`
  - [x] Import `DeterministicFakeEmbedding` from `langchain_core.embeddings`
  - [x] Import `VastDBVectorStore` from `langchain_vastdb`
  - [x] Create `mock_session` fixture: `MagicMock(spec=["transaction"])` with transaction context manager wired
  - [x] Create `mock_transaction` fixture: the `__enter__` return of `mock_session.transaction()`
  - [x] Create `fake_embedding` fixture: `DeterministicFakeEmbedding(size=3)`
  - [x] Create `vectorstore` fixture: `VastDBVectorStore(embedding=fake_embedding, session=mock_session, bucket="b", schema="s", table_name="t")`
  - [x] Create `sample_rows` fixture: list of dicts representing VastDB rows with id, text, metadata columns

- [x] **Task 2: Constructor and configuration tests (AC: #3)**
  - [x] Test session-first construction stores session and creates TableRef/TableMetadata
  - [x] Test `from_connection_params` patches `vastdb.connect` and delegates to constructor
  - [x] Test custom column name configuration (`id_column`, `text_column`, `vector_column`, `metadata_column`)
  - [x] Test `embeddings` property returns the provided Embeddings instance
  - [x] Test credentials are not stored as instance attributes (no `access_key` or `secret_key` on the instance)

- [x] **Task 3: Table access and cache tests (AC: #1)**
  - [x] Test `_get_table` calls `_table_metadata.load(tx)` on first call and `tx.table_from_metadata()` on every call
  - [x] Test `_get_table` skips `load()` on second call (cached metadata)
  - [x] Test `invalidate_table_cache` resets `_metadata_loaded` to `False`

- [x] **Task 4: add_texts tests (AC: #4)**
  - [x] Test texts are embedded via `embed_documents`
  - [x] Test `_insert_vectors` hook receives correct args (texts, embeddings, metadatas, ids)
  - [x] Test UUIDs are auto-generated when `ids=None`
  - [x] Test explicit IDs are used when provided
  - [x] Test empty metadata defaults to `[{}, {}]` when `metadatas=None`

- [x] **Task 5: Search method tests (AC: #5)**
  - [x] Test `similarity_search` embeds query, calls `_vector_search`, returns `list[Document]`
  - [x] Test `similarity_search_with_score` returns `list[tuple[Document, float]]`
  - [x] Test `similarity_search_by_vector` does NOT call `embed_query` (skips embedding)
  - [x] Test filter dict is passed through to `_vector_search` as ibis predicate
  - [x] Test `_row_to_document` deserializes JSON metadata and sets `page_content`
  - [x] Test `_build_predicate` returns `None` for empty/None input, ibis expr for single key, combined expr for multiple keys

- [x] **Task 6: Delete and get_by_ids tests (AC: #6)**
  - [x] Test `delete(ids=["id1"])` calls `_delete_by_ids` and returns `True`
  - [x] Test `delete(ids=None)` returns `None` (no-op)
  - [x] Test `delete(ids=[])` returns `None` (no-op)
  - [x] Test `get_by_ids` calls `_get_by_ids` and converts rows via `_row_to_document`
  - [x] Test `from_texts` constructs instance and calls `add_texts`

- [x] **Task 7: Hook extensibility tests (AC: #7)**
  - [x] Create a test subclass that overrides `_insert_vectors` to track calls
  - [x] Verify `add_texts` dispatches to the overridden `_insert_vectors`
  - [x] Create a test subclass that overrides `_row_to_document` to add score to metadata
  - [x] Verify `similarity_search_with_score` uses the overridden `_row_to_document`

- [x] **Task 8: Validate (AC: #1)**
  - [x] Run `uv run ruff check .` -- must pass with zero warnings
  - [x] Run `uv run pytest tests/unit_tests/ -v` -- all tests pass

## Dev Notes

### Test file location

Create exactly one file: `tests/unit_tests/test_vectorstore.py`. The `tests/unit_tests/__init__.py` already exists (created in Story 1.1).

### Mocking the VastDB SDK transaction chain

The most critical mock setup. VastDB uses a context manager pattern for transactions. The mock chain must be:

```python
mock_tx = MagicMock()
mock_session = MagicMock()
mock_session.transaction.return_value.__enter__ = MagicMock(return_value=mock_tx)
mock_session.transaction.return_value.__exit__ = MagicMock(return_value=False)
```

Then for table access:
```python
mock_table = MagicMock()
mock_tx.table_from_metadata.return_value = mock_table
```

And for table operations that return readers:
```python
# For select() and vector_search() -- they return a RecordBatchReader-like
mock_reader = MagicMock()
mock_reader.read_all.return_value.to_pylist.return_value = [
    {"id": "1", "text": "hello", "metadata": '{"k": "v"}'},
]
mock_table.select.return_value = mock_reader
mock_table.vector_search.return_value = mock_reader_with_distance
```

For `vector_search`, rows include `$distance`:
```python
mock_reader_vs = MagicMock()
mock_reader_vs.read_all.return_value.to_pylist.return_value = [
    {"id": "1", "text": "hello", "metadata": '{"k": "v"}', "$distance": 0.5},
]
mock_table.vector_search.return_value = mock_reader_vs
```

`table.insert()` and `table.delete()` return `None` (no return value to mock).

### Use DeterministicFakeEmbedding from langchain_core

```python
from langchain_core.embeddings import DeterministicFakeEmbedding

fake_embedding = DeterministicFakeEmbedding(size=3)
```

This produces deterministic, reproducible vectors for any input text. Use `size=3` to keep test data small. The `embed_documents` and `embed_query` methods are real -- no mocking needed for the embedding itself.

### Patching `vastdb.connect` for `from_connection_params` test

```python
with patch("langchain_vastdb.vectorstores.vastdb.connect") as mock_connect:
    mock_connect.return_value = mock_session
    store = VastDBVectorStore.from_connection_params(
        embedding=fake_embedding,
        endpoint="http://vast:8080",
        access_key="ak",
        secret_key="sk",
        bucket="b", schema="s", table_name="t",
    )
    mock_connect.assert_called_once_with(
        endpoint="http://vast:8080", access_key="ak", secret_key="sk"
    )
```

### Testing `_get_table` metadata caching

The `_get_table` method calls `self._table_metadata.load(tx)` on first invocation, then skips it. To test:

```python
def test_get_table_loads_metadata_on_first_call(vectorstore, mock_transaction):
    vectorstore._get_table(mock_transaction)
    vectorstore._table_metadata.load.assert_called_once_with(mock_transaction)
    mock_transaction.table_from_metadata.assert_called_once()

def test_get_table_skips_load_on_subsequent_calls(vectorstore, mock_transaction):
    vectorstore._get_table(mock_transaction)
    vectorstore._get_table(mock_transaction)
    # load() called once (first call), table_from_metadata called twice
    vectorstore._table_metadata.load.assert_called_once()
    assert mock_transaction.table_from_metadata.call_count == 2
```

### Testing add_texts UUID generation

Use `patch("langchain_vastdb.vectorstores.uuid.uuid4")` to control UUID generation:

```python
with patch("langchain_vastdb.vectorstores.uuid.uuid4") as mock_uuid:
    mock_uuid.return_value = MagicMock(__str__=lambda self: "test-uuid")
    ids = store.add_texts(["hello"])
    assert ids == ["test-uuid"]
```

Or, more simply, verify returned IDs are valid UUID strings:

```python
ids = store.add_texts(["hello"])
assert len(ids) == 1
uuid.UUID(ids[0])  # Raises if not valid UUID
```

### Testing `_build_predicate` (helper method)

Test three cases:
1. `_build_predicate(None)` returns `None`
2. `_build_predicate({})` returns `None`
3. `_build_predicate({"key": "val"})` returns an ibis expression (check it's not None, type is `ibis.Expr`)
4. `_build_predicate({"a": 1, "b": 2})` returns a combined expression

Since ibis expressions don't support direct equality comparison, verify type/non-None:
```python
result = store._build_predicate({"key": "val"})
assert result is not None
```

### Testing hook extensibility

Create a concrete test subclass:

```python
class TrackingVectorStore(VastDBVectorStore):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.insert_calls = []

    def _insert_vectors(self, texts, embeddings, metadatas, ids, *, tx=None):
        self.insert_calls.append((texts, embeddings, metadatas, ids))
        return ids

store = TrackingVectorStore(embedding=fake_embedding, session=mock_session, ...)
store.add_texts(["hello"])
assert len(store.insert_calls) == 1
assert store.insert_calls[0][0] == ["hello"]
```

This verifies `add_texts` dispatches to the subclass override, not the base default.

### Previous story intelligence

**From Story 2.4 (delete, get_by_ids, from_texts):**
- `delete(ids=None)` and `delete(ids=[])` both return `None` (no-op via `if not ids`).
- `get_by_ids` calls `_get_by_ids` then maps rows through `_row_to_document`.
- `from_texts` constructs instance then calls `add_texts` -- can be tested by patching `add_texts`.
- `_delete_by_ids` uses `ibis._[self._id_column].isin(ids)` for predicate.
- `_get_by_ids` selects columns `[id, text, metadata]` (omits vector).

**From Story 2.3 (search methods):**
- `similarity_search` calls `embed_query` then `_vector_search` then `_row_to_document`.
- `similarity_search_with_score` includes distance score in return tuples.
- `similarity_search_by_vector` skips embedding, passes vector directly.
- `_vector_search` pops `$distance` from each row dict.
- `_do_vector_search` is a private helper used inside `_vector_search`.

**From Story 2.2 (add_texts):**
- `add_texts` calls `embed_documents`, generates UUIDs if no ids, defaults empty metadatas.
- `_insert_vectors` builds `pa.RecordBatch.from_pydict()` and calls `table.insert()`.

**From Story 2.1 (constructor):**
- `_metadata_loaded` starts `False`, set to `True` after first `_get_table` call.
- `_table_ref` and `_table_metadata` created from bucket/schema/table_name.
- `invalidate_table_cache` resets both.

### What this story does NOT cover

- Integration tests against a real VAST cluster -- **Story 3.1**
- LangChain `VectorStoreIntegrationTests` standard suite -- **Story 3.1**
- Async tests -- not applicable (vastdb is sync-only)

### Anti-patterns to avoid

- Do NOT connect to a real VastDB cluster -- all tests use mocks.
- Do NOT test internal implementation details beyond what's specified (e.g., don't assert PyArrow schema specifics -- that's integration test territory).
- Do NOT import from `vastdb` directly in tests (except for `patch` targets). Use the public `langchain_vastdb` API.
- Do NOT add test dependencies to `pyproject.toml` -- `pytest` and `langchain-core` (which provides `DeterministicFakeEmbedding`) are already dev dependencies.
- Do NOT create conftest.py -- keep fixtures in the test file for simplicity (single test module).
- Do NOT use `pytest-mock` -- use `unittest.mock` which is in the standard library.

### Project Structure Notes

This story creates exactly one file:

```
tests/unit_tests/test_vectorstore.py  # NEW: comprehensive unit tests
```

All other files remain unchanged.

### Architecture compliance summary

| Constraint | Source | What this story does |
|---|---|---|
| Unit test patterns | architecture.md#Test Patterns | Uses `unittest.mock.MagicMock` for VastDB SDK mocking |
| Fixture naming | architecture.md#Test Patterns | `vectorstore`, `mock_session`, `mock_transaction`, `sample_documents` |
| DeterministicFakeEmbedding | architecture.md#Test Patterns | Used for embedding vectors |
| Test file location | architecture.md#Project Structure | `tests/unit_tests/test_vectorstore.py` |
| NFR14 | epics.md#NFR | Unit test coverage for all public methods and hook method defaults |

### Testing standards

1. `uv run ruff check .` exits with code 0 and zero warnings.
2. `uv run pytest tests/unit_tests/ -v` -- all tests pass, no skips, no errors.

### References

- Story requirements and ACs: [Source: _bmad-output/planning-artifacts/epics.md#Story 2.5: Unit Tests for VastDBVectorStore]
- Test patterns: [Source: _bmad-output/planning-artifacts/architecture.md#Test Patterns]
- Implementation under test: [Source: src/langchain_vastdb/vectorstores.py]
- Previous story (2.4): [Source: _bmad-output/implementation-artifacts/2-4-delete-get-by-ids-and-factory-method.md]
- Previous story (2.3): [Source: _bmad-output/implementation-artifacts/2-3-similarity-search-operations.md]
- Deferred work: [Source: _bmad-output/implementation-artifacts/deferred-work.md]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Fixed `test_add_texts_embeds_via_embed_documents` and `test_similarity_search_by_vector_skips_embed_query`: `DeterministicFakeEmbedding` is a frozen Pydantic model; instance-level `patch.object` fails. Fixed by patching at class level (`patch.object(DeterministicFakeEmbedding, "embed_documents/embed_query")`).

### Completion Notes List

- Created `tests/unit_tests/test_vectorstore.py` with 29 unit tests covering all public methods and hook defaults.
- All 29 tests pass: `uv run pytest tests/unit_tests/ -v` → 29 passed in 3.71s.
- Ruff: `uv run ruff check .` → All checks passed.
- Key patterns: `_table_metadata` replaced with `MagicMock()` in `vectorstore` fixture to avoid needing a real VastDB cluster; Pydantic frozen model workaround for spying on embed methods.

### File List

- tests/unit_tests/test_vectorstore.py (new)