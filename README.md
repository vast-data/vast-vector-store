# langchain-vastdb

LangChain VectorStore integration for [VAST Database](https://vastdata.com/).

`langchain-vastdb` provides a `VastDBVectorStore` class that implements the
LangChain `VectorStore` interface, enabling similarity search, document storage,
and retrieval-augmented generation (RAG) workflows backed by VAST Database's
native vector indexing.

**Compatibility:** Python 3.10 - 3.13 | langchain-core >= 1.0, < 2 | vastdb >= 2.0.3 | Query Engine paths require VAST 5.4+

**Status:** Alpha (v0.0.1). API may change between minor releases.

**License:** Apache-2.0

## Requirements

- Python 3.10+
- A running VAST Database cluster. The store reads the cluster version from
  the SDK session and picks paths per operation:

  | VAST | search | `get_by_ids` | delete | notes |
  |---|---|---|---|---|
  | 5.3 | SDK in-memory scan (`VASTDB_ALLOW_FALLBACK=1` required) | SDK | SDK | no Query Engine |
  | 5.4 | Query Engine, brute force | Query Engine | SDK | not live-tested; Query Engine DML unverified |
  | 5.5 | Query Engine, vector index when built | Query Engine | Query Engine | verified on 5.5.1 |
  | unknown | Query Engine | Query Engine | SDK | session reports no version; one warning per store |

  Configuring ADBC on a 5.3 cluster is harmless: lookup and delete stay on the SDK.
- `vastdb` SDK >= 2.0.3
- `langchain-core` >= 1.0, < 2
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
    access="YOUR_ACCESS_KEY",
    secret="YOUR_SECRET_KEY",
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

Credentials are passed to `vastdb.connect()` for the SDK session. They are also
kept on the instance as private attributes (`_access_key`, `_secret_key`) so the
ADBC Query Engine connection can reuse them; they are never exposed publicly.

### Option 3: Create a store and add texts in one call

```python
import vastdb
from langchain_vastdb import VastDBVectorStore

session = vastdb.connect(
    endpoint="http://vast-cluster:8070",
    access="YOUR_ACCESS_KEY",
    secret="YOUR_SECRET_KEY",
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
| `adbc_driver_path` | `str \| None` | `None` | Path to `libadbc_driver_vastdb.so`. Enables Query Engine search, lookup and delete. |
| `adbc_endpoint` | `str \| None` | `None` | Full Query Engine URL (e.g. `http://host:80`), separate from the SDK endpoint. |
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

### ADBC Query Engine operations

With the ADBC driver, endpoint and credentials configured, vector search fetches
ranked documents in one Query Engine SQL query. `get_by_ids` and delete also
use the Query Engine; upsert joins the SQL delete and SDK Arrow insert in one
transaction. Insertion remains SDK Arrow. A vector index is optional: without
one (or on VAST 5.4) the Query Engine brute-forces the distance; with one, the
distance function comes from the index metadata (`array_distance` for l2sq,
`array_inner_product` for ip). A freshly created indexed table may brute-force
until the index is built. See the version table under Requirements for which
operations use the Query Engine on 5.3, 5.4 and 5.5. Without ADBC, lookup and
delete retain their SDK paths. With `VASTDB_ALLOW_FALLBACK=1`, search, lookup
and delete all fall back to the SDK on ADBC errors; otherwise errors propagate.
Search and lookup without a transaction or per-call overrides reuse one
autocommit connection per store per thread, reconnecting after an error; calls
given `tx` and delete use a dedicated connection joined to the transaction.

Unfiltered `count()` uses cached table stats, which may lag recent writes or
over-count while a table settles. Use `count(predicate)` for an exact count;
it scans matching IDs rather than using Query Engine `COUNT(*)`.

```python
store = VastDBVectorStore(
    embedding=my_embeddings,
    session=session,
    bucket="my-bucket",
    schema="my-schema",
    table_name="my-table",
    adbc_driver_path="/usr/lib/libadbc_driver_vastdb.so",
    adbc_endpoint="http://query-engine.example.com:80",
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
| `_build_metadata_columns` | Customize column layout for metadata | `dict[str, list]` |
| `_select_columns` / `_typed_metadata_columns` | Customize document columns projected during search and lookup | `list[str]` / mapping |
| `_vector_search` | Customize similarity search | `list[tuple[dict, float]]` |
| `_delete_by_ids` | Customize document deletion | `bool` |
| `_get_by_ids` | Customize ID lookup (not used by ADBC search) | `list[dict]` |
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
    tx: Transaction | None = None,
    **kwargs: Any,
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

Override `_open_adbc_connection(self, **kwargs)` with `**kwargs` even if your
subclass currently ignores them: joined operations pass
`adbc_conn_kwargs_overrides={"vast.db.external_txid": str(tx.active_txid)}`.
The base implementation caches a connection when no overrides are passed; an
override that opens a fresh connection per call bypasses that cache.
Overrides of `_do_vector_search` and `_do_vector_search_adbc` receive
`tx=None` when the caller passes no transaction.

### Transaction reuse

Write hooks open a transaction by default. The optional `tx` parameter lets
subclasses pass in an existing transaction for multi-step atomic operations
(ADBC delete joins it):

```python
with self._session.transaction() as tx:
    self._insert_vectors(texts, embeddings, metadatas, ids, tx=tx)
    # additional operations in the same transaction
```

### Example: typed metadata columns

The base class stores metadata as a single JSON string column. If you need typed
columns for performance-critical filtering, set `_typed_metadata_columns`:

```python
from langchain_vastdb import TypedColumn, VastDBVectorStore


class TypedMetadataStore(VastDBVectorStore):
    """Store with typed 'category' and 'priority' metadata columns."""

    _typed_metadata_columns = {
        "category": TypedColumn(),
        "priority": TypedColumn(),
    }
```

This automatically extracts `category` and `priority` into separate typed columns
on insert, preserves any extra metadata in the JSON column, and merges everything
back together on read. The public LangChain interface (`add_texts`,
`similarity_search`, etc.) stays unchanged.

Use `TypedColumn` fields for custom defaults, PyArrow type coercion, or
controlling which columns are backfilled on read
(see the [Migration Guide](docs/migration-guide.md) for details).

## Examples

See the [`examples/`](examples/) directory for runnable scripts:

- `basic_usage.py` -- add texts, search, retrieve
- `rag_pipeline.py` -- `as_retriever()` + LCEL RAG chain
- `subclassing.py` -- declarative typed metadata columns
- `filtered_search.py` -- metadata filtering patterns

## Migration Guide

Migrating an existing `VectorStore` subclass to `VastDBVectorStore`? See the
[Migration Guide](docs/migration-guide.md) for step-by-step instructions,
a hook mapping table, and a before/after code comparison.

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
test sync
