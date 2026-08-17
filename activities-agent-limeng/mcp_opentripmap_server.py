"""
MCP Server: OpenTripMap
--------------------------
Wraps the OpenTripMap REST API as an MCP tool, so the Activities
Agent can look up real activities/attractions for ANY city — not
just the ones with local data (New York). This is knowledge-source
tier 3: used only when tiers 1 (exact local lookup) and 2 (local
vector search) don't apply, because the requested city isn't in our
local dataset.

Requires a free API key from https://dev.opentripmap.org (no cost,
no credit card). Set it as OPENTRIPMAP_API_KEY in your .env file.

Run standalone to test:
    python mcp_opentripmap_server.py
(then connect to it via stdio from an MCP client — see
activities_agent.py for how this project connects to it)
"""

import os
import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

OPENTRIPMAP_API_KEY = os.environ.get("OPENTRIPMAP_API_KEY", "")
BASE_URL = "https://api.opentripmap.com/0.1/en/places"

mcp = FastMCP("opentripmap")


def _geocode_city(city: str) -> dict | None:
    """City name -> {lat, lon}. Returns None if the city can't be found."""
    resp = requests.get(
        f"{BASE_URL}/geoname",
        params={"name": city, "apikey": OPENTRIPMAP_API_KEY},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if "lat" not in data or "lon" not in data:
        return None
    return {"lat": data["lat"], "lon": data["lon"]}


@mcp.tool()
def search_opentripmap(city: str, category: str = "", limit: int = 5) -> dict:
    """Search OpenTripMap for real activities/attractions in any city.

    Args:
        city: the city to search, e.g. "Miami", "Boston".
        category: optional OpenTripMap "kinds" filter, e.g.
                  "cultural", "natural", "amusements", "sport".
                  Leave blank to search all kinds.
        limit: max number of results to return (default 5).

    Returns a dict matching the project's shared schema:
        {"city": ..., "source": "mcp_opentripmap", "activities": [...]}
    or {"error": "..."} on any failure (bad city, no API key, network
    error, etc.) — never raises.
    """
    if not OPENTRIPMAP_API_KEY:
        return {"error": "OPENTRIPMAP_API_KEY is not set — add it to your .env file."}

    try:
        coords = _geocode_city(city)
        if coords is None:
            return {"error": f"Could not find coordinates for city '{city}'."}

        resp = requests.get(
            f"{BASE_URL}/radius",
            params={
                "radius": 8000,
                "lon": coords["lon"],
                "lat": coords["lat"],
                "kinds": category if category else None,
                "limit": limit,
                "format": "json",
                "apikey": OPENTRIPMAP_API_KEY,
            },
            timeout=10,
        )
        resp.raise_for_status()
        places = resp.json()

        if not places:
            return {"error": f"No activities found for '{city}'" + (f" in category '{category}'." if category else ".")}

        activities = []
        for place in places[:limit]:
            activities.append({
                "name": place.get("name") or "Unnamed location",
                "category": place.get("kinds", "").split(",")[0] if place.get("kinds") else "unspecified",
                "price_tier": "unknown",  # OpenTripMap doesn't provide pricing
                "description": f"Distance from city center: {place.get('dist', '?'):.0f}m" if place.get("dist") else "",
            })

        return {"city": city, "source": "mcp_opentripmap", "activities": activities}

    except requests.exceptions.RequestException as e:
        return {"error": f"OpenTripMap request failed: {e}"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
