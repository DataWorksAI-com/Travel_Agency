"""
money_tools.py -- reusable "Money & Customs" tools for travel agents.

Three tools, each a plain Python function with type hints and a docstring --
no dependency on deepagents, a specific model, or any agent framework. Any
framework that can register a Python function as a tool (LangChain,
deepagents, OpenAI function-calling, MCP, etc.) can use these as-is.

  1. get_exchange_rate    -- live currency conversion (Frankfurter API)
  2. get_money_customs    -- tipping/haggling norms, broken down per service
  3. get_income_context   -- rough economic scale reference (World Bank GNI
                             per capita) so a traveller has a sense of local
                             price scale, not just a raw currency conversion

Every function returns a JSON-serializable dict with a "found" (and, where
relevant, "error") field, so a calling agent/orchestrator can check success
programmatically instead of parsing a sentence.
"""

import requests

# ---------------------------------------------------------------------------
# Shared country -> ISO3 code map. ISO3 is what the World Bank API requires;
# reusing the same keys as MONEY_CUSTOMS_FACTS keeps both tools consistent
# and makes it obvious which countries the whole toolset currently covers.
# ---------------------------------------------------------------------------

COUNTRY_ISO3 = {
    "france": "FRA",
    "india": "IND",
    "usa": "USA",
    "japan": "JPN",
    "mexico": "MEX",
    "morocco": "MAR",
    "germany": "DEU",
}


# ---------------------------------------------------------------------------
# TOOL 1: Live exchange rate
# ---------------------------------------------------------------------------
# Uses Frankfurter (https://frankfurter.dev) -- free, no API key, backed by
# the European Central Bank.

def get_exchange_rate(from_currency: str, to_currency: str) -> dict:
    """Get the current live exchange rate between two currencies.

    Args:
        from_currency: 3-letter currency code to convert from, e.g. "USD".
        to_currency: 3-letter currency code to convert to, e.g. "EUR".

    Returns:
        {"from", "to", "rate", "date", "found", "error"}. "found" is False
        and "error" holds a message if the lookup failed.
    """
    frm = from_currency.strip().upper()
    to = to_currency.strip().upper()

    try:
        response = requests.get(
            "https://api.frankfurter.dev/v1/latest",
            params={"base": frm, "symbols": to},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        rate = data["rates"].get(to)
        if rate is None:
            return {"from": frm, "to": to, "rate": None, "date": None,
                     "found": False, "error": f"No rate found for {frm} to {to}."}
        return {"from": frm, "to": to, "rate": rate, "date": data.get("date"),
                 "found": True, "error": None}
    except requests.exceptions.RequestException as exc:
        return {"from": frm, "to": to, "rate": None, "date": None,
                 "found": False, "error": str(exc)}
    except (KeyError, ValueError):
        return {"from": frm, "to": to, "rate": None, "date": None,
                 "found": False, "error": "Unexpected response format from provider."}


# ---------------------------------------------------------------------------
# TOOL 2: Money customs, broken down per service
# ---------------------------------------------------------------------------
# Static knowledge today. Structured per-service rather than one flat
# sentence, so an agent can answer "what about taxis specifically" as well
# as "should I tip in general".

MONEY_CUSTOMS_FACTS = {
    "france": {
        "tipping_expected": False,
        "general_note": "A service charge is included in restaurant bills; tipping is not expected.",
        "by_service": {
            "restaurants": "not expected, service is included",
            "taxis": "round up to the nearest euro",
            "hotel_housekeeping": "1-2 EUR/day if desired, not required",
            "tour_guides": "10-20 EUR for a full-day tour, appreciated not required",
        },
        "haggling_expected": False,
        "haggling_note": "Prices in shops and markets are fixed; haggling is not customary.",
    },
    "india": {
        "tipping_expected": True,
        "general_note": "Modest tipping is appreciated across most services; amounts are small relative to Western norms.",
        "by_service": {
            "restaurants": "5-10% if no service charge is included",
            "taxis": "round up the fare; tipping not required for metered rides",
            "hotel_housekeeping": "50-100 INR/day",
            "tour_guides": "200-500 INR for a full-day tour",
        },
        "haggling_expected": True,
        "haggling_note": "Haggling is expected in open-air markets and with street vendors; not in fixed-price stores.",
    },
    "usa": {
        "tipping_expected": True,
        "general_note": "Tipping is a significant part of income in many service jobs and is broadly expected.",
        "by_service": {
            "restaurants": "18-20% of the pre-tax bill",
            "taxis": "15-20% of the fare",
            "hotel_housekeeping": "3-5 USD/day",
            "tour_guides": "15-20% of the tour cost, or 10-20 USD for a half/full day",
        },
        "haggling_expected": False,
        "haggling_note": "Prices in department stores and most retail are fixed; do not haggle there.",
    },
    "japan": {
        "tipping_expected": False,
        "general_note": "Tipping is not customary and can be perceived as awkward or even rude; leave the exact bill amount.",
        "by_service": {
            "restaurants": "not customary, do not tip",
            "taxis": "not customary, pay the metered fare",
            "hotel_housekeeping": "not customary",
            "tour_guides": "not customary, though a small wrapped gift is sometimes appreciated",
        },
        "haggling_expected": False,
        "haggling_note": "Prices are fixed essentially everywhere; haggling is not part of the culture.",
    },
    "mexico": {
        "tipping_expected": True,
        "general_note": "Tipping around 10-15% is expected in restaurants; norms vary more for other services.",
        "by_service": {
            "restaurants": "10-15% of the bill",
            "taxis": "not required for metered/app rides, rounding up is common",
            "hotel_housekeeping": "20-50 MXN/day",
            "tour_guides": "50-100 MXN per person for a half-day tour",
        },
        "haggling_expected": True,
        "haggling_note": "Haggling is common in markets and with street vendors; not in fixed-price stores.",
    },
    "morocco": {
        "tipping_expected": True,
        "general_note": "Small tips are customary across most services; haggling is a significant, expected part of shopping.",
        "by_service": {
            "restaurants": "5-10% if not already included",
            "taxis": "rounding up is common, not strictly required",
            "hotel_housekeeping": "10-20 MAD/day",
            "tour_guides": "50-100 MAD for a full-day tour",
        },
        "haggling_expected": True,
        "haggling_note": "Haggling is expected and culturally significant in souks and markets; not in fixed-price shops.",
    },
    "germany": {
        "tipping_expected": True,
        "general_note": "A modest tip is appreciated in restaurants but not strictly required elsewhere.",
        "by_service": {
            "restaurants": "round up or add ~5-10%",
            "taxis": "round up to the nearest euro",
            "hotel_housekeeping": "1-2 EUR/day if desired, not required",
            "tour_guides": "5-10 EUR appreciated, not required",
        },
        "haggling_expected": False,
        "haggling_note": "Prices are fixed in shops and markets; haggling is not customary.",
    },
}


def get_money_customs(country: str, service: str = "") -> dict:
    """Look up money-related customs for a country, optionally for one service.

    Args:
        country: Name of the country, e.g. "France", "India", "USA".
        service: Optional -- one of "restaurants", "taxis",
            "hotel_housekeeping", "tour_guides". Leave empty for the full
            breakdown across all services.

    Returns:
        {"country", "found", "tipping_expected", "haggling_expected",
        "general_note", "haggling_note", "by_service"} on success (by_service
        narrowed to one entry if "service" was given), or
        {"country", "found": False, "error"} if the country isn't covered
        (or the requested service isn't in by_service).
    """
    key = country.strip().lower()
    facts = MONEY_CUSTOMS_FACTS.get(key)

    if facts is None:
        return {"country": country.strip(), "found": False,
                 "error": f"No money-customs data for '{country}' yet."}

    result = {"country": country.strip(), "found": True, **facts}

    if service:
        service_key = service.strip().lower()
        note = facts["by_service"].get(service_key)
        if note is None:
            return {"country": country.strip(), "found": False,
                     "error": f"No data for service '{service}' in {country}. "
                              f"Available services: {list(facts['by_service'].keys())}"}
        result["by_service"] = {service_key: note}

    return result


# ---------------------------------------------------------------------------
# TOOL 3: Rough income context (World Bank GNI per capita)
# ---------------------------------------------------------------------------
# Free, keyless World Bank Open Data API. This is a national AVERAGE (GNI
# per capita), not a city-level median -- framed explicitly as rough scale
# context, not a precise local benchmark, since median income data isn't
# reliably available for free, real-time API access across countries.

WORLD_BANK_URL = "https://api.worldbank.org/v2/country/{code}/indicator/NY.GNP.PCAP.CD"


def get_income_context(country: str) -> dict:
    """Get a rough economic scale reference for a country (GNI per capita).

    This reports gross national income per capita (current USD, World Bank
    Atlas method) -- a national AVERAGE, not a median, and not city-specific.
    It is meant to give a traveller a rough sense of local price scale, not
    a precise benchmark.

    Args:
        country: Name of the country, e.g. "France", "India", "USA".

    Returns:
        {"country", "gni_per_capita_usd", "year", "found", "error", "note"}.
        "found" is False and "error" holds a message if unavailable.
    """
    key = country.strip().lower()
    iso3 = COUNTRY_ISO3.get(key)

    note = ("This is gross national income per capita (a national AVERAGE, "
             "World Bank Atlas method, current USD) -- not a city-level "
             "median. Use it as rough scale context, not a precise local "
             "benchmark.")

    if iso3 is None:
        return {"country": country.strip(), "gni_per_capita_usd": None,
                 "year": None, "found": False,
                 "error": f"No country code mapping for '{country}' yet.",
                 "note": note}

    try:
        response = requests.get(
            WORLD_BANK_URL.format(code=iso3),
            params={"format": "json", "per_page": 20},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.RequestException as exc:
        return {"country": country.strip(), "gni_per_capita_usd": None,
                 "year": None, "found": False,
                 "error": f"World Bank lookup failed: {exc}", "note": note}
    except ValueError:
        return {"country": country.strip(), "gni_per_capita_usd": None,
                 "year": None, "found": False,
                 "error": "World Bank returned a response that was not valid JSON.",
                 "note": note}

    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        return {"country": country.strip(), "gni_per_capita_usd": None,
                 "year": None, "found": False,
                 "error": f"World Bank returned no records for '{country}' ({iso3}).",
                 "note": note}

    # Records are newest-first; take the first one with a non-null value.
    latest = next((r for r in payload[1] if r.get("value") is not None), None)
    if latest is None:
        return {"country": country.strip(), "gni_per_capita_usd": None,
                 "year": None, "found": False,
                 "error": f"World Bank had no non-null GNI per capita values for '{country}'.",
                 "note": note}

    return {
        "country": country.strip(),
        "gni_per_capita_usd": round(latest["value"], 2),
        "year": latest.get("date"),
        "found": True,
        "error": None,
        "note": note,
    }


# ---------------------------------------------------------------------------
# Quick manual test -- run this file directly, no agent or LLM required.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(get_exchange_rate("USD", "EUR"))
    print(get_money_customs("France"))
    print(get_money_customs("India", service="taxis"))
    print(get_income_context("Mexico"))
