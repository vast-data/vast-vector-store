"""Filtered similarity search with VastDBVectorStore.

Demonstrates adding documents with varied metadata and using the
``filter`` parameter to narrow similarity search results.

Prerequisites:
    - A running VAST cluster with vector search support
    - Environment variables: VASTDB__ENDPOINT, VASTDB__ACCESS_KEY, VASTDB__SECRET_KEY

Usage:
    export VASTDB__ENDPOINT="http://your-vast-endpoint:443"
    export VASTDB__ACCESS_KEY="your-access-key"
    export VASTDB__SECRET_KEY="your-secret-key"
    python examples/filtered_search.py
"""

from __future__ import annotations

import os

from langchain_core.embeddings import FakeEmbeddings

from langchain_vastdb import VastDBVectorStore

# ---------------------------------------------------------------------------
# 1. Connection setup.
# ---------------------------------------------------------------------------
ENDPOINT = os.environ["VASTDB__ENDPOINT"]
ACCESS_KEY = os.environ["VASTDB__ACCESS_KEY"]
SECRET_KEY = os.environ["VASTDB__SECRET_KEY"]
BUCKET = os.environ.get("VASTDB__BUCKET", "example-bucket")

# ---------------------------------------------------------------------------
# 2. Create the vector store.
#    Replace FakeEmbeddings with your real embedding model.
# ---------------------------------------------------------------------------
embedding = FakeEmbeddings(size=1536)

store = VastDBVectorStore.from_connection_params(
    embedding=embedding,
    endpoint=ENDPOINT,
    access_key=ACCESS_KEY,
    secret_key=SECRET_KEY,
    bucket=BUCKET,
    schema="example-schema",
    table_name="example-filtered-search",
)

# ---------------------------------------------------------------------------
# 3. Add documents with diverse metadata.
#    The metadata is stored as JSON and can be used for filtering.
# ---------------------------------------------------------------------------
store.add_texts(
    texts=[
        "Introduction to machine learning algorithms.",
        "Deep learning with neural networks.",
        "Database indexing strategies for performance.",
        "SQL query optimization techniques.",
        "Natural language processing fundamentals.",
        "Distributed systems design patterns.",
    ],
    metadatas=[
        {"category": "ml", "level": "beginner"},
        {"category": "ml", "level": "advanced"},
        {"category": "database", "level": "intermediate"},
        {"category": "database", "level": "advanced"},
        {"category": "ml", "level": "beginner"},
        {"category": "systems", "level": "advanced"},
    ],
)
print("Added 6 documents with varied metadata.")

# ---------------------------------------------------------------------------
# 4. Search WITHOUT a filter -- returns the most similar documents
#    regardless of metadata.
# ---------------------------------------------------------------------------
print("\n--- Unfiltered search for 'data processing' ---")
results = store.similarity_search("data processing", k=3)
for doc in results:
    print(f"  - {doc.page_content!r}  metadata={doc.metadata}")

# ---------------------------------------------------------------------------
# 5. Search WITH a filter -- only returns documents whose metadata
#    matches the filter dict. The filter is converted to an ibis
#    predicate internally and applied during the vector search.
# ---------------------------------------------------------------------------
print("\n--- Filtered search: category='ml' ---")
results = store.similarity_search("data processing", k=3, filter={"category": "ml"})
for doc in results:
    print(f"  - {doc.page_content!r}  metadata={doc.metadata}")

# ---------------------------------------------------------------------------
# 6. Filter by a different key to further narrow results.
# ---------------------------------------------------------------------------
print("\n--- Filtered search: category='database' ---")
results = store.similarity_search(
    "performance optimization", k=3, filter={"category": "database"}
)
for doc in results:
    print(f"  - {doc.page_content!r}  metadata={doc.metadata}")

# ---------------------------------------------------------------------------
# 7. Filter by level to show another metadata dimension.
# ---------------------------------------------------------------------------
print("\n--- Filtered search: level='beginner' ---")
results = store.similarity_search("learning", k=3, filter={"level": "beginner"})
for doc in results:
    print(f"  - {doc.page_content!r}  metadata={doc.metadata}")
