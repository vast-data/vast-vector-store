"""RAG pipeline using VastDBVectorStore as a retriever.

Demonstrates creating a store, populating it with documents,
converting it to a LangChain retriever, and building an LCEL RAG chain.

Prerequisites:
    - A running VAST cluster with vector search support
    - Environment variables: VASTDB__ENDPOINT, VASTDB__ACCESS_KEY, VASTDB__SECRET_KEY
    - An LLM provider package (e.g., langchain-openai) for the full chain

Usage:
    export VASTDB__ENDPOINT="http://your-vast-endpoint:443"
    export VASTDB__ACCESS_KEY="your-access-key"
    export VASTDB__SECRET_KEY="your-secret-key"
    python examples/rag_pipeline.py
"""

from __future__ import annotations

import os

from langchain_core.embeddings import FakeEmbeddings
from langchain_core.prompts import ChatPromptTemplate

from langchain_vastdb import VastDBVectorStore

# ---------------------------------------------------------------------------
# 1. Connection setup.
# ---------------------------------------------------------------------------
ENDPOINT = os.environ["VASTDB__ENDPOINT"]
ACCESS_KEY = os.environ["VASTDB__ACCESS_KEY"]
SECRET_KEY = os.environ["VASTDB__SECRET_KEY"]
BUCKET = os.environ.get("VASTDB__BUCKET", "example-bucket")

# ---------------------------------------------------------------------------
# 2. Create the vector store and add sample documents.
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
    table_name="example-rag-pipeline",
)

store.add_texts(
    texts=[
        "VastDB supports vector similarity search on analytical data.",
        "langchain-vastdb provides a VectorStore integration for VAST Database.",
        "The as_retriever() method converts a vector store into a LangChain retriever.",
        "LCEL (LangChain Expression Language) lets you compose chains with the | operator.",
    ],
    metadatas=[
        {"source": "vastdb-docs"},
        {"source": "langchain-vastdb-docs"},
        {"source": "langchain-docs"},
        {"source": "langchain-docs"},
    ],
)
print("Documents added to the vector store.")

# ---------------------------------------------------------------------------
# 3. Create a retriever from the vector store.
#    search_kwargs controls how many documents to retrieve per query.
# ---------------------------------------------------------------------------
retriever = store.as_retriever(search_kwargs={"k": 2})

# ---------------------------------------------------------------------------
# 4. Define a helper to format retrieved documents into a single string.
# ---------------------------------------------------------------------------


def format_docs(docs: list) -> str:
    """Join document contents with double newlines."""
    return "\n\n".join(doc.page_content for doc in docs)


# ---------------------------------------------------------------------------
# 5. Build an LCEL RAG chain.
#
#    The chain retrieves relevant documents, formats them into a prompt,
#    sends the prompt to an LLM, and parses the output as a string.
#
#    NOTE: You must provide an actual LLM to run this chain. For example:
#        from langchain_openai import ChatOpenAI
#        llm = ChatOpenAI(model="gpt-4o-mini")
#    The chain construction below is shown for reference.
# ---------------------------------------------------------------------------
prompt = ChatPromptTemplate.from_template(
    "Answer the question based only on the following context:\n\n"
    "{context}\n\n"
    "Question: {question}"
)

# Uncomment and replace with your LLM to run the full chain:
#   from langchain_core.output_parsers import StrOutputParser
#   from langchain_core.runnables import RunnablePassthrough
#   from langchain_openai import ChatOpenAI
#
#   llm = ChatOpenAI(model="gpt-4o-mini")
#
#   chain = (
#       {"context": retriever | format_docs, "question": RunnablePassthrough()}
#       | prompt
#       | llm
#       | StrOutputParser()
#   )
#
#   answer = chain.invoke("What is langchain-vastdb?")
#   print(f"Answer: {answer}")

# ---------------------------------------------------------------------------
# 6. Demonstrate the retriever independently (no LLM required).
# ---------------------------------------------------------------------------
docs = retriever.invoke("How does langchain-vastdb work?")
print(f"\nRetrieved {len(docs)} documents:")
for doc in docs:
    print(f"  - {doc.page_content!r}")

print("\nTo run the full RAG chain, uncomment the LLM section above")
print("and install an LLM provider (e.g., pip install langchain-openai).")
