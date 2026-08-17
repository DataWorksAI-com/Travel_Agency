"""
Activities Agent — New York (+ MCP fallback for any other city)
--------------------------------------------------------------------
Author: Limeng Zhang

Domain-expert agent for "things to do." Three-tier knowledge source,
matching the pattern used elsewhere on the Activities module:

    Tier 1 — Exact local lookup:   new_york.json, filtered by
                                    category/price_tier. Fast, free,
                                    only works for New York.
    Tier 2 — Local semantic RAG:   Chroma vector search over the same
                                    New York data, for vague/natural-
                                    language queries that don't match
                                    an exact category. Only New York.
    Tier 3 — MCP live fallback:    mcp_opentripmap_server.py, wrapping
                                    the OpenTripMap REST API. Used for
                                    ANY city not covered by tiers 1/2.

Orchestrator contract (per the team-wide sub-agent rules):
- Input: a single task string from the orchestrator. This agent does
  not share context with other sub-agents — anything it needs (e.g.
  a city) must be explicit in that task string.
- Output: exactly ONE self-contained final message via answer(task).
  Never asks a follow-up question back to the orchestrator or user —
  if a tool errors or something's missing, the agent explains that
  honestly in its final message rather than stopping to ask.
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
import asyncio
import chromadb
from dotenv import load_dotenv
from deepagents import create_deep_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

DB_PATH = "./chroma_db"
COLLECTION_NAME = "activities_ny"
CITY_NAME = "New York"
LOCAL_DATA_FILE = os.path.join(os.path.dirname(__file__), "new_york.json")
MCP_SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "mcp_opentripmap_server.py")

MODEL = os.environ.get("DEEP_AGENT_MODEL", "openrouter:z-ai/glm-5.2")


# ---------------------------------------------------------------------
# Tier 1: exact local lookup
# ---------------------------------------------------------------------

def _load_local_data():
    with open(LOCAL_DATA_FILE, "r") as f:
        return json.load(f)


def search_activities_local_exact(category: str = "", price_tier: str = "") -> dict:
    """Tier 1 — exact filter lookup over New York's local activity data.

    Only covers New York. Use this first for precise category/price
    filters; if it returns no matches, fall back to
    search_activities_semantic for a vaguer natural-language query.

    Args:
        category: exact filter, e.g. "outdoor", "art", "cultural",
                  "sightseeing", "entertainment". Food/dining is out
                  of scope — that's the Restaurants Agent's domain.
        price_tier: exact filter: "free", "moderate", or "premium".

    Returns the shared schema dict, or {"error": "..."} if nothing
    matches. Never raises.
    """
    try:
        data = _load_local_data()
    except Exception as e:
        return {"error": f"Could not load local activity data: {e}"}

    filtered = data
    if category:
        filtered = [a for a in filtered if a["category"].lower() == category.lower()]
    if price_tier:
        filtered = [a for a in filtered if a["price_tier"].lower() == price_tier.lower()]

    if not filtered:
        return {"error": "No exact match in local data for that category/price_tier."}

    return {"city": CITY_NAME, "source": "local_exact", "activities": filtered}


# ---------------------------------------------------------------------
# Tier 2: local semantic search (Chroma)
# ---------------------------------------------------------------------

def search_activities_semantic(query: str, category: str = "", price_tier: str = "") -> dict:
    """Tier 2 — semantic (meaning-based) search over New York activities.

    Use this when the traveler's request is a vague or natural-
    language description (e.g. "something romantic") rather than an
    exact category — search_activities_local_exact won't match those.
    Only covers New York.

    Args:
        query: natural-language description of what the traveler wants.
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

    where = {}
    if category:
        where["category"] = category
    if price_tier:
        where["price_tier"] = price_tier

    results = collection.query(
        query_texts=[query],
        n_results=5,
        where=where if where else None,
    )

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]

    if not docs:
        return {"error": "No semantic match found for that query/filter combination."}

    activities = [
        {"name": m["name"], "category": m["category"], "price_tier": m["price_tier"], "description": d}
        for d, m in zip(docs, metas)
    ]
    return {"city": CITY_NAME, "source": "vector_db", "activities": activities}


# ---------------------------------------------------------------------
# Agent assembly — tiers 1 & 2 are local Python tools; tier 3 (MCP) is
# loaded dynamically since MCP tool loading is async.
# ---------------------------------------------------------------------

async def build_agent():
    """Build the Deep Agent with local tools (tiers 1-2) plus the
    MCP-loaded OpenTripMap tool (tier 3, for any city outside New York).

    Async because MCP tool discovery requires connecting to the
    mcp_opentripmap_server.py subprocess over stdio.
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
        # Tier 3 is a fallback, not a hard requirement — if the MCP
        # server can't start (e.g. no OPENTRIPMAP_API_KEY set yet),
        # the agent still works for New York via tiers 1-2.
        print(f"[warning] MCP tier unavailable, continuing with local tools only: {e}")

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
            "You have three knowledge sources, in priority order: "
            "(1) search_activities_local_exact — try this first for New York with a clear "
            "category/price filter; "
            "(2) search_activities_semantic — use this for New York if (1) finds nothing, or "
            "the request is vague/descriptive rather than an exact category; "
            "(3) the OpenTripMap MCP tool — use this for any city OTHER than New York, since "
            "tiers 1 and 2 only have New York data. "
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
        "I want something with a great skyline view in New York.",
        # Grounding test: no good match in the New York data
        "Find underwater scuba diving in New York.",
        # Domain-boundary test: should redirect to the Restaurants Agent
        "Where should I get dinner in New York?",
        # Tier-3 test: a city with no local data — exercises the MCP fallback
        "Find a cultural activity in Miami.",
    ]

    for task in test_tasks:
        print(f"=== Task: {task} ===")
        response = await answer(task)
        print(response)
        print()


if __name__ == "__main__":
    print(f"Using model: {MODEL}\n")
    asyncio.run(_run_self_tests())
