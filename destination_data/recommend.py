"""Destination recommendation tool (RAG) for the Destination Agent data layer.

Case 2: the user described what they want but named no city. This embeds the
local destination corpus into a ChromaDB vector store and returns the closest
matches by meaning.

Corpus  : destinations.json, produced by build_corpus.py (rerun that to refresh).
Vectors : ChromaDB, local and on-disk under ./chroma_db - no API key, no service.
Embedding: ChromaDB's default all-MiniLM-L6-v2 (ONNX). The model file (~80 MB)
           downloads once on first use and is cached locally afterwards.

Contract:
  - returns plain Python lists/dicts, never JSON strings
  - never raises: every failure path returns {"error": "..."}
  - every field returned comes from the corpus, which came from real APIs
"""

# truststore MUST be injected before any HTTPS happens - here that includes the
# one-off embedding model download, not just requests.
import truststore

truststore.inject_into_ssl()

import hashlib
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CORPUS_PATH = os.path.join(BASE_DIR, "destinations.json")
VECTOR_DB_PATH = os.path.join(BASE_DIR, "chroma_db")
COLLECTION_NAME = "destinations"

DEFAULT_TOP_K = 5
MIN_TOP_K = 1
MAX_TOP_K = 20

_collection = None  # cached across calls so the corpus is embedded only once


def _load_corpus():
    """Read destinations.json. Returns (entries, None) or (None, error_dict)."""
    if not os.path.exists(CORPUS_PATH):
        return None, {"error": f"Destination corpus not found at {CORPUS_PATH}. Run build_corpus.py first."}

    try:
        with open(CORPUS_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as exc:
        return None, {"error": f"Destination corpus could not be read ({exc})"}

    entries = payload.get("destinations") if isinstance(payload, dict) else None
    if not isinstance(entries, list) or not entries:
        return None, {"error": "Destination corpus contained no destinations. Rerun build_corpus.py."}

    usable = [
        e
        for e in entries
        if isinstance(e, dict)
        and isinstance(e.get("description"), str)
        and e.get("name")
        and e.get("lat") is not None
        and e.get("lon") is not None
    ]
    if not usable:
        return None, {"error": "Destination corpus had no entries with the required fields."}

    return usable, None


def _get_collection():
    """Build or reuse the vector store. Returns (collection, None) or (None, error_dict)."""
    global _collection
    if _collection is not None:
        return _collection, None

    entries, error = _load_corpus()
    if error:
        return None, error

    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError as exc:
        return None, {"error": f"ChromaDB is not installed ({exc}). Run: pip install chromadb"}

    # Fingerprint the actual text we are about to embed. A count check is not
    # enough: editing descriptions without changing how many there are would
    # otherwise leave a stale index in place forever.
    fingerprint = hashlib.sha256(
        "\n".join(f"{e.get('name')}|{e.get('country_code')}|{e['description']}" for e in entries).encode("utf-8")
    ).hexdigest()[:16]

    # Cosine space makes match_score readable as a similarity in 0..1.
    collection_metadata = {"hnsw:space": "cosine", "corpus_fingerprint": fingerprint}

    try:
        client = chromadb.PersistentClient(
            path=VECTOR_DB_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata=collection_metadata,
        )
    except Exception as exc:  # chromadb raises a wide range of backend errors
        return None, {"error": f"Vector store unavailable: could not open ChromaDB ({exc})"}

    try:
        stored_fingerprint = (collection.metadata or {}).get("corpus_fingerprint")
        needs_load = stored_fingerprint != fingerprint or collection.count() != len(entries)
    except Exception as exc:
        return None, {"error": f"Vector store unavailable: could not inspect ChromaDB ({exc})"}

    if needs_load:
        try:
            client.delete_collection(COLLECTION_NAME)
            collection = client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata=collection_metadata,
            )
            collection.add(
                ids=[f"{e['name']}|{e.get('country_code')}|{i}" for i, e in enumerate(entries)],
                documents=[e["description"] for e in entries],
                metadatas=[
                    {
                        "name": str(e.get("name")),
                        "country_code": str(e.get("country_code") or ""),
                        "lat": float(e["lat"]),
                        "lon": float(e["lon"]),
                    }
                    for e in entries
                ],
            )
        except Exception as exc:
            return None, {"error": f"Vector store unavailable: could not embed the corpus ({exc})"}

    _collection = collection
    return _collection, None


def _as_query_text(preferences):
    """Flatten preferences into one query string. Returns (text, None) or (None, error)."""
    if isinstance(preferences, str):
        text = preferences.strip()
    elif isinstance(preferences, (list, tuple, set)):
        parts = [str(p).strip() for p in preferences if p is not None and str(p).strip()]
        text = ", ".join(parts)
    elif isinstance(preferences, dict):
        parts = [f"{k}: {v}" for k, v in preferences.items() if v is not None and str(v).strip()]
        text = ", ".join(parts)
    elif preferences is None:
        return None, {"error": "preferences was empty - describe what the traveller wants"}
    else:
        return None, {"error": f"preferences must be a string, list or dict, got {type(preferences).__name__}"}

    if not text:
        return None, {"error": "preferences was empty - describe what the traveller wants"}
    return text, None


def recommend_destinations(preferences, top_k=DEFAULT_TOP_K):
    """Return a ranked shortlist of candidate destinations.

    Args:
        preferences: what the traveller wants - a string, a list of strings,
            or a dict of preference fields.
        top_k: how many candidates to return (default 5).

    Returns:
        On success, a list of {"name", "country_code", "lat", "lon",
        "description", "match_score"}, best first. match_score is cosine
        similarity in roughly 0..1, higher is closer.
        On any failure, a dict {"error": "..."}.
    """
    query_text, error = _as_query_text(preferences)
    if error:
        return error

    try:
        top_k = int(top_k)
    except (TypeError, ValueError):
        return {"error": f"top_k must be an integer, got {top_k!r}"}
    top_k = max(MIN_TOP_K, min(MAX_TOP_K, top_k))

    collection, error = _get_collection()
    if error:
        return error

    try:
        available = collection.count()
    except Exception as exc:
        return {"error": f"Vector store unavailable: could not count the collection ({exc})"}

    try:
        results = collection.query(
            query_texts=[query_text],
            n_results=min(top_k, available),
        )
    except Exception as exc:
        return {"error": f"Recommendation failed: vector search error ({exc})"}

    documents = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]

    if not documents:
        return {"error": f"No destinations matched {query_text!r}"}

    shortlist = []
    for document, metadata, distance in zip(documents, metadatas, distances):
        metadata = metadata or {}
        # Cosine distance -> similarity. Clamped because tiny negative
        # distances can come back from the index on near-identical vectors.
        score = 1.0 - float(distance)
        score = max(0.0, min(1.0, score))
        shortlist.append(
            {
                "name": metadata.get("name"),
                "country_code": metadata.get("country_code"),
                "lat": metadata.get("lat"),
                "lon": metadata.get("lon"),
                "description": document,
                "match_score": round(score, 3),
            }
        )

    return shortlist


if __name__ == "__main__":
    probes = [
        ["warm", "coastal", "Asia"],
        ["cool", "historic", "Europe", "inland"],
        "",
    ]

    for probe in probes:
        print(f"\n=== recommend_destinations({probe!r}) ===")
        outcome = recommend_destinations(probe)

        if isinstance(outcome, dict):
            print(outcome)
            continue

        for rank, candidate in enumerate(outcome, start=1):
            print(f"\n{rank}. {candidate['name']} ({candidate['country_code']})  match_score={candidate['match_score']}")
            print(f"   lat={candidate['lat']}, lon={candidate['lon']}")
            print(f"   description: {candidate['description']}")
        print(f"\nkeys returned: {sorted(outcome[0].keys())}")
