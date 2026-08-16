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

import os
import re
import threading

import chromadb
try:  # works when imported as part of the restaurant_agent package
    from .restaurants_data import RESTAURANTS
except ImportError:  # works when this file is run directly from its folder
    from restaurants_data import RESTAURANTS

_COLLECTION = None  # built once, then reused

# The vocabulary the database actually contains. Read from the data itself, so
# it can never drift out of step with the records.
CITIES = sorted({r["city"] for r in RESTAURANTS})
CUISINES = sorted({r["cuisine"] for r in RESTAURANTS})


def _fold(text):
    """Lowercase and strip accents, so Cancun matches Cancún.

    Joel's destination corpus writes it with the accent; this agent's records
    do not. Without folding, a destination the system genuinely covers would be
    treated as uncovered.
    """
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", (text or "").lower())
        if unicodedata.category(c) != "Mn"
    )


# Words that follow "in"/"to" and are NOT places. Kept deliberately short - a
# false positive here only costs a clear refusal, never a wrong recommendation.
_NOT_PLACES = {
    "the", "a", "an", "town", "advance", "general", "particular", "mind",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "morning", "evening", "afternoon", "night", "summer", "winter",
}


_NEGATIONS = ("not", "no", "non", "isn't", "arent", "aren't", "without",
              "avoid", "except", "other than", "rather than", "dont", "don't")


def _wants(low, word):
    """True when the word appears AND is not negated just before it."""
    for match in re.finditer(re.escape(word), low):
        before = low[max(0, match.start() - 18):match.start()]
        if any(neg in before for neg in _NEGATIONS):
            continue
        return True
    return False


def _named_but_uncovered(text):
    """Return the place name if the task names a destination this agent lacks.

    Looks for "in X" / "to X" / "near X" followed by a capitalised name, and
    returns it when it is not one of the covered cities. Returns None when no
    place is named at all - which is the genuinely-unspecified case and is
    handled separately with a stated assumption.
    """
    import re as _re
    covered = {_fold(c) for c in CITIES}
    for match in _re.finditer(
        r"\b(?:in|to|near|around|at|visiting)\s+([A-Z][a-zA-Z\u00C0-\u024F]+(?:\s+[A-Z][a-zA-Z\u00C0-\u024F]+)?)",
        text or "",
    ):
        candidate = match.group(1).strip()
        if _fold(candidate) in covered:
            return None
        first_word = _fold(candidate.split()[0])
        if first_word in _NOT_PLACES:
            continue
        if _fold(candidate) in {_fold(c) for c in CUISINES}:
            continue
        return candidate
    return None


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
    meta = {
        "name": r["name"], "city": r["city"], "cuisine": r["cuisine"],
        "vegetarian": r["vegetarian"], "vegan": r["vegan"],
        "gluten_free": r["gluten_free"], "description": r["description"],
        # Whether this record carries a price and a rating at all. Live records
        # from OpenStreetMap carry neither, and Chroma rejects a None value, so
        # the field is omitted and its presence recorded as a boolean instead.
        "has_price": r.get("price") is not None,
        "has_rating": r.get("rating") is not None,
        "source": r.get("source", "mock"),
    }
    if r.get("price") is not None:
        meta["price"] = r["price"]
    if r.get("rating") is not None:
        meta["rating"] = r["rating"]
    return meta


# The database lives beside this file, NOT in whatever directory the caller
# happened to start in. A bare relative path meant the orchestrator would ignore
# the pre-built database and silently create an empty one of its own, then pay
# for an 80 MB embedding-model download inside a customer's first request.
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "restaurant_db")

# One process may answer several travellers at once. Building the collection is
# a check-then-create, which two threads can enter together - and the build used
# to delete the collection first, so one worker could delete what another was
# reading. This lock makes the build happen exactly once.
_BUILD_LOCK = threading.Lock()


def build_collection(embedding_function=None, in_memory=False, persist_path=None):
    """Create or reuse the vector database and load all restaurants into it.

    Rebuilds only when the stored collection does not match the dataset. The
    previous version deleted and re-embedded on every start, which was both slow
    and unsafe while another thread was querying.
    """
    if in_memory:
        client = chromadb.EphemeralClient()
    else:
        client = chromadb.PersistentClient(path=persist_path or DEFAULT_DB_PATH)

    kwargs = {}
    if embedding_function is not None:
        kwargs["embedding_function"] = embedding_function
    col = client.get_or_create_collection("restaurants", **kwargs)

    try:
        already = col.count()
    except Exception:
        already = -1
    if already == len(RESTAURANTS):
        return col  # already built and complete - reuse it

    if already:  # partial or stale, start clean
        try:
            client.delete_collection("restaurants")
        except Exception:
            pass
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
        with _BUILD_LOCK:
            if _COLLECTION is None:  # re-check inside the lock
                _COLLECTION = build_collection(
                    embedding_function=embedding_function, in_memory=in_memory)
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
        conds.append({"has_price": {"$eq": True}})
        conds.append({"price": {"$lte": int(max_price)}})
    if min_rating:
        conds.append({"has_rating": {"$eq": True}})
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
            "price": m.get("price"), "rating": m.get("rating"),
            "vegetarian": m["vegetarian"], "vegan": m["vegan"],
            "gluten_free": m["gluten_free"], "description": m["description"],
            "source": m.get("source", "mock"),
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
    # Comma groups are captured whole. Measured 16 Aug: the old pattern stopped
    # at the comma, so "the flight cost $1,250 already" was read as a $1 budget.
    # A composed orchestrator task string will routinely carry a flight price.
    r"(?:under|below|less than|up to|within|at most|max(?:imum)?|budget of)\s*\$?\s*(\d{1,3}(?:,\d{3})+|\d{1,5})",
    r"\$\s*(\d{1,3}(?:,\d{3})+|\d{1,5})",
    r"(\d{1,3}(?:,\d{3})+|\d{1,5})\s*(?:dollars|usd|bucks)",
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
    low = _fold(text)
    assumptions = []

    city = next((c for c in CITIES if _fold(c) in low), None)

    # A city that was NAMED but is not covered is a completely different case
    # from no city at all, and collapsing the two is dangerous. Measured on
    # 16 Aug 2026: the destination layer already merged into main
    # (destination_data/destinations.json) carries 47 cities - Paris, Rome,
    # Bangkok, Kyoto - and shares exactly ONE of them with this agent's six.
    # So in the merged system the orchestrator will routinely name a city this
    # agent has never heard of. Before this check, that fell through to a search
    # across all six Caribbean cities and attached the sentence "No destination
    # city was named in the task", which was simply false. Asked for dinner in
    # Tokyo, it recommended a restaurant in Cancun.
    #
    # Answering about the wrong country is the exact failure this agent's own
    # NEVER_RELAXED rule exists to prevent, so it is caught here instead.
    city_uncovered = None if city else _named_but_uncovered(text)

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
            max_price = int(found.group(1).replace(",", ""))
            break

    min_rating = 4.5 if any(w in low for w in _QUALITY_WORDS) else None

    # A dietary word that is NEGATED is not a dietary requirement. Measured
    # 16 Aug: "guests are not vegan but love steak" set dietary=['vegan'], and
    # because the tool only ever ADDS dietary flags by design, nothing
    # downstream could undo it. The traveller would be served vegan food.
    dietary = []
    if _wants(low, "vegan"):
        dietary.append("vegan")
    if _wants(low, "vegetarian") or _wants(low, "veggie"):
        dietary.append("vegetarian")

    # Gluten is asymmetric and needs its own handling. For vegan and vegetarian
    # the requirement is the PRESENCE of the thing, so "not vegan" cancels it.
    # For gluten the requirement is its ABSENCE, so "no gluten", "without
    # gluten" and "avoid gluten" all mean the diner NEEDS gluten-free, while
    # "not gluten-free" is the one phrasing that cancels it. Treating gluten
    # like the other two turned "no gluten please" into no requirement at all.
    if any(p in low for p in ("no gluten", "without gluten", "avoid gluten",
                              "gluten intoleran", "gluten allerg", "coeliac",
                              "celiac")):
        dietary.append("gluten_free")
    elif _wants(low, "gluten"):
        dietary.append("gluten_free")

    if not city and not city_uncovered:
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
        "city_uncovered": city_uncovered,
        "assumptions": assumptions,
    }


def _headline(r):
    """One itinerary line for a single restaurant."""
    tags = [t for t, on in (("vegetarian", r["vegetarian"]),
                            ("vegan", r["vegan"]),
                            ("gluten-free", r["gluten_free"])) if on]
    tag_str = (" Dietary: " + ", ".join(tags) + ".") if tags else ""
    price = (f"About ${r['price']} per person" if r.get("price") is not None
             else "price not published by this source")
    rating = (f"rated {r['rating']}/5" if r.get("rating") is not None
              else "no published rating")
    return f"{r['name']} - {r['cuisine']}, {r['city']}. {price}, {rating}.{tag_str}"


def format_for_itinerary(results, assumptions=None, relaxations=None,
                         city_uncovered=None):
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

    # A destination this agent does not cover is refused outright, before any
    # search runs. Returning a Caribbean restaurant for a request about Tokyo
    # would be worse than returning nothing: the orchestrator would drop it
    # into an itinerary and nobody downstream could tell it was wrong.
    if city_uncovered:
        return (
            "Coverage limit: this restaurant agent holds records for "
            + ", ".join(CITIES) + " only. "
            + str(city_uncovered) + " is outside that coverage, so no "
            "restaurant has been recommended and nothing has been invented. "
            "Treat the restaurant section of the itinerary as unavailable for "
            "this destination."
        )

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
