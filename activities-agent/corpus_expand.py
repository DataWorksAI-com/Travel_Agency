"""
Corpus expansion for the Activities Agent
------------------------------------------------
Lets a one-off live lookup (the OpenTripMap fallback for an uncovered
city) turn into permanent local coverage: fetch real activities via
OpenTripMap, save them as a new local_activity_docs/<city>.json file,
and rebuild the Chroma index — so the next question about the same
city is answered by tier 1/2 (fast, free, no live API call) instead
of falling through to a live lookup every time.

This calls OpenTripMap directly with requests, separately from
mcp_opentripmap_server.py's MCP tool — the MCP tool stays available
for a genuine one-off MCP-protocol lookup; this module is what makes
that lookup "stick" for next time. This mirrors the self-expanding
corpus in Jainam's Activities Agent (his fetch_live_activities /
corpus_expand.py), adopted here as a genuinely useful capability
after comparing the two implementations — not reconstructed
guesswork.
"""

import os
import json
import requests

DOCS_DIR = os.path.join(os.path.dirname(__file__), "local_activity_docs")
OPENTRIPMAP_BASE = "https://api.opentripmap.com/0.1/en/places"


def _geocode_city(city: str, api_key: str):
    """City name -> (lat, lon), or None if it can't be found."""
    resp = requests.get(
        f"{OPENTRIPMAP_BASE}/geoname",
        params={"name": city, "apikey": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if "lat" not in data or "lon" not in data:
        return None
    return data["lat"], data["lon"]


def fetch_live_activities(city: str, category: str = "", limit: int = 5) -> list:
    """Call OpenTripMap directly and return activities in the shared
    schema. Raises on failure — callers should catch and convert to
    the project's {"error": "..."} shape rather than letting an
    exception reach the agent."""
    api_key = os.environ.get("OPENTRIPMAP_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENTRIPMAP_API_KEY is not set.")

    coords = _geocode_city(city, api_key)
    if coords is None:
        raise RuntimeError(f"Could not find coordinates for city '{city}'.")
    lat, lon = coords

    resp = requests.get(
        f"{OPENTRIPMAP_BASE}/radius",
        params={
            "radius": 8000,
            "lon": lon,
            "lat": lat,
            "kinds": category if category else None,
            "limit": limit,
            "format": "json",
            "apikey": api_key,
        },
        timeout=10,
    )
    resp.raise_for_status()
    places = resp.json()

    activities = []
    for place in places[:limit]:
        name = (place.get("name") or "").strip()
        if not name:
            continue
        activities.append({
            "name": name,
            "category": (place.get("kinds") or category or "unspecified").split(",")[0],
            "price_tier": "unknown",
            "description": f"Live OpenTripMap place near {city}; pricing not provided.",
        })
    return activities


def save_activities_for_city(city: str, activities: list) -> str:
    """Write (or overwrite) local_activity_docs/<city>.json in the
    same schema every other city file uses. Returns the file path."""
    os.makedirs(DOCS_DIR, exist_ok=True)
    slug = city.strip().lower().replace(" ", "_")
    path = os.path.join(DOCS_DIR, f"{slug}.json")
    with open(path, "w") as f:
        json.dump(activities, f, indent=2)
    return path
