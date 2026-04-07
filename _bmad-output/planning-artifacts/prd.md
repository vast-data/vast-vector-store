---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-04-journeys', 'step-05-domain-skipped', 'step-06-innovation-skipped', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish', 'step-12-complete']
inputDocuments:
  - '_bmad-output/planning-artifacts/research/technical-vast-langchain-vectorstore-research-2026-04-07.md'
workflowType: 'prd'
documentCounts:
  briefs: 0
  research: 1
  brainstorming: 0
  projectDocs: 0
classification:
  projectType: developer_tool
  domain: scientific_ai
  complexity: medium
  projectContext: greenfield
---

# Product Requirements Document - vast-vector-store

**Author:** Genaier
**Date:** 2026-04-07

## Executive Summary

`langchain-vastdb` is an open-source Python package that provides a LangChain VectorStore implementation for VAST Database. It enables developers with VAST infrastructure to use VAST's native vector search capabilities directly within LangChain workflows — similarity search, RAG pipelines, and retriever chains — without building a custom integration from scratch.

As of April 2026, no LangChain integration for VAST Database exists on PyPI despite VAST's growing presence in enterprise AI infrastructure. This package fills that gap as a first-to-market partner integration. It targets two user segments: (1) any developer using VAST who wants a drop-in LangChain-compatible vector store, and (2) internal teams who currently maintain duplicate VectorStore implementations and need a shared, extensible base.

The package is built on the native `vastdb` SDK (Apache-2.0) and `langchain-core>=0.3`, following LangChain's partner integration conventions. It is a focused, single-class implementation (~300-500 LOC) designed for standalone use and subclass extensibility.

### What Makes This Special

The core design insight comes from two existing internal implementations (`VideoVectorStore` and `VastDBOnlyVectorStore`) that share ~60% of their code — all LangChain interface boilerplate — and diverge only in storage-layer details (ORM vs. direct SDK, single-tenant vs. multi-tenant, sync vs. async).

`langchain-vastdb` uses a Template Method architecture with 5 overridable hook methods (`_insert_vectors`, `_vector_search`, `_delete_by_ids`, `_get_by_ids`, `_row_to_document`). The base class handles all LangChain interface concerns — embedding, Document conversion, method signatures. Subclasses override only storage-layer hooks to add domain-specific behavior (ORM layers, collection-based multi-tenancy, custom metadata models) without forking or modifying the base package.

This means: `pip install`, configure connection settings, and get full VectorStore functionality. Need custom behavior? Inherit, override hooks, done.

## Project Classification

- **Project Type:** Developer Tool — open-source Python library/package distributed via PyPI
- **Domain:** AI/ML Infrastructure — bridging VAST Database's vector search with the LangChain ecosystem
- **Complexity:** Medium — no regulatory concerns, but requires precise API contract adherence to both LangChain VectorStore and VastDB SDK interfaces
- **Project Context:** Greenfield — first-to-market, no existing `langchain-vastdb` package

## Success Criteria

### User Success

- **External developer:** Goes from `pip install langchain-vastdb` to a working similarity search against their VAST cluster in under 15 minutes, following the README alone.
- **Internal team:** Inherits from `VastDBVectorStore`, overrides hooks for their domain-specific behavior, and has a working custom store in under a day — without touching or forking the base package.
- **LangChain user:** Uses `langchain-vastdb` identically to any other LangChain VectorStore partner package — `as_retriever()`, RAG chains, and all standard patterns work as expected with zero surprises.

### Business Success

- Published to PyPI as `langchain-vastdb` and installable with no friction
- Both existing internal stores (`VideoVectorStore`, `VastDBOnlyVectorStore`) successfully migrated to inherit from the base
- Submitted to LangChain's partner integrations directory

### Technical Success

- All LangChain `VectorStoreIntegrationTests` pass
- Both migrated stores pass their existing test suites unchanged
- No measurable performance overhead vs. direct `vastdb` SDK usage (thin wrapper)
- Existing stores reduced by ~40-60% LOC after migration (duplicate interface code removed)

### Measurable Outcomes

- Package published to PyPI with Apache-2.0 license
- 2 internal stores successfully migrated and running in production
- <5 minute setup for new users with existing VAST infrastructure
- ~300-500 LOC for the core implementation

## Product Scope

### MVP (Single Phase — Full Scope)

**MVP Approach:** Problem-solving MVP — deliver a fully functional, production-ready package in a single phase. The scope is intentionally narrow (one class, one module, one purpose) which makes a single-phase approach viable.

**Resource Requirements:** Single developer with Python packaging experience and access to a VAST Database cluster for integration testing.

**Must-Have Capabilities:**
- `VastDBVectorStore` class with full LangChain VectorStore interface
- 5 hook methods with default VastDB SDK implementations
- Constructor supporting both connection params and pre-built session
- Configurable column names (text, vector, id, metadata)
- JSON metadata column (default strategy)
- `add_texts`, `similarity_search`, `similarity_search_with_score`, `similarity_search_by_vector`
- `delete`, `get_by_ids`
- Sync-only implementation (LangChain provides async wrappers for free)
- Unit tests (mocked VastDB) + integration tests (real cluster)
- LangChain `VectorStoreIntegrationTests` standard suite
- Migration of `VideoVectorStore` and `VastDBOnlyVectorStore`
- README with quickstart, configuration, subclassing guide
- `examples/` directory with runnable scripts
- PyPI publication, submitted to LangChain partner integrations

### Post-MVP (Future Enhancements)

- MMR (Max Marginal Relevance) search support
- Native async support (blocked on `vastdb` SDK async API)
- Batch operations optimization for large-scale ingestion
- Hybrid metadata column strategies (typed + JSON)
- Official LangChain partner package status with co-maintained CI
- Community-contributed advanced filtering patterns

## User Journeys

### Journey 1: External Developer — First-Time Setup

**Persona:** Noa, a backend engineer at a company using VAST Data for their AI platform. She's building a RAG pipeline with LangChain and needs a vector store.

**Opening Scene:** Noa searches PyPI for a VAST Database integration with LangChain. She's been using `vastdb` SDK directly but wants proper LangChain integration for her retrieval chain. She finds `langchain-vastdb`.

**Rising Action:** She runs `pip install langchain-vastdb`, reads the README quickstart, and writes 10 lines of code: instantiate `VastDBVectorStore` with her connection params, embedding model, and table config. She calls `add_texts()` with her documents, then `similarity_search()` with a query.

**Climax:** Results come back correctly ranked. She plugs the store into `as_retriever()` and her existing LangChain RAG chain works immediately — no adapter code, no custom wrappers.

**Resolution:** Noa has a working RAG pipeline backed by VAST in under 15 minutes. She didn't need to understand VastDB's transaction model, PyArrow schemas, or ibis predicates. The store handled all of that.

**Capabilities revealed:** Constructor with connection params, `add_texts`, `similarity_search`, `as_retriever()`, README quickstart documentation.

### Journey 2: Internal Team — Migrating an Existing Store

**Persona:** Yoav, a developer on the insight-engine team. He maintains `VastDBOnlyVectorStore` — ~400 lines of code, half of which is LangChain interface boilerplate duplicated from another team's implementation.

**Opening Scene:** Yoav learns about `langchain-vastdb` and sees that the base class already implements the LangChain interface methods he's been maintaining. He wants to reduce his maintenance surface.

**Rising Action:** He changes his class to inherit from `VastDBVectorStore` instead of `VectorStore`. He moves his VastDB driver calls into the 3 hook methods he needs to override: `_insert_vectors` (to add collection hash), `_vector_search` (to add collection filter), and `_delete_by_ids` (to scope deletes to his collection). He deletes `similarity_search`, `similarity_search_with_score`, `add_texts`, and `from_texts` — all inherited now.

**Climax:** He runs his existing test suite. All tests pass. His domain-specific methods (`set_up_dbs`, `delete_doc`, `update_acl_fields`) are untouched — they were never part of the LangChain interface.

**Resolution:** `VastDBOnlyVectorStore` drops from ~400 LOC to ~180 LOC. Yoav no longer worries about keeping up with LangChain VectorStore interface changes — that's the base package's job now.

**Capabilities revealed:** Clean hook method API, inheritance without breakage, domain-specific methods preserved, base handles LangChain interface evolution.

### Journey 3: New Subclass Author — Building a Custom Store

**Persona:** Dana, a developer starting a new project that needs vector search with a custom metadata schema — typed columns for fast filtering instead of JSON serialization.

**Opening Scene:** Dana needs a LangChain VectorStore backed by VAST, but with typed metadata columns (`category: string`, `priority: int`) instead of the default JSON blob.

**Rising Action:** She inherits from `VastDBVectorStore` and overrides two hooks: `_insert_vectors` to build a PyArrow RecordBatch with her typed columns, and `_row_to_document` to map her columns back to LangChain Document metadata. She doesn't touch search — the base class's `_vector_search` works fine with her schema.

**Climax:** Her custom store supports fast predicate-based filtering on typed columns (`filter={"category": "urgent"}`) while inheriting all LangChain interface methods for free.

**Resolution:** Dana shipped a custom VectorStore in a few hours. She wrote ~50 lines of override code instead of ~300+ lines from scratch.

**Capabilities revealed:** Selective hook overriding, schema flexibility, filter passthrough, minimal subclass surface area.

### Journey Requirements Summary

| Capability | Journey 1 (External) | Journey 2 (Migration) | Journey 3 (Subclass) |
|---|---|---|---|
| Constructor with connection params | Required | Inherited | Inherited |
| `add_texts` / `from_texts` | Required | Inherited | Inherited |
| `similarity_search` / `with_score` / `by_vector` | Required | Inherited | Inherited |
| `delete` / `get_by_ids` | Required | Inherited | Inherited |
| `as_retriever()` | Required | Inherited | Inherited |
| Hook methods (`_insert_vectors`, etc.) | Default impl | Override 3 of 5 | Override 2 of 5 |
| Session/connection management | Required | Override | Inherited |
| PyArrow schema handling | Internal | Override | Override |
| Metadata serialization (JSON default) | Required | Override | Override |
| README / quickstart docs | Required | — | Subclassing guide |

## Developer Tool Requirements

### Language & Platform Matrix

| Aspect | Specification |
|---|---|
| Language | Python 3.10 – 3.13 |
| Package Manager | PyPI (`pip install langchain-vastdb`), `uv` compatible |
| Build System | `hatchling` |
| Linting | `ruff` |
| Testing | `pytest` + `langchain-tests` standard suite |
| License | Apache-2.0 |

### API Surface

The public API surface is intentionally minimal:

**Public class:** `VastDBVectorStore`
- Constructor with connection params or pre-built session
- All LangChain `VectorStore` interface methods (inherited + implemented)
- `embeddings` property

**Protected hook methods (for subclasses):**
- `_insert_vectors()`, `_vector_search()`, `_delete_by_ids()`, `_get_by_ids()`, `_row_to_document()`

**No other public API.** The package exports one class from `langchain_vastdb`.

### Installation & Setup

```bash
pip install langchain-vastdb
# or
uv add langchain-vastdb
```

Prerequisites: access to a VAST Database cluster (v5.0.0-sp10+) with vector search enabled, and an `Embeddings` instance (user's choice of embedding model).

### Documentation

- **README.md** — quickstart, configuration reference, subclassing guide
- **`examples/` directory** — runnable scripts demonstrating:
  - Basic usage (add texts, search, retrieve)
  - RAG pipeline integration with `as_retriever()`
  - Subclassing with custom hook overrides
  - Filter-based search with metadata

### Migration Guide

For teams migrating existing VectorStore implementations:
1. Change parent class from `VectorStore` to `VastDBVectorStore`
2. Move storage operations into hook method overrides
3. Delete inherited LangChain interface methods (`similarity_search`, `add_texts`, `from_texts`, etc.)
4. Keep all domain-specific methods unchanged
5. Run existing test suite to validate

### Implementation Considerations

- **Minimal dependency footprint:** Only `langchain-core>=0.3` and `vastdb>=2.0.3` as runtime dependencies
- **No bundled embedding models:** Users bring their own `Embeddings` instance
- **PyArrow as internal data format:** Matches `vastdb` SDK's native data interchange format
- **Transaction-per-operation:** Each VectorStore method opens and closes its own transaction (no held-open connections)
- **Distance metric is index-level:** Configured when the VAST table's vector index is created, not per-query

## Risk Mitigation

**Technical Risks:**
- *VastDB SDK API changes (v2.x still evolving)* — Pin minimum version `>=2.0.3`, test against multiple versions in CI
- *Vector column schema mismatch at runtime* — Validate schema at init, provide clear error messages
- *VAST cluster unavailability for integration tests* — Separate unit tests (no cluster) from integration tests (needs cluster) in CI

**Market Risks:**
- *Low adoption* — Mitigated by first-mover advantage and immediate internal adoption (2 stores migrated)
- *LangChain VectorStore interface changes* — Use `langchain-tests` standard suite to catch breaking changes early

**Resource Risks:**
- *Single-developer project* — Scope is intentionally small (~300-500 LOC). If constrained, defer examples directory, ship core class + tests + README first

## Functional Requirements

### Vector Store Core Operations

- **FR1:** Developer can add texts with optional metadata and IDs to the vector store
- **FR2:** Developer can search for similar documents by text query, returning ranked results
- **FR3:** Developer can search for similar documents by text query and receive distance scores alongside results
- **FR4:** Developer can search for similar documents by pre-computed embedding vector
- **FR5:** Developer can delete documents by their IDs
- **FR6:** Developer can retrieve documents by their IDs without performing a search
- **FR7:** Developer can create a vector store instance from a list of texts (factory method)

### Connection & Configuration

- **FR8:** Developer can instantiate the vector store with connection parameters (endpoint, access key, secret key)
- **FR9:** Developer can instantiate the vector store with a pre-built `vastdb` session for connection reuse
- **FR10:** Developer can configure custom column names for text, vector, ID, and metadata fields
- **FR11:** Developer can specify the target bucket, schema, and table name for storage

### Embedding Integration

- **FR12:** Developer can inject any LangChain-compatible `Embeddings` instance at construction time
- **FR13:** Vector store automatically embeds text inputs using the configured embedding function during add and search operations
- **FR14:** Developer can access the configured embedding function via the `embeddings` property

### LangChain Ecosystem Integration

- **FR15:** Developer can use the vector store as a LangChain retriever via `as_retriever()`
- **FR16:** Developer can use the vector store in LangChain RAG chains and retrieval pipelines
- **FR17:** Developer can pass metadata filters to search methods via `filter` keyword argument
- **FR18:** Vector store passes LangChain's standard `VectorStoreIntegrationTests` suite

### Extensibility (Subclassing)

- **FR19:** Subclass author can override `_insert_vectors()` to customize how records are written to VastDB
- **FR20:** Subclass author can override `_vector_search()` to customize search behavior (e.g., add collection filters)
- **FR21:** Subclass author can override `_delete_by_ids()` to customize deletion logic
- **FR22:** Subclass author can override `_get_by_ids()` to customize retrieval logic
- **FR23:** Subclass author can override `_row_to_document()` to customize how VastDB rows map to LangChain Documents
- **FR24:** Subclass author can add domain-specific methods without conflicting with base class behavior

### Package Distribution

- **FR25:** Developer can install the package via `pip install langchain-vastdb` or `uv add langchain-vastdb`
- **FR26:** Package exports `VastDBVectorStore` as the single public class from `langchain_vastdb`

### Documentation & Examples

- **FR27:** Developer can follow the README quickstart to achieve a working vector store in under 15 minutes
- **FR28:** Developer can reference runnable example scripts for basic usage, RAG integration, subclassing, and filtered search
- **FR29:** Developer can follow the migration guide to convert an existing VectorStore subclass to inherit from `VastDBVectorStore`

## Non-Functional Requirements

### Performance

- The vector store wrapper adds no measurable latency overhead vs. direct `vastdb` SDK calls (thin wrapper principle)
- Embedding computation time is excluded from wrapper performance — that's the user's `Embeddings` model
- PyArrow data conversion (Document ↔ RecordBatch) completes in under 10ms for batches of up to 1,000 documents

### Security

- Database credentials (access key, secret key) are accepted at construction time but never logged, serialized, or included in error messages
- No credentials are stored in metadata, search results, or Document objects
- The package does not persist credentials to disk or transmit them to any system other than the configured VAST endpoint
- SSL connections are supported when the `vastdb` SDK endpoint uses HTTPS

### Integration Compatibility

- Compatible with `langchain-core>=0.3` (current stable interface)
- Compatible with `vastdb>=2.0.3` (vector search API introduced)
- Tested against Python 3.10, 3.11, 3.12, and 3.13
- No conflicts with other LangChain partner packages when installed side-by-side
- Subclasses can override hook methods without requiring changes to the base package version

### Code Quality

- 100% of public API methods have docstrings with usage examples
- Unit test coverage for all public methods and hook method defaults
- `ruff` linting passes with zero warnings
- Type hints on all public method signatures
