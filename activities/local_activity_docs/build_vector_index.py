"""
Build a local Vector DB (Chroma) from local_activity_docs/*.json.
Run whenever you add/edit city JSON files:
    python build_vector_index.py
Requires Ollama embedding model:
    ollama pull nomic-embed-text
"""

import os
import shutil
import json
import glob

from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma

BASE_DIR = os.path.dirname(__file__)
DOCS_DIR = os.path.join(BASE_DIR, "local_activity_docs")
INDEX_DIR = os.path.join(BASE_DIR, "vector_index")
COLLECTION = "activities"
EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")

def load_activity_documents() -> list[Document]:

    docs: list[Document] = []
    paths = sorted(glob.glob(os.path.join(DOCS_DIR, "*.json")))

    if not paths:
        raise FileNotFoundError(f"No json files found in {DOCS_DIR}")

    for path in paths:
        city = os.path.splitext(os.path.basename(path))[0].lower()

        with open(path, "r") as f:
            activities = json.load(f)

        for i, activity in enumerate(activities):
            text=(
                f"City: {city}. "
                f"Activity: {activity['name']}. "
                f"Category: {activity['category']}. "
                f"Price: {activity['price_tier']}. "
                f"Description: {activity['description']}"
            )
            docs.append(
                Document(
                    page_content = text,
                    metadata={
                        "city": city,
                        "name": activity['name'],
                        "category": activity['category'],
                        "price_tier": activity['price_tier'],
                        "description": activity['description'],
                        "doc_id": f"{city}-{i}",
                    },
                )
            )

    return docs

def main() -> None:

    documents = load_activity_documents()

    print(f"Loaded {len(documents)} activities from {DOCS_DIR}")

    if os.path.exists(INDEX_DIR):
        shutil.rmtree(INDEX_DIR)

        print(f"Removed old index at {INDEX_DIR}")

    embeddings = OllamaEmbeddings(model=EMBED_MODEL)

    Chroma.from_documents(
        documents = documents,
        embedding = embeddings,
        persist_directory = INDEX_DIR,
        collection_name = COLLECTION,
    )

    print(f"Build vector index at {INDEX_DIR} using embeddings={EMBED_MODEL}")
    print("Done. Next: wire search_activities into activities_agent.py")

if __name__ == "__main__":
    main()