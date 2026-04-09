# langchain-vastdb

LangChain VectorStore integration for [VAST Database](https://vastdata.com/).

`langchain-vastdb` provides a `VastDBVectorStore` class that implements the
LangChain `VectorStore` interface, enabling similarity search, document storage,
and retrieval-augmented generation (RAG) workflows backed by VAST Database's
native vector indexing.

> **Status:** Alpha (v0.0.1). The constructor and session management are
> available; vector operations (`add_texts`, `similarity_search`, `delete`, etc.)
> are under active development.

## Requirements

- Python 3.10+
- A running VAST Database cluster with vector index support
- `vastdb` SDK >= 2.0.3
- `langchain-core` >= 0.3

## Installation

```bash
pip install langchain-vastdb
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add langchain-vastdb
```

## Quick start

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

### Cache management

`VastDBVectorStore` caches table metadata after the first access to avoid
repeated bucket/schema/table round trips. If you alter the table structure
externally, invalidate the cache:

```python
store.invalidate_table_cache()
```

## Development

Clone the repository and install dependencies with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Run the linter:

```bash
uv run ruff check .
```

Run tests:

```bash
uv run pytest tests/
```

## License

Apache-2.0 -- see [LICENSE](LICENSE) for details.
