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

import re

import chromadb
from restaurants_data import RESTAURANTS

_COLLECTION = None  # built once, then reused

# The vocabulary the database actually contains. Read from the data itself, so
# it can never drift out of step with the records.
CITIES = sorted({r["city"] for r in RESTAURANTS})
CUISINES = sorted({r["cuisine"] for r in RESTAURANTS})


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


# -----------------------------------------------------------------------------
# ORCHESTRATOR CONTRACT HELPERS
# -----------------------------------------------------------------------------
# The orchestrator sends this agent ONE task string and expects ONE final
# message back that can be dropped straight into an itinerary. The two
# functions below are the deterministic halves of that contract:
#   parse_task            reads filters out of a plain task string
#   format_for_itinerary  writes the single itinerary-ready message
# Both are pure Python with no LLM and no network, so the test jig can check
# them directly and they behave identically on every machine.
# -----------------------------------------------------------------------------

_BUDGET_PATTERNS = (
    r"(?:under|below|less than|up to|within|at most|max(?:imum)?|budget of)\s*\$?\s*(\d{1,4})",
    r"\$\s*(\d{1,4})",
    r"(\d{1,4})\s*(?:dollars|usd|bucks)",
)

_QUALITY_WORDS = ("highly rated", "best rated", "top rated", "highest rated",
                  "very well reviewed", "top-rated", "best-rated")


def parse_task(task):
    """Read hard filters out of a plain-language task string.

    Returns a dict with: query, city, cuisine, max_price, min_rating, dietary,
    and assumptions (a list of plain sentences describing anything that had to
    be inferred). Nothing here guesses silently - every inference is recorded
    in assumptions so the final message can state it out loud.
    """
    text = (task or "").strip()
    low = text.lower()
    assumptions = []

    city = next((c for c in CITIES if c.lower() in low), None)

    # Longest cuisine name first, so "Fine Dining" wins over a shorter overlap.
    cuisine = next((c for c in sorted(CUISINES, key=len, reverse=True)
                    if c.lower() in low), None)

    max_price = None
    for pattern in _BUDGET_PATTERNS:
        found = re.search(pattern, low)
        if found:
            max_price = int(found.group(1))
            break

    min_rating = 4.5 if any(w in low for w in _QUALITY_WORDS) else None

    dietary = []
    if "vegan" in low:
        dietary.append("vegan")
    if "vegetarian" in low or re.search(r"\bveggie\b", low):
        dietary.append("vegetarian")
    if "gluten" in low:
        dietary.append("gluten_free")

    if not city:
        assumptions.append(
            "No destination city was named in the task, so this searched all "
            "covered cities (" + ", ".join(CITIES) + "). Pass a city in the "
            "task string for a destination-specific pick."
        )

    return {
        "query": text,
        "city": city,
        "cuisine": cuisine,
        "max_price": max_price,
        "min_rating": min_rating,
        "dietary": dietary,
        "assumptions": assumptions,
    }


def _headline(r):
    """One itinerary line for a single restaurant."""
    tags = [t for t, on in (("vegetarian", r["vegetarian"]),
                            ("vegan", r["vegan"]),
                            ("gluten-free", r["gluten_free"])) if on]
    tag_str = (" Dietary: " + ", ".join(tags) + ".") if tags else ""
    return (f"{r['name']} - {r['cuisine']}, {r['city']}. "
            f"About ${r['price']} per person, rated {r['rating']}/5.{tag_str}")


def format_for_itinerary(results, assumptions=None):
    """Write the single self-contained message the orchestrator receives.

    Shape: one committed top pick with a reason, then up to two alternatives.
    Specific enough to drop directly into a final itinerary - never a vague
    "found some options" and never a question back to the orchestrator.
    """
    lines = []
    for note in (assumptions or []):
        lines.append("Assumption: " + note)

    if not results:
        lines.append(
            "No restaurant in this agent's database matches those requirements. "
            "Nothing has been invented to fill the gap. The requirement that most "
            "likely caused this is the budget, the cuisine, or the dietary filter - "
            "relaxing any one of them should return options."
        )
        return "\n".join(lines)

    top = results[0]
    lines.append("Recommended restaurant: " + _headline(top))
    lines.append("Why: " + top["description"])

    alternatives = results[1:3]
    if alternatives:
        lines.append("")
        lines.append("Alternatives:")
        for r in alternatives:
            lines.append("- " + _headline(r))

    return "\n".join(lines)
