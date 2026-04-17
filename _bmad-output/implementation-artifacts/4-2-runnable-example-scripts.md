# Story 4.2: Runnable Example Scripts

Status: review

## Story

As a developer,
I want runnable example scripts demonstrating common usage patterns,
so that I can copy and adapt working code for my use case.

## Acceptance Criteria

1. **AC1:** `examples/basic_usage.py` exists and demonstrates: creating a `VastDBVectorStore`, adding texts with metadata, performing `similarity_search`, and retrieving by ID.
2. **AC2:** `examples/rag_pipeline.py` exists and demonstrates: creating a `VastDBVectorStore`, using `as_retriever()`, and integrating into a LangChain RAG chain using LCEL.
3. **AC3:** `examples/subclassing.py` exists and demonstrates: creating a subclass that overrides `_insert_vectors` and `_row_to_document` hooks for typed metadata columns, showing the Template Method pattern in action.
4. **AC4:** `examples/filtered_search.py` exists and demonstrates: adding documents with varied metadata, performing `similarity_search` with `filter={"key": "value"}`, and showing how filters narrow results.
5. **AC5:** All example scripts are self-contained (no shared fixtures), import from `langchain_vastdb` as a user would, include comments explaining each step, and use environment variables for connection credentials (never hardcoded).

## Tasks / Subtasks

- [x] Task 1: Create `examples/basic_usage.py` (AC: #1, #5)
  - [x] 1.1: Import from `langchain_vastdb` and standard libs
  - [x] 1.2: Read connection credentials from env vars (`VASTDB_ENDPOINT`, `VASTDB_ACCESS_KEY`, `VASTDB_SECRET_KEY`)
  - [x] 1.3: Instantiate `VastDBVectorStore` using `from_connection_params()`
  - [x] 1.4: Add texts with metadata using `add_texts()`
  - [x] 1.5: Perform `similarity_search()` and print results
  - [x] 1.6: Retrieve documents by ID using `get_by_ids()` and print
  - [x] 1.7: Add step-by-step comments explaining each operation
- [x] Task 2: Create `examples/rag_pipeline.py` (AC: #2, #5)
  - [x] 2.1: Import from `langchain_vastdb`, `langchain_core`, env setup
  - [x] 2.2: Instantiate `VastDBVectorStore` using `from_connection_params()`
  - [x] 2.3: Add sample documents
  - [x] 2.4: Create retriever via `as_retriever()`
  - [x] 2.5: Build LCEL RAG chain (prompt | llm | output_parser) with retriever
  - [x] 2.6: Invoke the chain with a sample question and print result
  - [x] 2.7: Add comments explaining each LCEL step
- [x] Task 3: Create `examples/subclassing.py` (AC: #3, #5)
  - [x] 3.1: Import from `langchain_vastdb`, env setup
  - [x] 3.2: Define a custom subclass (e.g., `TypedMetadataStore`) that overrides `_insert_vectors` and `_row_to_document`
  - [x] 3.3: Show typed metadata columns instead of JSON blob
  - [x] 3.4: Instantiate and demonstrate add/search with typed metadata
  - [x] 3.5: Add comments explaining Template Method pattern and hook role
- [x] Task 4: Create `examples/filtered_search.py` (AC: #4, #5)
  - [x] 4.1: Import from `langchain_vastdb`, env setup
  - [x] 4.2: Add documents with diverse metadata (e.g., different categories, sources)
  - [x] 4.3: Show `similarity_search(query, filter={"key": "value"})` narrowing results
  - [x] 4.4: Show multiple filter patterns (single key, different values)
  - [x] 4.5: Add comments explaining filter behavior
- [x] Task 5: Remove `examples/.gitkeep` (AC: #5)
  - [x] 5.1: Delete the `.gitkeep` placeholder now that real files exist
- [x] Task 6: Update `README.md` Examples section (AC: #1-#5)
  - [x] 6.1: Remove the "*(Coming in a future release.)*" note from the Examples section
- [x] Task 7: Validate all scripts (AC: #1-#5)
  - [x] 7.1: `uv run ruff check examples/` exits 0
  - [x] 7.2: `uv run pytest tests/unit_tests/` — all existing tests still pass (no regressions)

## Dev Notes

### Key Insight: This is an Examples-Only Story

No production code (`src/langchain_vastdb/`) changes. The examples are standalone scripts that users copy — they live in `examples/` at the repo root. The only non-example change is removing the "Coming in a future release" note from README.md.

### Credential Handling Pattern

Every script must use environment variables — never hardcoded credentials. Use this standard pattern at the top of each script:

```python
import os

ENDPOINT = os.environ["VASTDB_ENDPOINT"]
ACCESS_KEY = os.environ["VASTDB_ACCESS_KEY"]
SECRET_KEY = os.environ["VASTDB_SECRET_KEY"]
```

These are the same env var names used by the integration test suite (`tests/integration_tests/`). The bucket, schema, and table_name can be hardcoded as example constants (e.g., `"example-bucket"`, `"example-schema"`, `"example-table"`) — they are not credentials.

### Embedding Model Placeholder

Examples need an `Embeddings` instance. Use a well-known LangChain embedding that users likely have:

```python
# Use any LangChain-compatible embedding model.
# Shown here with FakeEmbeddings for a runnable demo;
# replace with your actual model (e.g., OpenAIEmbeddings).
from langchain_core.embeddings import FakeEmbeddings

embedding = FakeEmbeddings(size=1536)
```

Using `FakeEmbeddings` from `langchain_core` means the scripts are runnable without extra dependencies beyond what the package already requires (`langchain-core>=0.3`). Add a comment telling users to replace with their real model.

### Actual Constructor / Factory Signatures (from source)

**Constructor:**
```python
VastDBVectorStore(
    embedding, session, bucket, schema, table_name,
    id_column="id", text_column="text", vector_column="vector",
    metadata_column="metadata", adbc_driver_path=None, adbc_endpoint=None,
    access_key=None, secret_key=None,
)
```

**Factory (preferred for examples):**
```python
VastDBVectorStore.from_connection_params(
    embedding, endpoint, access_key, secret_key,
    bucket, schema, table_name,
    adbc_driver_path=None, adbc_endpoint=None, **kwargs,
)
```

Use `from_connection_params()` in all examples — it is simpler and doesn't require the user to create a `vastdb.Session` manually.

### Hook Method Signatures (for subclassing.py)

```python
def _insert_vectors(self, texts, embeddings, metadatas, ids, *, tx=None) -> list[str]
def _row_to_document(self, row, score=None) -> Document
```

The subclassing example overrides these two hooks to demonstrate typed metadata columns (instead of the default JSON blob in the `metadata` column). Show a store that stores `category: str` and `source: str` as separate columns.

### RAG Chain Pattern (for rag_pipeline.py)

Use LCEL (LangChain Expression Language) to build the chain. The pattern is:

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

retriever = store.as_retriever(search_kwargs={"k": 3})

prompt = ChatPromptTemplate.from_template(
    "Answer based on context:\n{context}\n\nQuestion: {question}"
)

# NOTE: An actual LLM is required here. Example uses a placeholder.
# Replace with: from langchain_openai import ChatOpenAI; llm = ChatOpenAI()
chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)
```

Since this example cannot run without an actual LLM, the script should show the chain construction but note that `llm` must be provided by the user. Use a comment placeholder rather than importing a specific LLM provider — the package's dependencies don't include one.

### Files to Create

- `examples/basic_usage.py` — basic CRUD operations
- `examples/rag_pipeline.py` — retriever + LCEL RAG chain
- `examples/subclassing.py` — hook override with typed metadata
- `examples/filtered_search.py` — metadata filter patterns

### Files to Modify

- `README.md` — remove "Coming in a future release" note from Examples section (line ~384)

### Files to Delete

- `examples/.gitkeep` — no longer needed

### Files NOT to Modify

- `src/langchain_vastdb/vectorstores.py` — no production code changes
- `pyproject.toml` — no dependency changes
- Any test files — example-only story

### Testing Standards

1. `uv run ruff check .` exits 0 with zero warnings (ruff config in pyproject.toml covers the entire repo).
2. `uv run pytest tests/unit_tests/` — all existing tests pass (no regressions). Examples are NOT tested via pytest; they are runnable scripts for humans.
3. No new test files needed for this story.

### Previous Story Intelligence (from 4-1)

- Story 4-1 rewrote the README comprehensively. It already references the `examples/` directory with the 4 filenames above and a "Coming in a future release" note.
- Story 4-1 established patterns for code examples in the README: they use `from_connection_params()` and `FakeEmbeddings`. Follow the same patterns in the standalone scripts for consistency.
- The code review of 4-1 caught undefined variables in code examples (missing `llm`, `embedding_vector`, `session` definitions). Each example script must define all variables before use — no implicit context.

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Story 4.2 acceptance criteria]
- [Source: _bmad-output/planning-artifacts/architecture.md — File Organization Patterns / Examples section]
- [Source: _bmad-output/implementation-artifacts/4-1-readme-with-quickstart-configuration-and-subclassing-guide.md — Dev Notes]
- [Source: src/langchain_vastdb/vectorstores.py — constructor, factory, hook signatures]
- [Source: README.md — Examples section (lines 375-384)]

## Dev Agent Record

### Agent Model Used

Claude Opus 4 (claude-opus-4.6)

### Debug Log References

### Completion Notes List

- All 4 example scripts created: basic_usage.py, rag_pipeline.py, subclassing.py, filtered_search.py
- Each script is self-contained with env var credential handling and FakeEmbeddings placeholder
- Uses from_connection_params() factory consistently across all examples
- rag_pipeline.py shows chain construction with commented-out LLM section (no LLM provider in deps)
- subclassing.py demonstrates TypedMetadataStore overriding _insert_vectors and _row_to_document
- filtered_search.py shows 3 filter patterns (category=ml, category=database, level=beginner)
- Removed .gitkeep placeholder, removed "Coming in a future release" from README
- ruff check passes with zero warnings, all 47 unit tests pass (no regressions)

### File List

- examples/basic_usage.py (created)
- examples/rag_pipeline.py (created)
- examples/subclassing.py (created)
- examples/filtered_search.py (created)
- examples/.gitkeep (deleted)
- README.md (modified — removed "Coming in a future release" note)
