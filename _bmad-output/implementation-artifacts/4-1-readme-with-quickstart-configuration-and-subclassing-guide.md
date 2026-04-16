# Story 4.1: README with Quickstart, Configuration & Subclassing Guide

Status: ready-for-dev

## Story

As a developer discovering langchain-vastdb,
I want a comprehensive README with quickstart instructions, configuration reference, and a subclassing guide,
So that I can go from installation to working vector store in under 15 minutes and learn how to customize it.

## Acceptance Criteria

1. **Given** the README.md file **When** a developer reads the Quickstart section **Then** it shows: `pip install langchain-vastdb` (or `uv add`), a minimal code example (~10 lines) that instantiates `VastDBVectorStore`, adds texts, and performs a similarity search, with clear prerequisites (VAST cluster access, embedding model).

2. **Given** the README.md file **When** a developer reads the Configuration Reference section **Then** it documents all constructor parameters: `embedding`, `session`, `bucket`, `schema`, `table_name`, `id_column`, `text_column`, `vector_column`, `metadata_column`, and the `from_connection_params()` classmethod with `endpoint`, `access_key`, `secret_key`.

3. **Given** the README.md file **When** a developer reads the Subclassing Guide section **Then** it explains the Template Method architecture, lists all 5 hook methods with their signatures, shows a concrete example of overriding 2 hooks for a custom store, and explains the optional `tx` parameter for transaction reuse.

4. **Given** the README.md file **When** it is viewed on PyPI or GitLab **Then** it includes: project description, installation, quickstart, configuration reference, subclassing guide, link to examples, link to migration guide, license (Apache-2.0), and compatibility info (Python 3.10-3.13, langchain-core>=0.3, vastdb>=2.0.3).

## Tasks / Subtasks

- [ ] Task 1: Rewrite README.md with full structure (AC: #1, #2, #3, #4)
  - [ ] 1.1 Write project description and badges/compatibility header
  - [ ] 1.2 Write Installation section (pip, uv)
  - [ ] 1.3 Write Quickstart section with 3 paths: session-first, factory classmethod, from_texts
  - [ ] 1.4 Write CRUD Operations section (add_texts, similarity_search, get_by_ids, delete)
  - [ ] 1.5 Write Configuration Reference section documenting all constructor params + ADBC params
  - [ ] 1.6 Write Subclassing Guide section with Template Method explanation + 5 hook signatures + concrete example
  - [ ] 1.7 Write footer sections: links to examples/migration guide, development setup, license, compatibility
- [ ] Task 2: Validate README renders correctly (AC: #4)
  - [ ] 2.1 Verify all code blocks have correct syntax highlighting
  - [ ] 2.2 Verify internal/external links are valid
  - [ ] 2.3 Verify section anchors work for cross-references
- [ ] Task 3: Run linter to ensure no project regressions (AC: all)
  - [ ] 3.1 `uv run ruff check .` exits 0
  - [ ] 3.2 `uv run pytest tests/unit_tests/` all pass (no regressions from doc-only changes)

## Dev Notes

### Key Insight: This is a Documentation-Only Story

No production code changes should be needed. The README.md already exists with basic content (158 lines). This story rewrites it comprehensively. All code examples must reflect the ACTUAL constructor signature and public API — read them from the source, do not copy from the epics/PRD blindly.

### Existing README Structure (to replace)

The current README at `README.md` (158 lines) has:
- Basic project description with alpha status note
- Requirements section
- Installation (pip, uv)
- Quick start with 3 options (session, factory, from_texts)
- Custom column names
- Cache management (invalidate_table_cache)
- CRUD operations
- Development section
- License

The new README must preserve all of the above while significantly expanding it with Configuration Reference and Subclassing Guide sections.

### Actual Constructor Signature (from source code)

```python
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
    adbc_driver_path: str | None = None,
    adbc_endpoint: str | None = None,
    access_key: str | None = None,
    secret_key: str | None = None,
) -> None
```

### Factory Classmethod Signature (from source code)

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
    adbc_driver_path: str | None = None,
    adbc_endpoint: str | None = None,
    **kwargs: Any,
) -> VastDBVectorStore
```

### 5 Hook Methods (from architecture.md + source)

All hooks follow the Template Method pattern. Subclasses override these to customize behavior:

1. `_insert_vectors(self, texts, embeddings, metadatas, ids, *, tx=None) -> list[str]`
2. `_vector_search(self, query_vector, k, predicate=None, *, tx=None) -> list[tuple[dict, float]]`
3. `_delete_by_ids(self, ids, *, tx=None) -> bool`
4. `_get_by_ids(self, ids, *, tx=None) -> list[dict]`
5. `_row_to_document(self, row, score=None) -> Document`

The optional `tx` parameter allows subclasses to pass in an existing transaction for multi-step atomic operations.

### Subclassing Example Pattern

The concrete example should show overriding `_insert_vectors` and `_row_to_document` for typed metadata columns (matching architecture spec: "Subclasses that need typed columns for performance-critical filtering override `_insert_vectors` and `_row_to_document` hooks"). Show a custom store that replaces JSON metadata with typed columns.

### ADBC Parameters Documentation

The constructor accepts optional ADBC parameters for native vector search:
- `adbc_driver_path`: Path to `libadbc_driver_vastdb.so` — enables native ADBC vector search via `array_distance()` SQL (no vector index required).
- `adbc_endpoint`: ADBC/QueryEngine endpoint (hostname or IP), separate from the HTTP REST endpoint.
- `access_key` / `secret_key`: Passed through for ADBC connection.

When ADBC is configured, the store uses `array_distance()` SQL for vector search. When unavailable, falls back to in-memory L2Sq scan.

### Public API Surface

Single public export: `VastDBVectorStore` from `langchain_vastdb` (`from langchain_vastdb import VastDBVectorStore`).

Public methods (inherited from `VectorStore` + implemented):
- `add_texts()` — add documents with optional metadata
- `similarity_search()` — search by text query
- `similarity_search_with_score()` — search with distance scores
- `similarity_search_by_vector()` — search by pre-computed vector
- `delete()` — delete by IDs
- `get_by_ids()` — retrieve documents by IDs
- `from_texts()` — class method to create store and add texts in one call
- `as_retriever()` — return a LangChain `VectorStoreRetriever` (inherited)
- `invalidate_table_cache()` — clear cached table metadata

### Project Package Metadata (from pyproject.toml)

- name: `langchain-vastdb`
- version: `0.0.1`
- license: Apache-2.0
- Python: `>=3.10`
- Dependencies: `langchain-core>=0.3,<2`, `vastdb>=2.0.3`
- Classifiers: Alpha status, Python 3.10-3.13

### Files to Modify

- `README.md` — complete rewrite with expanded content

### Files NOT to Modify

- `src/langchain_vastdb/vectorstores.py` — no production code changes
- `pyproject.toml` — no dependency changes
- Any test files — doc-only story

### Testing Standards

1. `uv run ruff check .` exits 0 with zero warnings.
2. `uv run pytest tests/unit_tests/` — all 47 tests pass (no regressions).
3. No integration tests to run for a doc-only change.

### Previous Story Intelligence (from 3-2)

- 47 unit tests and 19 integration tests exist and pass.
- Store supports retriever via `as_retriever()` (inherited from VectorStore).
- LCEL RAG chain works end-to-end (validated in story 3-2).
- Metadata filtering only works on top-level columns (`id`, `text`), not JSON metadata path extraction — document this limitation in the README if mentioning filters.
- ADBC env vars are optional; CI runs through fallback path.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.1]
- [Source: _bmad-output/planning-artifacts/architecture.md#Hook Method Signatures]
- [Source: _bmad-output/planning-artifacts/architecture.md#Constructor Design]
- [Source: _bmad-output/planning-artifacts/architecture.md#Project Structure & Boundaries]
- [Source: _bmad-output/planning-artifacts/prd.md#Documentation]
- [Source: src/langchain_vastdb/vectorstores.py — actual constructor and hook signatures]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List

