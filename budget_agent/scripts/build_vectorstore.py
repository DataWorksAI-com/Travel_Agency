#!/usr/bin/env python3
"""
Build the Budget Agent's vector store from the source-of-truth city
cost documents.

This is the "R" (retrieval) setup step in RAG:
  1. Load the raw documents (src/budget_agent/data/city_cost_docs.py)
  2. Split them into chunks (each doc is short, so mostly 1 chunk each,
     but chunking is included so this scales if docs get longer)
  3. Embed each chunk using a local sentence-transformers model
  4. Store the embeddings + text in a persisted Chroma vector DB

Run this ONCE (or whenever city_cost_docs.py changes):
    python scripts/build_vectorstore.py

This downloads a small embedding model on first run (~80MB), so it
needs internet access the first time. After that, the vector store is
persisted to ./chroma_db and no internet is needed to query it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

from budget_agent.data import CITY_COST_DOCS

PERSIST_DIR = str(Path(__file__).resolve().parent.parent / "chroma_db")
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def build_vectorstore() -> None:
    print(f"Loading {len(CITY_COST_DOCS)} source documents...")

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

    documents = []
    for entry in CITY_COST_DOCS:
        chunks = splitter.split_text(entry["text"])
        for chunk in chunks:
            documents.append(
                Document(
                    page_content=chunk,
                    metadata={"city": entry["city"], "country": entry["country"]},
                )
            )

    print(f"Split into {len(documents)} chunks.")
    print(f"Loading embedding model ({EMBEDDING_MODEL})... this may take a moment on first run.")
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

    print(f"Embedding and persisting to {PERSIST_DIR}...")
    Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=PERSIST_DIR,
    )

    print("Vector store built successfully.")


if __name__ == "__main__":
    build_vectorstore()
