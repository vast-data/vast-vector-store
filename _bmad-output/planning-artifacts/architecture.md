---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: 'complete'
completedAt: '2026-04-07'
inputDocuments:
  - '_bmad-output/planning-artifacts/prd.md'
  - '_bmad-output/planning-artifacts/research/technical-vast-langchain-vectorstore-research-2026-04-07.md'
workflowType: 'architecture'
project_name: 'vast-vector-store'
user_name: 'Genaier'
date: '2026-04-07'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
29 functional requirements across 7 categories:
- **Core Operations (FR1-FR7):** Standard VectorStore CRUD — add texts, similarity search (3 variants), delete, get by ID, factory method. These map 1:1 to VastDB SDK operations wrapped in PyArrow conversion.
- **Connection & Configuration (FR8-FR11):** Dual constructor pattern (connection params OR pre-built session), configurable column names, bucket/schema/table targeting.
- **Embedding Integration (FR12-FR14):** Inject any LangChain `Embeddings` instance; auto-embed on add and search.
- **LangChain Ecosystem (FR15-FR18):** Full retriever compatibility, RAG chain integration, metadata filtering, standard test suite compliance.
- **Extensibility (FR19-FR24):** 5 hook methods for subclass customization + freedom to add domain-specific methods.
- **Distribution (FR25-FR26):** PyPI package with single public class export.
- **Documentation (FR27-FR29):** Quickstart, examples, migration guide.

**Non-Functional Requirements:**
- **Performance:** Zero measurable overhead vs. direct SDK usage; <10ms PyArrow conversion for 1K-doc batches.
- **Security:** Credentials never logged/serialized/persisted; no credentials in metadata or results.
- **Compatibility:** Python 3.10-3.13, langchain-core>=0.3, vastdb>=2.0.3, no conflicts with other partner packages.
- **Code Quality:** 100% public API docstrings, full unit test coverage, ruff-clean, type-hinted signatures.

**Scale & Complexity:**

- Primary domain: Python library / SDK integration
- Complexity level: Low-Medium
- Estimated architectural components: 1 module, 1 class, 5 hook methods, 2 data conversion flows

### Technical Constraints & Dependencies

- **VastDB SDK (vastdb>=2.0.3):** Sync-only, PyArrow-native, transaction-per-operation model. All data interchange uses `pyarrow.RecordBatch`.
- **LangChain Core (langchain-core>=0.3):** Defines VectorStore abstract interface, Document model, Embeddings protocol. Post-v1.0 stable API.
- **PyArrow:** Transitive dependency via vastdb. Used for schema definition, data insertion, and search result parsing.
- **No async:** vastdb SDK has no async API. Rely on LangChain's default `run_in_executor` wrappers.
- **Distance metric is index-level:** Configured when VAST table's vector index is created, not per-query. The VectorStore doesn't control distance strategy at search time.
- **VAST cluster required for integration tests:** Unit tests use mocked SDK; integration tests need a live v5.0.0-sp10+ cluster.

### Cross-Cutting Concerns Identified

- **PyArrow data conversion:** Every hook method deals with PyArrow RecordBatch/RecordBatchReader ↔ Python dicts/Documents. Conversion logic must be consistent across insert, search, and retrieval paths.
- **Metadata serialization:** Default JSON strategy affects insert (`dict → JSON string`), search result parsing (`JSON string → dict`), and filter passthrough. Subclasses may override entirely.
- **Transaction lifecycle:** Every public method must open a transaction, perform the operation, and close it. This pattern repeats across all hooks and must be handled consistently.
- **ID generation:** Base class needs a default ID strategy (UUID) that subclasses can override. IDs flow through insert, delete, get_by_ids.
- **Error handling at SDK boundary:** VastDB SDK errors (connection failures, schema mismatches, transaction errors) must surface as meaningful exceptions to LangChain callers.

## Starter Template Evaluation

### Primary Technology Domain

Python library / SDK integration — open-source PyPI package following LangChain partner integration conventions.

### Starter Options Considered

1. **LangChain Integration Repo Template** ([langchain-ai/integration-repo-template](https://github.com/langchain-ai/integration-repo-template)) — Official LangChain partner scaffold. Provides standard directory structure, test configuration, and CI workflows. May need adaptation for uv/hatchling preferences.

2. **`uv init --lib`** ([uv project init](https://docs.astral.sh/uv/concepts/projects/init/)) — Modern Python library scaffold with src-layout, hatchling build backend, and uv dependency management. Requires manual addition of LangChain-specific conventions.

### Selected Starter: Hybrid (uv init + LangChain conventions)

**Rationale for Selection:**
The PRD specifies `uv`, `hatchling`, and `ruff` as the toolchain — these are 2026 Python packaging best practices. Starting with `uv init --lib` gives us the correct build system foundation, then we align directory structure and test conventions with LangChain's partner integration pattern for ecosystem compatibility. This avoids template cleanup while ensuring the package looks and behaves like a proper LangChain partner package.

**Initialization Command:**

```bash
uv init --lib langchain-vastdb
cd langchain-vastdb
uv add langchain-core vastdb
uv add --dev ruff pytest pytest-asyncio langchain-tests
```

**Architectural Decisions Provided by Starter:**

**Language & Runtime:**
Python 3.10+ with src-layout (`src/langchain_vastdb/`)

**Build System:**
`hatchling` build backend via `pyproject.toml`, managed by `uv`

**Linting & Formatting:**
`ruff` — replaces flake8, isort, and black in a single tool

**Testing Framework:**
`pytest` with `langchain-tests` standard suite for VectorStore validation

**Code Organization:**
```
langchain-vastdb/
├── src/
│   └── langchain_vastdb/
│       ├── __init__.py          # Public exports: VastDBVectorStore
│       └── vectorstores.py      # Single class implementation
├── tests/
│   ├── unit_tests/
│   │   └── test_vectorstore.py  # Mocked VastDB SDK
│   └── integration_tests/
│       └── test_vectorstore.py  # Real VAST cluster
├── examples/                    # Runnable usage scripts
├── pyproject.toml
├── README.md
├── LICENSE                      # Apache-2.0
└── .github/
    └── workflows/
        ├── ci.yml               # Lint + unit tests on PR
        ├── integration.yml      # Integration tests (manual/nightly)
        └── release.yml          # PyPI Trusted Publishing
```

**Development Experience:**
`uv` handles virtualenv creation, dependency resolution, lockfile generation, and build/publish — single tool for the entire development lifecycle.

**Note:** Project initialization using this command should be the first implementation story.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
- Constructor design (session ownership)
- Metadata serialization strategy
- Transaction management pattern
- Filter/predicate passthrough strategy

**Important Decisions (Shape Architecture):**
- Error handling strategy
- CI/CD pipeline approach

**Deferred Decisions (Not Applicable):**
- Authentication & security architecture (N/A — library, not a service)
- Frontend architecture (N/A)
- Hosting/scaling strategy (N/A — library, not deployed)
- API design patterns (N/A — single class, not a service API)

### Constructor Design

**Decision:** Session-first with convenience classmethod

The primary constructor accepts a `vastdb.Session` object. A `from_connection_params(endpoint, access_key, secret_key, ...)` classmethod provides a convenience path that creates the session internally.

**Rationale:** Keeps the class focused on VectorStore concerns, not connection management. Advanced users and subclasses can share sessions across stores. Follows PGVectorStore's factory-method pattern from the LangChain ecosystem.

**Affects:** All public methods (session used in every hook), subclass constructors, testing (easy to inject mock sessions).

### Metadata Serialization

**Decision:** JSON default in base class, typed columns via subclass hook overrides

The base class uses a single JSON string column for metadata serialization (`json.dumps`/`json.loads`). Subclasses that need typed columns for performance-critical filtering override `_insert_vectors` and `_row_to_document` hooks to use their own schema.

**Rationale:** Matches both existing internal implementations — VastDBOnlyVectorStore uses flexible dict storage (close to JSON default), VideoVectorStore uses typed ORM columns (hook overrides). Clean separation: base stays generic, subclasses add domain-specific schema.

**Affects:** `_insert_vectors` hook (serialization), `_row_to_document` hook (deserialization), `_vector_search` hook (filter compatibility), `_get_by_ids` hook (deserialization).

### Transaction Management

**Decision:** Transactions managed in hook methods, with optional `tx` parameter for subclass reuse

Each hook opens and closes its own transaction by default (transaction-per-operation). Hooks accept an optional `tx` (transaction) parameter — when provided, the hook uses the existing transaction instead of opening a new one. This is a protected-level concern for subclasses only; public template methods do not expose it.

**Rationale:** Keeps hooks self-contained for the default standalone path. Subclasses that need multi-step atomic operations (e.g., insert + update ACL fields) can wrap multiple hook calls in a single transaction. VideoVectorStore's ORM layer may manage connections entirely differently — self-contained hooks don't force a transaction model on it.

**Affects:** All 5 hook methods (`_insert_vectors`, `_vector_search`, `_delete_by_ids`, `_get_by_ids`, `_row_to_document`), subclass transaction batching patterns.

### Filter / Predicate Passthrough

**Decision:** Dict-to-ibis conversion in base template methods; hooks receive ibis predicates

The base class template methods (`similarity_search`, `similarity_search_with_score`, `similarity_search_by_vector`) convert LangChain `filter` dicts to ibis expressions before calling hooks. Hooks receive `predicate: ibis.Expr | None` — a clean, typed contract.

**Rationale:** All subclasses use the VastDB SDK, which means ibis predicates everywhere. Converting in the base class keeps the hook contract clean (one type, no ambiguity) and avoids duplicate conversion logic in subclasses. Subclasses that need to add predicates (e.g., collection scoping) combine ibis expressions directly.

**Affects:** `_vector_search` hook signature, base class template methods, subclass filter customization.

### Error Handling

**Decision:** Passthrough VastDB SDK exceptions with contextual messages at key boundaries

VastDB SDK exceptions propagate as-is to callers. No custom exception types, no wrapping. The base class adds contextual error messages only at meaningful boundaries (e.g., table-not-found during init surfaces a clear message with bucket/schema/table names).

**Rationale:** `vastdb` is a direct dependency — callers already have it installed. SDK-specific errors like `MissingSchema` or `TableExists` carry precise meaning that generic Python exceptions would flatten. Wrapping would add maintenance burden (keeping wrapper types in sync with SDK evolution) for no real value.

**Affects:** All hook methods (errors propagate), constructor/init (contextual messages), caller error handling (import errors from `vastdb` directly).

### CI/CD & Publishing

**Decision:** GitLab CI with integration tests on every MR; PyPI Trusted Publishing

- **Platform:** GitLab CI/CD (not GitHub Actions)
- **Unit tests + linting:** Run on every MR
- **Integration tests:** Run on every MR against an always-available VAST cluster, plus manual trigger capability
- **Publishing:** PyPI Trusted Publishing (OIDC tokens, no stored secrets)

**Rationale:** Always-available cluster means no reason to defer integration test feedback. Catching regressions on every MR is strictly better than nightly-only. GitLab's default manual trigger capability covers release validation.

**Affects:** `.gitlab-ci.yml` configuration, test separation (unit vs. integration), PyPI publishing pipeline.

### Decision Impact Analysis

**Implementation Sequence:**
1. Constructor design (session-first) — foundational, everything depends on session access
2. Transaction management (in hooks with optional tx) — must be established before any hook implementation
3. Metadata serialization (JSON default) — drives PyArrow schema definition
4. Filter passthrough (dict-to-ibis in base) — needed before search methods
5. Error handling (passthrough) — applies across all methods
6. CI/CD (GitLab) — can be set up in parallel with implementation

**Cross-Component Dependencies:**
- Constructor → Transaction management: Session created in constructor, used in hook transactions
- Metadata serialization → Filter passthrough: JSON metadata affects what's filterable in the base class
- Transaction management → All hooks: Optional `tx` parameter is part of every hook signature
- Filter passthrough → `_vector_search` hook: Predicate type in hook contract depends on this decision

## Implementation Patterns & Consistency Rules

### Critical Conflict Points Identified

7 areas where AI agents could make different choices, all addressed below.

### Naming Patterns

**Python Code Naming (PEP 8, enforced by ruff):**
- Classes: `PascalCase` — `VastDBVectorStore`
- Methods/functions: `snake_case` — `similarity_search`, `_insert_vectors`
- Variables: `snake_case` — `query_vector`, `table_name`
- Constants: `UPPER_SNAKE_CASE` — not expected in this package
- Protected methods (hook methods): single leading underscore — `_vector_search`
- Private attributes: single leading underscore — `_session`, `_table_metadata`

**VastDB Column Defaults:**
- ID column: `"id"` (string, configurable via `id_column`)
- Text column: `"text"` (string, configurable via `text_column`)
- Vector column: `"vector"` (fixed-size list, configurable via `vector_column`)
- Metadata column: `"metadata"` (string/JSON, configurable via `metadata_column`)

**Docstrings: Google style** (matches LangChain codebase):
```python
def similarity_search(self, query: str, k: int = 4, **kwargs) -> list[Document]:
    """Search for similar documents by text query.

    Args:
        query: The text query to search for.
        k: Number of results to return.
        **kwargs: Additional arguments, including `filter` for metadata filtering.

    Returns:
        List of Documents most similar to the query.
    """
```

### Table Access Pattern: Non-Interactive Workflow

**Decision:** Use VastDB SDK's non-interactive workflow (`TableMetadata` + `TableRef` + `tx.table_from_metadata()`) to cache table metadata and eliminate repeated bucket→schema→table round trips.

Reference: [VastDB SDK — Interactive and Non-Interactive Workflows](https://vastdb-sdk.readthedocs.io/en/latest/#interactive-and-non-interactive-workflows)

**Base class pattern:**
```python
from vastdb.table_metadata import TableMetadata, TableRef

class VastDBVectorStore(VectorStore):
    def __init__(self, embedding, session, bucket, schema, table_name, ...):
        self._session = session
        self._table_ref = TableRef(bucket=bucket, schema=schema, table=table_name)
        self._table_metadata = TableMetadata(ref=self._table_ref)
        self._metadata_loaded = False

    def _get_table(self, tx: Transaction) -> ITable:
        """Get table using cached metadata (non-interactive workflow).

        First call loads metadata via md.load(tx). Subsequent calls reuse
        cached metadata via tx.table_from_metadata(), skipping
        bucket→schema→table round trips entirely.
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

**Subclass optimization:** Subclasses that know their PyArrow schema at init time can skip the `load()` round trip entirely:
```python
self._table_metadata = TableMetadata(ref=self._table_ref, arrow_schema=my_schema)
self._metadata_loaded = True  # No load() needed
```

**Cache invalidation:** Call `invalidate_table_cache()` after any operation that changes the table structure (create, drop, schema alter). Subclasses that manage table lifecycle must call this.

### Transaction Pattern

**Every hook that accesses VastDB follows this exact shape:**
```python
def _some_hook(self, ..., *, tx: Transaction | None = None) -> ...:
    if tx is not None:
        table = self._get_table(tx)
        return self._do_work(table, ...)

    with self._session.transaction() as new_tx:
        table = self._get_table(new_tx)
        return self._do_work(table, ...)
```

**Rules:**
- `tx` is always keyword-only (after `*`)
- If `tx` is provided, use it (subclass transaction reuse)
- If `tx` is `None`, open a new transaction (default standalone path)
- Always use `self._get_table(tx)` — never navigate bucket→schema→table manually
- `_row_to_document` has no `tx` — it's pure data conversion, no DB access

### Hook Method Signatures

**Canonical contract — all AI agents must use these exact signatures:**

```python
def _insert_vectors(
    self,
    texts: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict],
    ids: list[str],
    *,
    tx: Transaction | None = None,
) -> list[str]: ...

def _vector_search(
    self,
    query_vector: list[float],
    k: int,
    predicate: ibis.Expr | None = None,
    *,
    tx: Transaction | None = None,
) -> list[tuple[dict, float]]: ...

def _delete_by_ids(
    self,
    ids: list[str],
    *,
    tx: Transaction | None = None,
) -> bool: ...

def _get_by_ids(
    self,
    ids: list[str],
    *,
    tx: Transaction | None = None,
) -> list[dict]: ...

def _row_to_document(
    self,
    row: dict,
    score: float | None = None,
) -> Document: ...
```

**Return type rules:**
- Hooks return plain Python types (dicts, lists, bools), not PyArrow objects
- PyArrow ↔ dict conversion happens inside each hook
- `_vector_search` returns `list[tuple[dict, float]]` — row dict + distance score
- `_row_to_document` returns a LangChain `Document` — this is the only place PyArrow-free data becomes a Document

### PyArrow Data Conversion Pattern

**Ingest flow (add_texts → _insert_vectors):**
```
texts + metadatas + embeddings + ids
→ Build pa.RecordBatch using self._table_metadata.arrow_schema
→ table.insert(batch)
```

**Search flow (_vector_search → _row_to_document):**
```
table.vector_search(...) → pa.RecordBatchReader
→ reader.read_all().to_pylist() → list[dict]
→ Each dict passed to _row_to_document() → Document
```

**Rules:**
- Always use `self._table_metadata.arrow_schema` for schema reference — never reconstruct manually
- JSON metadata serialization: `json.dumps()` on insert, `json.loads()` on read
- Vector column uses `pa.list_(pa.float32(), list_size=embedding_dim)`
- IDs are always `pa.utf8()` strings

### Import Organization (enforced by ruff)

```python
# Standard library
import json
import uuid

# Third-party
import ibis
import pyarrow as pa
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore
from vastdb.table_metadata import TableMetadata, TableRef
from vastdb.transaction import Transaction

# Local
# (none expected — single module package)
```

### Test Patterns

**Unit tests (mocked VastDB):**
- Use `unittest.mock.MagicMock` for `vastdb.Session`, `Transaction`, `Table`
- Use `DeterministicFakeEmbedding` from `langchain-core` for embedding vectors
- Test file: `tests/unit_tests/test_vectorstore.py`
- Fixture naming: `vectorstore`, `mock_session`, `mock_transaction`, `sample_documents`

**Integration tests (real cluster):**
- Test file: `tests/integration_tests/test_vectorstore.py`
- Inherit from `langchain_tests.integration_tests.VectorStoreIntegrationTests`
- Use a dedicated test table, clean up after each test
- Connection params from environment variables

### Enforcement Guidelines

**All AI agents MUST:**
- Use the exact hook method signatures defined above — no parameter reordering, renaming, or type changes
- Follow the transaction pattern exactly — `tx` keyword-only, `_get_table()` for table access
- Use the non-interactive workflow — `TableMetadata`/`TableRef`, never bucket→schema→table navigation
- Use Google-style docstrings for all public methods
- Return plain Python types from hooks, not PyArrow objects
- Call `invalidate_table_cache()` after any table structure changes

**Anti-Patterns:**
- ❌ `tx.bucket(name).schema(name).table(name)` — use `self._get_table(tx)` instead
- ❌ Returning `pa.RecordBatch` from hooks — convert to dicts inside the hook
- ❌ Opening transactions in template methods — transactions belong in hooks
- ❌ Hardcoding column names — always use `self._text_column`, `self._vector_column`, etc.
- ❌ Building PyArrow schemas from scratch — use `self._table_metadata.arrow_schema`

## Project Structure & Boundaries

### Complete Project Directory Structure

```
langchain-vastdb/
├── src/
│   └── langchain_vastdb/
│       ├── __init__.py              # Public exports: VastDBVectorStore
│       └── vectorstores.py          # VastDBVectorStore class (~300-500 LOC)
├── tests/
│   ├── unit_tests/
│   │   ├── __init__.py
│   │   └── test_vectorstore.py      # Mocked VastDB SDK tests
│   └── integration_tests/
│       ├── __init__.py
│       └── test_vectorstore.py      # Real VAST cluster + LangChain standard suite
├── examples/
│   ├── basic_usage.py               # Add texts, search, retrieve
│   ├── rag_pipeline.py              # as_retriever() + RAG chain
│   ├── subclassing.py               # Custom hook overrides
│   └── filtered_search.py           # Metadata filtering
├── pyproject.toml                   # uv + hatchling + ruff + pytest config
├── uv.lock                          # Deterministic dependency lock
├── README.md                        # Quickstart, config reference, subclassing guide, migration guide
├── LICENSE                          # Apache-2.0
├── .gitignore
├── .gitlab-ci.yml                   # Lint + unit tests + integration tests + publish
└── .python-version                  # 3.10+
```

### Requirements to Structure Mapping

**FR Category → File Location:**

| FR Category | Primary File | Notes |
|---|---|---|
| Core Operations (FR1-FR7) | `src/langchain_vastdb/vectorstores.py` | Template methods: `add_texts`, `similarity_search`, `delete`, `get_by_ids`, `from_texts` |
| Connection & Config (FR8-FR11) | `src/langchain_vastdb/vectorstores.py` | Constructor + `from_connection_params()` classmethod |
| Embedding Integration (FR12-FR14) | `src/langchain_vastdb/vectorstores.py` | `_embedding` attribute + `embeddings` property |
| LangChain Ecosystem (FR15-FR18) | `src/langchain_vastdb/vectorstores.py` + `tests/integration_tests/` | `as_retriever()` inherited; standard suite validates |
| Extensibility (FR19-FR24) | `src/langchain_vastdb/vectorstores.py` | 5 hook methods with default implementations |
| Distribution (FR25-FR26) | `pyproject.toml` + `src/langchain_vastdb/__init__.py` | Package config + public exports |
| Documentation (FR27-FR29) | `README.md` + `examples/` | Quickstart, subclassing guide, migration guide, runnable scripts |

### Architectural Boundaries

**Package Boundary:**
- Single public export: `VastDBVectorStore` from `langchain_vastdb`
- `__init__.py` exports only the class — no internal modules, no utilities, no helpers exposed
- Everything in `vectorstores.py` that starts with `_` is protected (for subclasses only)

**Dependency Boundaries:**
- Upstream: `langchain-core` — provides `VectorStore`, `Document`, `Embeddings` base types
- Downstream: `vastdb` — provides `Session`, `Transaction`, `TableMetadata`, `TableRef`, vector search
- Transitive: `pyarrow` (via vastdb), `ibis` (for predicates) — used internally, not part of public API

**Data Flow:**

```
User Code
    │
    ▼
VastDBVectorStore (public API)
    │  Template methods: add_texts, similarity_search, delete, get_by_ids
    │  Filter conversion: dict → ibis predicate
    │  Embedding: text → vector via self._embedding
    │
    ▼
Hook Methods (protected, overridable)
    │  _insert_vectors, _vector_search, _delete_by_ids, _get_by_ids
    │  Transaction management (open/close or reuse tx)
    │  Table access via _get_table() (cached TableMetadata)
    │  PyArrow conversion: dicts ↔ RecordBatch
    │
    ▼
VastDB SDK
    │  session.transaction() → tx
    │  tx.table_from_metadata() → table
    │  table.insert(), table.vector_search(), table.select(), table.delete()
    │
    ▼
VAST Database Cluster
```

**Test Boundaries:**
- Unit tests mock at the `vastdb.Session` boundary — no network, no cluster
- Integration tests hit a real cluster — validate end-to-end behavior
- LangChain standard suite (`VectorStoreIntegrationTests`) lives in integration tests

### File Organization Patterns

**Single module, single file:**
The entire implementation lives in `vectorstores.py`. No reason to split — the class is ~300-500 LOC, well within single-file readability. If it grows beyond ~800 LOC (e.g., adding MMR support post-MVP), consider splitting into `vectorstores.py` (class) and `_utils.py` (conversion helpers).

**Configuration:**
- `pyproject.toml` — all project config (build, deps, ruff, pytest) in one file
- `.gitlab-ci.yml` — CI/CD pipeline
- No `.env` files — this is a library, not a service. Connection params come from user code.

**Examples:**
- Each example is a standalone, runnable script
- Examples import from `langchain_vastdb` as a user would
- No shared fixtures between examples — each is self-contained

### Development Workflow

**Local development:**
```bash
uv sync                    # Install deps + create venv
uv run ruff check .        # Lint
uv run pytest tests/unit_tests/       # Unit tests (no cluster)
uv run pytest tests/integration_tests/ # Integration tests (needs cluster)
```

**Build & publish:**
```bash
uv build                   # Build wheel + sdist
uv publish                 # Publish to PyPI (or via GitLab CI)
```

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:**
All technology choices are compatible: `langchain-core>=0.3` + `vastdb>=2.0.3` + `pyarrow` (transitive) + `ibis` (for predicates). Session-first constructor integrates cleanly with the non-interactive `TableMetadata` workflow. Filter passthrough (dict→ibis in base) aligns with hook contract (ibis predicates). Error passthrough is consistent with `vastdb` being a direct dependency.

**Pattern Consistency:**
Transaction-in-hooks, optional `tx` parameter, and `_get_table()` caching form a coherent pattern. All hooks follow the same shape. Naming conventions (PEP 8 + Google docstrings) align with both Python standards and LangChain ecosystem. Import organization enforced by `ruff`.

**Structure Alignment:**
Single-file implementation (`vectorstores.py`) is appropriate for the ~300-500 LOC scope. Test split (unit/integration) maps directly to CI/CD pipeline stages. Package boundary (single public export) is clean and minimal.

### Requirements Coverage Validation ✅

**Functional Requirements Coverage (29/29):**

| FR Range | Architectural Support |
|---|---|
| FR1-FR7 (Core Operations) | Template methods delegate to hook methods with default VastDB SDK implementations |
| FR8-FR11 (Connection & Config) | Session-first constructor + `from_connection_params()` classmethod + configurable column names |
| FR12-FR14 (Embedding Integration) | `_embedding` attribute + `embeddings` property + auto-embed in template methods |
| FR15-FR18 (LangChain Ecosystem) | Inherits `as_retriever()`, dict→ibis filter passthrough, `VectorStoreIntegrationTests` in CI |
| FR19-FR24 (Extensibility) | 5 hook methods with canonical signatures, keyword-only `tx` for transaction reuse |
| FR25-FR26 (Distribution) | `pyproject.toml` with hatchling + `__init__.py` single export |
| FR27-FR29 (Documentation) | README with quickstart/subclassing/migration guides + `examples/` directory |

**Non-Functional Requirements Coverage:**
- **Performance:** Cached `TableMetadata` eliminates 3 round trips per operation. PyArrow conversion is the only wrapper overhead. ✅
- **Security:** Session-first design — credentials passed to `vastdb.connect()` only. Never logged, serialized, or stored. ✅
- **Compatibility:** Python 3.10-3.13, langchain-core>=0.3, vastdb>=2.0.3 specified. No conflicts with other partner packages. ✅
- **Code Quality:** Google-style docstrings, ruff enforcement, typed signatures on all public methods. ✅

### Implementation Readiness Validation ✅

**Decision Completeness:**
All 6 critical decisions documented with rationale: constructor design, metadata serialization, transaction management, filter passthrough, error handling, CI/CD. Technology versions verified.

**Structure Completeness:**
Complete directory tree with every file specified. FR-to-file mapping table ensures no requirement is orphaned. Data flow diagram shows the full path from user code to VAST cluster.

**Pattern Completeness:**
Hook signatures locked with exact types. Transaction boilerplate pattern defined. Table access pattern (non-interactive workflow) specified. Anti-patterns listed. Import organization defined. Test fixture naming conventions established.

### Gap Analysis Results

**Critical Gaps:** None

**Important Gaps:** None

**Minor Observations:**
- `from_texts` factory classmethod is a template method (constructor + `add_texts`) — straightforward, no hook needed. Implementing agent should note this is not a hook override point.
- Post-MVP items (MMR search, native async, batch optimization) are documented in PRD but intentionally excluded from architecture — they can be addressed in future architecture updates.

### Architecture Completeness Checklist

**✅ Requirements Analysis**
- [x] Project context thoroughly analyzed
- [x] Scale and complexity assessed (low-medium)
- [x] Technical constraints identified (vastdb sync-only, index-level distance metric)
- [x] Cross-cutting concerns mapped (PyArrow conversion, metadata serialization, transaction lifecycle, ID generation, error handling)

**✅ Architectural Decisions**
- [x] Constructor design: session-first + convenience classmethod
- [x] Metadata: JSON default, typed via subclass hooks
- [x] Transactions: in hooks, optional `tx` for reuse
- [x] Filters: dict→ibis in base, hooks receive predicates
- [x] Errors: SDK passthrough, contextual messages at boundaries
- [x] CI/CD: GitLab, integration tests on every MR, PyPI Trusted Publishing

**✅ Implementation Patterns**
- [x] Naming conventions (PEP 8 + Google docstrings)
- [x] Table access (non-interactive workflow with TableMetadata caching)
- [x] Transaction boilerplate pattern
- [x] Hook method canonical signatures
- [x] PyArrow data conversion flows
- [x] Import organization
- [x] Test patterns and fixture naming
- [x] Anti-patterns documented

**✅ Project Structure**
- [x] Complete directory tree with all files
- [x] FR-to-file mapping table
- [x] Architectural boundaries defined (package, dependency, data flow, test)
- [x] Development workflow commands specified

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level:** High — all requirements covered, all decisions coherent, patterns precise enough for consistent AI agent implementation.

**Key Strengths:**
- Template Method pattern provides clean separation between LangChain interface (base) and VastDB storage (hooks)
- Non-interactive workflow (TableMetadata caching) is a concrete performance optimization drawn from production experience (MR 189)
- Hook signatures are locked with exact types — eliminates agent interpretation variance
- Single-file, single-class scope keeps complexity low

**Areas for Future Enhancement:**
- MMR (Max Marginal Relevance) search — post-MVP
- Native async support — blocked on `vastdb` SDK async API
- Batch operations optimization — post-MVP
- Hybrid metadata column strategies — post-MVP

### Implementation Handoff

**AI Agent Guidelines:**
- Follow all architectural decisions exactly as documented
- Use implementation patterns consistently — especially hook signatures, transaction pattern, and table access pattern
- Respect project structure and boundaries — single public export, single implementation file
- Refer to this document for all architectural questions
- When in doubt, check the Anti-Patterns section

**First Implementation Priority:**
```bash
uv init --lib langchain-vastdb
cd langchain-vastdb
uv add langchain-core vastdb
uv add --dev ruff pytest pytest-asyncio langchain-tests
```
Then implement `VastDBVectorStore` in `src/langchain_vastdb/vectorstores.py` following the hook architecture and patterns defined in this document.