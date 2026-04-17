"""Basic usage of VastDBVectorStore.

Demonstrates creating a store, adding texts with metadata,
performing similarity search, and retrieving documents by ID.

Prerequisites:
    - A running VAST cluster with vector search support
    - Environment variables: VASTDB_ENDPOINT, VASTDB_ACCESS_KEY, VASTDB_SECRET_KEY

Usage:
    export VASTDB_ENDPOINT="http://your-vast-endpoint:443"
    export VASTDB_ACCESS_KEY="your-access-key"
    export VASTDB_SECRET_KEY="your-secret-key"
    python examples/basic_usage.py
"""

from __future__ import annotations

import os

from langchain_core.embeddings import FakeEmbeddings

from langchain_vastdb import VastDBVectorStore

# ---------------------------------------------------------------------------
# 1. Read connection credentials from environment variables.
#    Never hardcode credentials in scripts.
# ---------------------------------------------------------------------------
ENDPOINT = os.environ["VASTDB_ENDPOINT"]
ACCESS_KEY = os.environ["VASTDB_ACCESS_KEY"]
SECRET_KEY = os.environ["VASTDB_SECRET_KEY"]

# ---------------------------------------------------------------------------
# 2. Choose an embedding model.
#    FakeEmbeddings is used here so the script runs without an external model.
#    Replace with your actual model, e.g.:
#        from langchain_openai import OpenAIEmbeddings
#        embedding = OpenAIEmbeddings()
# ---------------------------------------------------------------------------
embedding = FakeEmbeddings(size=1536)

# ---------------------------------------------------------------------------
# 3. Create a VastDBVectorStore using the convenience factory.
#    This builds a vastdb.Session internally from the provided credentials.
# ---------------------------------------------------------------------------
store = VastDBVectorStore.from_connection_params(
    embedding=embedding,
    endpoint=ENDPOINT,
    access_key=ACCESS_KEY,
    secret_key=SECRET_KEY,
    bucket="example-bucket",
    schema="example-schema",
    table_name="example-basic-usage",
)

# ---------------------------------------------------------------------------
# 4. Add texts with metadata.
#    Each text is embedded automatically by the configured embedding model.
#    Metadata is stored as JSON in the metadata column.
# ---------------------------------------------------------------------------
ids = store.add_texts(
    texts=[
        "VastDB is a high-performance analytical database.",
        "LangChain provides tools for building LLM applications.",
        "Vector search finds semantically similar documents.",
    ],
    metadatas=[
        {"source": "docs", "topic": "database"},
        {"source": "docs", "topic": "framework"},
        {"source": "docs", "topic": "search"},
    ],
)
print(f"Added {len(ids)} documents with IDs: {ids}")

# ---------------------------------------------------------------------------
# 5. Perform a similarity search.
#    Returns the k most similar documents to the query text.
# ---------------------------------------------------------------------------
results = store.similarity_search("analytical database", k=2)
print(f"\nSimilarity search results ({len(results)} docs):")
for doc in results:
    print(f"  - {doc.page_content!r}  metadata={doc.metadata}")

# ---------------------------------------------------------------------------
# 6. Retrieve documents by ID.
#    Fetches specific documents without performing a vector search.
# ---------------------------------------------------------------------------
retrieved = store.get_by_ids(ids[:2])
print(f"\nRetrieved {len(retrieved)} documents by ID:")
for doc in retrieved:
    print(f"  - [{doc.id}] {doc.page_content!r}")
