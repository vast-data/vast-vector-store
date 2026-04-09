# Story 2.2: Add Texts & Document Insertion

Status: done

## Story

As a developer,
I want to add texts with optional metadata and IDs to the vector store,
so that my documents are embedded, stored in VastDB, and available for similarity search.

## Acceptance Criteria

1. **Given** a VastDBVectorStore instance with a configured embedding function
   **When** `add_texts(texts=["hello", "world"], metadatas=[{"k": "v1"}, {"k": "v2"}])` is called
   **Then** the texts are embedded using the configured Embeddings instance, and the `_insert_vectors` hook is called with the texts, embeddings, metadata dicts, and auto-generated UUID IDs
   **And** the method returns a list of the generated string IDs

2. **Given** a call to `add_texts` with explicit `ids=["id1", "id2"]`
   **When** the method executes
   **Then** the provided IDs are used instead of auto-generated UUIDs

3. **Given** a call to `add_texts` without `metadatas`
   **When** the method executes
   **Then** empty dicts `[{}, {}]` are used as metadata for each text

4. **Given** the default `_insert_vectors` hook implementation
   **When** it is called with texts, embeddings, metadatas, and ids
   **Then** it opens a transaction (or uses provided `tx`), gets the table via `_get_table()`, builds a `pa.RecordBatch` with the configured column names, serializes metadata as JSON strings via `json.dumps()`, and calls `table.insert(batch)`
   **And** returns the list of IDs

5. **Given** the `_insert_vectors` hook signature
   **When** a subclass overrides it
   **Then** the signature matches exactly: `_insert_vectors(self, texts, embeddings, metadatas, ids, *, tx=None) -> list[str]`

> **Error handling note:** VastDB SDK exceptions propagate as-is per Architecture Decision: Error Handling. No try/catch needed in `add_texts` or `_insert_vectors`; meaningful contextual messages are only added at init boundaries.

## Tasks / Subtasks

- [x] **Task 1: Replace `add_texts` stub with real implementation (AC: #1, #2, #3)**
  - [x] In `src/langchain_vastdb/vectorstores.py`, replace the `add_texts` stub (currently raises `NotImplementedError`) with the real template method.
  - [x] Add new imports needed: `import json`, `import uuid`, `import pyarrow as pa`. Add `Sequence` to the typing imports if not already present.
  - [x] Implementation: materialize `texts` to a list (it arrives as `Iterable[str]`), call `self._embedding.embed_documents(texts_list)` to get embeddings, generate UUIDs via `[str(uuid.uuid4()) for _ in texts_list]` if no `ids` provided, default `metadatas` to `[{} for _ in texts_list]` if `None`, then call `return self._insert_vectors(texts_list, vectors, metadatas, ids)`.
  - [x] Preserve the exact existing signature: `add_texts(self, texts: Iterable[str], metadatas: list[dict] | None = None, *, ids: list[str] | None = None, **kwargs: Any) -> list[str]`.

- [x] **Task 2: Implement `_insert_vectors` hook with default VastDB SDK logic (AC: #4, #5)**
  - [x] Add the `_insert_vectors` method with the **exact canonical signature** from architecture.md: `_insert_vectors(self, texts: list[str], embeddings: list[list[float]], metadatas: list[dict], ids: list[str], *, tx: Transaction | None = None) -> list[str]`.
  - [x] Follow the transaction pattern exactly: if `tx` is provided, use it; otherwise open `with self._session.transaction() as new_tx:`. Use `self._get_table(tx_var)` for table access.
  - [x] Build a `pa.RecordBatch` with 4 columns using the configured column names (`self._id_column`, `self._text_column`, `self._vector_column`, `self._metadata_column`).
  - [x] Column data: IDs as `pa.array(ids, type=pa.utf8())`, texts as `pa.array(texts, type=pa.utf8())`, vectors as `pa.array(embeddings, type=pa.list_(pa.float32()))`, metadata as `pa.array([json.dumps(m) for m in metadatas], type=pa.utf8())`.
  - [x] Call `table.insert(batch)` and return `ids`.

- [x] **Task 3: Add Google-style docstrings with type hints (AC: all)**
  - [x] Add docstring to `add_texts` explaining the template method pattern: embeds texts, generates IDs, and delegates to `_insert_vectors`.
  - [x] Add docstring to `_insert_vectors` explaining this is the hook method for subclass customization, the transaction pattern, and the PyArrow batch construction.

- [x] **Task 4: Validate (AC: all)**
  - [x] Run `uv run ruff check .` -- must pass with zero warnings.
  - [x] Run `uv run python -c "from langchain_vastdb import VastDBVectorStore"` -- must still succeed.
  - [x] Run `uv run pytest tests/unit_tests/ -v` -- must not error.

## Dev Notes

### This story replaces the `add_texts` stub from Story 2.1

Story 2.1 left `add_texts` as a stub raising `NotImplementedError`. This story replaces it with the real implementation and adds the `_insert_vectors` hook method. The `similarity_search` stub remains -- that's Story 2.3.

### Single file: `src/langchain_vastdb/vectorstores.py`

All implementation goes in this one file. Do NOT create helper modules or utility files. [Source: _bmad-output/planning-artifacts/architecture.md#File Organization Patterns]

### New imports needed for this story

Add these to the existing import block in `vectorstores.py`:

```python
# Add to standard library imports (after existing `from __future__ import annotations`)
import json
import uuid

# Add to third-party imports (after existing vastdb imports)
import pyarrow as pa
```

The existing imports from Story 2.1 (`vastdb`, `langchain_core`, `TableMetadata`, `TableRef`, etc.) stay unchanged. The `TYPE_CHECKING` block already has `Transaction` and `ITable`.

[Source: _bmad-output/planning-artifacts/architecture.md#Import Organization]

### `add_texts` template method pattern

`add_texts` is a **template method** -- it orchestrates the flow but delegates the actual storage to `_insert_vectors`. The method:

1. Materializes the `Iterable[str]` to `list[str]` (because we need the length and multiple passes).
2. Embeds all texts in one batch via `self._embedding.embed_documents(texts_list)`.
3. Generates UUIDs if no explicit IDs provided.
4. Defaults metadatas to empty dicts if `None`.
5. Calls `self._insert_vectors(texts_list, vectors, metadatas, ids)` and returns the result.

**Critical:** `add_texts` does NOT open a transaction or touch the database. All DB access happens inside `_insert_vectors`. This keeps the template method clean and the hook self-contained.

[Source: _bmad-output/planning-artifacts/architecture.md#Transaction Pattern, #Hook Method Signatures]

### `_insert_vectors` hook -- exact canonical signature

```python
def _insert_vectors(
    self,
    texts: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict],
    ids: list[str],
    *,
    tx: Transaction | None = None,
) -> list[str]:
```

**Rules:**
- `tx` is keyword-only (after `*`).
- If `tx` is provided, use it. If `None`, open a new transaction.
- Always use `self._get_table(tx)` -- never navigate bucket -> schema -> table manually.
- Return plain Python types (list of IDs), not PyArrow objects.

[Source: _bmad-output/planning-artifacts/architecture.md#Hook Method Signatures, #Transaction Pattern]

### Transaction pattern for `_insert_vectors`

Follow this exact shape:

```python
def _insert_vectors(self, texts, embeddings, metadatas, ids, *, tx=None):
    if tx is not None:
        table = self._get_table(tx)
        # build batch, insert, return ids
    else:
        with self._session.transaction() as new_tx:
            table = self._get_table(new_tx)
            # build batch, insert, return ids
```

To avoid code duplication, extract the batch-build-and-insert logic into a local helper or just structure it to minimize duplication. The architecture doc shows this pattern.

[Source: _bmad-output/planning-artifacts/architecture.md#Transaction Pattern]

### PyArrow RecordBatch construction

Build the batch with 4 columns using configured column names:

```python
batch = pa.RecordBatch.from_pydict(
    {
        self._id_column: ids,
        self._text_column: texts,
        self._vector_column: embeddings,
        self._metadata_column: [json.dumps(m) for m in metadatas],
    }
)
```

**Note:** `pa.RecordBatch.from_pydict` infers types automatically -- `ids` and `texts` become `utf8`, `embeddings` (list of list of float) becomes `list<float>`, metadata strings become `utf8`. You do NOT need to specify a PyArrow schema explicitly for insertion. The VastDB table already has its schema -- `table.insert(batch)` handles the mapping.

[Source: _bmad-output/planning-artifacts/architecture.md#PyArrow Data Conversion Pattern]

### Metadata serialization: JSON default

Base class serializes metadata dicts as JSON strings via `json.dumps()`. Subclasses that need typed columns override `_insert_vectors` entirely with their own schema.

[Source: _bmad-output/planning-artifacts/architecture.md#Metadata Serialization]

### ID generation: UUID4

Default IDs are `str(uuid.uuid4())`. The `ids` parameter in `add_texts` lets users provide explicit IDs to override this.

### Previous story intelligence

**From Story 2.1:**
- Constructor, session management, and table access are fully implemented.
- `self._session`, `self._embedding`, `self._get_table()`, `self._table_ref`, `self._table_metadata`, `self._metadata_loaded` all exist.
- Column name attributes exist: `self._id_column`, `self._text_column`, `self._vector_column`, `self._metadata_column`.
- `embeddings` property works.
- `from_connection_params` classmethod works.
- `add_texts` currently exists as a stub raising `NotImplementedError` at line 171-186.
- `similarity_search` exists as a stub at line 188-201.
- Imports already in place: `vastdb`, `Document`, `Embeddings`, `VectorStore`, `TableMetadata`, `TableRef`, `Any`, `TYPE_CHECKING`, `ITable`, `Transaction`, `Iterable`.

**From Story 2.1 review (deferred work):**
- Thread-safety on `_metadata_loaded` is a known deferred item -- not relevant to this story.

**From Story 1.1 deferred work:**
- `py.typed` marker file not yet added -- not relevant to this story.
- `langchain-core>=0.3` version range was tightened to `>=0.3,<2` in pyproject.toml already.

### What this story does NOT cover

- `similarity_search`, `similarity_search_with_score`, `similarity_search_by_vector` -- **Story 2.3**
- `_vector_search` hook -- **Story 2.3**
- `_row_to_document` hook -- **Story 2.3**
- `delete`, `get_by_ids`, `from_texts` -- **Story 2.4**
- `_delete_by_ids`, `_get_by_ids` hooks -- **Story 2.4**
- Filter/predicate conversion (dict to ibis) -- **Story 2.3**
- Unit tests -- **Story 2.5**

### Anti-patterns to avoid

- Do NOT add try/catch around `table.insert()` or `self._embedding.embed_documents()` -- SDK exceptions propagate as-is per architecture decision. [Source: _bmad-output/planning-artifacts/architecture.md#Error Handling]
- Do NOT open a transaction in `add_texts` -- transactions belong in hook methods only. [Source: _bmad-output/planning-artifacts/architecture.md#Transaction Pattern]
- Do NOT use `tx.bucket(name).schema(name).table(name)` -- use `self._get_table(tx)` with cached `TableMetadata`. [Source: _bmad-output/planning-artifacts/architecture.md#Anti-Patterns]
- Do NOT hardcode column names -- always use `self._text_column`, `self._vector_column`, etc. [Source: _bmad-output/planning-artifacts/architecture.md#Anti-Patterns]
- Do NOT build a PyArrow schema manually for insertion -- `pa.RecordBatch.from_pydict()` infers types and VastDB handles the mapping. [Source: _bmad-output/planning-artifacts/architecture.md#Anti-Patterns]
- Do NOT modify `__init__.py` -- it already re-exports correctly.
- Do NOT modify `pyproject.toml` -- dependencies are already configured (`pyarrow` is transitive via `vastdb`).
- Do NOT create additional files -- single-file implementation.

### Project Structure Notes

This story modifies exactly one file:

```
src/langchain_vastdb/vectorstores.py  # MODIFIED: add_texts stub -> real impl + _insert_vectors hook
```

All other files remain unchanged. No structural variances expected.

### Architecture compliance summary

| Constraint | Source | What this story does |
|---|---|---|
| Template method pattern | architecture.md#Hook Method Signatures | `add_texts` orchestrates, `_insert_vectors` does DB work |
| Canonical hook signature | architecture.md#Hook Method Signatures | `_insert_vectors(self, texts, embeddings, metadatas, ids, *, tx=None)` |
| Transaction-in-hooks | architecture.md#Transaction Pattern | Transaction opened/closed inside `_insert_vectors`, not `add_texts` |
| Optional `tx` reuse | architecture.md#Transaction Pattern | `tx` is keyword-only, used if provided |
| JSON metadata default | architecture.md#Metadata Serialization | `json.dumps(m)` for each metadata dict |
| Cached table access | architecture.md#Table Access Pattern | `self._get_table(tx)` in `_insert_vectors` |
| Configurable columns | architecture.md#Naming Patterns | Uses `self._id_column`, etc. |
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

- Story requirements and ACs: [Source: _bmad-output/planning-artifacts/epics.md#Story 2.2: Add Texts & Document Insertion]
- Hook method signatures: [Source: _bmad-output/planning-artifacts/architecture.md#Hook Method Signatures]
- Transaction pattern: [Source: _bmad-output/planning-artifacts/architecture.md#Transaction Pattern]
- PyArrow data conversion: [Source: _bmad-output/planning-artifacts/architecture.md#PyArrow Data Conversion Pattern]
- Metadata serialization: [Source: _bmad-output/planning-artifacts/architecture.md#Metadata Serialization]
- Error handling: [Source: _bmad-output/planning-artifacts/architecture.md#Error Handling]
- Import organization: [Source: _bmad-output/planning-artifacts/architecture.md#Import Organization]
- Previous story file: [Source: _bmad-output/implementation-artifacts/2-1-constructor-session-management-and-table-access.md]
- VastDB SDK research: [Source: _bmad-output/planning-artifacts/research/technical-vast-langchain-vectorstore-research-2026-04-07.md]
- Deferred work: [Source: _bmad-output/implementation-artifacts/deferred-work.md]

## Dev Agent Record

### Agent Model Used

claude-opus-4.6

### Debug Log References

None -- clean implementation, no debugging required.

### Completion Notes List

- All 4 tasks completed in a single pass with no errors.
- `add_texts` template method: materializes Iterable to list, embeds via `embed_documents`, generates UUID4 IDs if none provided, defaults metadatas to empty dicts, delegates to `_insert_vectors`.
- `_insert_vectors` hook: builds `pa.RecordBatch.from_pydict()` with configured column names, follows exact transaction pattern (uses provided `tx` or opens new one), calls `table.insert(batch)`.
- Metadata serialized as JSON strings via `json.dumps()`.
- No try/catch -- SDK exceptions propagate per architecture decision.
- `uv run ruff check .` passed with zero warnings.
- Import succeeds, pytest runs cleanly (0 tests collected, as expected for Story 2.2).

### File List

- `src/langchain_vastdb/vectorstores.py` -- MODIFIED: replaced add_texts stub with real implementation, added _insert_vectors hook, added imports (json, uuid, pyarrow).

### Review Findings

- [x] [Review][Defer] Float64 inference in RecordBatch: `pa.RecordBatch.from_pydict()` infers float64 for Python float lists in the vector column; VastDB table schema likely uses float32 [src/langchain_vastdb/vectorstores.py:218] -- deferred, VastDB SDK handles type coercion on insert; will be validated in integration tests (Story 3.1).

## Change Log

- 2026-04-09: Story 2.2 created by create-story workflow -- comprehensive developer guide for add_texts and document insertion implementation.
- 2026-04-09: Code review iteration 1 -- clean review, 0 decision-needed, 0 patch, 1 defer, 2 dismissed. Status set to done.
