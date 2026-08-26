"""Place resolution tool for the Destination Agent data layer.

Case 1: the user already named a city. This does a live lookup of any city name
and returns the coordinates the other tools need. It does NOT touch the corpus.

Source: Open-Meteo Geocoding API (free, keyless, GeoNames-derived)
    https://geocoding-api.open-meteo.com/v1/search

Contract:
  - returns plain Python dicts, never JSON strings
  - never raises: every failure path returns {"error": "..."}
  - reports only what the API returns; nothing is filled in from model knowledge
"""

# truststore MUST be injected before requests is imported, or HTTPS calls on
# this network hang ~5 minutes behind the intercepting proxy certificate.
import truststore

truststore.inject_into_ssl()

import requests

import unicodedata

API_URL = "https://geocoding-api.open-meteo.com/v1/search"
TIMEOUT_SECONDS = 30
RESULT_COUNT = 10


def resolve_place(city_name):
    """Resolve a city name to its coordinates and country code.

    Args:
        city_name: a city name, e.g. "Tokyo".

    Returns:
        On success, {"name", "country_code", "lat", "lon"}.
        On any failure, a dict {"error": "..."}.
    """
    if not isinstance(city_name, str):
        return {"error": f"city_name must be a string, got {type(city_name).__name__}"}

    query = city_name.strip()
    if not query:
        return {"error": "city_name was empty or blank"}

    params = {
        "name": query,
        "count": RESULT_COUNT,
        "language": "en",
        "format": "json",
    }

    try:
        response = requests.get(API_URL, params=params, timeout=TIMEOUT_SECONDS)
    except requests.exceptions.Timeout:
        return {"error": f"Place lookup unavailable: Open-Meteo geocoding timed out after {TIMEOUT_SECONDS}s"}
    except requests.exceptions.RequestException as exc:
        return {"error": f"Place lookup unavailable: network error contacting Open-Meteo geocoding ({exc})"}

    if response.status_code != 200:
        return {"error": f"Place lookup unavailable: Open-Meteo geocoding returned HTTP {response.status_code}"}

    try:
        payload = response.json()
    except ValueError:
        return {"error": "Place lookup unavailable: Open-Meteo geocoding returned a response that was not valid JSON"}

    if not isinstance(payload, dict):
        return {"error": f"Place lookup unavailable: expected a JSON object, got {type(payload).__name__}"}

    # Open-Meteo omits "results" entirely when nothing matched.
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return {"error": f"No place found matching {city_name!r}"}

    match = _pick_best(results, query)
    if match is None:
        return {"error": f"No usable place record found matching {city_name!r}"}

    lat = match.get("latitude")
    lon = match.get("longitude")
    name = match.get("name")
    country_code = match.get("country_code")

    missing = [
        field
        for field, value in (
            ("name", name),
            ("country_code", country_code),
            ("latitude", lat),
            ("longitude", lon),
        )
        if value is None
    ]
    if missing:
        return {"error": f"Place record for {city_name!r} was missing required field(s): {', '.join(missing)}"}

    return {
        "name": name,
        "country_code": country_code,
        "lat": lat,
        "lon": lon,
    }


def _fold(text: str) -> str:
    """Casefold and strip accents.

    Open-Meteo's record is "Cancún". A user typing "Cancun" found no exact
    match here, fell through to the API's top hit, and resolved to a village in
    Guangxi, China -- which the destination agent then wrote into the committed
    shared RAG corpus. Comparing folded forms is what stops that.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _pick_best(results, query):
    """Prefer an exact name match; otherwise take the API's own top ranking."""
    usable = [r for r in results if isinstance(r, dict)]
    if not usable:
        return None

    lowered = _fold(query)
    exact = [r for r in usable if isinstance(r.get("name"), str) and _fold(r["name"]) == lowered]
    if exact:
        # Among exact name matches, the most populous is the one a traveller means.
        return max(exact, key=lambda r: r.get("population") or 0)

    return usable[0]


if __name__ == "__main__":
    for probe in ("Tokyo", "asdfghjkl", "  ", 42):
        print(f"--- resolve_place({probe!r}) ---")
        print(resolve_place(probe))
