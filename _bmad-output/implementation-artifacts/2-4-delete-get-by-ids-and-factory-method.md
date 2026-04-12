# Story 2.4: Delete, Get by IDs & Factory Method

Status: done

## Story

As a developer,
I want to delete documents by ID, retrieve documents by ID without searching, and create a vector store from a list of texts in one call,
so that I have complete CRUD operations and a convenient factory method.

## Acceptance Criteria

1. **Given** a VastDBVectorStore with documents stored with known IDs
   **When** `delete(ids=["id1", "id2"])` is called
   **Then** the `_delete_by_ids` hook is called with the ID list and returns `True` on success

2. **Given** the default `_delete_by_ids` hook implementation
   **When** it is called with a list of IDs
   **Then** it opens a transaction (or uses provided `tx`), gets the table, builds a predicate matching the ID column to the provided IDs, calls `table.delete(predicate)`, and returns `True`

3. **Given** a VastDBVectorStore with stored documents
   **When** `get_by_ids(ids=["id1", "id2"])` is called
   **Then** the `_get_by_ids` hook is called and returns the matching documents as `list[Document]` by passing each row through `_row_to_document`

4. **Given** the default `_get_by_ids` hook implementation
   **When** it is called with a list of IDs
   **Then** it opens a transaction (or uses provided `tx`), gets the table, selects rows matching the ID column, reads results via `to_pylist()`, and returns `list[dict]`

5. **Given** a developer who wants to create a vector store and add documents in one step
   **When** `VastDBVectorStore.from_texts(texts=["a", "b"], embedding=emb, session=session, bucket="b", schema="s", table_name="t")` is called
   **Then** a new `VastDBVectorStore` instance is created and `add_texts` is called with the provided texts, returning the populated store

6. **Given** the `_delete_by_ids` and `_get_by_ids` hook signatures
   **When** a subclass overrides them
   **Then** `_delete_by_ids` matches: `_delete_by_ids(self, ids, *, tx=None) -> bool`
   **And** `_get_by_ids` matches: `_get_by_ids(self, ids, *, tx=None) -> list[dict]`

> **Error handling note:** VastDB SDK exceptions propagate as-is per Architecture Decision: Error Handling. No try/catch needed in `delete`, `get_by_ids`, or hooks.

## Tasks / Subtasks

- [x] **Task 1: Implement `delete` template method (AC: #1)**
  - [x] Add `delete` method to `VastDBVectorStore` after the search methods block.
  - [x] Signature: `delete(self, ids: list[str] | None = None, **kwargs: Any) -> bool | None`. This matches LangChain's `VectorStore.delete()` signature.
  - [x] Implementation: if `ids` is `None` or empty, return `None` (no-op). Otherwise delegate to `self._delete_by_ids(ids)` and return its result.
  - [x] Add Google-style docstring.

- [x] **Task 2: Implement `_delete_by_ids` hook (AC: #2, #6)**
  - [x] Add `_delete_by_ids` method with the **exact canonical signature**: `_delete_by_ids(self, ids: list[str], *, tx: Transaction | None = None) -> bool`.
  - [x] Follow the transaction pattern: if `tx` provided, use it; otherwise open `with self._session.transaction() as new_tx:`.
  - [x] Use `self._get_table(tx_var)` for table access.
  - [x] Build an ibis predicate: `ibis._[self._id_column].isin(ids)`.
  - [x] Call `table.delete(predicate)`.
  - [x] Return `True`.
  - [x] Add Google-style docstring.

- [x] **Task 3: Implement `get_by_ids` template method (AC: #3)**
  - [x] Add `get_by_ids` method after `delete`.
  - [x] Signature: `get_by_ids(self, ids: list[str], /) -> list[Document]`. The `/` makes `ids` positional-only, matching LangChain's `VectorStore.get_by_ids()` signature from `langchain-core>=0.3`.
  - [x] Implementation: call `rows = self._get_by_ids(ids)`, then return `[self._row_to_document(row) for row in rows]`.
  - [x] Add Google-style docstring.

- [x] **Task 4: Implement `_get_by_ids` hook (AC: #4, #6)**
  - [x] Add `_get_by_ids` method with the **exact canonical signature**: `_get_by_ids(self, ids: list[str], *, tx: Transaction | None = None) -> list[dict]`.
  - [x] Follow the transaction pattern.
  - [x] Use `self._get_table(tx_var)` for table access.
  - [x] Build an ibis predicate: `ibis._[self._id_column].isin(ids)`.
  - [x] Call `table.select(columns=[self._id_column, self._text_column, self._metadata_column], predicate=predicate)` to get a `RecordBatchReader`.
  - [x] Convert: `reader.read_all().to_pylist()` and return the list of dicts.
  - [x] Add Google-style docstring.

- [x] **Task 5: Implement `from_texts` factory classmethod (AC: #5)**
  - [x] Add `from_texts` classmethod after `from_connection_params`.
  - [x] Signature: `from_texts(cls, texts: list[str], embedding: Embeddings, metadatas: list[dict] | None = None, *, session: vastdb.Session, bucket: str, schema: str, table_name: str, **kwargs: Any) -> VastDBVectorStore`.
  - [x] Implementation: create instance via `cls(embedding=embedding, session=session, bucket=bucket, schema=schema, table_name=table_name, **kwargs)`, then call `store.add_texts(texts, metadatas=metadatas)`, then return `store`.
  - [x] This is NOT a hook -- it's a convenience factory. [Source: architecture.md Gap Analysis]
  - [x] Add Google-style docstring.

- [x] **Task 6: Update class docstring (AC: all)**
  - [x] In the class docstring, remove the "(Story 2.4)" annotations from `_delete_by_ids` and `_get_by_ids` since they are now implemented.

- [x] **Task 7: Validate (AC: all)**
  - [x] Run `uv run ruff check .` -- must pass with zero warnings.
  - [x] Run `uv run python -c "from langchain_vastdb import VastDBVectorStore"` -- must succeed.
  - [x] Run `uv run pytest tests/unit_tests/ -v` -- must not error.

## Dev Notes

### This story completes VastDBVectorStore CRUD operations

Stories 2.1-2.3 implemented constructor, add_texts, and similarity search. This story adds delete, get_by_ids, and from_texts -- completing the full LangChain VectorStore interface. After this, all 5 hook methods will have default implementations.

### Single file: `src/langchain_vastdb/vectorstores.py`

All implementation goes in this one file. Do NOT create helper modules or utility files. [Source: _bmad-output/planning-artifacts/architecture.md#File Organization Patterns]

### No new imports needed

All required imports already exist from Stories 2.1-2.3: `json`, `uuid`, `ibis`, `pa`, `vastdb`, `Document`, `Embeddings`, `VectorStore`, `TableMetadata`, `TableRef`, `Any`, `TYPE_CHECKING`, `ITable`, `Transaction`, `Iterable`. The `ibis` import (added in Story 2.3) is reused for building delete/select predicates.

[Source: _bmad-output/planning-artifacts/architecture.md#Import Organization]

### `_delete_by_ids` hook -- exact canonical signature and pattern

```python
def _delete_by_ids(
    self,
    ids: list[str],
    *,
    tx: Transaction | None = None,
) -> bool:
```

**VastDB SDK delete pattern:**
```python
predicate = ibis._[self._id_column].isin(ids)
table.delete(predicate)
```

Use `ibis._.isin()` for matching multiple IDs -- this is more efficient and idiomatic than building individual equality predicates combined with `|`. The `_build_predicate` helper from Story 2.3 is NOT reused here because it handles `{"key": value}` equality dicts for search filters, not `IN` predicates on a specific column.

Follow the transaction pattern: `tx` keyword-only, `_get_table()` for table access.

[Source: _bmad-output/planning-artifacts/architecture.md#Hook Method Signatures, #Transaction Pattern]

### `_get_by_ids` hook -- exact canonical signature and pattern

```python
def _get_by_ids(
    self,
    ids: list[str],
    *,
    tx: Transaction | None = None,
) -> list[dict]:
```

**VastDB SDK select pattern:**
```python
predicate = ibis._[self._id_column].isin(ids)
reader = table.select(
    columns=[self._id_column, self._text_column, self._metadata_column],
    predicate=predicate,
)
rows = reader.read_all().to_pylist()
```

Do NOT include the vector column in `columns` -- it's large and unnecessary for returning Documents. Same pattern as `_vector_search` from Story 2.3.

Return `list[dict]` (plain Python types from hooks, not PyArrow objects). The template method `get_by_ids` converts each dict to a `Document` via `_row_to_document`.

[Source: _bmad-output/planning-artifacts/architecture.md#Hook Method Signatures, #PyArrow Data Conversion Pattern]

### `from_texts` is a simple factory, not a hook

`from_texts` is a LangChain convention: create store + add documents in one call. It's NOT an overridable hook -- it's a classmethod that calls the constructor and `add_texts`. Subclasses inherit it for free.

Note: `from_texts` parameters must include `session`, `bucket`, `schema`, and `table_name` as keyword-only arguments since these are required by the constructor. The `**kwargs` passes through additional constructor params like custom column names.

[Source: _bmad-output/planning-artifacts/architecture.md Gap Analysis]

### LangChain `VectorStore.delete()` signature

LangChain's base `VectorStore.delete()` has the signature: `delete(self, ids: list[str] | None = None, **kwargs: Any) -> bool | None`. The return type is `bool | None` -- `True` on success, `None` for no-op. Our `delete` template method must match this signature.

### LangChain `VectorStore.get_by_ids()` signature

LangChain's base `VectorStore.get_by_ids()` uses positional-only parameter: `get_by_ids(self, ids: Sequence[str], /) -> list[Document]`. Our implementation should use `list[str]` with `/` for positional-only, matching the base class pattern.

### Transaction pattern reminder

Every hook that accesses VastDB follows this exact shape:
```python
def _some_hook(self, ..., *, tx: Transaction | None = None) -> ...:
    if tx is not None:
        table = self._get_table(tx)
        # do work, return result

    with self._session.transaction() as new_tx:
        table = self._get_table(new_tx)
        # do work, return result
```

For `_delete_by_ids` and `_get_by_ids`, the logic is simple enough to inline in both branches (no `_do_*` helper needed like `_do_vector_search` was for `_vector_search`).

[Source: _bmad-output/planning-artifacts/architecture.md#Transaction Pattern]

### Previous story intelligence

**From Story 2.3 (similarity search):**
- `_do_vector_search` helper was used to avoid duplication in transaction branches for complex search logic. For `_delete_by_ids` and `_get_by_ids`, the operations are simple (2-3 lines each), so inline in both branches -- no helper needed.
- `ibis._[key]` deferred column expressions work correctly for VastDB predicates.
- `reader.read_all().to_pylist()` is the established pattern for converting VastDB results to dicts.
- `$distance` column is search-specific -- `_get_by_ids` does NOT return distance scores.

**From Story 2.2 (add_texts):**
- `pa.RecordBatch.from_pydict()` used for insertion -- not needed here.
- `json.dumps(m)` for metadata serialization on insert established; `json.loads()` for deserialization is in `_row_to_document` (already implemented in Story 2.3).
- Transaction pattern works correctly across both branches.

**From Story 2.1 (constructor):**
- `from_connection_params` is at line 95-140 -- `from_texts` should be placed after it.
- All instance attributes (`self._session`, `self._embedding`, `self._id_column`, etc.) established and working.

### Placement of new methods in vectorstores.py

Maintain logical grouping in the class:
1. `from_texts` classmethod: place after `from_connection_params` (line ~140), before `embeddings` property
2. `delete` template method: place after `similarity_search_by_vector` (line ~319)
3. `_delete_by_ids` hook: place after `delete`
4. `get_by_ids` template method: place after `_delete_by_ids`
5. `_get_by_ids` hook: place after `get_by_ids`

### What this story does NOT cover

- Unit tests -- **Story 2.5**
- Integration tests -- **Story 3.1**
- `_row_to_document` None safety for metadata -- **deferred to Story 3.1**

### Anti-patterns to avoid

- Do NOT add try/catch around `table.delete()` or `table.select()` -- SDK exceptions propagate as-is. [Source: architecture.md#Error Handling]
- Do NOT open a transaction in template methods (`delete`, `get_by_ids`) -- transactions belong in hook methods only. [Source: architecture.md#Transaction Pattern]
- Do NOT use `tx.bucket(name).schema(name).table(name)` -- use `self._get_table(tx)`. [Source: architecture.md#Anti-Patterns]
- Do NOT hardcode column names -- use `self._id_column`, `self._text_column`, etc. [Source: architecture.md#Anti-Patterns]
- Do NOT include the vector column in the `columns` list for `_get_by_ids` -- it's large and unused.
- Do NOT modify `__init__.py` -- it already re-exports correctly.
- Do NOT modify `pyproject.toml` -- no new dependencies needed.
- Do NOT create additional files -- single-file implementation.
- Do NOT reuse `_build_predicate` for delete/get predicates -- it's for `{"key": value}` filter dicts, not `isin()` predicates.

### Project Structure Notes

This story modifies exactly one file:

```
src/langchain_vastdb/vectorstores.py  # MODIFIED: add delete, _delete_by_ids, get_by_ids, _get_by_ids, from_texts. Update class docstring.
```

All other files remain unchanged. No structural variances expected.

### Architecture compliance summary

| Constraint | Source | What this story does |
|---|---|---|
| Template method pattern | architecture.md#Hook Method Signatures | `delete` delegates to `_delete_by_ids`, `get_by_ids` delegates to `_get_by_ids` |
| Canonical hook signatures | architecture.md#Hook Method Signatures | `_delete_by_ids(self, ids, *, tx=None) -> bool` and `_get_by_ids(self, ids, *, tx=None) -> list[dict]` |
| Transaction-in-hooks | architecture.md#Transaction Pattern | Transaction opened/closed inside hooks, not template methods |
| Optional `tx` reuse | architecture.md#Transaction Pattern | `tx` is keyword-only, used if provided |
| Cached table access | architecture.md#Table Access Pattern | `self._get_table(tx)` in both hooks |
| Configurable columns | architecture.md#Naming Patterns | Uses `self._id_column`, `self._text_column`, etc. |
| Error passthrough | architecture.md#Error Handling | No try/catch -- SDK errors propagate |
| Google-style docstrings | architecture.md#Naming Patterns | All public/protected methods |
| Type hints on all signatures | NFR16 | All method signatures typed |
| Single-file implementation | architecture.md#File Organization | Everything in `vectorstores.py` |
| Return plain Python types | architecture.md#Hook Method Signatures | Hooks return `bool` and `list[dict]`, not PyArrow |

### Testing standards (for this story)

No automated tests to write (Story 2.5). Validations:

1. `uv run ruff check .` exits with code 0 and zero warnings.
2. `uv run python -c "from langchain_vastdb import VastDBVectorStore"` succeeds.
3. `uv run pytest tests/unit_tests/ -v` does not error.

### References

- Story requirements and ACs: [Source: _bmad-output/planning-artifacts/epics.md#Story 2.4: Delete, Get by IDs & Factory Method]
- Hook method signatures: [Source: _bmad-output/planning-artifacts/architecture.md#Hook Method Signatures]
- Transaction pattern: [Source: _bmad-output/planning-artifacts/architecture.md#Transaction Pattern]
- PyArrow data conversion: [Source: _bmad-output/planning-artifacts/architecture.md#PyArrow Data Conversion Pattern]
- Error handling: [Source: _bmad-output/planning-artifacts/architecture.md#Error Handling]
- Import organization: [Source: _bmad-output/planning-artifacts/architecture.md#Import Organization]
- Previous story file: [Source: _bmad-output/implementation-artifacts/2-3-similarity-search-operations.md]
- Deferred work: [Source: _bmad-output/implementation-artifacts/deferred-work.md]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- All 7 tasks implemented in a single file: `src/langchain_vastdb/vectorstores.py`
- `from_texts` placed after `from_connection_params` (line ~140)
- `delete`, `_delete_by_ids`, `get_by_ids`, `_get_by_ids` placed after `similarity_search_by_vector`
- Ruff: 0 warnings. Import check: OK. Pytest: 0 errors (0 unit tests collected — expected, Story 2.5 adds tests).
- No new imports required; all types already in scope from Stories 2.1–2.3.

### File List

- `src/langchain_vastdb/vectorstores.py` — MODIFIED: added delete, _delete_by_ids, get_by_ids, _get_by_ids, from_texts; updated class docstring

### Review Findings

✅ Clean review — all layers passed. No findings (0 decision-needed, 0 patch, 0 deferred, 0 dismissed).