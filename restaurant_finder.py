"""
Restaurant finder: the retrieval ("RAG") engine.

What it does, in plain terms:
  1. Turns each restaurant into a short piece of text.
  2. Stores those in a local Chroma vector database, which lets us search
     by MEANING (semantic search) instead of exact keywords.
  3. When someone asks a question, we find the closest restaurants by
     meaning, then apply hard filters (city, max price, dietary needs).

By default this uses Chroma's own built-in embedding model, which downloads
once and then runs locally and free. No API key, no cost.
"""

import chromadb
from restaurants_data import RESTAURANTS

_COLLECTION = None  # built once, then reused


def _doc_text(r):
    """The text we embed for meaning-based search."""
    diet = []
    if r["vegetarian"]:
        diet.append("vegetarian")
    if r["vegan"]:
        diet.append("vegan")
    if r["gluten_free"]:
        diet.append("gluten-free")
    diet_str = ", ".join(diet) if diet else "no special dietary options"
    return (f"{r['name']}. {r['cuisine']} restaurant in {r['city']}. "
            f"{r['description']} Dietary options: {diet_str}.")


def _metadata(r):
    """The structured fields we filter on (Chroma metadata must be scalar)."""
    return {
        "name": r["name"], "city": r["city"], "cuisine": r["cuisine"],
        "price": r["price"], "rating": r["rating"],
        "vegetarian": r["vegetarian"], "vegan": r["vegan"],
        "gluten_free": r["gluten_free"], "description": r["description"],
    }


def build_collection(embedding_function=None, in_memory=False, persist_path="restaurant_db"):
    """Create the vector database and load all restaurants into it."""
    if in_memory:
        client = chromadb.EphemeralClient()
    else:
        client = chromadb.PersistentClient(path=persist_path)
    try:
        client.delete_collection("restaurants")  # rebuild fresh each run
    except Exception:
        pass
    kwargs = {}
    if embedding_function is not None:
        kwargs["embedding_function"] = embedding_function
    col = client.get_or_create_collection("restaurants", **kwargs)
    col.add(
        ids=[r["id"] for r in RESTAURANTS],
        documents=[_doc_text(r) for r in RESTAURANTS],
        metadatas=[_metadata(r) for r in RESTAURANTS],
    )
    return col


def _get_collection(embedding_function=None, in_memory=False):
    global _COLLECTION
    if _COLLECTION is None:
        _COLLECTION = build_collection(embedding_function=embedding_function, in_memory=in_memory)
    return _COLLECTION


_DIET_KEYS = {
    "vegetarian": "vegetarian", "veg": "vegetarian",
    "vegan": "vegan",
    "gluten_free": "gluten_free", "gluten-free": "gluten_free", "glutenfree": "gluten_free",
}


def _build_where(city, max_price, dietary, cuisine=None, min_rating=None):
    """Turn the hard filters into a Chroma 'where' clause."""
    conds = []
    if city:
        conds.append({"city": {"$eq": city.strip().title()}})
    if cuisine:
        conds.append({"cuisine": {"$eq": cuisine.strip().title()}})
    if max_price:
        conds.append({"price": {"$lte": int(max_price)}})
    if min_rating:
        conds.append({"rating": {"$gte": float(min_rating)}})
    for d in (dietary or []):
        key = _DIET_KEYS.get(str(d).lower().strip().replace(" ", "_"))
        if key:
            conds.append({key: {"$eq": True}})
    if not conds:
        return None
    if len(conds) == 1:
        return conds[0]
    return {"$and": conds}


def search_restaurants(query, city=None, max_price=None, dietary=None, cuisine=None,
                       min_rating=None, top_k=5, embedding_function=None, in_memory=False):
    """Return a ranked list of matching restaurants (list of dicts)."""
    col = _get_collection(embedding_function=embedding_function, in_memory=in_memory)
    where = _build_where(city, max_price, dietary, cuisine=cuisine, min_rating=min_rating)
    res = col.query(query_texts=[query], n_results=top_k, where=where)
    metas = res["metadatas"][0] if res.get("metadatas") else []
    out = []
    for m in metas:
        out.append({
            "name": m["name"], "city": m["city"], "cuisine": m["cuisine"],
            "price": m["price"], "rating": m["rating"],
            "vegetarian": m["vegetarian"], "vegan": m["vegan"],
            "gluten_free": m["gluten_free"], "description": m["description"],
        })
    return out


def warm_up():
    """Build/load the vector database once, up front (so the first question
    in a conversation is not slow). Returns the number of restaurants loaded."""
    col = _get_collection()
    return col.count()
