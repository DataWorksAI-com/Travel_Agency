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
# THE REFLECTION STEP - THE SECOND LOOK
# -----------------------------------------------------------------------------
# Everything above runs ONE search and stops. That is a search pipeline: it
# retrieves, filters, and returns whatever survives. On a genuinely tight
# request it returns nothing, even when loosening a single condition would
# have produced a good answer.
#
# A person would not stop there. Told "no vegan gluten-free lunch in Honolulu
# under $15", they would notice the gap, loosen ONE condition, look again, and
# say what they changed. That is what the code below does, and it is what makes
# this agent decide its own next search rather than just execute one.
#
# Three rules keep it honest:
#   1. One constraint at a time, in a fixed published order.
#   2. A hard stop after two second looks. A loop with no stopping rule is a
#      worse failure than never looping at all.
#   3. Every relaxation is reported in the final message. Silently bending a
#      requirement produces an answer that looks correct and is not.
# -----------------------------------------------------------------------------

# Relaxed in this order - least costly to the diner first. A rating floor is a
# preference, a cuisine is a preference, money is real, so price moves last.
RELAXATION_ORDER = ("min_rating", "cuisine", "max_price")

# NEVER relaxed, and the reason each one is off limits:
#   dietary - a medical or ethical requirement, not a preference. Relaxing it
#             could put someone in front of food they cannot safely eat.
#   city    - fixed upstream by the destination agent. A restaurant in the
#             wrong country is not a weaker answer, it is a broken itinerary.
NEVER_RELAXED = ("dietary", "city")

MAX_ATTEMPTS = 3          # the first search, plus at most two second looks
PRICE_WIDEN_FACTOR = 1.5  # how far the budget stretches on each relaxation


def _relax_one(filters):
    """Loosen exactly one constraint, in the published order.

    Mutates the filters dict in place. Returns a plain sentence describing what
    was changed, or None when nothing further may be relaxed.
    """
    for name in RELAXATION_ORDER:
        value = filters.get(name)
        if not value:
            continue

        if name == "min_rating":
            filters["min_rating"] = None
            return (f"Nothing met the {value}/5 rating floor, so the rating "
                    "requirement was dropped for this search.")

        if name == "cuisine":
            filters["cuisine"] = None
            return (f"No {value} option matched the other requirements, so the "
                    "cuisine preference was dropped for this search.")

        if name == "max_price":
            widened = int(round(float(value) * PRICE_WIDEN_FACTOR))
            filters["max_price"] = widened
            return (f"Nothing matched under ${int(value)} per person, so the "
                    f"budget was widened to ${widened} for this search.")

    return None


def search_with_reflection(query, city=None, max_price=None, dietary=None,
                           cuisine=None, min_rating=None, top_k=5,
                           embedding_function=None, in_memory=False):
    """Search; if nothing comes back, relax one constraint and look again.

    This is the agentic half of the agent. The plain search_restaurants above
    answers "what matches these filters". This answers the harder question a
    person actually asks: "what should I eat", deciding for itself which
    requirement to bend when the literal request cannot be met.

    Returns:
        (results, relaxations) - the ranked matches, and a list of plain
        sentences describing every constraint that had to be loosened. The
        list is empty when the original request was satisfied as written, so
        the caller can always tell a clean hit from a recovered one.
    """
    filters = {
        "city": city,
        "max_price": max_price,
        "dietary": dietary,
        "cuisine": cuisine,
        "min_rating": min_rating,
    }
    relaxations = []

    for attempt in range(MAX_ATTEMPTS):
        results = search_restaurants(
            query,
            city=filters["city"],
            max_price=filters["max_price"],
            dietary=filters["dietary"],
            cuisine=filters["cuisine"],
            min_rating=filters["min_rating"],
            top_k=top_k,
            embedding_function=embedding_function,
            in_memory=in_memory,
        )
        if results:
            return results, relaxations

        if attempt == MAX_ATTEMPTS - 1:
            break  # the hard stop - no third second look

        note = _relax_one(filters)
        if note is None:
            break  # only dietary and city are left, and neither may be relaxed
        relaxations.append(note)

    return [], relaxations


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

    # "Vegan" and "Vegetarian" are BOTH cuisine names in this database and
    # dietary words in plain speech. Someone asking for "a vegan dinner" means
    # the diet, not that cuisine specifically - reading it as a cuisine narrows
    # the search to one restaurant type and hides good matches. So a diet word
    # is treated as a diet only. Asking for a "vegan restaurant" still works,
    # because the dietary filter covers every place that serves vegan food.
    if cuisine and cuisine.lower() in ("vegan", "vegetarian"):
        cuisine = None

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


def format_for_itinerary(results, assumptions=None, relaxations=None):
    """Write the single self-contained message the orchestrator receives.

    Shape: one committed top pick with a reason, then up to two alternatives.
    Specific enough to drop directly into a final itinerary - never a vague
    "found some options" and never a question back to the orchestrator.

    Any constraint the reflection step had to loosen is stated on its own
    "Adjusted:" line, above the recommendation. This is deliberate. A diner who
    asked for a $15 lunch and is handed an $18 one needs to see that the budget
    moved; an answer that quietly bends a requirement looks correct and is not.
    """
    lines = []
    for note in (assumptions or []):
        lines.append("Assumption: " + note)
    for note in (relaxations or []):
        lines.append("Adjusted: " + note)

    if not results:
        if relaxations:
            lines.append(
                "No restaurant in this agent's database matches those "
                "requirements, even after the adjustments above. Nothing has "
                "been invented to fill the gap. The dietary requirement and the "
                "destination were held fixed, so the shortfall is genuine for "
                "this city. Treat the restaurant section as needing a wider "
                "search area or a different destination."
            )
        else:
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
