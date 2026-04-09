# Story 2.1: Constructor, Session Management & Table Access

Status: review

## Story

As a developer,
I want to instantiate VastDBVectorStore with either a pre-built session or connection parameters, configure column names and table targeting, and have efficient table access via cached metadata,
so that I can connect to my VAST cluster and the store is ready for operations.

## Acceptance Criteria

1. **Given** a developer with a pre-built `vastdb.Session`
   **When** they instantiate `VastDBVectorStore(embedding=emb, session=session, bucket="b", schema="s", table_name="t")`
   **Then** the store is created with the session stored as `_session`, a `TableRef` for the specified bucket/schema/table, and a `TableMetadata` instance for cached access

2. **Given** a developer with VAST connection parameters
   **When** they call `VastDBVectorStore.from_connection_params(embedding=emb, endpoint="...", access_key="...", secret_key="...", bucket="b", schema="s", table_name="t")`
   **Then** a `vastdb.Session` is created internally using `vastdb.connect()` and the store is instantiated with that session

3. **Given** a VastDBVectorStore instance
   **When** `_get_table(tx)` is called for the first time
   **Then** it calls `self._table_metadata.load(tx)` to load metadata, then returns `tx.table_from_metadata(self._table_metadata)`

4. **Given** a VastDBVectorStore instance where `_get_table(tx)` has been called before
   **When** `_get_table(tx)` is called again (with a new transaction)
   **Then** it skips the `load()` call and directly returns `tx.table_from_metadata(self._table_metadata)` using cached metadata

5. **Given** a VastDBVectorStore instance
   **When** `invalidate_table_cache()` is called
   **Then** the cached metadata is reset and the next `_get_table()` call will reload from the database

6. **Given** a VastDBVectorStore constructor call with custom column names
   **When** `id_column="doc_id"`, `text_column="content"`, `vector_column="emb"`, `metadata_column="meta"` are passed
   **Then** the store uses those column names for all operations instead of the defaults ("id", "text", "vector", "metadata")

7. **Given** a VastDBVectorStore instance
   **When** the `embeddings` property is accessed
   **Then** it returns the `Embeddings` instance provided at construction time

8. **Given** a constructor call with connection parameters
   **When** credentials (access_key, secret_key) are provided
   **Then** credentials are never logged, serialized, stored in instance attributes accessible via public API, or included in error messages

## Tasks / Subtasks

- [x] **Task 1: Replace the stub class with the full constructor (AC: #1, #6, #7)**
  - [x] Open `src/langchain_vastdb/vectorstores.py` and replace the stub class with the real `VastDBVectorStore` implementation.
  - [x] Add all required imports (see Dev Notes > Canonical imports).
  - [x] Implement `__init__` with these parameters: `embedding: Embeddings`, `session: vastdb.Session`, `bucket: str`, `schema: str`, `table_name: str`, `id_column: str = "id"`, `text_column: str = "text"`, `vector_column: str = "vector"`, `metadata_column: str = "metadata"`.
  - [x] Store `embedding` as `self._embedding`, session as `self._session`.
  - [x] Store column names as `self._id_column`, `self._text_column`, `self._vector_column`, `self._metadata_column`.
  - [x] Create `self._table_ref = TableRef(bucket=bucket, schema=schema, table=table_name)`.
  - [x] Create `self._table_metadata = TableMetadata(ref=self._table_ref)`.
  - [x] Set `self._metadata_loaded = False`.
  - [x] Implement the `embeddings` property that returns `self._embedding`.

- [x] **Task 2: Implement `from_connection_params` classmethod (AC: #2, #8)**
  - [x] Add `from_connection_params(cls, embedding, endpoint, access_key, secret_key, bucket, schema, table_name, **kwargs) -> VastDBVectorStore` classmethod.
  - [x] Inside, call `session = vastdb.connect(endpoint=endpoint, access_key=access_key, secret_key=secret_key)`.
  - [x] Return `cls(embedding=embedding, session=session, bucket=bucket, schema=schema, table_name=table_name, **kwargs)`.
  - [x] Do NOT store `endpoint`, `access_key`, or `secret_key` as instance attributes.

- [x] **Task 3: Implement `_get_table` and `invalidate_table_cache` (AC: #3, #4, #5)**
  - [x] Implement `_get_table(self, tx: Transaction) -> ITable` following the exact pattern from architecture.md (see Dev Notes > Table access pattern).
  - [x] Implement `invalidate_table_cache(self) -> None` that resets `self._metadata_loaded = False` and recreates `self._table_metadata = TableMetadata(ref=self._table_ref)`.

- [x] **Task 4: Add stub abstract method implementations to satisfy VectorStore (AC: all)**
  - [x] Add `add_texts` method stub that raises `NotImplementedError("Implemented in Story 2.2")`.
  - [x] Add `similarity_search` method stub that raises `NotImplementedError("Implemented in Story 2.3")`.
  - [x] These are required because `VectorStore` has abstract methods. Without them, instantiation fails. They will be replaced in Stories 2.2 and 2.3.
  - [x] Add Google-style docstrings on all stubs indicating they are placeholders.

- [x] **Task 5: Add Google-style docstrings with type hints (AC: all)**
  - [x] Add class-level docstring explaining VastDBVectorStore, its Template Method architecture, and the 5 hook methods.
  - [x] Add docstrings to `__init__`, `from_connection_params`, `_get_table`, `invalidate_table_cache`, and the `embeddings` property.
  - [x] Ensure all public and protected method signatures have type hints.

- [x] **Task 6: Validate (AC: all)**
  - [x] Run `uv run ruff check .` -- must pass with zero warnings.
  - [x] Run `uv run python -c "from langchain_vastdb import VastDBVectorStore; print(VastDBVectorStore)"` -- must still succeed.
  - [x] Run `uv run pytest tests/unit_tests/ -v` -- must pass (no tests yet, but should not error).
  - [x] Verify `from_connection_params` is accessible: `uv run python -c "from langchain_vastdb import VastDBVectorStore; print(hasattr(VastDBVectorStore, 'from_connection_params'))"` should print `True`.

## Dev Notes

### This is the first implementation story -- Epic 2 begins here

This story transforms the stub `VastDBVectorStore` from Story 1.1 into a real class with constructor, session management, and table access. The class will NOT yet have functional `add_texts`, `similarity_search`, etc. -- those arrive in Stories 2.2-2.4. But after this story, the class is instantiable with a real (or mocked) `vastdb.Session`.

### Single file: `src/langchain_vastdb/vectorstores.py`

All implementation goes in this one file. Do NOT create helper modules, utility files, or split the class. The architecture mandates a single-file implementation (~300-500 LOC). [Source: _bmad-output/planning-artifacts/architecture.md#File Organization Patterns]

### Canonical imports

Use this exact import block at the top of `vectorstores.py`:

```python
"""VastDBVectorStore -- LangChain VectorStore backed by VAST Database."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

import vastdb
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore
from vastdb.table_metadata import TableMetadata, TableRef

if TYPE_CHECKING:
    from vastdb.table import ITable
    from vastdb.transaction import Transaction
```

Notes:
- `from __future__ import annotations` enables PEP 604 union syntax (`X | None`) on Python 3.10.
- Use `TYPE_CHECKING` guard for imports only needed in type annotations to avoid heavy imports at runtime.
- `ITable` is the return type of `tx.table_from_metadata()`. Import it under TYPE_CHECKING.
- `Transaction` is used only in type hints for `_get_table`. Import under TYPE_CHECKING.
- Do NOT import `ibis`, `pyarrow`, `json`, or `uuid` yet -- those are needed in Stories 2.2-2.4.

[Source: _bmad-output/planning-artifacts/architecture.md#Import Organization]

### Constructor design: session-first

The primary constructor accepts a `vastdb.Session` object. The `from_connection_params` classmethod is a convenience factory.

```python
class VastDBVectorStore(VectorStore):
    def __init__(
        self,
        embedding: Embeddings,
        session: vastdb.Session,
        bucket: str,
        schema: str,
        table_name: str,
        id_column: str = "id",
        text_column: str = "text",
        vector_column: str = "vector",
        metadata_column: str = "metadata",
    ) -> None:
```

[Source: _bmad-output/planning-artifacts/architecture.md#Constructor Design]

### `from_connection_params` classmethod

```python
@classmethod
def from_connection_params(
    cls,
    embedding: Embeddings,
    endpoint: str,
    access_key: str,
    secret_key: str,
    bucket: str,
    schema: str,
    table_name: str,
    **kwargs: Any,
) -> VastDBVectorStore:
    session = vastdb.connect(
        endpoint=endpoint, access_key=access_key, secret_key=secret_key
    )
    return cls(
        embedding=embedding, session=session, bucket=bucket,
        schema=schema, table_name=table_name, **kwargs,
    )
```

The `**kwargs` forwards optional parameters like custom column names to `__init__`. Do NOT store `endpoint`, `access_key`, or `secret_key` as instance attributes -- they must not be accessible after construction.

[Source: _bmad-output/planning-artifacts/architecture.md#Constructor Design]

### Table access pattern (non-interactive workflow)

This is the exact pattern from the architecture document. Follow it precisely:

```python
def _get_table(self, tx: Transaction) -> ITable:
    """Get table using cached metadata (non-interactive workflow).

    First call loads metadata via md.load(tx). Subsequent calls reuse
    cached metadata via tx.table_from_metadata(), skipping
    bucket->schema->table round trips entirely.
    """
    if not self._metadata_loaded:
        self._table_metadata.load(tx)
        self._metadata_loaded = True
    return tx.table_from_metadata(self._table_metadata)

def invalidate_table_cache(self) -> None:
    """Invalidate cached table metadata. Call after create/drop operations."""
    self._metadata_loaded = False
    self._table_metadata = TableMetadata(ref=self._table_ref)
```

[Source: _bmad-output/planning-artifacts/architecture.md#Table Access Pattern: Non-Interactive Workflow]

### Abstract method stubs

`VectorStore` requires `similarity_search` and `from_texts` as abstract methods. Since this story does NOT implement them (Stories 2.2 and 2.3 do), you must add minimal stubs that raise `NotImplementedError`. Without these, the class cannot be instantiated:

```python
def add_texts(
    self,
    texts: Iterable[str],
    metadatas: list[dict] | None = None,
    *,
    ids: list[str] | None = None,
    **kwargs: Any,
) -> list[str]:
    """Add texts to the vector store. Implemented in Story 2.2."""
    raise NotImplementedError("add_texts is implemented in Story 2.2")

def similarity_search(
    self, query: str, k: int = 4, **kwargs: Any
) -> list[Document]:
    """Search for similar documents. Implemented in Story 2.3."""
    raise NotImplementedError("similarity_search is implemented in Story 2.3")
```

Note: `from_texts` has a default implementation in the base class that calls `add_texts`, so it does not need a separate stub.

You will also need `from collections.abc import Iterable` in the imports for the `add_texts` signature. Add it inside the `TYPE_CHECKING` block since it's only used in the annotation.

### Credential security (AC #8)

- `access_key` and `secret_key` are parameters of `from_connection_params` ONLY. They are passed directly to `vastdb.connect()` and NOT stored anywhere.
- The `__init__` method does not accept credentials -- it accepts a pre-built `session`.
- Do NOT add `__repr__` or `__str__` that might leak session internals.
- Do NOT log or include session details in any error messages.

[Source: _bmad-output/planning-artifacts/architecture.md#Constructor Design, _bmad-output/planning-artifacts/prd.md#Security]

### Previous story intelligence

**From Story 1.1:**
- The `__init__.py` already re-exports `VastDBVectorStore` from `vectorstores.py`. Do NOT change `__init__.py` in this story.
- The `pyproject.toml` has `ruff` configured with `exclude` for non-package directories. No changes needed.
- The ruff rules are `["E", "F", "I", "W", "UP"]` with line-length 100 and target py310.

**From Story 1.2:**
- The `.gitlab-ci.yml` is set up. No changes needed in this story.
- The CI unit-test job handles pytest exit code 5 (no tests collected) gracefully.

**From deferred work (Story 1.1 review):**
- No `py.typed` marker file yet (PEP 561). The architecture doc says to add it when Epic 2 introduces typed signatures. Consider adding `src/langchain_vastdb/py.typed` as an empty file in this story since we are adding type-hinted signatures. However, this is optional and can be deferred.

### What this story does NOT cover

- `add_texts` implementation -- **Story 2.2**
- `similarity_search`, `similarity_search_with_score`, `similarity_search_by_vector` -- **Story 2.3**
- `delete`, `get_by_ids`, `from_texts` -- **Story 2.4**
- Unit tests -- **Story 2.5**
- Hook method implementations (`_insert_vectors`, `_vector_search`, `_delete_by_ids`, `_get_by_ids`, `_row_to_document`) -- **Stories 2.2-2.4**
- Filter/predicate conversion (dict to ibis) -- **Story 2.3**
- Transaction management in hooks (optional `tx` parameter pattern) -- **Stories 2.2-2.4**

### Anti-patterns to avoid

- Do NOT use `tx.bucket(name).schema(name).table(name)` -- use `self._get_table(tx)` with cached `TableMetadata` instead. [Source: _bmad-output/planning-artifacts/architecture.md#Anti-Patterns]
- Do NOT store credentials as instance attributes or in any form that survives `from_connection_params`.
- Do NOT import `ibis`, `pyarrow`, `json`, or `uuid` -- not needed yet.
- Do NOT implement hook methods (`_insert_vectors`, etc.) -- those come in later stories.
- Do NOT modify `__init__.py` -- it already re-exports correctly.
- Do NOT modify `pyproject.toml` -- dependencies are already configured.
- Do NOT create additional files -- single-file implementation.
- Do NOT add a `distance_strategy` parameter -- distance metric is configured at the VAST table's vector index level, not per-query.

### Project Structure Notes

This story modifies exactly one file:

```
src/langchain_vastdb/vectorstores.py  # MODIFIED: stub -> real constructor + session management
```

All other files remain as Stories 1.1 and 1.2 left them. No structural variances expected.

### Architecture compliance summary

| Constraint | Source | What this story does |
|---|---|---|
| Session-first constructor | architecture.md#Constructor Design | `__init__` accepts `vastdb.Session` |
| `from_connection_params` classmethod | architecture.md#Constructor Design | Convenience factory creates session internally |
| Non-interactive table workflow | architecture.md#Table Access Pattern | `TableRef` + `TableMetadata` + `_get_table()` caching |
| Configurable column names | architecture.md#Naming Patterns | 4 column name params with defaults |
| `embeddings` property | architecture.md#Naming Patterns | Returns `self._embedding` |
| Credentials never stored | architecture.md#Constructor Design, prd.md#Security | Passed to `vastdb.connect()` only |
| Google-style docstrings | architecture.md#Naming Patterns | All public/protected methods |
| Type hints on all signatures | NFR16, architecture.md#Naming Patterns | All method signatures typed |
| Single-file implementation | architecture.md#File Organization Patterns | Everything in `vectorstores.py` |

### Testing standards (for this story)

There are no automated tests to write in this story (Story 2.5 writes unit tests). The validations are:

1. `uv run ruff check .` exits with code 0 and zero warnings.
2. `uv run python -c "from langchain_vastdb import VastDBVectorStore; print(VastDBVectorStore)"` succeeds.
3. `uv run pytest tests/unit_tests/ -v` does not error (no tests collected is acceptable -- CI handles exit code 5).
4. `uv run python -c "from langchain_vastdb import VastDBVectorStore; print(hasattr(VastDBVectorStore, 'from_connection_params'))"` prints `True`.

### References

- Story requirements and ACs: [Source: _bmad-output/planning-artifacts/epics.md#Story 2.1: Constructor, Session Management & Table Access]
- Constructor design: [Source: _bmad-output/planning-artifacts/architecture.md#Constructor Design]
- Table access pattern: [Source: _bmad-output/planning-artifacts/architecture.md#Table Access Pattern: Non-Interactive Workflow]
- Hook method signatures: [Source: _bmad-output/planning-artifacts/architecture.md#Hook Method Signatures]
- Transaction pattern: [Source: _bmad-output/planning-artifacts/architecture.md#Transaction Pattern]
- Naming conventions: [Source: _bmad-output/planning-artifacts/architecture.md#Naming Patterns]
- Import organization: [Source: _bmad-output/planning-artifacts/architecture.md#Import Organization]
- Security requirements: [Source: _bmad-output/planning-artifacts/prd.md#Security]
- VastDB SDK connection model: [Source: _bmad-output/planning-artifacts/research/technical-vast-langchain-vectorstore-research-2026-04-07.md#VastDB SDK Connection & Transaction Model]
- Previous story file: [Source: _bmad-output/implementation-artifacts/1-1-initialize-package-scaffold-with-uv-and-hatchling.md]
- Deferred work: [Source: _bmad-output/implementation-artifacts/deferred-work.md]

## Dev Agent Record

### Agent Model Used

claude-opus-4.6

### Debug Log References

None -- clean implementation, no debugging required.

### Completion Notes List

- All 6 tasks completed in a single pass with no errors.
- `uv run ruff check .` passed with zero warnings.
- `from langchain_vastdb import VastDBVectorStore` imports successfully.
- `from_connection_params` classmethod is accessible.
- `uv run pytest tests/unit_tests/ -v` ran cleanly (0 tests collected, as expected).
- Credentials (access_key, secret_key) are not stored as instance attributes -- only passed to `vastdb.connect()`.
- Used `Iterable` from `collections.abc` under `TYPE_CHECKING` for `add_texts` signature.

### File List

- `src/langchain_vastdb/vectorstores.py` -- MODIFIED: stub class replaced with full constructor, session management, table access, and abstract method stubs.

## Change Log

- 2026-04-09: Story 2.1 created by create-story workflow -- comprehensive developer guide for constructor, session management, and table access implementation.
