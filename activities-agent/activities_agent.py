"""
Activities Agent — merged (Limeng Zhang + Jainam Jayeshkumar Patel)
--------------------------------------------------------------------------
This is a merged version of two independently-built Activities Agents,
combined after comparing both implementations and finding the same
overall design (local exact filter -> local semantic search -> a
self-expanding live fallback) with different specific choices. Where
the two disagreed, a single choice was made for the merged version —
each decision and its reasoning is documented below rather than left
implicit.

Knowledge sources, tried in priority order:

    Tier 1 - Exact local lookup:   local_activity_docs/<city>.json,
                                    filtered by category/price_tier.
                                    Fast, free, only for covered cities.
    Tier 2 - Local semantic RAG:   Chroma vector search across all
                                    covered cities' data, for vague/
                                    natural-language queries.
    Tier 3 - Self-expanding live:  expand_activities_corpus() fetches
                                    live data via OpenTripMap for an
                                    uncovered city AND saves it as a
                                    new local_activity_docs/<city>.json
                                    file, rebuilding the Chroma index.
                                    The SAME city is answered by tiers
                                    1/2 next time - local coverage
                                    grows automatically.
    Tier 3b - Plain MCP fallback:  mcp_opentripmap_server.py, a real
                                    MCP server also wrapping OpenTripMap,
                                    kept available as a genuine MCP-
                                    protocol tool and a fallback if
                                    tier 3 is unavailable.

Covered out of the box (merged from both original implementations):
New York, Paris, Rome, Kyoto (from Limeng's version) plus Boston and
Chicago (from Jainam's version) - six cities total. Any city looked
up via expand_activities_corpus() is added automatically afterward.

Merge decisions and rationale
------------------------------
1. Embedding model: Chroma's default embedding model was kept,
   rather than Jainam's original choice of a local Ollama install
   (nomic-embed-text). Reasoning: Chroma's default requires no extra
   local software beyond the Python packages already needed, works
   the same way on any machine, and was already verified end-to-end
   (including a fully offline test path). Adding a hard dependency on
   a separately-installed local Ollama server for everyone who runs
   this merged agent was judged not worth the tradeoff, since neither
   original agent's design specifically depended on Ollama's
   embedding quality being different from Chroma's default.

2. Orchestrator entry point: answer(task) - one task string in, one
   self-contained message out - was kept as the primary interface,
   matching the team-wide convention used by Budget, Money & Customs,
   and Restaurants. Jainam's original ask_activities(destination,
   interests, constraints, limit) signature is preserved as a thin
   backward-compatible wrapper (see below) that builds one task
   string from its arguments and calls answer() - so any code already
   calling ask_activities() keeps working, but the "real" interface
   going forward is answer(task).

3. Domain-boundary guard: Limeng's deterministic, code-level check
   for food/dining requests (bypassing the model entirely) was kept
   as the merged version's food-handling behavior, since it does not
   depend on the model actually following the system prompt's
   instruction - a strictly stronger guarantee than a prompt-only
   approach.

4. Auxiliary tools: Jainam's hard_filter_activities (a deterministic
   post-filter for free-only/exact-category results) and
   list_curated_cities (reports which cities have local data) were
   both kept as additional tools, since neither conflicts with
   anything in Limeng's version and both are independently useful.

5. Live-fetch implementation: Limeng's corpus_expand.py (direct
   OpenTripMap REST calls via `requests`, no extra dependency) was
   kept as the underlying fetch-and-save mechanism for tier 3, since
   it was already verified working without requiring anything beyond
   what tier 1/2 already need.

Setup:
    1. pip install -r requirements.txt
    2. cp .env.example .env - fill in OPENROUTER_API_KEY, and
       OPENTRIPMAP_API_KEY (free, from dev.opentripmap.org) for
       tier-3 fallback support
    3. python build_vector_db.py
    4. python activities_agent.py
"""

import os
import json
import glob
import asyncio
import chromadb
from dotenv import load_dotenv
from deepagents import create_deep_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

from offline_embedding import OfflineFakeEmbeddingFunction
import build_vector_db
from corpus_expand import fetch_live_activities, save_activities_for_city

load_dotenv()

DB_PATH = "./chroma_db"
COLLECTION_NAME = "activities"

# Cutoff for search_activities_semantic. Measured against this corpus:
#   "ancient Roman ruins"      -> Colosseum            0.69   (keep)
#   "museums in Paris"         -> Louvre               1.04   (keep)
#   "beach day in Cancun"      -> Cinepolis            1.28   (drop)
#   unrelated text             -> anything             1.74+  (drop)
MAX_MATCH_DISTANCE = 1.1
DOCS_DIR = os.path.join(os.path.dirname(__file__), "local_activity_docs")
MCP_SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "mcp_opentripmap_server.py")


def _offline_mode() -> bool:
    """Read the offline-test flag fresh each call, not at import time,
    so run_tests_offline.py can flip it on for just the test run."""
    return os.environ.get("ACTIVITIES_OFFLINE_TEST", "").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------
# Deterministic domain-boundary guard - food/dining (from Limeng)
# ---------------------------------------------------------------------
# The system prompt below also tells the model to redirect food
# questions, but a prompt is a request, not a guarantee. This check
# runs in plain code before the model is ever called, so the
# boundary holds regardless of what the model does.
FOOD_KEYWORDS = (
    "food", "restaurant", "dining", "eat", "dinner", "lunch",
    "breakfast", "cafe", "café", "meal", "brunch", "cuisine",
)


def _is_food_request(task: str) -> bool:
    task_lower = task.lower()
    return any(keyword in task_lower for keyword in FOOD_KEYWORDS)


FOOD_REDIRECT_MESSAGE = (
    "Food and dining are out of scope for the Activities Agent — that's "
    "handled by the Restaurants Agent. Please route this request there "
    "instead."
)


def _covered_cities() -> list[str]:
    return sorted(
        os.path.splitext(os.path.basename(p))[0].replace("_", " ").title()
        for p in glob.glob(os.path.join(DOCS_DIR, "*.json"))
    )


def _city_file(city: str) -> str:
    return os.path.join(DOCS_DIR, f"{city.strip().lower().replace(' ', '_')}.json")


# ---------------------------------------------------------------------
# Tier 1: exact local lookup
# ---------------------------------------------------------------------

def search_activities_local_exact(city: str, category: str = "", price_tier: str = "") -> dict:
    """Tier 1 — exact filter lookup over a covered city's local activity data.

    Only works for covered cities (see list in the error response if
    the city isn't found). Use this first for precise category/price
    filters; if it returns no matches, fall back to
    search_activities_semantic for a vaguer natural-language query.

    Args:
        city: the city to search, e.g. "New York", "Boston".
        category: exact filter, e.g. "outdoor", "art", "cultural",
                  "sightseeing", "entertainment". Food/dining is out
                  of scope — that's the Restaurants Agent's domain.
        price_tier: exact filter: "free", "moderate", or "premium".

    Returns the shared schema dict, or {"error": "..."} listing
    covered cities if the city isn't covered, or if nothing matches
    the filters. Never raises.
    """
    path = _city_file(city)
    if not os.path.exists(path):
        return {"error": f"'{city}' is not covered by local data.", "covered_cities": _covered_cities()}

    with open(path, "r") as f:
        data = json.load(f)

    filtered = data
    if category:
        filtered = [a for a in filtered if a["category"].lower() == category.lower()]
    if price_tier:
        filtered = [a for a in filtered if a["price_tier"].lower() == price_tier.lower()]

    if not filtered:
        return {"error": f"No exact match in local data for {city} with that category/price_tier."}

    return {"city": city, "source": "local_exact", "activities": filtered}


# ---------------------------------------------------------------------
# Tier 2: local semantic search (Chroma), across all covered cities
# ---------------------------------------------------------------------

def search_activities_semantic(query: str, city: str = "", category: str = "", price_tier: str = "") -> dict:
    """Tier 2 — semantic (meaning-based) search over covered cities' activities.

    Use this when the traveler's request is a vague or natural-
    language description (e.g. "something romantic") rather than an
    exact category. If city is omitted, searches across ALL covered
    cities; pass city to restrict to one.

    Args:
        query: natural-language description of what the traveler wants.
        city: optional filter to one covered city.
        category: optional exact filter on top of the semantic search.
        price_tier: optional exact filter: "free", "moderate", "premium".

    Returns the shared schema dict, or {"error": "..."} if the vector
    DB hasn't been built yet or nothing matches. Never raises.
    """
    offline = _offline_mode()
    db_path = "./chroma_db_offline" if offline else DB_PATH
    collection_name = "activities_offline" if offline else COLLECTION_NAME
    embedding_function = OfflineFakeEmbeddingFunction() if offline else None

    try:
        client = chromadb.PersistentClient(path=db_path)
        collection = client.get_collection(collection_name, embedding_function=embedding_function)
    except Exception as e:
        hint = "run_tests_offline.py" if offline else "build_vector_db.py"
        return {"error": f"Vector DB not available — run {hint} first. ({e})"}

    where_clauses = []
    if city:
        where_clauses.append({"city": city.title()})
    if category:
        where_clauses.append({"category": category})
    if price_tier:
        where_clauses.append({"price_tier": price_tier})

    where = None
    if len(where_clauses) == 1:
        where = where_clauses[0]
    elif len(where_clauses) > 1:
        where = {"$and": where_clauses}

    results = collection.query(
        query_texts=[query], n_results=5, where=where,
        include=["documents", "metadatas", "distances"],
    )

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    if not docs:
        return {"error": "No semantic match found for that query/filter combination."}

    # Nearest-neighbour search always returns SOMETHING. Without a cutoff, a
    # "beach day in Cancun" query returned four cinemas and churches, and a
    # "museums in Paris" query returned Boston's Museum of Fine Arts ahead of
    # the Louvre. Measured on this corpus: a genuine match sits near 0.7-1.0,
    # boilerplate-description filler at ~1.28, unrelated text at 1.7+.
    # Offline test mode embeds with hashed vectors (OfflineFakeEmbeddingFunction,
    # "NOT a real embedding"), so distances there are arbitrary and a cutoff would
    # reject everything. Filter only when the embeddings are real.
    cutoff = float("inf") if _offline_mode() else MAX_MATCH_DISTANCE
    keep = [(d, m) for d, m, dist in zip(docs, metas, dists) if dist <= cutoff]
    if not keep:
        return {
            "error": (
                f"No activity in the corpus is a close enough match for {query!r} "
                f"(nearest {min(dists):.2f}, cutoff {MAX_MATCH_DISTANCE}). This is a "
                f"coverage limit, not a transient failure -- do not retry with different wording."
            ),
            "covered_cities": _covered_cities(),
        }

    activities = [
        # city is per-activity on purpose: without a city filter this searches
        # every city at once, and the caller cannot otherwise tell that a Paris
        # query was answered with a Boston museum.
        {"name": m["name"], "city": m.get("city"), "category": m["category"],
         "price_tier": m["price_tier"], "description": d}
        for d, m in keep
    ]
    return {"city": city or "multiple", "source": "vector_db", "activities": activities}


# ---------------------------------------------------------------------
# Auxiliary tools (from Jainam) — deterministic post-filter and a
# simple coverage report. Neither conflicts with anything above.
# ---------------------------------------------------------------------

def hard_filter_activities(activities_json: str, free_only: bool = False, category: str = "") -> str:
    """Apply a deterministic hard filter to a previous tool's JSON
    result, without going back to the model's judgment for it.

    Use this AFTER another search tool, when the user has a hard
    requirement (e.g. "must be free") that should be enforced exactly
    rather than left to the model to remember and apply correctly.

    Args:
        activities_json: the JSON string returned by another search tool.
        free_only: if True, keep only activities with price_tier "free".
        category: if set, keep only activities with this exact category.

    Returns a JSON string with the same shape, filtered. Never raises.
    """
    try:
        payload = json.loads(activities_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "activities_json is not valid JSON"})

    items = payload.get("activities") or []
    if free_only:
        items = [a for a in items if str(a.get("price_tier", "")).lower() == "free"]
    if category:
        items = [a for a in items if str(a.get("category", "")).lower() == category.lower()]

    payload["activities"] = items
    payload["filter"] = {"free_only": free_only, "category": category}
    return json.dumps(payload)


def list_curated_cities() -> str:
    """List cities that currently have local activity data (tier 1/2 coverage)."""
    return json.dumps({"curated_cities": _covered_cities()})


# ---------------------------------------------------------------------
# Tier 3: self-expanding live lookup — grows local coverage over time
# ---------------------------------------------------------------------

def expand_activities_corpus(city: str, category: str = "", country: str = "") -> dict:
    """Fetch live activities for an uncovered city AND save them
    locally, so this city becomes part of the fast local coverage for
    future questions instead of requiring a live lookup every time.

    Use this for any city NOT in the locally covered list, in place
    of (or in addition to) the plain OpenTripMap MCP tool, since this
    one makes the coverage grow over time.

    Args:
        city: the city to fetch and add to local coverage.
        category: optional OpenTripMap "kinds" filter, e.g.
                  "cultural", "natural", "amusements", "sport".
        country: ISO 3166-1 alpha-2 code, e.g. "MX" for Cancun, "AW" for
                  Aruba. ALWAYS pass this when you know it. Without it the
                  lookup matches on city name alone and can resolve to a
                  same-named town in another country, which then gets cached
                  locally and served as though it were correct.

    Returns the shared schema dict (source: "mcp_opentripmap_autosaved"),
    or {"error": "..."} on failure. Never raises.
    """
    if os.path.exists(_city_file(city)):
        # save_activities_for_city opens the file in "w". Calling this for a
        # city that already has coverage REPLACES it -- which is how five
        # hand-written Rome entries (Colosseum, Vatican, Trevi) became five
        # OpenTripMap cemeteries. Expansion exists to add cities the corpus
        # lacks, never to rewrite ones it has.
        return {
            "error": (
                f"'{city}' already has local coverage, and expanding would overwrite it. "
                f"Use search_activities_local_exact or search_activities_semantic instead."
            ),
            "covered_cities": _covered_cities(),
        }

    try:
        activities = fetch_live_activities(city, category=category, country=country)
    except Exception as e:
        return {"error": f"Could not fetch live activities for '{city}': {e}"}

    if not activities:
        return {"error": f"No activities found for '{city}' via OpenTripMap."}

    if not country:
        # Only cache what was verified. Without a country code the geocode
        # matches on name alone -- "Aruba" resolves to a town in Piedmont and
        # returns Italian churches -- and anything written here is permanent,
        # served by tiers 1 and 2 from then on. Returning the results without
        # saving keeps a one-off lookup useful while making a wrong one
        # temporary rather than a lasting corruption of the corpus.
        return {
            "city": city,
            "source": "opentripmap_live_unverified",
            "activities": activities,
            "warning": (
                f"No country code was given for {city!r}, so this lookup could not be "
                f"verified and has NOT been added to local coverage. Call again with "
                f"country=<ISO 3166-1 alpha-2> to cache it."
            ),
        }

    saved_path = save_activities_for_city(city, activities)

    try:
        build_vector_db.build_collection()
    except Exception as e:
        return {
            "city": city,
            "source": "mcp_opentripmap_autosaved",
            "activities": activities,
            "warning": f"Saved to {saved_path}, but re-indexing the vector DB failed: {e}",
        }

    return {
        "city": city,
        "source": "mcp_opentripmap_autosaved",
        "activities": activities,
        "saved_to": saved_path,
    }


# ---------------------------------------------------------------------
# Agent assembly
# ---------------------------------------------------------------------

async def build_agent():
    """Build the Deep Agent with all local tools plus the MCP-loaded
    OpenTripMap tool (tier 3b, plain live fallback)."""
    local_tools = [
        search_activities_local_exact,
        search_activities_semantic,
        hard_filter_activities,
        list_curated_cities,
        expand_activities_corpus,
    ]

    mcp_tools = []
    try:
        mcp_client = MultiServerMCPClient({
            "opentripmap": {
                "command": "python",
                "args": [MCP_SERVER_SCRIPT],
                "transport": "stdio",
            }
        })
        mcp_tools = await mcp_client.get_tools()
    except Exception as e:
        print(f"[warning] MCP tier unavailable, continuing with local tools only: {e}")

    covered = ", ".join(_covered_cities())

    agent = create_deep_agent(
        model=MODEL,
        tools=local_tools + mcp_tools,
        system_prompt=(
            "You are the Activities domain-expert agent in a multi-agent travel planning "
            "system. You receive a single task string from the orchestrator — you do not "
            "share context with other sub-agents, so only rely on what's explicitly in the "
            "task string. "
            "You help find things to do — sightseeing, outdoor activities, cultural "
            "experiences, art, and entertainment. Food and dining is out of scope — that's "
            "the Restaurants Agent's domain, so redirect food questions there instead of "
            "answering them yourself. "
            f"Locally covered cities (fast, curated data): {covered}. This list grows over "
            "time as expand_activities_corpus is used on new cities. "
            "You have tools, in priority order: "
            "(1) search_activities_local_exact — try this first for a covered city with a "
            "clear category/price filter; "
            "(2) search_activities_semantic — use this for a covered city if (1) finds "
            "nothing, or the request is vague/descriptive rather than an exact category; "
            "(3) hard_filter_activities — use this on top of (1) or (2)'s result if the "
            "user has a hard requirement (like 'must be free') that needs to be enforced "
            "exactly, not just remembered; "
            "(4) list_curated_cities — use this if you need to tell the user which cities "
            "are covered; "
            "(5) expand_activities_corpus — use this for any city NOT in the locally "
            "covered list. It fetches live data via OpenTripMap AND saves it locally, so "
            "the same city can be answered by tiers 1/2 next time; "
            "(6) the OpenTripMap MCP tool directly — only if expand_activities_corpus is "
            "unavailable or fails for some other reason. "
            "Never invent an activity that no tool returned. If a tool returns an error, "
            "explain that honestly in your final message rather than guessing or ignoring it. "
            "Produce exactly ONE self-contained final message — never ask a follow-up "
            "question. If some detail is missing, state a reasonable assumption explicitly, "
            "or clearly flag what's missing. "
            "Your final message must be specific enough to drop directly into a day-by-day "
            "itinerary: name each activity, its category, its price tier (say 'unknown' if "
            "not available, e.g. from a live lookup), and a short description."
        ),
    )
    return agent


MODEL = os.environ.get("DEEP_AGENT_MODEL", "openrouter:z-ai/glm-5.2")


async def answer(task: str) -> str:
    """Team-standard entry point: one task string in, one self-contained
    message out. Matches the answer(task) convention used by the
    Budget, Money & Customs, and Restaurants sub-agents.

    Food/dining requests are rejected deterministically, in code,
    before the model is ever called — see the domain-boundary guard
    above.
    """
    if _is_food_request(task):
        return FOOD_REDIRECT_MESSAGE

    agent = await build_agent()
    result = await agent.ainvoke({"messages": [{"role": "user", "content": task}]})
    return result["messages"][-1].content


async def ask_activities(destination: str, interests: str = "", constraints: list | None = None, limit: int = 5) -> dict:
    """Backward-compatible wrapper matching Jainam's original entry-
    point signature. Builds one task string from the structured
    arguments and delegates to answer() — new code should call
    answer(task) directly; this exists so any code already calling
    ask_activities(...) keeps working unmodified.
    """
    constraints = constraints or []
    task = (
        f"Destination: {destination}. "
        f"Interests: {interests or 'general things to do'}. "
        f"Constraints: {', '.join(constraints) if constraints else 'none'}. "
        f"Return at most {limit} activities."
    )
    message = await answer(task)
    return {"agent": "activities", "destination": destination, "needs_from": [], "message": message}


# ---------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------

async def _run_self_tests():
    test_tasks = [
        "Find a free outdoor activity in New York.",
        "I want something romantic and artsy in Paris.",
        "What's a good cultural activity in Rome?",
        "Suggest a free outdoor activity in Kyoto.",
        "What can I do in Boston for free?",
        "Find an art activity in Chicago.",
        # Grounding test: no good match in the covered cities' data
        "Find underwater scuba diving in New York.",
        # Domain-boundary test: should redirect to the Restaurants Agent
        "Where should I get dinner in Paris?",
        # Tier-3 test: a city with no local coverage — exercises the self-expanding fallback
        "Find a cultural activity in Miami.",
    ]

    for task in test_tasks:
        print(f"=== Task: {task} ===")
        response = await answer(task)
        print(response)
        print()


if __name__ == "__main__":
    print(f"Using model: {MODEL}\n")
    print(f"Locally covered cities: {', '.join(_covered_cities())}\n")
    asyncio.run(_run_self_tests())
