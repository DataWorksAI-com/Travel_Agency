"""
Activities Agent — multi-city (+ MCP fallback for any other city)
--------------------------------------------------------------------
Author: Limeng Zhang

Domain-expert agent for "things to do." Three-tier knowledge source:

    Tier 1 — Exact local lookup:   local_activity_docs/<city>.json,
                                    filtered by category/price_tier.
                                    Fast, free, only for covered cities.
    Tier 2 — Local semantic RAG:   Chroma vector search across all
                                    covered cities' data, for vague/
                                    natural-language queries. Can be
                                    filtered to one city or searched
                                    across all covered cities.
    Tier 3 — MCP live fallback:    mcp_opentripmap_server.py, wrapping
                                    the OpenTripMap REST API. Used for
                                    ANY city not covered by tiers 1/2.

Currently covered by tiers 1-2: New York, Paris, Rome, Kyoto.
Add a new city by dropping a <city>.json file into
local_activity_docs/ (same schema) and re-running build_vector_db.py
— no code changes needed here.

Note on scope: the Destination Agent's semantic recommender draws
from its own separate 47-city corpus, which does NOT include New
York. So when a traveler gets a destination recommended (rather than
naming one directly), tiers 1-2 here are most useful for the covered
cities that DO overlap with that corpus (Paris, Rome, Kyoto);
New York is mainly reached when a user names it directly.

Orchestrator contract (per the team-wide sub-agent rules):
- Input: a single task string from the orchestrator. This agent does
  not share context with other sub-agents — anything it needs (e.g.
  a city) must be explicit in that task string.
- Output: exactly ONE self-contained final message via answer(task).
  Never asks a follow-up question — if a tool errors or something's
  missing, the agent explains that honestly in its final message.
- The final message is specific enough to drop directly into a
  day-by-day itinerary: activity name, category, price tier (when
  known), and a short description.

Shared output schema used internally by every tier:
    {
      "city": "...",
      "source": "local_exact" | "vector_db" | "mcp_opentripmap",
      "activities": [
        {"name": ..., "category": ..., "price_tier": ..., "description": ...}
      ]
    }
    or {"error": "..."} on failure — tools never raise.

Setup:
    1. pip install -r requirements.txt
    2. cp .env.example .env — fill in OPENROUTER_API_KEY, and
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

load_dotenv()

DB_PATH = "./chroma_db"
COLLECTION_NAME = "activities"
DOCS_DIR = os.path.join(os.path.dirname(__file__), "local_activity_docs")
MCP_SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "mcp_opentripmap_server.py")

MODEL = os.environ.get("DEEP_AGENT_MODEL", "openrouter:z-ai/glm-5.2")


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
        city: the city to search, e.g. "New York", "Paris".
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
    try:
        client = chromadb.PersistentClient(path=DB_PATH)
        collection = client.get_collection(COLLECTION_NAME)
    except Exception as e:
        return {"error": f"Vector DB not available — run build_vector_db.py first. ({e})"}

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

    results = collection.query(query_texts=[query], n_results=5, where=where)

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]

    if not docs:
        return {"error": "No semantic match found for that query/filter combination."}

    activities = [
        {"name": m["name"], "category": m["category"], "price_tier": m["price_tier"], "description": d}
        for d, m in zip(docs, metas)
    ]
    return {"city": city or "multiple", "source": "vector_db", "activities": activities}


# ---------------------------------------------------------------------
# Agent assembly — tiers 1 & 2 are local Python tools; tier 3 (MCP) is
# loaded dynamically since MCP tool loading is async.
# ---------------------------------------------------------------------

async def build_agent():
    """Build the Deep Agent with local tools (tiers 1-2) plus the
    MCP-loaded OpenTripMap tool (tier 3, for any uncovered city).
    """
    local_tools = [search_activities_local_exact, search_activities_semantic]

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
            f"Locally covered cities (fast, curated data): {covered}. "
            "You have three knowledge sources, in priority order: "
            "(1) search_activities_local_exact — try this first for a covered city with a "
            "clear category/price filter; "
            "(2) search_activities_semantic — use this for a covered city if (1) finds "
            "nothing, or the request is vague/descriptive rather than an exact category; "
            "(3) the OpenTripMap MCP tool — use this for any city NOT in the locally "
            "covered list. "
            "Never invent an activity that no tool returned. If a tool returns an error, "
            "explain that honestly in your final message rather than guessing or ignoring it. "
            "Produce exactly ONE self-contained final message — never ask a follow-up "
            "question. If some detail is missing, state a reasonable assumption explicitly, "
            "or clearly flag what's missing. "
            "Your final message must be specific enough to drop directly into a day-by-day "
            "itinerary: name each activity, its category, its price tier (say 'unknown' if "
            "not available, e.g. from the MCP tier), and a short description."
        ),
    )
    return agent


async def answer(task: str) -> str:
    """Team-standard entry point: one task string in, one self-contained
    message out. Matches the answer(task) convention used by the
    Budget, Money & Customs, and Restaurants sub-agents.
    """
    agent = await build_agent()
    result = await agent.ainvoke({"messages": [{"role": "user", "content": task}]})
    return result["messages"][-1].content


# ---------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------

async def _run_self_tests():
    test_tasks = [
        "Find a free outdoor activity in New York.",
        "I want something romantic and artsy in Paris.",
        "What's a good cultural activity in Rome?",
        "Suggest a free outdoor activity in Kyoto.",
        # Grounding test: no good match in the covered cities' data
        "Find underwater scuba diving in New York.",
        # Domain-boundary test: should redirect to the Restaurants Agent
        "Where should I get dinner in Paris?",
        # Tier-3 test: a city with no local coverage — exercises the MCP fallback
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
