"""
MCP server: wraps OpenTripMap REST API as MCP tools.
Run standalone for a quick test:
    python mcp_opentripmap_server.py
(Normally started automatically via stdio by the agent.)
"""

import os
import json
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("opentripmap-activities")
API_BASE = "https://api.opentripmap.com/0.1/en"
API_KEY = os.environ.get("OPENTRIPMAP_API_KEY", "")


def _get(path: str, params: dict) -> dict:
    params = {**params, "apikey": API_KEY}
    r = httpx.get(f"{API_BASE}{path}", params=params, timeout=30.0)
    r.raise_for_status()
    return r.json()


@mcp.tool()
def search_live_places(city: str, kinds: str = "interesting_places", limit: int = 5) -> str:
    """Search live tourist places/activities for ANY city via OpenTripMap.

    Use this when the city is not in local docs / vector DB, or when the
    user wants live/external activity options. Not for restaurants/food
    (that's the Restaurants Agent).

    Args:
        city: city name, e.g. "Miami", "Paris", "Tokyo".
        kinds: OpenTripMap kinds filter, e.g. "interesting_places",
               "museums", "historic", "natural", "sport".
        limit: max results (default 5).
    """
    if not API_KEY:
        return json.dumps({"error": "OPENTRIPMAP_API_KEY is not set in the environment."})

    try:
        geo = _get("/places/geoname", {"name": city})
    except Exception as e:
        return json.dumps({"error": f"Geocoding failed for '{city}': {e}"})

    lat = geo.get("lat")
    lon = geo.get("lon")
    if lat is None or lon is None:
        return json.dumps({"error": f"Could not locate city '{city}'.", "raw": geo})

    try:
        places = _get(
            "/places/radius",
            {
                "radius": 8000,
                "lon": lon,
                "lat": lat,
                "kinds": kinds,
                "rate": 2,
                "limit": limit,
                "format": "json",
            },
        )
    except Exception as e:
        return json.dumps({"error": f"Places search failed: {e}"})

    activities = []
    for p in places:
        name = p.get("name") or ""
        if not name.strip():
            continue
        activities.append({
            "name": name,
            "category": (p.get("kinds") or kinds).split(",")[0],
            "price_tier": "unknown",
            "description": f"Live place near {city} (OpenTripMap). kinds={p.get('kinds')}",
        })

    return json.dumps({
        "city": city,
        "source": "mcp_opentripmap",
        "activities": activities,
    })


if __name__ == "__main__":
    mcp.run(transport="stdio")