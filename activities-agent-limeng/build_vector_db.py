"""
Build Chroma Vector DB for the Activities Agent (multi-city)
-----------------------------------------------------------------
This is knowledge-source tier 2 (semantic RAG). Loads every
*.json file under local_activity_docs/ into a single persistent
Chroma collection, tagging each entry with its city as metadata so
search can be filtered per city.

Cities are added by dropping a new <city>.json file into
local_activity_docs/ (same schema: name/category/price_tier/
description) and re-running this script — no code changes needed.

Run once to (re)build the DB, or any time a city file changes:
    python build_vector_db.py
"""

import json
import glob
import os
import chromadb

DB_PATH = "./chroma_db"
COLLECTION_NAME = "activities"
DOCS_DIR = os.path.join(os.path.dirname(__file__), "local_activity_docs")


def load_all_cities():
    """Load every city JSON file, returning a flat list of
    (city_name, activity_dict) pairs."""
    entries = []
    for path in sorted(glob.glob(os.path.join(DOCS_DIR, "*.json"))):
        city_name = os.path.splitext(os.path.basename(path))[0].replace("_", " ").title()
        with open(path, "r") as f:
            activities = json.load(f)
        for activity in activities:
            entries.append((city_name, activity))
    return entries


def build_collection():
    client = chromadb.PersistentClient(path=DB_PATH)

    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "Multi-city activities/attractions for the Travel Agent capstone"},
    )

    entries = load_all_cities()

    collection.add(
        ids=[f"{city.lower().replace(' ', '_')}_{i:03d}" for i, (city, _) in enumerate(entries)],
        documents=[a["description"] for _, a in entries],
        metadatas=[
            {
                "name": a["name"],
                "city": city,
                "category": a["category"],
                "price_tier": a["price_tier"],
            }
            for city, a in entries
        ],
    )

    cities = sorted(set(city for city, _ in entries))
    print(f"Loaded {len(entries)} activities across {len(cities)} cities into Chroma collection '{COLLECTION_NAME}' at {DB_PATH}")
    print(f"Cities: {', '.join(cities)}")
    return collection


if __name__ == "__main__":
    build_collection()
