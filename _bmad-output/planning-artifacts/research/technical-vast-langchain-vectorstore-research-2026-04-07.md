---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments: []
workflowType: 'research'
lastStep: 1
research_type: 'technical'
research_topic: 'VAST LangChain VectorStore - Open Source Base Implementation'
research_goals: 'Create a base LangChain VectorStore implementation for VAST infrastructure that can be open-sourced and used independently'
user_name: 'Genaier'
date: '2026-04-07'
web_research_enabled: true
source_verification: true
---

# langchain-vastdb: Comprehensive Technical Research for an Open-Source LangChain VectorStore on VAST Database

**Date:** 2026-04-07
**Author:** Genaier
**Research Type:** Technical Architecture & Implementation

---

## Research Overview

This research document provides a comprehensive technical analysis for building `langchain-vastdb` — an open-source LangChain VectorStore integration for VAST Database. The research was conducted across five phases: technology stack analysis, integration patterns, architectural design, and implementation planning, with all technical claims verified against current public sources.

**Key finding:** No existing LangChain integration for VAST Database exists as of April 2026, making this the first-to-market opportunity. The native `vastdb` SDK (Apache-2.0, v2.0.14) provides all necessary vector search primitives, and the LangChain VectorStore interface requires only 2 abstract method implementations with ~6 recommended methods. The proposed Template Method architecture enables both existing internal stores (`VideoVectorStore` and `VastDBOnlyVectorStore`) to inherit from the base with moderate migration effort and no changes to their domain-specific logic.

For the full executive summary and strategic recommendations, see the **Research Synthesis** section at the end of this document.

---

## Technical Research Scope Confirmation

**Research Topic:** VAST LangChain VectorStore - Open Source Base Implementation
**Research Goals:** Create a base LangChain VectorStore implementation for VAST infrastructure that can be open-sourced and used independently

**Key Constraints (from user):**
- Must be as generic as possible
- Use the native `vastdb` SDK package (already open-sourced) — NOT the sqlalchemy-vastdb integration
- Must implement the LangChain VectorStore interface
- Target: standalone, open-source package usable by anyone with VAST infrastructure

**Existing Implementations to Extract From:**
1. `VideoVectorStore` (vast-pipelines) — ORM-like pattern with async, uses `AgentDescription` model
2. `VastDBOnlyVectorStore` (insight-engine) — Direct VDBDriver usage, sync-only, collection-based multi-tenancy

**Technical Research Scope:**

- Architecture Analysis - design patterns, frameworks, system architecture
- Implementation Approaches - development methodologies, coding patterns
- Technology Stack - languages, frameworks, tools, platforms
- Integration Patterns - APIs, protocols, interoperability
- Performance Considerations - scalability, optimization, patterns

**Research Methodology:**

- Current web data with rigorous source verification
- Multi-source validation for critical technical claims
- Confidence level framework for uncertain information
- Comprehensive technical coverage with architecture-specific insights

**Scope Confirmed:** 2026-04-07

---

## Technology Stack Analysis

### Core SDK: VAST DB Python SDK (`vastdb`)

The foundation for this project is the **vastdb** Python SDK — an Apache-2.0 licensed, open-source package maintained by VAST Data.

_Package Details:_
- **PyPI:** `vastdb` (latest: v2.0.14)
- **Python Support:** 3.10 – 3.13 (Linux clients)
- **Core Dependencies:** PyArrow (columnar data), Ibis (predicate pushdown), DuckDB (post-processing)
- **Repository:** [vast-data/vastdb_sdk](https://github.com/vast-data/vastdb_sdk)
- **License:** Apache-2.0
- **Weekly Downloads:** ~1,769

_Vector Search API (added v2.0.3, enhanced v2.0.7):_
```python
Table.vector_search(
    vec: list[float],           # Query vector
    columns: list[str],         # Columns to return
    limit: int,                 # Top-N results
    predicate: ibis.expr | None # Optional filter
) -> pyarrow.RecordBatchReader
```

_Supported Distance Metrics (configured at index level):_
- Cosine similarity (`array_cosine_distance`)
- Euclidean distance (`array_distance`)
- Negative inner product (`array_negative_inner_product`)

_Key SDK Operations for VectorStore:_
- `vastdb.connect(endpoint, access_key, secret_key)` — session creation
- `session.bucket(name).schema(name).table(name)` — table access
- `table.insert(pyarrow.RecordBatch)` — data insertion
- `table.select(columns, predicate)` — filtered reads
- `table.vector_search(...)` — similarity search
- `table.delete(predicate)` — filtered deletion

_Source: [vastdb PyPI](https://pypi.org/project/vastdb/), [vastdb_sdk GitHub](https://github.com/vast-data/vastdb_sdk), [VAST DB SDK Changelog](https://github.com/vast-data/vastdb_sdk/blob/main/CHANGELOG.md)_

### LangChain VectorStore Interface (`langchain-core`)

The LangChain VectorStore base class defines the standard interface our implementation must satisfy.

_Abstract Methods (MUST implement):_
1. **`similarity_search(query: str, k: int = 4, **kwargs) -> list[Document]`** — Core search
2. **`from_texts(texts, embedding, metadatas, *, ids, **kwargs) -> VST`** — Factory classmethod

_Methods that raise NotImplementedError (SHOULD implement):_
3. **`similarity_search_with_score(...) -> list[tuple[Document, float]]`** — Search with distances
4. **`similarity_search_by_vector(embedding: list[float], k, **kwargs) -> list[Document]`** — Search by pre-computed vector
5. **`delete(ids: list[str] | None, **kwargs) -> bool | None`** — Delete by IDs
6. **`get_by_ids(ids: Sequence[str]) -> list[Document]`** — Retrieve by IDs
7. **`max_marginal_relevance_search(...)` / `max_marginal_relevance_search_by_vector(...)`** — MMR search

_Methods with Default Implementations (inherit for free):_
- `add_documents` / `aadd_documents` — delegates to `add_texts`
- `from_documents` / `afrom_documents` — delegates to `from_texts`
- `as_retriever(**kwargs) -> VectorStoreRetriever` — standard retriever
- `search(query, search_type, **kwargs)` — routing method
- All `a*` async variants — default `run_in_executor` wrappers

_Key Property:_
- `embeddings -> Embeddings | None` — returns embedding function

_Source: [LangChain VectorStore base.py](https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/vectorstores/base.py), [LangChain VectorStore API Reference](https://api.python.langchain.com/en/latest/vectorstores/langchain_core.vectorstores.VectorStore.html)_

### Package Structure: LangChain Partner Integration Pattern

Following LangChain's official partner integration pattern, the package should be structured as `langchain-vastdb`.

_Naming Convention:_ `langchain-{provider}` → `langchain-vastdb`
_Python Package:_ `langchain_vastdb`

_Standard Directory Structure:_
```
langchain-vastdb/
├── langchain_vastdb/
│   ├── __init__.py
│   └── vectorstores.py          # VastDBVectorStore class
├── tests/
│   ├── unit_tests/
│   └── integration_tests/
├── pyproject.toml
├── README.md
├── LICENSE                       # Apache-2.0 (matching vastdb SDK)
└── .github/
    └── workflows/
```

_Core Dependencies:_
- `langchain-core` (>=0.3) — VectorStore base class, Document, Embeddings types
- `vastdb` (>=2.0.3) — VAST DB Python SDK with vector search support
- `pyarrow` — Columnar data handling (transitive via vastdb)

_Source: [LangChain Integration Repo Template](https://github.com/langchain-ai/integration-repo-template), [langchain-pinecone PyPI](https://pypi.org/project/langchain-pinecone/)_

### VAST Data Platform Context

VAST Database is a unified data platform where vector embeddings are stored natively alongside structured and unstructured data — no separate vector database needed.

_Key Architecture Characteristics:_
- Vectors stored in regular table columns alongside metadata
- Vector indexing is a table-level configuration (not per-query)
- Distance metric is set at index creation time
- Claims trillion-vector scale with constant-time search
- Supports hybrid queries across vectors + structured data via SQL and SDK
- Arrow Database Connectivity (ADBC) driver for SQL access

_VAST Version Requirement:_ 5.0.0-sp10 or later for SDK compatibility

_Source: [VAST Vector Search Blog](https://www.vastdata.com/blog/introducing-vast-vector-search-real-time-ai-retrieval-without-limits), [VAST Vector Search Foundation](https://www.vastdata.com/blog/vast-vector-search-the-right-foundation-for-real-time-ai)_

### Technology Adoption Trends

_LangChain Ecosystem:_
- LangChain v1.0 released October 2025 — partner packages are the preferred integration pattern
- Community integrations (`langchain_community.vectorstores`) are being deprecated in favor of standalone partner packages
- Standard test suites are available for validating VectorStore implementations

_Vector Database Market:_
- Trend toward unified platforms (vectors + structured data in one system) over standalone vector DBs
- VAST Data positioned in enterprise AI infrastructure, partnered with NVIDIA (Feb 2026 announcement)
- Growing demand for open-source LangChain integrations from database vendors

_Source: [LangChain Vector Store Integrations](https://docs.langchain.com/oss/python/integrations/vectorstores), [VAST Data NVIDIA Partnership](https://www.globenewswire.com/news-release/2026/02/25/3244905/0/en/VAST-Data-Introduces-End-to-End-Fully-Accelerated-AI-Data-Stack-with-NVIDIA.html)_

---

## Integration Patterns Analysis

### VastDB SDK Connection & Transaction Model

The vastdb SDK uses a hierarchical access pattern that our VectorStore must wrap cleanly:

```
Session → Transaction → Bucket → Schema → Table
```

_Connection Pattern:_
```python
import vastdb

session = vastdb.connect(
    endpoint="http://vastdb-endpoint:port",
    access_key="...",
    secret_key="..."
)

with session.transaction() as tx:
    table = tx.bucket("bucket-name").schema("schema-name").table("table-name")
    # All operations happen within transaction context
    table.insert(record_batch)
    results = table.vector_search(vec=query_vec, columns=[...], limit=k)
    table.select(columns=[...], predicate=filter_expr)
```

_Key Integration Considerations:_
- Every DB operation requires a transaction context manager
- The VectorStore must manage session lifecycle (create once, reuse across calls)
- Transactions are short-lived — open per operation, not held open
- Table reference requires navigating bucket → schema → table hierarchy
- PyArrow is the data interchange format (RecordBatch in, RecordBatchReader out)

_Source: [vastdb_sdk GitHub](https://github.com/vast-data/vastdb_sdk), [VAST DB SDK Documentation](https://vastdb-sdk.readthedocs.io/en/v1.3.0/)_

### Constructor Pattern: Following LangChain Partner Conventions

Analyzing how mature LangChain partner packages initialize, the recommended pattern for `langchain-vastdb`:

_Reference: PGVectorStore Pattern (langchain-postgres):_
- Uses factory methods (`create_sync` / `create`) rather than complex constructors
- Connection management delegated to a separate engine class
- Embedding function injected via constructor
- Collection/table name as a parameter
- Distance strategy configurable at init time

_Proposed VastDBVectorStore Constructor:_
```python
class VastDBVectorStore(VectorStore):
    def __init__(
        self,
        embedding: Embeddings,
        # VastDB connection params
        endpoint: str,
        access_key: str,
        secret_key: str,
        # Table location
        bucket: str,
        schema: str,
        table_name: str,
        # Vector search config
        vector_column: str = "vector",
        text_column: str = "text",
        distance_strategy: str = "cosine",  # cosine | euclidean | inner_product
    ):
```

_Alternative: Accept pre-built session for connection reuse:_
```python
    def __init__(
        self,
        embedding: Embeddings,
        session: vastdb.Session,  # Pre-connected session
        bucket: str,
        schema: str,
        table_name: str,
        ...
    ):
```

_Design Decision:_ Support both patterns — accept either connection params (for simplicity) or a pre-built session (for connection reuse in applications managing multiple stores).

_Source: [PGVectorStore DeepWiki](https://deepwiki.com/langchain-ai/langchain-postgres/3.1-pgvectorstore-(current-implementation)), [langchain-chroma API](https://api.python.langchain.com/en/latest/vectorstores/langchain_chroma.vectorstores.Chroma.html)_

### LangChain VectorStore Method Mapping to VastDB SDK

How each required VectorStore method maps to vastdb SDK operations:

| LangChain Method | VastDB SDK Operation | Notes |
|---|---|---|
| `add_texts(texts, metadatas)` | `table.insert(RecordBatch)` | Embed texts → build PyArrow batch with vectors + metadata → insert |
| `similarity_search(query, k)` | `table.vector_search(vec, columns, limit)` | Embed query → vector_search → convert RecordBatch to Documents |
| `similarity_search_with_score(...)` | `table.vector_search(...)` | Same as above, extract distance from results |
| `similarity_search_by_vector(embedding, k)` | `table.vector_search(vec, columns, limit)` | Skip embedding step, search directly |
| `delete(ids)` | `table.delete(predicate)` | Build ibis predicate on ID column |
| `get_by_ids(ids)` | `table.select(columns, predicate)` | Select with ID filter |
| `from_texts(texts, embedding)` | Constructor + `add_texts` | Factory: create store, then add initial texts |
| `as_retriever(**kwargs)` | Inherited from base | No custom implementation needed |

### Data Format Integration: PyArrow ↔ LangChain Document

_Ingest Flow (add_texts):_
```
texts + metadatas → embed_documents() → list[list[float]]
→ Build pyarrow.RecordBatch with columns: [id, text, vector, metadata_cols...]
→ table.insert(batch)
```

_Search Flow (similarity_search):_
```
query → embed_query() → list[float]
→ table.vector_search(vec, columns, limit) → pyarrow.RecordBatchReader
→ Convert rows to Document(page_content=text, metadata={...})
```

_Key Data Mapping:_
- LangChain `Document.page_content` ↔ VastDB text column (configurable name)
- LangChain `Document.metadata` ↔ VastDB additional columns (flexible schema)
- Embedding vectors ↔ VastDB vector column (PyArrow fixed-size list type)
- Document IDs ↔ VastDB primary key or generated ID column

### Metadata Handling Strategy

_Challenge:_ LangChain metadata is a flexible `dict[str, Any]`, but VastDB requires typed columnar schema.

_Approaches (from existing implementations):_
1. **JSON serialization** (VastDBOnlyVectorStore pattern) — Store metadata as a JSON string column. Simple but loses queryability.
2. **Flat columns** (VideoVectorStore pattern) — Map known metadata keys to typed columns. Fast but rigid.
3. **Hybrid** (Recommended) — Core fields as typed columns + overflow JSON column for arbitrary metadata.

_For the generic base package:_ Use a configurable metadata column strategy. Default to a single JSON metadata column for maximum flexibility. Allow users to specify additional typed columns for performance-critical metadata filtering.

### Retriever & RAG Integration

The `as_retriever()` method is inherited from the VectorStore base class and requires no custom implementation. It automatically:
- Creates a `VectorStoreRetriever` configured with the store
- Supports `search_type`: "similarity" (default), "mmr", "similarity_score_threshold"
- Passes `search_kwargs` through to the underlying search methods
- Integrates directly with LangChain's `create_retrieval_chain()` for RAG pipelines

_Usage in RAG chains:_
```python
retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
chain = create_retrieval_chain(retriever, document_chain)
```

_Source: [LangChain Retrieval](https://www.langchain.com/retrieval), [LangChain Vector Stores Guide](https://oneuptime.com/blog/post/2026-02-02-langchain-vector-stores/view)_

### Sync/Async Strategy

_From research on partner packages:_
- PGVectorStore wraps an async implementation with sync facades
- LangChain base class provides default async wrappers via `run_in_executor`
- The vastdb SDK is currently sync-only (no native async API)

_Recommendation for langchain-vastdb:_
1. Implement sync methods natively (matching vastdb SDK)
2. Rely on LangChain's default `run_in_executor` async wrappers initially
3. Add native async support later if vastdb SDK adds async API

This matches how most LangChain partner packages start — sync-first, with the base class providing async compatibility for free.

---

## Architectural Patterns and Design

### Core Architecture Decision: Template Method + Composition

The base `VastDBVectorStore` should use the **Template Method pattern** — implementing the full LangChain VectorStore interface with concrete methods that delegate to a small set of overridable hook methods for VastDB operations. This lets the two existing stores inherit and override only the parts that differ.

_Design Principle:_ The base class handles all LangChain interface concerns (embedding, Document conversion, method signatures). Subclasses only override **storage-layer hooks** (how data gets in/out of VastDB).

_Source: [Template Method Pattern](https://sbcode.net/python/template/), [Python ABC Guide](https://www.datacamp.com/tutorial/python-abstract-classes)_

### Class Hierarchy Design

```
langchain_core.vectorstores.VectorStore  (LangChain abstract base)
    └── VastDBVectorStore                (this package - concrete, fully usable)
            ├── VideoVectorStore          (vast-pipelines - extends with ORM layer)
            └── VastDBOnlyVectorStore     (insight-engine - extends with collection multi-tenancy)
```

_The base `VastDBVectorStore` must be:_
1. **Fully functional standalone** — usable by anyone with `vastdb` SDK + VAST cluster
2. **Extensible via inheritance** — existing stores override specific behaviors without rewriting core logic
3. **Generic** — no domain-specific assumptions (no "agent descriptions", no "chunks" table names)

### Existing Implementation Analysis: What Goes in Base vs. Subclass

#### Common Patterns (→ Base Class)

| Concern | VideoVectorStore | VastDBOnlyVectorStore | Base Class Design |
|---|---|---|---|
| Embedding function | `self._embedding_function` | `self.embedding_function` | `self._embedding: Embeddings` + `embeddings` property |
| Embed query | `embed_query(query)` | `embed_query(query)` | Base handles embedding in search methods |
| Embed documents | `aembed_documents(texts)` | `embed_documents(texts)` | Base handles embedding in add_texts |
| Result → Document | Custom converter | Manual dict→Document | Base provides generic PyArrow→Document conversion |
| similarity_search | Delegates to `_with_score` | Direct implementation | Base: embed → vector_search → convert |
| similarity_search_with_score | Embed + search + convert | Delegates to `similarity_search` | Base: embed → vector_search → convert with scores |

#### Divergent Patterns (→ Subclass Overrides)

| Concern | VideoVectorStore | VastDBOnlyVectorStore | How Subclass Overrides |
|---|---|---|---|
| Storage backend | ORM (`AgentDescription.asave()`) | Driver (`vastdb_driver.insert_from_list()`) | Override `_insert_records()` hook |
| Search backend | ORM (`AgentDescription.search_by_vector()`) | Driver (`vastdb_driver.vector_similarity_search()`) | Override `_vector_search()` hook |
| Delete mechanism | ORM filter (`adelete_by_filter`) | Driver predicate (`delete_where`) | Override `_delete_by_ids()` hook |
| Metadata model | Typed `AgentDescriptionMetadata` | Flexible dict with `collection_name` hash | Override metadata handling in hooks |
| Table management | Implicit (ORM manages) | `ensure_table()` / `teardown_dbs()` | Subclass adds own setup/teardown |
| Multi-tenancy | None (one table per entity type) | `collection_name` + `collection_hash` filtering | Subclass adds collection filtering |
| Async | Native async (ORM has async methods) | Sync only | VideoVectorStore overrides async hooks |
| Metrics/tracing | `ServiceMetrics`, `@trace_span` | `monitoring_utils.traces`, custom metrics | Subclass wraps with own observability |

### Proposed Hook Method Architecture

The base class implements all LangChain methods and delegates to these overridable hooks:

```python
class VastDBVectorStore(VectorStore):
    """Base LangChain VectorStore for VAST Database."""

    # ── Core hooks (override these in subclasses) ──

    def _get_table(self) -> vastdb.table.Table:
        """Get the VastDB table handle within a transaction.
        Base: uses session.transaction() → bucket → schema → table.
        Override: to use custom connection/driver patterns."""

    def _insert_vectors(
        self,
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
        ids: list[str],
    ) -> list[str]:
        """Insert text+vector+metadata records into VastDB.
        Base: builds PyArrow RecordBatch → table.insert().
        Override: to use ORM, custom schema, collection filtering, etc."""

    def _vector_search(
        self,
        query_vector: list[float],
        k: int,
        filter: dict | None = None,
    ) -> list[tuple[dict, float]]:
        """Execute vector similarity search against VastDB.
        Base: table.vector_search() → parse results.
        Override: to add collection filters, custom columns, etc.
        Returns: list of (row_dict, distance_score) tuples."""

    def _delete_by_ids(self, ids: list[str]) -> bool:
        """Delete records by their IDs.
        Base: table.delete() with ID predicate.
        Override: to add collection scoping, custom predicates, etc."""

    def _get_by_ids(self, ids: list[str]) -> list[dict]:
        """Retrieve records by their IDs.
        Base: table.select() with ID predicate.
        Override: for custom column selection, collection scoping."""

    def _row_to_document(self, row: dict, score: float | None = None) -> Document:
        """Convert a VastDB row dict to a LangChain Document.
        Base: uses text_column for page_content, remaining cols as metadata.
        Override: for custom field mapping (e.g., AgentDescription fields)."""
```

_Template methods (in base, call hooks):_
```python
    # These are FINAL - subclasses should NOT override
    def add_texts(self, texts, metadatas, *, ids, **kwargs):
        embeddings = self._embedding.embed_documents(list(texts))
        return self._insert_vectors(texts, embeddings, metadatas, ids)

    def similarity_search(self, query, k=4, **kwargs):
        query_vec = self._embedding.embed_query(query)
        results = self._vector_search(query_vec, k, kwargs.get("filter"))
        return [self._row_to_document(row) for row, _ in results]

    def similarity_search_with_score(self, query, k=4, **kwargs):
        query_vec = self._embedding.embed_query(query)
        results = self._vector_search(query_vec, k, kwargs.get("filter"))
        return [(self._row_to_document(row, score), score) for row, score in results]

    def similarity_search_by_vector(self, embedding, k=4, **kwargs):
        results = self._vector_search(embedding, k, kwargs.get("filter"))
        return [self._row_to_document(row) for row, _ in results]
```

### Migration Path: Minimal Changes to Existing Stores

#### VideoVectorStore Migration

```python
# BEFORE: class VideoVectorStore(VectorStore)
# AFTER:
class VideoVectorStore(VastDBVectorStore):
    # Override hooks to use ORM pattern
    def _insert_vectors(self, texts, embeddings, metadatas, ids):
        # Keep existing AgentDescription.asave() logic
        ...

    def _vector_search(self, query_vector, k, filter=None):
        # Keep existing AgentDescription.search_by_vector() logic
        ...

    def _row_to_document(self, row, score=None):
        # Keep existing _convert_agent_description_to_document() logic
        ...

    # REMOVE: similarity_search, similarity_search_with_score,
    #         add_texts, from_texts (inherited from base)
    # KEEP: delete_media, clear_data, acount_entries (domain-specific)
```

_Changes required:_ ~moderate. Remove duplicate LangChain interface methods, rewire ORM calls into hook overrides. Domain-specific methods (delete_media, clear_data) stay as-is.

#### VastDBOnlyVectorStore Migration

```python
# BEFORE: class VastDBOnlyVectorStore(VectorStore)
# AFTER:
class VastDBOnlyVectorStore(VastDBVectorStore):
    def __init__(self, ..., collection_name, vastdb_driver, ...):
        super().__init__(...)
        self.collection_name = collection_name
        self.vastdb_driver = vastdb_driver

    def _insert_vectors(self, texts, embeddings, metadatas, ids):
        # Keep existing _prepare_db_entries_with_vectors + insert_from_list
        # Add collection_name/collection_hash to entries
        ...

    def _vector_search(self, query_vector, k, filter=None):
        # Keep existing driver.vector_similarity_search()
        # Add collection_name filter to WHERE clause
        ...

    def _delete_by_ids(self, ids):
        # Keep existing collection-scoped delete logic
        ...

    # REMOVE: similarity_search, similarity_search_with_score,
    #         add_texts, from_texts (inherited from base)
    # KEEP: set_up_dbs, teardown_dbs, delete_doc, is_doc_exists,
    #        get_chunks_containing_text, get_chunks_from_page,
    #        update_acl_fields, get_row_count (domain-specific)
```

_Changes required:_ ~moderate. Same pattern — remove LangChain interface duplications, move VastDB operations into hook overrides. All domain-specific methods (ACL management, chunk operations, doc management) remain untouched.

### Data Architecture: Table Schema Strategy

_Base class default schema (for standalone usage):_

| Column | Type | Description |
|---|---|---|
| `id` | `string` | Primary key (UUID or user-provided) |
| `text` | `string` | Document page_content |
| `vector` | `fixed_size_list[float32, N]` | Embedding vector |
| `metadata` | `string` (JSON) | Serialized metadata dict |

_Configurable via constructor:_ Column names are not hardcoded. Users can specify `text_column`, `vector_column`, `id_column`, and `metadata_column` names. Subclasses can use entirely different schemas by overriding hooks.

### Security Architecture

_Connection Security:_
- VastDB SDK supports SSL connections (configurable)
- Access/secret key credential management — base class accepts credentials, does not store/log them
- No credentials in metadata or search results

_Data Isolation:_
- Base class operates on a single table (no multi-tenancy by default)
- Subclasses can add collection-based isolation (as VastDBOnlyVectorStore does)
- Predicate-based filtering prevents cross-tenant data leakage when implemented

_Source: [Composition vs Inheritance](https://python-patterns.guide/gang-of-four/composition-over-inheritance/), [PGVectorStore Architecture](https://deepwiki.com/langchain-ai/langchain-postgres/3.1-pgvectorstore-(current-implementation))_

### Deployment Architecture

_Package Distribution:_
- Published to PyPI as `langchain-vastdb`
- Minimal dependencies: `langchain-core>=0.3`, `vastdb>=2.0.3`
- No bundled embedding models — users bring their own `Embeddings` instance
- Apache-2.0 license (matching vastdb SDK)

_Usage Patterns:_
```python
# Standalone (open source user)
from langchain_vastdb import VastDBVectorStore
store = VastDBVectorStore(embedding=my_embeddings, endpoint="...", ...)

# As base class (internal teams)
from langchain_vastdb import VastDBVectorStore
class VideoVectorStore(VastDBVectorStore):
    ...
```

---

## Implementation Approaches and Technology Adoption

### Implementation Roadmap

**Phase 1: Core Package (MVP)**
1. Project scaffolding — `langchain-vastdb` package with `pyproject.toml`, `uv` tooling
2. `VastDBVectorStore` base class with all LangChain interface methods
3. Hook methods with default VastDB SDK implementations
4. Basic tests (unit + integration against a VAST cluster)
5. README with quickstart documentation
6. Publish to PyPI

**Phase 2: Existing Store Migration**
1. `VideoVectorStore` inherits from `VastDBVectorStore`, override hooks
2. `VastDBOnlyVectorStore` inherits from `VastDBVectorStore`, override hooks
3. Validate both stores pass their existing test suites unchanged
4. Remove duplicate LangChain interface code from both stores

**Phase 3: Hardening**
1. LangChain standard test suite (`VectorStoreIntegrationTests`)
2. MMR (Max Marginal Relevance) search support
3. Batch operations optimization
4. Comprehensive documentation and examples

### Package Structure and Tooling

Following 2026 Python packaging best practices:

```
langchain-vastdb/
├── src/
│   └── langchain_vastdb/
│       ├── __init__.py              # Public exports
│       └── vectorstores.py          # VastDBVectorStore class
├── tests/
│   ├── unit_tests/
│   │   └── test_vectorstore.py      # Unit tests with mocked VastDB
│   └── integration_tests/
│       └── test_vectorstore.py      # Integration tests against VAST cluster
├── pyproject.toml                   # uv + ruff + pytest config
├── README.md
├── LICENSE                          # Apache-2.0
└── .github/
    └── workflows/
        ├── ci.yml                   # Lint + unit tests on PR
        ├── integration.yml          # Integration tests (manual/nightly)
        └── release.yml              # PyPI publish via Trusted Publishing
```

_Build System:_ `uv` (2026 golden path — 10-100x faster than pip, handles builds, venvs, lockfiles)
_Linting:_ `ruff` (replaces flake8 + isort + black)
_Testing:_ `pytest` with `langchain-tests` standard suite
_Publishing:_ PyPI Trusted Publishing (OIDC tokens, no stored secrets)

_Source: [2026 Golden Path with uv](https://medium.com/@diwasb54/the-2026-golden-path-building-and-publishing-python-packages-with-a-single-tool-uv-b19675e02670), [Python Packaging Best Practices 2026](https://dasroot.net/posts/2026/01/python-packaging-best-practices-setuptools-poetry-hatch/)_

### pyproject.toml Configuration

```toml
[project]
name = "langchain-vastdb"
version = "0.1.0"
description = "LangChain VectorStore integration for VAST Database"
readme = "README.md"
license = "Apache-2.0"
requires-python = ">=3.10"
dependencies = [
    "langchain-core>=0.3",
    "vastdb>=2.0.3",
]

[project.optional-dependencies]
test = [
    "pytest>=8.0",
    "pytest-asyncio",
    "langchain-tests>=1.1",
]
dev = [
    "ruff",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
target-version = "py310"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

### Testing Strategy

**1. Unit Tests (no VAST cluster needed)**
- Mock the `vastdb` session/transaction/table to verify:
  - `add_texts` builds correct PyArrow schema and calls `table.insert`
  - `similarity_search` calls `table.vector_search` with correct parameters
  - `delete` builds correct ibis predicates
  - Document conversion from PyArrow rows works correctly
- Use `DeterministicFakeEmbedding` from langchain-core for deterministic embedding vectors

**2. LangChain Standard Integration Tests**
```python
from langchain_tests.integration_tests import VectorStoreIntegrationTests

class TestVastDBVectorStore(VectorStoreIntegrationTests):
    @pytest.fixture
    def vectorstore(self):
        return VastDBVectorStore(
            embedding=DeterministicFakeEmbedding(size=128),
            endpoint="...",
            access_key="...",
            secret_key="...",
            bucket="test-bucket",
            schema="test-schema",
            table_name="test-vectors",
        )
```

The `langchain-tests` package (v1.1.5) provides `VectorStoreIntegrationTests` base class with standard tests:
- `test_vectorstore_is_empty` — empty store returns no results
- `test_add_documents` — documents added successfully
- `test_deleting_documents` — deletion works
- `test_add_documents_with_ids_is_idempotent` — idempotent upsert behavior
- Supports toggling `has_sync`/`has_async` properties

_Source: [langchain-tests PyPI](https://pypi.org/project/langchain-tests/), [VectorStoreIntegrationTests Reference](https://reference.langchain.com/python/langchain_tests/integration_tests/vectorstores/)_

### VastDB-Specific Implementation Details

**Vector Column Schema with PyArrow:**
```python
import pyarrow as pa

schema = pa.schema([
    pa.field("id", pa.utf8()),
    pa.field("text", pa.utf8()),
    pa.field("vector", pa.list_(pa.float32(), list_size=embedding_dim)),
    pa.field("metadata", pa.utf8()),  # JSON-serialized
])
```

**Insert Flow:**
```python
with self._session.transaction() as tx:
    table = tx.bucket(self._bucket).schema(self._schema).table(self._table_name)
    batch = pa.RecordBatch.from_pydict({
        "id": ids,
        "text": texts,
        "vector": embeddings,
        "metadata": [json.dumps(m) for m in metadatas],
    }, schema=self._schema)
    table.insert(batch)
```

**Vector Search Flow:**
```python
with self._session.transaction() as tx:
    table = tx.bucket(self._bucket).schema(self._schema).table(self._table_name)
    reader = table.vector_search(
        vec=query_vector,
        columns=["id", "text", "metadata"],
        limit=k,
        predicate=filter_predicate,  # Optional ibis expression
    )
    results = reader.read_all()
```

_Distance metric is configured at the vector index level, not per query._ This means the VectorStore constructor's `distance_strategy` parameter maps to how the table's vector index was created, not to a per-search override.

_Source: [VAST Vector Database Technical Details](https://glennklockwood.com/garden/VAST-vector-database), [vastdb_sdk GitHub](https://github.com/vast-data/vastdb_sdk)_

### Risk Assessment and Mitigation

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| VastDB SDK API changes (v2.x still evolving) | Medium | High | Pin minimum version, test against multiple versions in CI |
| LangChain VectorStore interface changes (post v1.0) | Low | Medium | Use `langchain-tests` suite to catch breaking changes early |
| No native async in vastdb SDK | Certain | Low | Use LangChain's `run_in_executor` wrappers (proven pattern) |
| Vector column schema mismatch | Medium | Medium | Validate schema at init, provide clear error messages |
| VAST cluster unavailability for integration tests | High | Medium | Separate unit tests (no cluster) from integration tests (needs cluster) |
| Metadata serialization edge cases | Medium | Low | JSON serialization with clear docs on supported types |

### Cost Optimization

_Development Cost:_
- Base package is a focused, single-class implementation (~300-500 LOC)
- Testing against LangChain standard suite reduces manual QA effort
- Using `uv` and modern tooling minimizes build/CI time

_Runtime Cost:_
- No additional infrastructure beyond existing VAST cluster
- Embedding computation is the main cost driver (user's choice of model)
- VastDB vector search is handled by the database engine — no application-side compute for search

### Success Metrics

1. **Functional:** All `VectorStoreIntegrationTests` pass
2. **Compatibility:** Both existing stores successfully inherit and pass their test suites
3. **Adoption:** Package installable via `pip install langchain-vastdb` with <5 minute setup
4. **Performance:** No measurable overhead vs. direct SDK usage (thin wrapper)
5. **Code Reduction:** Existing stores reduced by ~40-60% LOC after migration (removal of duplicate interface code)

---

## Research Synthesis

### Executive Summary

This research establishes the complete technical foundation for `langchain-vastdb` — an open-source Python package that brings VAST Database's native vector search capabilities into the LangChain ecosystem. As of April 2026, no LangChain integration for VAST Database exists, despite VAST's growing presence in enterprise AI infrastructure (including a February 2026 partnership with NVIDIA). This package fills that gap.

The core design uses a **Template Method architecture** where `VastDBVectorStore` implements the full LangChain VectorStore interface and delegates storage operations to overridable hook methods. This achieves two goals simultaneously: (1) the package is fully functional as a standalone, generic vector store for any VAST user, and (2) two existing internal implementations can inherit from it with minimal refactoring — removing ~40-60% of their code (duplicate LangChain interface methods) while preserving all domain-specific logic untouched.

The implementation is a focused, single-class package (~300-500 LOC) built on the native `vastdb` SDK (Apache-2.0, v2.0.14) with `langchain-core>=0.3` as the only other dependency. It follows 2026 Python packaging best practices (`uv`, `ruff`, Trusted Publishing) and LangChain's partner integration template.

**Key Technical Findings:**

- **VastDB SDK vector search API** (`Table.vector_search`) provides clean primitives: query vector, column selection, limit, and optional ibis predicate filtering — maps 1:1 to LangChain methods
- **LangChain VectorStore interface** requires only 2 abstract methods (`similarity_search`, `from_texts`); 6 additional methods raise `NotImplementedError` and should be implemented; all async variants have default `run_in_executor` wrappers
- **VAST's vector indexing** uses hierarchical clustering (not HNSW), with distance metric configured at index creation time — meaning the VectorStore doesn't need per-query distance configuration
- **PyArrow** is the data interchange format for both VastDB SDK and the package's internal operations
- **No existing langchain-vastdb package** exists on PyPI — this is a greenfield opportunity

**Strategic Recommendations:**

1. **Start with sync-only MVP** — vastdb SDK is sync-only; LangChain provides free async wrappers via `run_in_executor`
2. **Use Template Method with 5 hook methods** — `_insert_vectors`, `_vector_search`, `_delete_by_ids`, `_get_by_ids`, `_row_to_document` — this is the minimal surface area for subclass customization
3. **Default to JSON metadata column** — maximum flexibility for generic usage; subclasses can override for typed columns
4. **Support both connection param injection and pre-built session** — simple for new users, reusable for applications
5. **Publish to PyPI immediately after MVP** — first-mover advantage in the LangChain partner ecosystem

### Table of Contents

1. [Technical Research Scope Confirmation](#technical-research-scope-confirmation)
2. [Technology Stack Analysis](#technology-stack-analysis)
   - Core SDK: VAST DB Python SDK
   - LangChain VectorStore Interface
   - Package Structure: LangChain Partner Integration Pattern
   - VAST Data Platform Context
   - Technology Adoption Trends
3. [Integration Patterns Analysis](#integration-patterns-analysis)
   - VastDB SDK Connection & Transaction Model
   - Constructor Pattern
   - LangChain VectorStore Method Mapping to VastDB SDK
   - Data Format Integration: PyArrow <> LangChain Document
   - Metadata Handling Strategy
   - Retriever & RAG Integration
   - Sync/Async Strategy
4. [Architectural Patterns and Design](#architectural-patterns-and-design)
   - Core Architecture Decision: Template Method + Composition
   - Class Hierarchy Design
   - Existing Implementation Analysis: Base vs. Subclass
   - Proposed Hook Method Architecture
   - Migration Path for Existing Stores
   - Data Architecture: Table Schema Strategy
   - Security Architecture
   - Deployment Architecture
5. [Implementation Approaches and Technology Adoption](#implementation-approaches-and-technology-adoption)
   - Implementation Roadmap (3 Phases)
   - Package Structure and Tooling
   - pyproject.toml Configuration
   - Testing Strategy
   - VastDB-Specific Implementation Details
   - Risk Assessment and Mitigation
   - Cost Optimization
   - Success Metrics

### Research Methodology and Source Verification

**Technical Sources Used:**

| Source | Type | Usage |
|---|---|---|
| [vastdb PyPI](https://pypi.org/project/vastdb/) | Primary | SDK version, dependencies, downloads |
| [vastdb_sdk GitHub](https://github.com/vast-data/vastdb_sdk) | Primary | API details, changelog, license |
| [VAST DB SDK Changelog](https://github.com/vast-data/vastdb_sdk/blob/main/CHANGELOG.md) | Primary | Vector search API history (v2.0.3+) |
| [LangChain VectorStore base.py](https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/vectorstores/base.py) | Primary | Complete interface specification |
| [LangChain Integration Repo Template](https://github.com/langchain-ai/integration-repo-template) | Primary | Package structure conventions |
| [langchain-tests PyPI](https://pypi.org/project/langchain-tests/) | Primary | Standard test suite (v1.1.5) |
| [PGVectorStore DeepWiki](https://deepwiki.com/langchain-ai/langchain-postgres/3.1-pgvectorstore-(current-implementation)) | Reference | Partner package architecture patterns |
| [VAST Vector Search Blog](https://www.vastdata.com/blog/introducing-vast-vector-search-real-time-ai-retrieval-without-limits) | Reference | VAST vector architecture |
| [VAST Vector Database Technical Details](https://glennklockwood.com/garden/VAST-vector-database) | Reference | Vector column schema, distance metrics, code examples |
| [2026 Python Packaging with uv](https://medium.com/@diwasb54/the-2026-golden-path-building-and-publishing-python-packages-with-a-single-tool-uv-b19675e02670) | Reference | Modern packaging best practices |

**Confidence Levels:**

- **High confidence:** VastDB SDK API (verified from source code + changelog), LangChain VectorStore interface (verified from source), package structure conventions (verified from templates)
- **Medium confidence:** `Table.vector_search` full parameter details (changelog confirmed method exists, signature extracted from docs but readthedocs returned 403 — cross-verified with third-party technical writeup)
- **Verified gap:** No existing `langchain-vastdb` package on PyPI as of April 2026 (confirmed via web search)

### Technical Research Conclusion

**Summary of Key Findings:**

The `langchain-vastdb` package is technically feasible and well-scoped. The vastdb SDK provides all required primitives, the LangChain interface is well-documented with a standard test suite, and the Template Method architecture cleanly separates generic base functionality from domain-specific extensions. The biggest risk is vastdb SDK API evolution (v2.x is still young), mitigated by pinning minimum versions and CI testing.

**Next Steps:**

1. Scaffold the `langchain-vastdb` package using the structure defined in this research
2. Implement `VastDBVectorStore` with the 5 hook methods architecture
3. Write unit tests with mocked VastDB, then integration tests against a real cluster
4. Publish v0.1.0 to PyPI
5. Migrate `VideoVectorStore` and `VastDBOnlyVectorStore` to inherit from the base
6. Submit to LangChain's partner integrations directory

---

**Technical Research Completion Date:** 2026-04-07
**Research Period:** Comprehensive technical analysis with current web verification
**Source Verification:** All technical facts cited with current sources
**Technical Confidence Level:** High — based on multiple authoritative technical sources
