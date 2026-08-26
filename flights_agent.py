"""
Flights Sub-Agent — REAL DATA via Travelpayouts (Aviasales Data API)

Scope: budgets and routes only — this agent should never touch hotels,
activities, or destination advice. Keep it narrow.

NOTE on data: Travelpayouts returns real cached prices from actual
Aviasales user searches (stored up to 7 days), not live real-time
availability. Good fit for a recommendation agent, not a booking engine.

Two tools:
  1. get_airport_code  — resolves a city name to an IATA code via
     Travelpayouts' free Autocomplete API (no token required)
  2. search_flights     — searches routes via the prices_for_dates
     endpoint, with an optional date and optional price filter

Requires in .env: TRAVELPAYOUTS_TOKEN
Get one: log in -> Profile -> API token
"""

import os
from typing import Optional
from datetime import date, timedelta

import requests
from dotenv import load_dotenv
load_dotenv()

TP_TOKEN = os.environ["TRAVELPAYOUTS_TOKEN"]
AUTOCOMPLETE_URL = "https://autocomplete.travelpayouts.com/places2"
SEARCH_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"


def _redact(error: object) -> str:
    """Stringify an error with the API token removed.

    The token is a query parameter (see search_prices below), and requests'
    exceptions stringify as the full request URL. Without this, a failed
    search returns the credential to the caller -- which reaches the browser
    transcript, and, under the agentic orchestrator, the model's context.
    """
    return str(error).replace(TP_TOKEN, "<token redacted>")


def get_airport_code(city: str) -> str:
    """Look up the IATA airport or city code for a given city name, using
    Travelpayouts' free Autocomplete API — works for any city worldwide.
    No token needed for this endpoint."""
    try:
        response = requests.get(
            AUTOCOMPLETE_URL,
            params={"term": city, "locale": "en", "types[]": ["city", "airport"]},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        return f"Airport lookup failed for '{city}': {error}"

    places = response.json()
    if not places:
        return f"No airport or city code found for '{city}'."

    # Prefer a city-level match (covers multiple airports) if one exists,
    # otherwise take the first airport match.
    city_match = next((p for p in places if p.get("type") == "city"), None)
    best = city_match or places[0]

    code = best.get("code")
    name = best.get("name", city)
    return f"{name} → {code}"


def _format_minutes(minutes) -> str:
    """Convert a plain integer minute count into '6h 40m' style text."""
    if minutes is None:
        return "unknown duration"
    minutes = int(minutes)
    hours, mins = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if mins:
        parts.append(f"{mins}m")
    return " ".join(parts) if parts else "0m"


def _fetch_offers(origin_code: str, destination_code: str, date_str: str) -> tuple:
    """Single request to the search API. Returns (offers, error_message_or_None)."""
    try:
        response = requests.get(
            SEARCH_URL,
            params={
                "origin": origin_code.upper(),
                "destination": destination_code.upper(),
                "departure_at": date_str,
                "currency": "usd",
                "sorting": "price",
                "one_way": "true",
                "direct": "false",
                "limit": 10,
                "token": TP_TOKEN,
            },
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        return [], f"Flight search failed for {origin_code}→{destination_code}: {_redact(error)}"

    payload = response.json()
    if not payload.get("success", False):
        return [], f"Flight search failed for {origin_code}→{destination_code}: {payload.get('error')}"

    return payload.get("data", []), None


def search_flights(
    origin_code: str,
    destination_code: str,
    date_str: Optional[str] = None,
    max_price: Optional[float] = None,
) -> str:
    """Search flights between two IATA airport or city codes (e.g. 'BOS', 'PAR').
    date_str is YYYY-MM-DD or YYYY-MM; defaults to 30 days from today if not
    given. max_price optionally filters results to that ceiling (USD).
    Returns real cached prices from Aviasales user searches (up to 7 days
    old), not live real-time availability. If no results exist for an exact
    date, automatically retries with just that month before giving up."""
    if not date_str:
        date_str = (date.today() + timedelta(days=30)).isoformat()

    offers, error = _fetch_offers(origin_code, destination_code, date_str)
    if error:
        return error

    widened = False
    if not offers and len(date_str) == 10:  # was a specific YYYY-MM-DD, try the whole month
        month_only = date_str[:7]
        offers, error = _fetch_offers(origin_code, destination_code, month_only)
        if error:
            return error
        widened = True

    if max_price is not None:
        offers = [o for o in offers if float(o.get("price", "inf")) <= max_price]

    if not offers:
        return (
            f"No cached flight data found from {origin_code.upper()} to {destination_code.upper()} "
            f"around {date_str}, even after widening to the full month. This route/date may simply "
            f"have no recent traveler searches in Aviasales's cache — try a different route to confirm."
        )

    # Already sorted by price via sorting=price, but keep top 5 to stay concise.
    offers = offers[:5]

    lines = []
    for offer in offers:
        price = offer.get("price")
        carrier = offer.get("airline", "??")
        duration = _format_minutes(offer.get("duration_to") or offer.get("duration"))
        stops = offer.get("transfers", 0)
        stop_text = "nonstop" if stops == 0 else f"{stops} stop(s)"
        # The searched code may be a CITY code (e.g. PAR covers CDG, ORY,
        # BVA) — show the actual arrival airport so it's clear which
        # specific airport this flight lands at.
        arrival_airport = offer.get("destination_airport", "??")
        lines.append(
            f"{carrier}: USD {price}, {duration}, {stop_text}, arrives {arrival_airport}"
        )

    header = f"Flights {origin_code.upper()}→{destination_code.upper()}"
    header += f" (month of {date_str[:7]}, no exact-date match)" if widened else f" on {date_str}"
    return header + ":\n" + "\n".join(lines)


# ── SubAgent config — plug this into your orchestrator ──────────────────
flights_subagent = {
    "name": "flights-agent",
    "description": "Handles flight search, routes, and budget comparisons.",
    "system_prompt": (
        "You are a flights specialist. Use get_airport_code to resolve city "
        "names to airport codes BEFORE calling search_flights — search_flights "
        "requires codes, not city names. Stay focused on flights only; "
        "do not discuss hotels, activities, or destinations.\n\n"
        "IMPORTANT — keep your final answer SHORT and DATA-ONLY:\n"
        "- List at most 3 options, one per line, e.g.: 'EY: $371, 16h, 1 stop, arrives DEL'\n"
        "- No headers, no bold/markdown formatting, no emojis\n"
        "- No written recommendation paragraph — just state which option is cheapest\n"
        "- If prices are cached/widened-month data, say so in ONE short trailing "
        "note, not a full paragraph\n"
        "The orchestrator handles final formatting and recommendations for the "
        "user — your job is to hand back clean facts, not a finished answer."
    ),
    "tools": [get_airport_code, search_flights],
    "model": "openrouter:openai/gpt-4o-mini",
}


# ── Standalone test — run this file directly to test just this sub-agent ──
if __name__ == "__main__":
    from deepagents import create_deep_agent

    agent = create_deep_agent(
        model="openrouter:anthropic/claude-sonnet-4.5",
        tools=[get_airport_code, search_flights],
        system_prompt=flights_subagent["system_prompt"],
    )

    result = agent.invoke({
        "messages": [
            {"role": "user", "content": "Find me a flight from Boston to India under $1300."}
        ]
    })

    print("\n--- Full message trace ---")
    for m in result["messages"]:
        role = getattr(m, "type", "unknown")
        print(f"\n[{role}]")
        print(m.content)