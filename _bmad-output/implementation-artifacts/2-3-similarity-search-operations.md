# Story 2.3: Similarity Search Operations

Status: done

## Story

As a developer,
I want to search for similar documents by text query, by vector, and with distance scores,
so that I can find relevant documents in my vector store using different search strategies.

## Acceptance Criteria

1. **Given** a VastDBVectorStore with indexed documents
   **When** `similarity_search(query="hello", k=4)` is called
   **Then** the query text is embedded using the configured Embeddings instance, `_vector_search` hook is called with the query vector, k, and predicate=None, and `_row_to_document` converts each result row to a LangChain `Document`
   **And** a list of up to k `Document` objects is returned, ordered by similarity

2. **Given** a VastDBVectorStore with indexed documents
   **When** `similarity_search_with_score(query="hello", k=4)` is called
   **Then** a list of `(Document, float)` tuples is returned, where each float is the distance score from `_vector_search`

3. **Given** a VastDBVectorStore with indexed documents
   **When** `similarity_search_by_vector(embedding=[0.1, 0.2, ...], k=4)` is called
   **Then** the pre-computed embedding vector is passed directly to `_vector_search` without re-embedding
   **And** results are returned as a list of `Document` objects

4. **Given** a search call with `filter={"category": "news"}`
   **When** the template method processes the filter
   **Then** the dict is converted to an ibis predicate expression before passing to `_vector_search` as the `predicate` parameter

5. **Given** the default `_vector_search` hook implementation
   **When** it is called with query_vector, k, and optional predicate
   **Then** it opens a transaction (or uses provided `tx`), gets the table, calls `table.vector_search(...)` with the query vector and k, applies the predicate if provided, reads the results into a list of dicts via `reader.read_all().to_pylist()`, and returns `list[tuple[dict, float]]` (row dict + distance score)

6. **Given** the default `_row_to_document` hook implementation
   **When** it is called with a row dict and optional score
   **Then** it extracts the text column value as `page_content`, deserializes the metadata column from JSON via `json.loads()`, and returns a `Document(page_content=text, metadata=metadata)`

7. **Given** the `_vector_search` and `_row_to_document` hook signatures
   **When** a subclass overrides them
   **Then** `_vector_search` matches: `_vector_search(self, query_vector, k, predicate=None, *, tx=None) -> list[tuple[dict, float]]`
   **And** `_row_to_document` matches: `_row_to_document(self, row, score=None) -> Document`

> **Error handling note:** VastDB SDK exceptions propagate as-is per Architecture Decision: Error Handling. No try/catch needed in `similarity_search` or `_vector_search`; meaningful contextual messages are only added at init boundaries.

## Tasks / Subtasks

- [x] **Task 1: Replace `similarity_search` stub with real template method (AC: #1, #4)**
  - [x] In `src/langchain_vastdb/vectorstores.py`, replace the `similarity_search` stub (currently raises `NotImplementedError` at line ~248-261) with the real template method.
  - [x] Add `import ibis` to imports (third-party block, after `import pyarrow as pa`).
  - [x] Implementation: embed query via `self._embedding.embed_query(query)`, extract `filter` from `**kwargs` via `kwargs.get("filter")`, convert filter dict to ibis predicate if present (see Dev Notes), call `self._vector_search(query_vector, k, predicate=predicate)`, convert results to Documents via `[self._row_to_document(row) for row, _ in results]`, return the list.
  - [x] Preserve the existing signature: `similarity_search(self, query: str, k: int = 4, **kwargs: Any) -> list[Document]`.

- [x] **Task 2: Implement `similarity_search_with_score` template method (AC: #2, #4)**
  - [x] Add `similarity_search_with_score` method after `similarity_search`.
  - [x] Signature: `similarity_search_with_score(self, query: str, k: int = 4, **kwargs: Any) -> list[tuple[Document, float]]`.
  - [x] Implementation: same as `similarity_search` (embed query, convert filter, call `_vector_search`), but return `[(self._row_to_document(row, score), score) for row, score in results]`.

- [x] **Task 3: Implement `similarity_search_by_vector` template method (AC: #3, #4)**
  - [x] Add `similarity_search_by_vector` method after `similarity_search_with_score`.
  - [x] Signature: `similarity_search_by_vector(self, embedding: list[float], k: int = 4, **kwargs: Any) -> list[Document]`.
  - [x] Implementation: skip embedding step, extract `filter` from `**kwargs`, convert filter to ibis predicate, call `self._vector_search(embedding, k, predicate=predicate)`, return `[self._row_to_document(row) for row, _ in results]`.

- [x] **Task 4: Implement `_build_predicate` helper for filter dict to ibis conversion (AC: #4)**
  - [x] Add a private method `_build_predicate(self, filter_dict: dict | None) -> ibis.Expr | None` that converts a LangChain filter dict to an ibis predicate expression.
  - [x] Implementation: if `filter_dict` is `None` or empty, return `None`. For each key-value pair, create `ibis._[key] == value` using ibis deferred column expressions. Combine multiple predicates with `&` (logical AND). Return the combined predicate.
  - [x] This is a private helper, not a hook -- subclasses that need custom filter logic override the entire template method or use typed metadata columns.

- [x] **Task 5: Implement `_vector_search` hook with default VastDB SDK logic (AC: #5, #7)**
  - [x] Add the `_vector_search` method with the **exact canonical signature**: `_vector_search(self, query_vector: list[float], k: int, predicate: ibis.Expr | None = None, *, tx: Transaction | None = None) -> list[tuple[dict, float]]`.
  - [x] Follow the transaction pattern exactly: if `tx` is provided, use it; otherwise open `with self._session.transaction() as new_tx:`. Use `self._get_table(tx_var)` for table access.
  - [x] Call `table.vector_search(vec=query_vector, columns=[self._id_column, self._text_column, self._metadata_column], limit=k, predicate=predicate)` to get a `RecordBatchReader`.
  - [x] Convert results: `reader.read_all().to_pylist()` to get a list of dicts.
  - [x] VastDB SDK returns a `$distance` column with the distance score. Extract it from each row dict: `score = row.pop("$distance", 0.0)`.
  - [x] Return `[(row, score) for row in rows]` after extracting the distance.

- [x] **Task 6: Implement `_row_to_document` hook (AC: #6, #7)**
  - [x] Add the `_row_to_document` method with the **exact canonical signature**: `_row_to_document(self, row: dict, score: float | None = None) -> Document`.
  - [x] Implementation: extract `page_content = row.get(self._text_column, "")`, deserialize metadata via `metadata = json.loads(row.get(self._metadata_column, "{}"))`, return `Document(page_content=page_content, metadata=metadata)`.
  - [x] Note: `_row_to_document` has NO `tx` parameter -- it's pure data conversion, no DB access.

- [x] **Task 7: Add Google-style docstrings with type hints (AC: all)**
  - [x] Add docstrings to all new methods: `similarity_search`, `similarity_search_with_score`, `similarity_search_by_vector`, `_build_predicate`, `_vector_search`, `_row_to_document`.
  - [x] Use Google-style format (Args, Returns).

- [x] **Task 8: Validate (AC: all)**
  - [x] Run `uv run ruff check .` -- must pass with zero warnings.
  - [x] Run `uv run python -c "from langchain_vastdb import VastDBVectorStore"` -- must succeed.
  - [x] Run `uv run pytest tests/unit_tests/ -v` -- must not error.

## Dev Notes

### This story replaces the `similarity_search` stub from Story 2.1

Story 2.1 left `similarity_search` as a stub raising `NotImplementedError` at line ~248-261. This story replaces it with the real implementation and adds `similarity_search_with_score`, `similarity_search_by_vector`, the `_vector_search` hook, and the `_row_to_document` hook. The `delete` and `get_by_ids` stubs remain -- that's Story 2.4.

### Single file: `src/langchain_vastdb/vectorstores.py`

All implementation goes in this one file. Do NOT create helper modules or utility files. [Source: _bmad-output/planning-artifacts/architecture.md#File Organization Patterns]

### New import needed for this story

Add to the third-party imports block (after `import pyarrow as pa`):

```python
import ibis
```

All other imports already exist from Stories 2.1 and 2.2 (`json`, `uuid`, `pa`, `vastdb`, `Document`, `Embeddings`, `VectorStore`, `TableMetadata`, `TableRef`, `Any`, `TYPE_CHECKING`, `ITable`, `Transaction`, `Iterable`).

[Source: _bmad-output/planning-artifacts/architecture.md#Import Organization]

### Template method pattern for search methods

All three search methods (`similarity_search`, `similarity_search_with_score`, `similarity_search_by_vector`) are **template methods** -- they orchestrate the flow but delegate actual DB access to `_vector_search` and data conversion to `_row_to_document`.

Flow:
1. `similarity_search`: embed query -> convert filter -> call `_vector_search` -> convert rows via `_row_to_document` -> return `list[Document]`
2. `similarity_search_with_score`: same, but return `list[tuple[Document, float]]` with scores
3. `similarity_search_by_vector`: skip embedding step -> convert filter -> call `_vector_search` -> convert rows -> return `list[Document]`

**Critical:** Template methods do NOT open transactions or touch the database directly. All DB access happens inside `_vector_search`. This keeps template methods clean and hooks self-contained.

[Source: _bmad-output/planning-artifacts/architecture.md#Transaction Pattern, #Hook Method Signatures]

### Filter dict to ibis predicate conversion

The base class converts LangChain `filter` dicts to ibis expressions using deferred column expressions. Use `ibis._[key] == value` for each key-value pair, combine with `&`:

```python
def _build_predicate(self, filter_dict: dict | None) -> ibis.Expr | None:
    if not filter_dict:
        return None
    predicates = [ibis._[key] == value for key, value in filter_dict.items()]
    result = predicates[0]
    for pred in predicates[1:]:
        result = result & pred
    return result
```

**Note:** `ibis._` is a deferred expression builder. `ibis._["column"]` creates a column reference resolved when the predicate is applied to a table. This works for VastDB SDK's `table.vector_search(predicate=...)`.

**Scope limitation:** The base class supports simple equality filters on table columns. For JSON metadata filtering (extracting values from the JSON metadata string column), subclasses should override `_vector_search` to implement custom predicate logic. This matches the architecture decision: "JSON default in base class, typed columns via subclass hook overrides."

[Source: _bmad-output/planning-artifacts/architecture.md#Filter / Predicate Passthrough]

### `_vector_search` hook -- exact canonical signature

```python
def _vector_search(
    self,
    query_vector: list[float],
    k: int,
    predicate: ibis.Expr | None = None,
    *,
    tx: Transaction | None = None,
) -> list[tuple[dict, float]]:
```

**Rules:**
- `tx` is keyword-only (after `*`).
- If `tx` is provided, use it. If `None`, open a new transaction.
- Always use `self._get_table(tx)` -- never navigate bucket -> schema -> table manually.
- Return `list[tuple[dict, float]]` -- row dict + distance score.

[Source: _bmad-output/planning-artifacts/architecture.md#Hook Method Signatures, #Transaction Pattern]

### VastDB SDK `table.vector_search()` call

```python
reader = table.vector_search(
    vec=query_vector,
    columns=[self._id_column, self._text_column, self._metadata_column],
    limit=k,
    predicate=predicate,  # Optional ibis expression, passed as-is
)
rows = reader.read_all().to_pylist()
```

**Important:** The VastDB SDK returns a `$distance` column in the results containing the distance score. Extract it from each row dict via `row.pop("$distance", 0.0)` before passing the row to `_row_to_document`.

**Do NOT include the vector column in the `columns` list** -- it's large and unnecessary for the return value. Only select id, text, and metadata.

[Source: _bmad-output/planning-artifacts/research/technical-vast-langchain-vectorstore-research-2026-04-07.md#VastDB SDK API]

### `_row_to_document` hook -- exact canonical signature

```python
def _row_to_document(
    self,
    row: dict,
    score: float | None = None,
) -> Document:
```

**Rules:**
- NO `tx` parameter -- this is pure data conversion, no DB access.
- Extract text from `row[self._text_column]`, deserialize metadata from JSON via `json.loads(row[self._metadata_column])`.
- Return `Document(page_content=text, metadata=metadata)`.
- The `score` parameter is available for subclasses that want to include distance in the Document metadata -- the base class ignores it.

[Source: _bmad-output/planning-artifacts/architecture.md#Hook Method Signatures]

### Transaction pattern for `_vector_search`

Follow the exact transaction pattern from the architecture:

```python
def _vector_search(self, query_vector, k, predicate=None, *, tx=None):
    if tx is not None:
        table = self._get_table(tx)
        # do search, return results
    else:
        with self._session.transaction() as new_tx:
            table = self._get_table(new_tx)
            # do search, return results
```

To avoid code duplication, extract the search logic into a local helper or structure to minimize duplication.

[Source: _bmad-output/planning-artifacts/architecture.md#Transaction Pattern]

### Previous story intelligence

**From Story 2.2 (add_texts / _insert_vectors):**
- Pattern established: template method (`add_texts`) handles orchestration, hook (`_insert_vectors`) handles DB access.
- `pa.RecordBatch.from_pydict()` used for insertion -- no explicit schema needed.
- `json.dumps(m)` for metadata serialization on insert. This story needs `json.loads()` for deserialization on read.
- Transaction pattern works: `if tx is not None` branch + `with self._session.transaction() as new_tx` branch.
- All imports already in place except `ibis`.

**From Story 2.1 (constructor):**
- `self._session`, `self._embedding`, `self._get_table()`, column attributes all work.
- `self._embedding.embed_query(query)` is the method for embedding a single query string (vs `embed_documents` for batches).
- `similarity_search` stub at lines 248-261 needs to be replaced.

**From Story 2.2 review (deferred work):**
- Float64 inference in RecordBatch deferred to integration tests -- not relevant here.

### What this story does NOT cover

- `delete`, `get_by_ids`, `from_texts` -- **Story 2.4**
- `_delete_by_ids`, `_get_by_ids` hooks -- **Story 2.4**
- Unit tests -- **Story 2.5**

### Anti-patterns to avoid

- Do NOT add try/catch around `table.vector_search()` or `self._embedding.embed_query()` -- SDK exceptions propagate as-is. [Source: architecture.md#Error Handling]
- Do NOT open a transaction in template methods (`similarity_search`, etc.) -- transactions belong in hook methods only. [Source: architecture.md#Transaction Pattern]
- Do NOT use `tx.bucket(name).schema(name).table(name)` -- use `self._get_table(tx)`. [Source: architecture.md#Anti-Patterns]
- Do NOT hardcode column names -- use `self._text_column`, `self._metadata_column`, etc. [Source: architecture.md#Anti-Patterns]
- Do NOT include the vector column in the `columns` list for search results -- it's large and unused.
- Do NOT modify `__init__.py` -- it already re-exports correctly.
- Do NOT modify `pyproject.toml` -- `ibis-framework` is a transitive dependency via `vastdb`.
- Do NOT create additional files -- single-file implementation.

### Project Structure Notes

This story modifies exactly one file:

```
src/langchain_vastdb/vectorstores.py  # MODIFIED: similarity_search stub -> real impl + _vector_search hook + _row_to_document hook + similarity_search_with_score + similarity_search_by_vector + _build_predicate helper
```

All other files remain unchanged. No structural variances expected.

### Architecture compliance summary

| Constraint | Source | What this story does |
|---|---|---|
| Template method pattern | architecture.md#Hook Method Signatures | `similarity_search`/`_with_score`/`_by_vector` orchestrate, `_vector_search` does DB work |
| Canonical hook signatures | architecture.md#Hook Method Signatures | `_vector_search(self, query_vector, k, predicate=None, *, tx=None)` and `_row_to_document(self, row, score=None)` |
| Transaction-in-hooks | architecture.md#Transaction Pattern | Transaction opened/closed inside `_vector_search`, not template methods |
| Optional `tx` reuse | architecture.md#Transaction Pattern | `tx` is keyword-only, used if provided |
| Dict-to-ibis filter | architecture.md#Filter/Predicate Passthrough | Base class converts filter dict to ibis expression via `_build_predicate` |
| JSON metadata default | architecture.md#Metadata Serialization | `json.loads()` for deserialization in `_row_to_document` |
| Cached table access | architecture.md#Table Access Pattern | `self._get_table(tx)` in `_vector_search` |
| Configurable columns | architecture.md#Naming Patterns | Uses `self._id_column`, `self._text_column`, etc. |
| Error passthrough | architecture.md#Error Handling | No try/catch -- SDK errors propagate |
| Google-style docstrings | architecture.md#Naming Patterns | All public/protected methods |
| Type hints on all signatures | NFR16 | All method signatures typed |
| Single-file implementation | architecture.md#File Organization | Everything in `vectorstores.py` |

### Testing standards (for this story)

No automated tests to write (Story 2.5). Validations:

1. `uv run ruff check .` exits with code 0 and zero warnings.
2. `uv run python -c "from langchain_vastdb import VastDBVectorStore"` succeeds.
3. `uv run pytest tests/unit_tests/ -v` does not error.

### References

- Story requirements and ACs: [Source: _bmad-output/planning-artifacts/epics.md#Story 2.3: Similarity Search Operations]
- Hook method signatures: [Source: _bmad-output/planning-artifacts/architecture.md#Hook Method Signatures]
- Transaction pattern: [Source: _bmad-output/planning-artifacts/architecture.md#Transaction Pattern]
- Filter/predicate passthrough: [Source: _bmad-output/planning-artifacts/architecture.md#Filter / Predicate Passthrough]
- PyArrow data conversion: [Source: _bmad-output/planning-artifacts/architecture.md#PyArrow Data Conversion Pattern]
- Metadata serialization: [Source: _bmad-output/planning-artifacts/architecture.md#Metadata Serialization]
- Error handling: [Source: _bmad-output/planning-artifacts/architecture.md#Error Handling]
- Import organization: [Source: _bmad-output/planning-artifacts/architecture.md#Import Organization]
- VastDB SDK vector search API: [Source: _bmad-output/planning-artifacts/research/technical-vast-langchain-vectorstore-research-2026-04-07.md]
- Previous story file: [Source: _bmad-output/implementation-artifacts/2-2-add-texts-and-document-insertion.md]
- Deferred work: [Source: _bmad-output/implementation-artifacts/deferred-work.md]

## Dev Agent Record

### Agent Model Used

claude-opus-4.6

### Debug Log References

None -- clean implementation, no debugging required.

### Completion Notes List

- All 8 tasks completed in a single pass with no errors.
- `similarity_search` template method: embeds query via `embed_query`, converts filter to ibis predicate via `_build_predicate`, delegates to `_vector_search`, converts rows via `_row_to_document`.
- `similarity_search_with_score`: same flow, returns `list[tuple[Document, float]]` with distance scores.
- `similarity_search_by_vector`: skips embedding step, passes pre-computed vector directly.
- `_build_predicate` helper: converts `{"key": "value"}` dicts to `ibis._[key] == value` predicates combined with `&`.
- `_vector_search` hook: follows exact transaction pattern, calls `table.vector_search(vec, columns, limit, predicate)`, extracts `$distance` score from each row.
- `_row_to_document` hook: extracts text from configured column, deserializes JSON metadata via `json.loads`, returns `Document`.
- Added `_do_vector_search` private helper to avoid code duplication in the transaction branches.
- No try/catch -- SDK exceptions propagate per architecture decision.
- `uv run ruff check .` passed with zero warnings.
- Import succeeds, pytest runs cleanly (0 tests collected, as expected -- tests are Story 2.5).

### File List

- `src/langchain_vastdb/vectorstores.py` -- MODIFIED: replaced similarity_search stub with real implementation, added similarity_search_with_score, similarity_search_by_vector, _build_predicate, _vector_search, _do_vector_search, _row_to_document. Added `import ibis`. Updated class docstring.

### Review Findings

- [x] [Review][Defer] Metadata None safety in _row_to_document: if a row has None for metadata column (e.g., inserted externally), json.loads(None) raises TypeError [src/langchain_vastdb/vectorstores.py:_row_to_document] -- deferred, base class _insert_vectors always writes json.dumps({}); will be validated in integration tests (Story 3.1).

## Change Log

- 2026-04-09: Story 2.3 created by create-story workflow -- comprehensive developer guide for similarity search operations.
- 2026-04-09: All 8 tasks implemented in a single pass. similarity_search, similarity_search_with_score, similarity_search_by_vector template methods, _vector_search and _row_to_document hooks, _build_predicate helper. Status set to review.
- 2026-04-09: Code review iteration 1 -- clean review, 0 decision-needed, 0 patch, 1 defer, 0 dismissed. Status set to done.
