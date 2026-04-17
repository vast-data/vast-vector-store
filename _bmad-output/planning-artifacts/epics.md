---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
inputDocuments:
  - '_bmad-output/planning-artifacts/prd.md'
  - '_bmad-output/planning-artifacts/architecture.md'
---

# vast-vector-store - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for vast-vector-store, decomposing the requirements from the PRD and Architecture into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: Developer can add texts with optional metadata and IDs to the vector store
FR2: Developer can search for similar documents by text query, returning ranked results
FR3: Developer can search for similar documents by text query and receive distance scores alongside results
FR4: Developer can search for similar documents by pre-computed embedding vector
FR5: Developer can delete documents by their IDs
FR6: Developer can retrieve documents by their IDs without performing a search
FR7: Developer can create a vector store instance from a list of texts (factory method)
FR8: Developer can instantiate the vector store with connection parameters (endpoint, access key, secret key)
FR9: Developer can instantiate the vector store with a pre-built vastdb session for connection reuse
FR10: Developer can configure custom column names for text, vector, ID, and metadata fields
FR11: Developer can specify the target bucket, schema, and table name for storage
FR12: Developer can inject any LangChain-compatible Embeddings instance at construction time
FR13: Vector store automatically embeds text inputs using the configured embedding function during add and search operations
FR14: Developer can access the configured embedding function via the embeddings property
FR15: Developer can use the vector store as a LangChain retriever via as_retriever()
FR16: Developer can use the vector store in LangChain RAG chains and retrieval pipelines
FR17: Developer can pass metadata filters to search methods via filter keyword argument
FR18: Vector store passes LangChain's standard VectorStoreIntegrationTests suite
FR19: Subclass author can override _insert_vectors() to customize how records are written to VastDB
FR20: Subclass author can override _vector_search() to customize search behavior (e.g., add collection filters)
FR21: Subclass author can override _delete_by_ids() to customize deletion logic
FR22: Subclass author can override _get_by_ids() to customize retrieval logic
FR23: Subclass author can override _row_to_document() to customize how VastDB rows map to LangChain Documents
FR24: Subclass author can add domain-specific methods without conflicting with base class behavior
FR25: Developer can install the package via pip install langchain-vastdb or uv add langchain-vastdb
FR26: Package exports VastDBVectorStore as the single public class from langchain_vastdb
FR27: Developer can follow the README quickstart to achieve a working vector store in under 15 minutes
FR28: Developer can reference runnable example scripts for basic usage, RAG integration, subclassing, and filtered search
FR29: Developer can follow the migration guide to convert an existing VectorStore subclass to inherit from VastDBVectorStore

### NonFunctional Requirements

NFR1: The vector store wrapper adds no measurable latency overhead vs. direct vastdb SDK calls (thin wrapper principle)
NFR2: Embedding computation time is excluded from wrapper performance — that's the user's Embeddings model
NFR3: PyArrow data conversion (Document <-> RecordBatch) completes in under 10ms for batches of up to 1,000 documents
NFR4: Database credentials (access key, secret key) are accepted at construction time but never logged, serialized, or included in error messages
NFR5: No credentials are stored in metadata, search results, or Document objects
NFR6: The package does not persist credentials to disk or transmit them to any system other than the configured VAST endpoint
NFR7: SSL connections are supported when the vastdb SDK endpoint uses HTTPS
NFR8: Compatible with langchain-core>=0.3 (current stable interface)
NFR9: Compatible with vastdb>=2.0.3 (vector search API introduced)
NFR10: Tested against Python 3.10, 3.11, 3.12, and 3.13
NFR11: No conflicts with other LangChain partner packages when installed side-by-side
NFR12: Subclasses can override hook methods without requiring changes to the base package version
NFR13: 100% of public API methods have docstrings with usage examples
NFR14: Unit test coverage for all public methods and hook method defaults
NFR15: ruff linting passes with zero warnings
NFR16: Type hints on all public method signatures

### Additional Requirements

- **Starter Template:** Architecture specifies a hybrid starter (uv init --lib + LangChain conventions). Project initialization using `uv init --lib langchain-vastdb` should be the first implementation story.
- Non-interactive workflow for table access: Use VastDB SDK's TableMetadata + TableRef + tx.table_from_metadata() to cache table metadata and eliminate repeated bucket->schema->table round trips.
- Transaction management pattern: Each hook opens/closes its own transaction by default. Hooks accept optional keyword-only `tx` parameter for subclass transaction reuse.
- Filter/predicate passthrough: Base class template methods convert LangChain filter dicts to ibis expressions before calling hooks. Hooks receive ibis.Expr | None.
- Error handling: VastDB SDK exceptions propagate as-is. Contextual error messages added only at meaningful boundaries (e.g., table-not-found at init).
- CI/CD: GitLab CI/CD (not GitHub Actions). Unit tests + linting on every MR. Integration tests on every MR against always-available VAST cluster. PyPI Trusted Publishing for releases.
- Session-first constructor design: Primary constructor accepts vastdb.Session. Convenience from_connection_params() classmethod creates session internally.
- Metadata serialization: JSON default in base class (json.dumps/json.loads). Typed columns via subclass hook overrides.
- Hook method signatures are locked with exact types as defined in Architecture document. All AI agents must use these exact signatures.
- Single-file implementation: vectorstores.py (~300-500 LOC). Split only if it grows beyond ~800 LOC.

### UX Design Requirements

N/A — This is a developer tool / Python library with no UI component.

### FR Coverage Map

FR1: Epic 2 — Add texts with metadata/IDs (core insert operation)
FR2: Epic 2 — Similarity search by text query (core search)
FR3: Epic 2 — Similarity search with distance scores
FR4: Epic 2 — Similarity search by pre-computed vector
FR5: Epic 2 — Delete documents by ID
FR6: Epic 2 — Retrieve documents by ID (no search)
FR7: Epic 2 — from_texts factory method
FR8: Epic 2 — Constructor with connection params (from_connection_params classmethod)
FR9: Epic 2 — Constructor with pre-built session (primary constructor)
FR10: Epic 2 — Configurable column names
FR11: Epic 2 — Configurable bucket/schema/table
FR12: Epic 2 — Inject Embeddings instance at construction
FR13: Epic 2 — Auto-embed during add and search
FR14: Epic 2 — embeddings property accessor
FR15: Epic 3 — as_retriever() integration
FR16: Epic 3 — RAG chain compatibility
FR17: Epic 2 — Metadata filter passthrough via filter kwarg
FR18: Epic 3 — LangChain VectorStoreIntegrationTests compliance
FR19: Epic 2 — Overridable _insert_vectors() hook
FR20: Epic 2 — Overridable _vector_search() hook
FR21: Epic 2 — Overridable _delete_by_ids() hook
FR22: Epic 2 — Overridable _get_by_ids() hook
FR23: Epic 2 — Overridable _row_to_document() hook
FR24: Epic 2 — Domain-specific method extensibility
FR25: Epic 1 — Package installable via pip/uv
FR26: Epic 1 — Single public class export from langchain_vastdb
FR27: Epic 4 — README quickstart guide
FR28: Epic 4 — Runnable example scripts
FR29: Epic 4 — Migration guide for existing stores

## Epic List

### Epic 1: Project Bootstrap & Package Foundation
Establish the langchain-vastdb package with proper directory structure, build system (uv + hatchling), dependencies, linting (ruff), and GitLab CI/CD pipeline — so that subsequent development has a solid, tested foundation to build on.
**FRs covered:** FR25, FR26
**NFRs addressed:** NFR8, NFR9, NFR10, NFR11, NFR15

### Epic 2: VastDBVectorStore Core Implementation
Implement the complete VastDBVectorStore class with all core operations (add, search, delete, retrieve), connection management, embedding integration, metadata filtering, and the Template Method hook architecture — so that developers can use the full VectorStore API against their VAST cluster and subclass authors can customize behavior.
**FRs covered:** FR1-FR14, FR17, FR19-FR24
**NFRs addressed:** NFR1, NFR2, NFR3, NFR4, NFR5, NFR6, NFR7, NFR12, NFR13, NFR14, NFR16

### Epic 3: LangChain Ecosystem Compliance & Integration Testing
Validate full LangChain ecosystem integration — retriever compatibility, RAG chain support, and passing the standard VectorStoreIntegrationTests suite — so that the package behaves identically to any other LangChain partner VectorStore.
**FRs covered:** FR15, FR16, FR18
**NFRs addressed:** NFR8, NFR11, NFR14

### Epic 4: Documentation, Examples & Publication
Create comprehensive developer documentation (README with quickstart, configuration reference, subclassing guide, migration guide), runnable example scripts, and publish to PyPI — so that developers can self-serve adoption and existing internal stores can migrate.
**FRs covered:** FR27, FR28, FR29
**NFRs addressed:** NFR13

---

## Epic 1: Project Bootstrap & Package Foundation

Establish the langchain-vastdb package with proper directory structure, build system (uv + hatchling), dependencies, linting (ruff), and GitLab CI/CD pipeline — so that subsequent development has a solid, tested foundation to build on.

### Story 1.1: Initialize Package Scaffold with uv and Hatchling

As a developer,
I want a properly scaffolded Python package with src-layout, correct dependencies, and ruff linting,
So that I have a working build system and can begin implementing the VastDBVectorStore class.

**Acceptance Criteria:**

**Given** an empty project directory
**When** the package is initialized with `uv init --lib langchain-vastdb`
**Then** the following directory structure exists:
- `src/langchain_vastdb/__init__.py` exports `VastDBVectorStore` (stub class inheriting from `VectorStore`)
- `src/langchain_vastdb/vectorstores.py` contains the stub `VastDBVectorStore` class
- `tests/unit_tests/__init__.py` and `tests/integration_tests/__init__.py` exist
- `examples/` directory exists
- `LICENSE` file contains Apache-2.0 license text
- `.gitignore` is configured for Python projects
- `.python-version` specifies Python 3.10+

**Given** the scaffolded package
**When** `pyproject.toml` is configured
**Then** it includes:
- `hatchling` as the build backend
- `langchain-core>=0.3` and `vastdb>=2.0.3` as runtime dependencies
- `ruff`, `pytest`, `pytest-asyncio`, and `langchain-tests` as dev dependencies
- Python version requirement `>=3.10`
- Package name `langchain-vastdb` with module name `langchain_vastdb`
- Apache-2.0 license metadata

**Given** the configured package
**When** `uv sync` is run
**Then** all dependencies install successfully and a lockfile (`uv.lock`) is generated

**Given** the configured package
**When** `uv run ruff check .` is run
**Then** linting passes with zero warnings

**Given** the stub package
**When** `from langchain_vastdb import VastDBVectorStore` is executed
**Then** the import succeeds and `VastDBVectorStore` is a class

### Story 1.2: Configure GitLab CI/CD Pipeline

As a developer,
I want a GitLab CI/CD pipeline that runs linting, unit tests, integration tests, and handles PyPI publishing,
So that every merge request is validated automatically and releases are published securely.

**Acceptance Criteria:**

**Given** the scaffolded package with `.gitlab-ci.yml`
**When** a merge request is opened
**Then** the pipeline runs the following stages in order:
- **lint**: `uv run ruff check .` passes
- **unit-test**: `uv run pytest tests/unit_tests/` passes
- **integration-test**: `uv run pytest tests/integration_tests/` runs against the VAST cluster

**Given** the CI pipeline configuration
**When** the integration test stage is configured
**Then** it connects to the always-available VAST cluster using environment variables for connection params (endpoint, access key, secret key)

**Given** the CI pipeline configuration
**When** a release tag is pushed
**Then** the publish stage builds the package with `uv build` and publishes to PyPI using Trusted Publishing (OIDC tokens, no stored secrets)

**Given** the CI pipeline
**When** the pipeline matrix is configured
**Then** unit tests run against Python 3.10, 3.11, 3.12, and 3.13

---

## Epic 2: VastDBVectorStore Core Implementation

Implement the complete VastDBVectorStore class with all core operations (add, search, delete, retrieve), connection management, embedding integration, metadata filtering, and the Template Method hook architecture — so that developers can use the full VectorStore API against their VAST cluster and subclass authors can customize behavior.

### Story 2.1: Constructor, Session Management & Table Access

As a developer,
I want to instantiate VastDBVectorStore with either a pre-built session or connection parameters, configure column names and table targeting, and have efficient table access via cached metadata,
So that I can connect to my VAST cluster and the store is ready for operations.

**Acceptance Criteria:**

**Given** a developer with a pre-built `vastdb.Session`
**When** they instantiate `VastDBVectorStore(embedding=emb, session=session, bucket="b", schema="s", table_name="t")`
**Then** the store is created with the session stored as `_session`, a `TableRef` for the specified bucket/schema/table, and a `TableMetadata` instance for cached access

**Given** a developer with VAST connection parameters
**When** they call `VastDBVectorStore.from_connection_params(embedding=emb, endpoint="...", access_key="...", secret_key="...", bucket="b", schema="s", table_name="t")`
**Then** a `vastdb.Session` is created internally using `vastdb.connect()` and the store is instantiated with that session

**Given** a VastDBVectorStore instance
**When** `_get_table(tx)` is called for the first time
**Then** it calls `self._table_metadata.load(tx)` to load metadata, then returns `tx.table_from_metadata(self._table_metadata)`

**Given** a VastDBVectorStore instance where `_get_table(tx)` has been called before
**When** `_get_table(tx)` is called again (with a new transaction)
**Then** it skips the `load()` call and directly returns `tx.table_from_metadata(self._table_metadata)` using cached metadata

**Given** a VastDBVectorStore instance
**When** `invalidate_table_cache()` is called
**Then** the cached metadata is reset and the next `_get_table()` call will reload from the database

**Given** a VastDBVectorStore constructor call with custom column names
**When** `id_column="doc_id"`, `text_column="content"`, `vector_column="emb"`, `metadata_column="meta"` are passed
**Then** the store uses those column names for all operations instead of the defaults ("id", "text", "vector", "metadata")

**Given** a VastDBVectorStore instance
**When** the `embeddings` property is accessed
**Then** it returns the `Embeddings` instance provided at construction time

**Given** a constructor call with connection parameters
**When** credentials (access_key, secret_key) are provided
**Then** credentials are never logged, serialized, stored in instance attributes accessible via public API, or included in error messages

### Story 2.2: Add Texts & Document Insertion

As a developer,
I want to add texts with optional metadata and IDs to the vector store,
So that my documents are embedded, stored in VastDB, and available for similarity search.

**Acceptance Criteria:**

**Given** a VastDBVectorStore instance with a configured embedding function
**When** `add_texts(texts=["hello", "world"], metadatas=[{"k": "v1"}, {"k": "v2"}])` is called
**Then** the texts are embedded using the configured Embeddings instance, and the `_insert_vectors` hook is called with the texts, embeddings, metadata dicts, and auto-generated UUID IDs
**And** the method returns a list of the generated string IDs

**Given** a call to `add_texts` with explicit `ids=["id1", "id2"]`
**When** the method executes
**Then** the provided IDs are used instead of auto-generated UUIDs

**Given** a call to `add_texts` without `metadatas`
**When** the method executes
**Then** empty dicts `[{}, {}]` are used as metadata for each text

**Given** the default `_insert_vectors` hook implementation
**When** it is called with texts, embeddings, metadatas, and ids
**Then** it opens a transaction (or uses provided `tx`), gets the table via `_get_table()`, builds a `pa.RecordBatch` with the configured column names, serializes metadata as JSON strings via `json.dumps()`, and calls `table.insert(batch)`
**And** returns the list of IDs

**Given** the `_insert_vectors` hook signature
**When** a subclass overrides it
**Then** the signature matches exactly: `_insert_vectors(self, texts, embeddings, metadatas, ids, *, tx=None) -> list[str]`

> **Error handling note:** VastDB SDK exceptions propagate as-is per Architecture Decision: Error Handling. No try/catch needed in `add_texts` or `_insert_vectors`; meaningful contextual messages are only added at init boundaries (e.g., table-not-found).

### Story 2.3: Similarity Search Operations

As a developer,
I want to search for similar documents by text query, by vector, and with distance scores,
So that I can find relevant documents in my vector store using different search strategies.

**Acceptance Criteria:**

**Given** a VastDBVectorStore with indexed documents
**When** `similarity_search(query="hello", k=4)` is called
**Then** the query text is embedded using the configured Embeddings instance, `_vector_search` hook is called with the query vector, k, and predicate=None, and `_row_to_document` converts each result row to a LangChain `Document`
**And** a list of up to k `Document` objects is returned, ordered by similarity

**Given** a VastDBVectorStore with indexed documents
**When** `similarity_search_with_score(query="hello", k=4)` is called
**Then** a list of `(Document, float)` tuples is returned, where each float is the distance score from `_vector_search`

**Given** a VastDBVectorStore with indexed documents
**When** `similarity_search_by_vector(embedding=[0.1, 0.2, ...], k=4)` is called
**Then** the pre-computed embedding vector is passed directly to `_vector_search` without re-embedding
**And** results are returned as a list of `Document` objects

**Given** a search call with `filter={"category": "news"}`
**When** the template method processes the filter
**Then** the dict is converted to an ibis predicate expression before passing to `_vector_search` as the `predicate` parameter

**Given** the default `_vector_search` hook implementation
**When** it is called with query_vector, k, and optional predicate
**Then** it opens a transaction (or uses provided `tx`), gets the table, calls `table.vector_search(...)` with the query vector and k, applies the predicate if provided, reads the results into a list of dicts via `reader.read_all().to_pylist()`, and returns `list[tuple[dict, float]]` (row dict + distance score)

**Given** the default `_row_to_document` hook implementation
**When** it is called with a row dict and optional score
**Then** it extracts the text column value as `page_content`, deserializes the metadata column from JSON via `json.loads()`, and returns a `Document(page_content=text, metadata=metadata)`

**Given** the `_vector_search` and `_row_to_document` hook signatures
**When** a subclass overrides them
**Then** `_vector_search` matches: `_vector_search(self, query_vector, k, predicate=None, *, tx=None) -> list[tuple[dict, float]]`
**And** `_row_to_document` matches: `_row_to_document(self, row, score=None) -> Document`

> **Error handling note:** VastDB SDK exceptions propagate as-is per Architecture Decision: Error Handling. No try/catch needed in `similarity_search` or `_vector_search`; meaningful contextual messages are only added at init boundaries.

### Story 2.4: Delete, Get by IDs & Factory Method

As a developer,
I want to delete documents by ID, retrieve documents by ID without searching, and create a vector store from a list of texts in one call,
So that I have complete CRUD operations and a convenient factory method.

**Acceptance Criteria:**

**Given** a VastDBVectorStore with documents stored with known IDs
**When** `delete(ids=["id1", "id2"])` is called
**Then** the `_delete_by_ids` hook is called with the ID list and returns `True` on success

**Given** the default `_delete_by_ids` hook implementation
**When** it is called with a list of IDs
**Then** it opens a transaction (or uses provided `tx`), gets the table, builds a predicate matching the ID column to the provided IDs, calls `table.delete(predicate)`, and returns `True`

**Given** a VastDBVectorStore with stored documents
**When** `get_by_ids(ids=["id1", "id2"])` is called
**Then** the `_get_by_ids` hook is called and returns the matching documents as `list[Document]` by passing each row through `_row_to_document`

**Given** the default `_get_by_ids` hook implementation
**When** it is called with a list of IDs
**Then** it opens a transaction (or uses provided `tx`), gets the table, selects rows matching the ID column, reads results via `to_pylist()`, and returns `list[dict]`

**Given** a developer who wants to create a vector store and add documents in one step
**When** `VastDBVectorStore.from_texts(texts=["a", "b"], embedding=emb, session=session, bucket="b", schema="s", table_name="t")` is called
**Then** a new `VastDBVectorStore` instance is created and `add_texts` is called with the provided texts, returning the populated store

**Given** the `_delete_by_ids` and `_get_by_ids` hook signatures
**When** a subclass overrides them
**Then** `_delete_by_ids` matches: `_delete_by_ids(self, ids, *, tx=None) -> bool`
**And** `_get_by_ids` matches: `_get_by_ids(self, ids, *, tx=None) -> list[dict]`

> **Error handling note:** VastDB SDK exceptions propagate as-is per Architecture Decision: Error Handling. No try/catch needed in `delete` or `get_by_ids`; meaningful contextual messages are only added at init boundaries.

### Story 2.5: Unit Tests for VastDBVectorStore

As a developer,
I want comprehensive unit tests with mocked VastDB SDK calls covering all public methods and hook defaults,
So that I can confidently refactor and extend the class without regressions.

**Acceptance Criteria:**

**Given** the unit test file `tests/unit_tests/test_vectorstore.py`
**When** `uv run pytest tests/unit_tests/` is run
**Then** all tests pass with mocked VastDB SDK (no cluster needed)

**Given** unit test fixtures
**When** the test module is set up
**Then** it provides: `mock_session` (mocked `vastdb.Session`), `mock_transaction` (mocked `Transaction`), `vectorstore` (instance with mocked session and `DeterministicFakeEmbedding`), and `sample_documents` (list of test `Document` objects)

**Given** unit tests for constructor
**When** tests execute
**Then** they verify: session-first construction, `from_connection_params` classmethod, custom column name configuration, embeddings property, and that credentials are not exposed

**Given** unit tests for `add_texts`
**When** tests execute
**Then** they verify: texts are embedded, `_insert_vectors` is called with correct args, UUIDs are generated when no IDs provided, explicit IDs are used when provided, empty metadata defaults work

**Given** unit tests for search methods
**When** tests execute
**Then** they verify: `similarity_search` returns `list[Document]`, `similarity_search_with_score` returns `list[tuple[Document, float]]`, `similarity_search_by_vector` skips embedding, filter dict is converted to ibis predicate, `_row_to_document` correctly deserializes JSON metadata

**Given** unit tests for delete and get_by_ids
**When** tests execute
**Then** they verify: `delete` calls `_delete_by_ids` with correct IDs, `get_by_ids` returns correct documents, `from_texts` creates store and calls `add_texts`

**Given** unit tests for hook extensibility
**When** a test subclass overrides a hook method
**Then** the template methods correctly call the overridden hook instead of the default, verifying FR24 (domain-specific methods don't conflict)

---

## Epic 3: LangChain Ecosystem Compliance & Integration Testing

Validate full LangChain ecosystem integration — retriever compatibility, RAG chain support, and passing the standard VectorStoreIntegrationTests suite — so that the package behaves identically to any other LangChain partner VectorStore.

### Story 3.1: LangChain Standard Integration Test Suite

As a developer,
I want the VastDBVectorStore to pass LangChain's standard VectorStoreIntegrationTests,
So that I can trust it behaves identically to any other LangChain partner VectorStore.

**Acceptance Criteria:**

**Given** the integration test file `tests/integration_tests/test_vectorstore.py`
**When** the test class inherits from `langchain_tests.integration_tests.VectorStoreIntegrationTests`
**Then** it implements all required fixtures and configuration for the standard test suite

**Given** the integration test setup
**When** connection parameters are configured
**Then** they are read from environment variables (`VASTDB__ENDPOINT`, `VASTDB__ACCESS_KEY`, `VASTDB__SECRET_KEY`, `VASTDB__BUCKET` — double-underscore convention shared with `vast-pipelines`; schema is auto-generated per test run)

**Given** the integration test lifecycle
**When** each test runs
**Then** a dedicated test table is created before the test and cleaned up (dropped) after the test completes

**Given** the full `VectorStoreIntegrationTests` suite
**When** `uv run pytest tests/integration_tests/` is run against a live VAST cluster (v5.0.0-sp10+)
**Then** all standard LangChain VectorStore integration tests pass

**Given** the integration test configuration
**When** the test class is set up
**Then** it uses a real `Embeddings` instance (or a deterministic fake compatible with the standard suite) and targets a real VAST cluster

### Story 3.2: Retriever & RAG Chain Integration Validation

As a developer,
I want to use VastDBVectorStore as a LangChain retriever and in RAG chain pipelines,
So that I can integrate VAST-backed vector search into my LangChain applications seamlessly.

**Acceptance Criteria:**

**Given** a VastDBVectorStore instance with indexed documents
**When** `store.as_retriever()` is called
**Then** a LangChain `VectorStoreRetriever` is returned that can be invoked with a query string

**Given** a retriever created from VastDBVectorStore
**When** `retriever.invoke("search query")` is called
**Then** it returns a list of `Document` objects matching the query, using the store's `similarity_search` under the hood

**Given** a retriever with custom search kwargs
**When** `store.as_retriever(search_kwargs={"k": 2, "filter": {"category": "news"}})` is called
**Then** the retriever uses the specified k and filter when performing searches

**Given** a VastDBVectorStore retriever
**When** it is used in a LangChain RAG chain (e.g., `create_retrieval_chain` or LCEL `retriever | prompt | llm`)
**Then** the chain executes successfully with the retriever providing context documents from VAST

**Given** integration tests for retriever functionality
**When** they run against a live VAST cluster
**Then** they verify `as_retriever()` returns correct documents, custom search_kwargs are respected, and the retriever integrates into a simple chain

---

## Epic 4: Documentation, Examples & Publication

Create comprehensive developer documentation (README with quickstart, configuration reference, subclassing guide, migration guide), runnable example scripts, and publish to PyPI — so that developers can self-serve adoption and existing internal stores can migrate.

### Story 4.1: README with Quickstart, Configuration & Subclassing Guide

As a developer discovering langchain-vastdb,
I want a comprehensive README with quickstart instructions, configuration reference, and a subclassing guide,
So that I can go from installation to working vector store in under 15 minutes and learn how to customize it.

**Acceptance Criteria:**

**Given** the README.md file
**When** a developer reads the Quickstart section
**Then** it shows: `pip install langchain-vastdb` (or `uv add`), a minimal code example (~10 lines) that instantiates `VastDBVectorStore`, adds texts, and performs a similarity search, with clear prerequisites (VAST cluster access, embedding model)

**Given** the README.md file
**When** a developer reads the Configuration Reference section
**Then** it documents all constructor parameters: `embedding`, `session`, `bucket`, `schema`, `table_name`, `id_column`, `text_column`, `vector_column`, `metadata_column`, and the `from_connection_params()` classmethod with `endpoint`, `access_key`, `secret_key`

**Given** the README.md file
**When** a developer reads the Subclassing Guide section
**Then** it explains the Template Method architecture, lists all 5 hook methods with their signatures, shows a concrete example of overriding 2 hooks for a custom store, and explains the optional `tx` parameter for transaction reuse

**Given** the README.md file
**When** it is viewed on PyPI or GitLab
**Then** it includes: project description, installation, quickstart, configuration reference, subclassing guide, link to examples, link to migration guide, license (Apache-2.0), and compatibility info (Python 3.10-3.13, langchain-core>=0.3, vastdb>=2.0.3)

### Story 4.2: Runnable Example Scripts

As a developer,
I want runnable example scripts demonstrating common usage patterns,
So that I can copy and adapt working code for my use case.

**Acceptance Criteria:**

**Given** `examples/basic_usage.py`
**When** a developer reads and runs it (with their VAST cluster)
**Then** it demonstrates: creating a VastDBVectorStore, adding texts with metadata, performing similarity_search, and retrieving by ID

**Given** `examples/rag_pipeline.py`
**When** a developer reads and runs it
**Then** it demonstrates: creating a VastDBVectorStore, using `as_retriever()`, and integrating into a LangChain RAG chain (using LCEL or a retrieval chain)

**Given** `examples/subclassing.py`
**When** a developer reads and runs it
**Then** it demonstrates: creating a subclass that overrides `_insert_vectors` and `_row_to_document` hooks for typed metadata columns, showing the Template Method pattern in action

**Given** `examples/filtered_search.py`
**When** a developer reads and runs it
**Then** it demonstrates: adding documents with varied metadata, performing `similarity_search` with `filter={"key": "value"}`, and showing how filters narrow results

**Given** all example scripts
**When** they are reviewed
**Then** each script is self-contained (no shared fixtures), imports from `langchain_vastdb` as a user would, includes comments explaining each step, and uses the project's double-underscore environment variables for connection credentials (`VASTDB__ENDPOINT`, `VASTDB__ACCESS_KEY`, `VASTDB__SECRET_KEY`, `VASTDB__BUCKET` — never hardcoded)

### Story 4.3: Migration Guide & PyPI Publication

As a developer maintaining an existing VectorStore subclass,
I want a clear migration guide and a published PyPI package,
So that I can migrate my existing store to inherit from VastDBVectorStore and install it via pip.

**Acceptance Criteria:**

**Given** the Migration Guide section (in README or separate doc)
**When** a developer reads it
**Then** it provides step-by-step instructions:
1. Change parent class from `VectorStore` to `VastDBVectorStore`
2. Move storage operations into hook method overrides (with mapping table showing which methods map to which hooks)
3. Delete inherited LangChain interface methods (`similarity_search`, `add_texts`, `from_texts`, etc.)
4. Keep all domain-specific methods unchanged
5. Run existing test suite to validate

**Given** the Migration Guide
**When** a developer follows it for an existing store
**Then** the guide includes a before/after code comparison showing the LOC reduction and hook override pattern

**Given** the package is ready for publication
**When** `uv build` is run
**Then** it produces a valid wheel and sdist with correct metadata (name: `langchain-vastdb`, version, license, dependencies, Python version)

**Given** the package publication
**When** the package is published to PyPI
**Then** `pip install langchain-vastdb` succeeds, `from langchain_vastdb import VastDBVectorStore` works, and the package has no dependency conflicts with other LangChain partner packages