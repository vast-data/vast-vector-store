# Migration Guide: Moving to VastDBVectorStore

This guide shows how to migrate an existing LangChain `VectorStore` subclass
to inherit from `VastDBVectorStore` instead. The Template Method pattern lets
you keep your domain logic while removing boilerplate for embedding, batching,
filter conversion, and transaction management.

## Before you start

Install the package:

```bash
pip install langchain-vastdb
# or
uv add langchain-vastdb
```

## Step 1: Change the parent class

Replace `VectorStore` (or any custom base) with `VastDBVectorStore`:

```python
# Before
from langchain_core.vectorstores import VectorStore

class MyStore(VectorStore):
    ...

# After
from langchain_vastdb import VastDBVectorStore

class MyStore(VastDBVectorStore):
    ...
```

## Step 2: Map your methods to hook overrides

`VastDBVectorStore` handles the full LangChain interface (`add_texts`,
`similarity_search`, `delete`, `get_by_ids`, `from_texts`). Your subclass
only overrides the **hook methods** that customize storage behavior.

| LangChain interface method | VastDBVectorStore hook to override | What the hook does |
|---|---|---|
| `add_texts()` / `add_documents()` | `_insert_vectors()` | Build and insert a PyArrow RecordBatch |
| `similarity_search()` / `similarity_search_by_vector()` | `_vector_search()` | Execute the vector similarity query |
| `delete()` | `_delete_by_ids()` | Delete rows by document ID |
| `get_by_ids()` | `_get_by_ids()` | Retrieve rows by document ID |
| *(result conversion)* | `_row_to_document()` | Convert a VastDB row dict to a `Document` |

Move the storage logic from your old interface methods into the matching hook.
Each hook receives pre-processed inputs (embeddings already computed, filters
already converted) and returns a simple result.

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

The optional `tx` parameter lets your hook reuse an existing transaction
(e.g., for atomic upsert). If `tx` is `None`, the hook opens its own.

## Step 3: Delete inherited interface methods

Remove any methods that `VastDBVectorStore` already provides:

- `add_texts` / `add_documents`
- `similarity_search` / `similarity_search_with_score` / `similarity_search_by_vector`
- `from_texts` / `from_documents`
- `delete`
- `get_by_ids`
- `as_retriever`

These are now handled by the base class. Your subclass only keeps hooks and
domain-specific methods (e.g., custom query builders, business logic).

## Step 4: Keep domain-specific methods

Any methods unique to your subclass that are not part of the LangChain
`VectorStore` interface stay unchanged. The base class does not touch them.

## Step 5: Validate

Run your existing test suite. The public API (`add_texts`, `similarity_search`,
etc.) is unchanged, so callers should work without modification.

```bash
pytest tests/
```

## Before/after comparison

### Before: Custom VectorStore subclass (~200 LOC)

```python
from langchain_core.vectorstores import VectorStore
from langchain_core.documents import Document
import pyarrow as pa
import vastdb

class MyStore(VectorStore):
    def __init__(self, embedding, session, bucket, schema, table_name):
        self.embedding = embedding
        self.session = session
        self.bucket = bucket
        self.schema = schema
        self.table_name = table_name

    def add_texts(self, texts, metadatas=None, ids=None, **kwargs):
        # Compute embeddings manually
        embeddings = self.embedding.embed_documents(texts)
        # Generate IDs if missing
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]
        if metadatas is None:
            metadatas = [{} for _ in texts]
        # Build PyArrow batch
        vector_dim = len(embeddings[0])
        vector_type = pa.list_(pa.float32(), vector_dim)
        batch = pa.RecordBatch.from_pydict({
            "id": ids,
            "text": texts,
            "vector": pa.array(embeddings, type=vector_type),
            "metadata": [json.dumps(m) for m in metadatas],
        })
        # Open transaction, get table, insert
        with self.session.transaction() as tx:
            table = tx.bucket(self.bucket).schema(self.schema).table(self.table_name)
            table.insert(batch)
        return ids

    def similarity_search(self, query, k=4, **kwargs):
        # Compute query embedding manually
        query_vector = self.embedding.embed_query(query)
        # Open transaction, run vector search
        with self.session.transaction() as tx:
            table = tx.bucket(self.bucket).schema(self.schema).table(self.table_name)
            result = table.select(
                columns=["id", "text", "metadata"],
                vector_search=VectorSearch(
                    vector_column="vector",
                    query_vector=query_vector,
                    top_k=k,
                ),
            ).read_all().to_pylist()
        # Convert rows to Documents manually
        return [
            Document(
                page_content=row["text"],
                metadata=json.loads(row.get("metadata", "{}")),
                id=row["id"],
            )
            for row in result
        ]

    def from_texts(cls, texts, embedding, metadatas=None, **kwargs):
        store = cls(embedding=embedding, **kwargs)
        store.add_texts(texts, metadatas=metadatas)
        return store

    def delete(self, ids, **kwargs):
        # Manual transaction + predicate building + row selection + delete
        ...

    def get_by_ids(self, ids, **kwargs):
        # Manual transaction + select + convert
        ...

    # ... more boilerplate for search_with_score, by_vector, etc.
```

### After: VastDBVectorStore subclass (~40 LOC)

```python
from langchain_vastdb import VastDBVectorStore
from langchain_core.documents import Document
import pyarrow as pa

class MyStore(VastDBVectorStore):
    CATEGORY_COLUMN = "category"

    def _select_columns(self) -> list[str]:
        return [self._id_column, self._text_column, self.CATEGORY_COLUMN]

    def _insert_vectors(self, texts, embeddings, metadatas, ids, *, tx=None):
        if not embeddings:
            return ids
        vector_dim = len(embeddings[0])
        vector_type = pa.list_(
            pa.field("item", pa.float32(), nullable=False), vector_dim
        )
        batch = pa.RecordBatch.from_pydict({
            self._id_column: ids,
            self._text_column: texts,
            self._vector_column: pa.array(embeddings, type=vector_type),
            self.CATEGORY_COLUMN: [m.get("category", "") for m in metadatas],
        })
        if tx is not None:
            self._get_table(tx).insert(batch)
            return ids
        with self._session.transaction() as new_tx:
            self._get_table(new_tx).insert(batch)
            return ids

    def _row_to_document(self, row, score=None):
        return Document(
            page_content=row.get(self._text_column, ""),
            metadata={"category": row.get(self.CATEGORY_COLUMN, "")},
            id=row.get(self._id_column),
        )
```

**Result:** ~80% less code. No manual embedding, no transaction boilerplate,
no filter conversion, no `from_texts`/`delete`/`get_by_ids` reimplementation.

## Post-migration checklist

- [ ] Parent class changed to `VastDBVectorStore`
- [ ] Storage logic moved into hook overrides
- [ ] Old interface methods (`add_texts`, `similarity_search`, etc.) deleted
- [ ] Domain-specific methods preserved unchanged
- [ ] `from_connection_params()` used for construction (or direct constructor)
- [ ] Tests pass with no caller-side changes
