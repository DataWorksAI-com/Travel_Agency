"""
Build Chroma Vector DB for the Activities Agent (New York)
-------------------------------------------------------------
This is knowledge-source tier 2 (semantic RAG). Loads new_york.json
into a persistent Chroma collection, enabling meaning-based search
over activity descriptions — used when tier 1 (exact filtering)
doesn't find a good match, e.g. for a vague query like "something
romantic."

Run once to (re)build the DB, or any time new_york.json changes:
    python build_vector_db.py
"""

import json
import chromadb

DB_PATH = "./chroma_db"
COLLECTION_NAME = "activities_ny"
DATA_FILE = "new_york.json"
CITY_NAME = "New York"


def load_data(path=DATA_FILE):
    with open(path, "r") as f:
        return json.load(f)


def build_collection():
    client = chromadb.PersistentClient(path=DB_PATH)

    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "New York activities/attractions for the Travel Agent capstone"},
    )

    activities = load_data()

    collection.add(
        ids=[f"ny_{i:03d}" for i in range(len(activities))],
        documents=[a["description"] for a in activities],
        metadatas=[
            {
                "name": a["name"],
                "city": CITY_NAME,
                "category": a["category"],
                "price_tier": a["price_tier"],
            }
            for a in activities
        ],
    )

    print(f"Loaded {len(activities)} activities into Chroma collection '{COLLECTION_NAME}' at {DB_PATH}")
    return collection


if __name__ == "__main__":
    build_collection()
