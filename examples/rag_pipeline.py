"""RAG pipeline using VastDBVectorStore as a retriever.

Demonstrates creating a store, populating it with documents,
converting it to a LangChain retriever, and building an LCEL RAG chain.

Prerequisites:
    - A running VAST cluster with vector search support
    - A ``.env`` file at the project root (loaded automatically)
    - An LLM provider package (e.g., langchain-openai) for the full chain

Usage:
    python examples/rag_pipeline.py
"""

from __future__ import annotations

import os
import uuid

import pyarrow as pa
import vastdb
from dotenv import load_dotenv
from langchain_core.embeddings import FakeEmbeddings
from langchain_core.prompts import ChatPromptTemplate

from langchain_vastdb import VastDBVectorStore

# ---------------------------------------------------------------------------
# 0. Load environment variables from .env (same mechanism as conftest.py).
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# 1. Connection setup.
# ---------------------------------------------------------------------------
ENDPOINT = os.environ["VASTDB__ENDPOINT"]
ACCESS_KEY = os.environ["VASTDB__ACCESS_KEY"]
SECRET_KEY = os.environ["VASTDB__SECRET_KEY"]
BUCKET = os.environ.get("VASTDB__BUCKET", "example-bucket")

# ---------------------------------------------------------------------------
# 2. Create an isolated schema and table for this example run.
# ---------------------------------------------------------------------------
VECTOR_DIM = 1536
embedding = FakeEmbeddings(size=VECTOR_DIM)

run_id = uuid.uuid4().hex[:8]
SCHEMA = f"example_rag_{run_id}"
TABLE = f"example_rag_{run_id}"

TABLE_SCHEMA = pa.schema(
    [
        pa.field("id", pa.string()),
        pa.field("text", pa.string()),
        pa.field(
            "embedding",
            pa.list_(
                pa.field("item", pa.float32(), nullable=False), VECTOR_DIM
            ),
        ),
        pa.field("metadata", pa.string()),
    ]
)

session = vastdb.connect(
    endpoint=ENDPOINT, access=ACCESS_KEY, secret=SECRET_KEY, ssl_verify=False
)
with session.transaction() as tx:
    b = tx.bucket(BUCKET)
    b.create_schema(SCHEMA)
    b.schema(SCHEMA).create_table(TABLE, TABLE_SCHEMA)

try:
    # -------------------------------------------------------------------
    # 3. Create the vector store and add sample documents.
    #    Replace FakeEmbeddings with your real embedding model.
    # -------------------------------------------------------------------
    store = VastDBVectorStore.from_connection_params(
        embedding=embedding,
        endpoint=ENDPOINT,
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        bucket=BUCKET,
        schema=SCHEMA,
        table_name=TABLE,
        ssl_verify=False,
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

    # -------------------------------------------------------------------
    # 4. Create a retriever from the vector store.
    #    search_kwargs controls how many documents to retrieve per query.
    # -------------------------------------------------------------------
    retriever = store.as_retriever(search_kwargs={"k": 2})

    # -------------------------------------------------------------------
    # 5. Define a helper to format retrieved documents into a single string.
    # -------------------------------------------------------------------

    def format_docs(docs: list) -> str:
        """Join document contents with double newlines."""
        return "\n\n".join(doc.page_content for doc in docs)

    # -------------------------------------------------------------------
    # 6. Build an LCEL RAG chain.
    #
    #    The chain retrieves relevant documents, formats them into a
    #    prompt, sends the prompt to an LLM, and parses the output.
    #
    #    NOTE: You must provide an actual LLM to run this chain:
    #        from langchain_openai import ChatOpenAI
    #        llm = ChatOpenAI(model="gpt-4o-mini")
    #    The chain construction below is shown for reference.
    # -------------------------------------------------------------------
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

    # -------------------------------------------------------------------
    # 7. Demonstrate the retriever independently (no LLM required).
    # -------------------------------------------------------------------
    docs = retriever.invoke("How does langchain-vastdb work?")
    print(f"\nRetrieved {len(docs)} documents:")
    for doc in docs:
        print(f"  - {doc.page_content!r}")

    print("\nTo run the full RAG chain, uncomment the LLM section above")
    print("and install an LLM provider (e.g., pip install langchain-openai).")

finally:
    # -------------------------------------------------------------------
    # Cleanup: drop the table and schema created for this run.
    # -------------------------------------------------------------------
    try:
        with session.transaction() as tx:
            sc = tx.bucket(BUCKET).schema(SCHEMA)
            sc.table(TABLE).drop()
            sc.drop()
    except Exception:
        pass
