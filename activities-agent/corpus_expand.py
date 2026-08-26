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

# Categories a traveller would plausibly visit. Passing nothing here lets
# OpenTripMap return any POI type at all, including cinemas and churches.
DEFAULT_KINDS = "interesting_places,beaches,natural,cultural,historic,museums,architecture"


def _geocode_city(city: str, api_key: str, country: str = ""):
    """City name -> (lat, lon), or None if it can't be found.

    `country` is an ISO 3166-1 alpha-2 code. Without it this resolves on name
    alone: "Aruba" returned a town in Piedmont, Italy, and the caller then wrote
    Italian castles into local_activity_docs/aruba.json, where tiers 1 and 2
    serve them forever after. The result is verified as well as filtered,
    because the filter is only advisory.
    """
    params = {"name": city, "apikey": api_key}
    if country:
        params["country"] = country.lower()
    resp = requests.get(f"{OPENTRIPMAP_BASE}/geoname", params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if "lat" not in data or "lon" not in data:
        return None
    resolved = (data.get("country") or "").lower()
    if country and resolved and resolved != country.lower():
        raise ValueError(
            f"OpenTripMap resolved {city!r} to a place in {resolved.upper()}, not "
            f"{country.upper()}. Refusing to cache activities for the wrong place."
        )
    return data["lat"], data["lon"]


def fetch_live_activities(city: str, category: str = "", limit: int = 5, country: str = "") -> list:
    """Call OpenTripMap directly and return activities in the shared
    schema. Raises on failure — callers should catch and convert to
    the project's {"error": "..."} shape rather than letting an
    exception reach the agent."""
    api_key = os.environ.get("OPENTRIPMAP_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENTRIPMAP_API_KEY is not set.")

    coords = _geocode_city(city, api_key, country=country)
    if coords is None:
        raise RuntimeError(f"Could not find coordinates for city '{city}'.")
    lat, lon = coords

    resp = requests.get(
        f"{OPENTRIPMAP_BASE}/radius",
        params={
            # 8km around the city centre missed everything a traveller would
            # actually go to: for Cancun it reached the shopping district but
            # not the ruins, the underwater museum, or the island coast.
            "radius": 25000,
            "lon": lon,
            "lat": lat,
            "kinds": category or DEFAULT_KINDS,
            # OpenTripMap's importance rating. Without it, an unfiltered radius
            # search returns the nearest POI of ANY type -- Cancun yielded two
            # cinemas and two Pentecostal churches, which were then cached and
            # served as the activity plan for a Caribbean beach holiday. rate=2
            # restricts to places rated notable. Fewer results, and if that
            # means none, the caller reports no coverage rather than filler.
            "rate": 2,
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
