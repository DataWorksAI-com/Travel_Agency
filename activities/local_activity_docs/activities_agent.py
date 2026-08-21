"""
Activities Agent (stub version)
---------------------------------
A Deep Agent with an Activities system prompt and a stub tool that
reads local activity docs for one city, rather than a vector DB.
Used to validate tool-calling logic and domain boundaries before
adding real retrieval (vector DB or MCP/REST API).

Covers Chicago. Add more city files under local_activity_docs/ as
coverage expands.

Proposed shared input/output JSON — a starting proposal for this
tool's contract, not yet an agreed-upon interface:

  Input to the agent (conceptually — the Deep Agent takes a natural
  language message, but the *tool* takes structured args):
    {
      "city": "Chicago",
      "category": "outdoor"    # optional
    }

  Output from the read_activity_docs tool:
    {
      "city": "Chicago",
      "source": "local_docs",
      "activities": [
        {
          "name": "...",
          "category": "...",
          "price_tier": "...",
          "description": "..."
        },
        ...
      ]
    }

Setup:
    1. pip install -r requirements.txt
    2. cp .env.example .env, fill in your OPENROUTER_API_KEY
    3. python activities_agent.py
"""

import os
import json
import glob
from dotenv import load_dotenv
from deepagents import create_deep_agent

from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma

import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

DOCS_DIR = os.path.join(os.path.dirname(__file__), "local_activity_docs")

INDEX_DIR = os.path.join(os.path.dirname(__file__), "vector_index")
COLLECTION = "activities"
EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")

_vector_store = None

def _load_city_docs(city: str):
    """Load the local activity doc file for a city, case-insensitive."""
    path = os.path.join(DOCS_DIR, f"{city.strip().lower()}.json")
    if not os.path.exists(path):
        available = [
            os.path.splitext(os.path.basename(p))[0]
            for p in glob.glob(os.path.join(DOCS_DIR, "*.json"))
        ]
        return None, available
    with open(path, "r") as f:
        return json.load(f), None

def _get_vector_store()-> Chroma:
    """Load the Chroma index built by build_vector_index.py (cached)."""

    global _vector_store
    if _vector_store is None:
        if not os.path.isdir(INDEX_DIR):
            raise FileNotFoundError(
                f"Vector index not found at {INDEX_DIR}. "
                "Run: python build_vector_index.py"
            )

        embeddings = OllamaEmbeddings(model=EMBED_MODEL)
        _vector_store = Chroma(
            persist_directory=INDEX_DIR,
            embedding_function=embeddings,
            collection_name=COLLECTION,
        )

    return _vector_store

def read_activity_docs(city: str, category: str = "") -> str:
    """Read local activity docs for a city and optionally filter by category.

    This is a stub knowledge source: it reads a local JSON file of
    activities for the given city (no external API or vector search
    yet). Use this to find real activity options before answering.

    Args:
        city: the city to look up, e.g. "Chicago".
        category: optional exact filter, e.g. "outdoor", "art",
                  "cultural", "sightseeing", "entertainment"
                  (food/dining is out of scope — that's the
                  Restaurants Agent's domain).

    Returns a JSON string matching the shared output schema documented
    at the top of this file, or an error message listing which cities
    are actually available if the city isn't covered yet.
    """
    docs, available = _load_city_docs(city)
    if docs is None:
        return json.dumps({
            "error": f"No local activity docs found for '{city}'.",
            "available_cities": available,
        })

    if category:
        docs = [d for d in docs if d["category"].lower() == category.lower()]

    return json.dumps({
        "city": city,
        "source": "local_docs",
        "activities": docs,
    })

def search_activities(query: str, city: str = "", k: int = 4) -> str:
    """Semantically search activities in the Vector DB (RAG).
    Use this when the user describes what they want in natural language
    (e.g. "kid-friendly waterfront", "free outdoor history walk") instead
    of an exact category name. Optionally pass city to restrict results.
    Args:
        query: natural-language description of desired activities.
        city: optional city filter, e.g. "Boston".
        k: max number of results (default 4).
    """

    try:
        store = _get_vector_store()

    except FileNotFoundError as e:
        return json.dumps({"error": str(e)})

    city_norm = city.strip().lower()
    available = [
        os.path.splitext(os.path.basename(p))[0]
        for p in glob.glob(os.path.join(DOCS_DIR, "*.json"))
    ]

    if city_norm:
        if city_norm not in available:
            return json.dumps({
                "error": f"No activity coverage index for '{city}'.",
                "available_cities": available,
            })
        results = store.similarity_search(
            query,
            k=k,
            filter={"city": city_norm},
        )

    else:
        results = store.similarity_search(query, k=k)

    activities=[
        {
            "name": doc.metadata["name"],
            "category": doc.metadata["category"],
            "price_tier": doc.metadata["price_tier"],
            "description": doc.metadata["description"],
        }

        for doc in results
    ]

    return json.dumps({
        "city": city or "any",
        "source": "vector_db",
        "query": query,
        "activities": activities,
    })

MODEL = os.environ.get("DEEP_AGENT_MODEL", "openrouter:z-ai/glm-5.2")

async def build_agent():
    """Create Deep Agent with local tools + MCP OpenTripMap tools."""
    server_path = os.path.join(os.path.dirname(__file__), "mcp_opentripmap_server.py")
    client = MultiServerMCPClient(
        {
            "opentripmap": {
                "transport": "stdio",
                "command": "python",
                "args": [server_path],
                "env": {
                    **os.environ,
                    "OPENTRIPMAP_API_KEY": os.environ.get("OPENTRIPMAP_API_KEY", ""),
                },
            }
        }
    )
    mcp_tools = await client.get_tools()

# agent = create_deep_agent(
#     model=MODEL,
#     tools=[read_activity_docs, search_activities],
#     # system_prompt=(
#     #     "You are the Activities domain-expert agent for a travel planning system. "
#     #     "You help find things to do — sightseeing, outdoor activities, cultural experiences, "
#     #     "art, and entertainment. Food and dining recommendations are out of scope — "
#     #     "that's handled by the separate Restaurants Agent, so redirect food questions there "
#     #     "instead of answering them yourself. "
#     #     "Always use the read_activity_docs tool to look up real options before answering. "
#     #     "Never invent an activity that the tool did not return. "
#     #     "If the requested city isn't covered yet, tell the user honestly and mention "
#     #     "which cities are currently available."
#     # ),
#     system_prompt=(
#     "Only name activities that appear in the tool JSON. If the tool returned one item, recommend only that."
#     "You are the Activities domain-expert agent for a travel planning system. "
#     "You help find things to do — sightseeing, outdoor activities, cultural experiences, "
#     "art, entertainment, and family-friendly options. Food and dining are out of scope — "
#     "redirect those to the Restaurants Agent. "
#     "Use search_activities for natural-language needs (semantic / RAG search). "
#     "Use read_activity_docs for simple city/category listings from local JSON. "
#     "Never invent an activity that a tool did not return. "
#     "If a city isn't covered, say so and list available cities."
# ),
# )


    return create_deep_agent(
        model=MODEL,
        tools=[read_activity_docs, search_activities, *mcp_tools],
        system_prompt=(
            "You are the Activities domain-expert agent for a travel planning system. "
            "You help find things to do. Food/dining is out of scope — redirect to the Restaurants Agent. "
            "Tool choice: "
            "1) search_activities for semantic search over curated local docs (Chicago/Boston). "
            "2) read_activity_docs for simple city/category listings from local JSON. "
            "3) search_live_places (MCP) for ANY other city or when local docs have no coverage. "
            "Never invent activities. Only use what tools return. "
            "If a tool errors, explain the error honestly."
        ),
    )

# def main():
#     print(f"Using model: {MODEL}\n")

#     # test_queries = [
#     #     "What's a good free outdoor activity in Chicago?",
#     #     "Find me something fun and artsy to do in Chicago",
#     #     "What should I do in Boston for a family day?",
#     #     "What's a free outdoor activity in Boston?",
#     #     # Grounding test: a city that isn't covered yet
#     #     "What activities are there in Miami?",
#     #     # Domain-boundary test: should redirect to the Restaurants Agent, not answer directly
#     #     "Where should I eat dinner in Chicago?",
#     # ]

#     test_queries = [
#     # Exact-style (often read_activity_docs)
#     "What's a good free outdoor activity in Chicago?",
#     "Find me something fun and artsy to do in Chicago",
#     # Semantic RAG (should prefer search_activities)
#     "I want something kid-friendly near the water in Boston",
#     "Suggest a free historic walk outdoors in Boston",
#     # Still useful
#     "What should I do in Boston for a family day?",
#     # Grounding
#     "What activities are there in Miami?",
#     # Domain boundary
#     "Where should I eat dinner in Chicago?",
# ]

#     for q in test_queries:
#         print(f"=== Query: {q} ===")
#         result = agent.invoke({"messages": [{"role": "user", "content": q}]})
#         print(result["messages"][-1].content)
#         print()


# if __name__ == "__main__":
#     main()

async def main():
    print(f"Using model: {MODEL}\n")
    agent = await build_agent()

    test_queries = [
        "What's a good free outdoor activity in Chicago?",
        "I want something kid-friendly near the water in Boston",
        # LIVE MCP — city not in local JSON
        "What are some interesting places to visit in Miami?",
        "Suggest museums or historic sites in Paris",
        "Where should I eat dinner in Chicago?",
    ]

    for q in test_queries:
        print(f"=== Query: {q} ===")
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": q}]}
        )
        print(result["messages"][-1].content)
        print()


if __name__ == "__main__":
    asyncio.run(main())
