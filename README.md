# langchain-vastdb

LangChain VectorStore integration for [VAST Database](https://vastdata.com/).

`langchain-vastdb` provides a `VastDBVectorStore` class that implements the
LangChain `VectorStore` interface, enabling similarity search, document storage,
and retrieval-augmented generation (RAG) workflows backed by VAST Database's
native vector indexing.

**Compatibility:** Python 3.10 - 3.13 | langchain-core >= 0.3 | vastdb >= 2.0.3

**Status:** Alpha (v0.0.1). API may change between minor releases.

**License:** Apache-2.0

## Requirements

- Python 3.10+
- A running VAST Database cluster with vector index support
- `vastdb` SDK >= 2.0.3
- `langchain-core` >= 0.3
- An `Embeddings` model (e.g., OpenAI, HuggingFace, or any LangChain-compatible embeddings)

## Installation

```bash
pip install langchain-vastdb
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add langchain-vastdb
```

## Quickstart

### Option 1: Pass a pre-built session

```python
import vastdb
from langchain_vastdb import VastDBVectorStore

session = vastdb.connect(
    endpoint="http://vast-cluster:8070",
    access_key="YOUR_ACCESS_KEY",
    secret_key="YOUR_SECRET_KEY",
)

store = VastDBVectorStore(
    embedding=my_embeddings,
    session=session,
    bucket="my-bucket",
    schema="my-schema",
    table_name="my-table",
)

# Add documents and search
ids = store.add_texts(["Paris is the capital of France."])
results = store.similarity_search("capital city", k=1)
print(results[0].page_content)
```

### Option 2: Use the convenience factory

```python
from langchain_vastdb import VastDBVectorStore

store = VastDBVectorStore.from_connection_params(
    embedding=my_embeddings,
    endpoint="http://vast-cluster:8070",
    access_key="YOUR_ACCESS_KEY",
    secret_key="YOUR_SECRET_KEY",
    bucket="my-bucket",
    schema="my-schema",
    table_name="my-table",
)
```

Credentials are passed directly to `vastdb.connect()` and are **not** stored on
the instance.

### Option 3: Create a store and add texts in one call

```python
import vastdb
from langchain_vastdb import VastDBVectorStore

session = vastdb.connect(
    endpoint="http://vast-cluster:8070",
    access_key="YOUR_ACCESS_KEY",
    secret_key="YOUR_SECRET_KEY",
)

store = VastDBVectorStore.from_texts(
    texts=["Paris is the capital of France.", "Berlin is the capital of Germany."],
    embedding=my_embeddings,
    session=session,
    bucket="my-bucket",
    schema="my-schema",
    table_name="my-table",
)
```

## CRUD Operations

```python
# Add documents with metadata
ids = store.add_texts(
    ["Some text", "More text"],
    metadatas=[{"source": "wiki"}, {"source": "blog"}],
)

# Similarity search by text query
docs = store.similarity_search("capital city", k=2)

# Similarity search with distance scores
scored = store.similarity_search_with_score("capital city", k=2)
for doc, score in scored:
    print(f"{doc.page_content} (distance: {score})")

# Search with a pre-computed vector
docs = store.similarity_search_by_vector([0.1, 0.2, ...], k=2)

# Retrieve documents by ID
docs = store.get_by_ids(ids)

# Delete by ID
store.delete(ids=ids)
```

### Using as a retriever

`VastDBVectorStore` integrates directly with LangChain's retriever interface:

```python
retriever = store.as_retriever(search_kwargs={"k": 3})
docs = retriever.invoke("What is the capital of France?")
```

This works seamlessly in LCEL RAG chains:

```python
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough

retriever = store.as_retriever(search_kwargs={"k": 3})
prompt = ChatPromptTemplate.from_template(
    "Answer based on context:\n{context}\n\nQuestion: {question}"
)

def format_docs(docs):
    return "\n".join(d.page_content for d in docs)

chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm  # any LangChain-compatible LLM
    | StrOutputParser()
)
answer = chain.invoke("What is the capital of France?")
```

### Cache management

`VastDBVectorStore` caches table metadata after the first access to avoid
repeated bucket/schema/table round trips. If you alter the table structure
externally, invalidate the cache:

```python
store.invalidate_table_cache()
```

## Configuration Reference

### Constructor: `VastDBVectorStore(...)`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `embedding` | `Embeddings` | *required* | The embeddings model used to generate vectors. |
| `session` | `vastdb.Session` | *required* | A pre-built session connected to the VAST cluster. |
| `bucket` | `str` | *required* | The VAST bucket name containing the target table. |
| `schema` | `str` | *required* | The schema name within the bucket. |
| `table_name` | `str` | *required* | The table name for vector operations. |
| `id_column` | `str` | `"id"` | Column name for document IDs. |
| `text_column` | `str` | `"text"` | Column name for document text. |
| `vector_column` | `str` | `"vector"` | Column name for embedding vectors. |
| `metadata_column` | `str` | `"metadata"` | Column name for document metadata (stored as JSON). |
| `adbc_driver_path` | `str \| None` | `None` | Path to `libadbc_driver_vastdb.so`. Enables native ADBC vector search via `array_distance()` SQL. |
| `adbc_endpoint` | `str \| None` | `None` | ADBC/QueryEngine endpoint (hostname or IP). Separate from the HTTP REST endpoint. |
| `access_key` | `str \| None` | `None` | Access key for ADBC connection. |
| `secret_key` | `str \| None` | `None` | Secret key for ADBC connection. |

### Custom column names

Column names default to `id`, `text`, `vector`, and `metadata`. Override them at
construction time:

```python
store = VastDBVectorStore(
    embedding=my_embeddings,
    session=session,
    bucket="my-bucket",
    schema="my-schema",
    table_name="my-table",
    id_column="doc_id",
    text_column="content",
    vector_column="emb",
    metadata_column="meta",
)
```

### Factory classmethod: `from_connection_params(...)`

Creates a `VastDBVectorStore` by building a `vastdb.Session` internally from
connection parameters.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `embedding` | `Embeddings` | *required* | The embeddings model. |
| `endpoint` | `str` | *required* | The VAST cluster HTTP endpoint URL. |
| `access_key` | `str` | *required* | Access key for authentication. |
| `secret_key` | `str` | *required* | Secret key for authentication. |
| `bucket` | `str` | *required* | The VAST bucket name. |
| `schema` | `str` | *required* | The schema name within the bucket. |
| `table_name` | `str` | *required* | The table name for vector operations. |
| `adbc_driver_path` | `str \| None` | `None` | Path to ADBC driver shared library. |
| `adbc_endpoint` | `str \| None` | `None` | ADBC/QueryEngine endpoint. |
| `**kwargs` | | | Additional keyword arguments forwarded to the constructor (e.g., custom column names). |

### ADBC vector search

When `adbc_driver_path` and `adbc_endpoint` are both provided, the store uses
native ADBC SQL with `array_distance()` for server-side vector search. This does
not require a vector index on the table. If ADBC is unavailable or fails, the
store falls back to an in-memory L2Sq distance scan.

```python
store = VastDBVectorStore(
    embedding=my_embeddings,
    session=session,
    bucket="my-bucket",
    schema="my-schema",
    table_name="my-table",
    adbc_driver_path="/usr/lib/libadbc_driver_vastdb.so",
    adbc_endpoint="172.27.74.17",
    access_key="YOUR_ACCESS_KEY",
    secret_key="YOUR_SECRET_KEY",
)
```

## Subclassing Guide

`VastDBVectorStore` uses the **Template Method** pattern. Public methods like
`add_texts` and `similarity_search` handle embedding, filter conversion, and
result formatting, then delegate storage operations to five protected hook
methods. Override these hooks to customize behavior without reimplementing the
full LangChain interface.

### Hook methods

| Hook | Purpose | Returns |
|------|---------|---------|
| `_insert_vectors` | Customize record insertion | `list[str]` (IDs) |
| `_vector_search` | Customize similarity search | `list[tuple[dict, float]]` |
| `_delete_by_ids` | Customize document deletion | `bool` |
| `_get_by_ids` | Customize document retrieval | `list[dict]` |
| `_row_to_document` | Customize row-to-Document conversion | `Document` |

### Hook signatures

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
    filter_dict: dict | None = None,
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

### Transaction reuse

Each hook opens and closes its own transaction by default. The optional `tx`
parameter lets subclasses pass in an existing transaction for multi-step atomic
operations:

```python
with self._session.transaction() as tx:
    self._insert_vectors(texts, embeddings, metadatas, ids, tx=tx)
    # additional operations in the same transaction
```

### Example: typed metadata columns

The base class stores metadata as a single JSON string column. If you need typed
columns for performance-critical filtering, override `_insert_vectors` and
`_row_to_document`:

```python
import pyarrow as pa
from langchain_core.documents import Document
from langchain_vastdb import VastDBVectorStore


class TypedMetadataStore(VastDBVectorStore):
    """Store with typed 'category' and 'priority' metadata columns."""

    def _insert_vectors(self, texts, embeddings, metadatas, ids, *, tx=None):
        vector_dim = len(embeddings[0])
        vector_type = pa.list_(pa.field("item", pa.float32(), nullable=False), vector_dim)
        batch = pa.RecordBatch.from_pydict({
            self._id_column: ids,
            self._text_column: texts,
            self._vector_column: pa.array(embeddings, type=vector_type),
            "category": [m.get("category", "") for m in metadatas],
            "priority": [m.get("priority", 0) for m in metadatas],
        })
        if tx is not None:
            table = self._get_table(tx)
            table.insert(batch)
            return ids
        with self._session.transaction() as new_tx:
            table = self._get_table(new_tx)
            table.insert(batch)
            return ids

    def _row_to_document(self, row, score=None):
        return Document(
            page_content=row.get(self._text_column, ""),
            metadata={
                "id": row.get(self._id_column),
                "category": row.get("category", ""),
                "priority": row.get("priority", 0),
            },
        )
```

This gives you typed, indexable columns while the public LangChain interface
(`add_texts`, `similarity_search`, etc.) stays unchanged.

## Examples

See the [`examples/`](examples/) directory for runnable scripts:

- `basic_usage.py` -- add texts, search, retrieve
- `rag_pipeline.py` -- `as_retriever()` + LCEL RAG chain
- `subclassing.py` -- custom hook overrides for typed metadata
- `filtered_search.py` -- metadata filtering patterns

## Development

Clone the repository and install dependencies with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Run the linter:

```bash
uv run ruff check .
```

Run unit tests:

```bash
uv run pytest tests/unit_tests/
```

Run integration tests (requires a VAST cluster):

```bash
uv run pytest tests/integration_tests/
```

## License

Apache-2.0 -- see [LICENSE](LICENSE) for details.
