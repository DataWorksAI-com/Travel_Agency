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

import difflib
import hashlib
import os

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
# TOOL 2b: Agentic RAG layer over the same money-customs data
# ---------------------------------------------------------------------------
# get_money_customs() above is an exact, case-insensitive dict lookup --
# fast and precise, but it fails outright on a misspelled country name, an
# unlisted-but-similar country, or loose phrasing ("Mexican tipping norms").
#
# search_money_customs() is what actually gets exposed to the agent as a
# tool. It tries the exact lookup first (same as get_money_customs), and
# only falls back to semantic search -- a local ChromaDB vector index built
# from MONEY_CUSTOMS_FACTS itself, same default embedding model Destination
# uses (no API key, no service, ~80MB download on first use) -- if the exact
# lookup fails. This mirrors the same exact-lookup + vector-RAG split used
# by Destination (resolve_place / recommend_destinations) and Activities
# (read_activity_docs / search_activities): one tool for known-exact input,
# one for anything looser.
#
# The REFLECTION step: if even the best semantic match is a weak one (low
# cosine similarity), this does NOT fail or ask a follow-up question -- it
# returns the closest match anyway, with an "adjusted" field explaining
# it's an approximation, exactly the "never ask, state what changed"
# convention already used by Restaurants' search_with_reflection.

CONFIDENCE_THRESHOLD = 0.55  # below this cosine similarity, flag as approximate

_money_collection = None  # cached across calls, corpus embedded only once


def _get_money_collection():
    """Build or reuse the money-customs vector store. Returns (collection, None)
    or (None, error_dict)."""
    global _money_collection
    if _money_collection is not None:
        return _money_collection, None

    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError as exc:
        return None, {"error": f"ChromaDB is not installed ({exc}). Run: pip install chromadb"}

    entries = list(MONEY_CUSTOMS_FACTS.items())

    # Fingerprint the actual text being embedded, same reasoning as
    # Destination's recommend.py: a count check alone would miss edits to
    # existing entries and leave a stale index in place forever.
    fingerprint = hashlib.sha256(
        "\n".join(f"{key}|{facts['general_note']}|{facts['haggling_note']}" for key, facts in entries).encode("utf-8")
    ).hexdigest()[:16]

    base_dir = os.path.dirname(os.path.abspath(__file__))
    vector_db_path = os.path.join(base_dir, "money_customs_chroma_db")
    collection_metadata = {"hnsw:space": "cosine", "corpus_fingerprint": fingerprint}

    try:
        client = chromadb.PersistentClient(
            path=vector_db_path,
            settings=Settings(anonymized_telemetry=False),
        )
        collection = client.get_or_create_collection(
            name="money_customs",
            metadata=collection_metadata,
        )
    except Exception as exc:
        return None, {"error": f"Vector store unavailable: could not open ChromaDB ({exc})"}

    try:
        stored_fingerprint = (collection.metadata or {}).get("corpus_fingerprint")
        needs_load = stored_fingerprint != fingerprint or collection.count() != len(entries)
    except Exception as exc:
        return None, {"error": f"Vector store unavailable: could not inspect ChromaDB ({exc})"}

    if needs_load:
        try:
            client.delete_collection("money_customs")
            collection = client.get_or_create_collection(
                name="money_customs",
                metadata=collection_metadata,
            )
            documents, ids, metadatas = [], [], []
            for key, facts in entries:
                doc_text = (
                    f"{key.title()}. {facts['general_note']} {facts['haggling_note']} "
                    f"Tipping expected: {facts['tipping_expected']}. "
                    f"Haggling expected: {facts['haggling_expected']}."
                )
                documents.append(doc_text)
                ids.append(key)
                metadatas.append({"country_key": key})
            collection.add(ids=ids, documents=documents, metadatas=metadatas)
        except Exception as exc:
            return None, {"error": f"Vector store unavailable: could not embed the corpus ({exc})"}

    _money_collection = collection
    return _money_collection, None


def search_money_customs(country: str, service: str = "") -> dict:
    """Look up money customs for a country -- exact match, then fuzzy
    match, then semantic search as a last resort (agentic RAG). This is
    the tool to call for money customs questions; it never fails outright
    on a misspelling or loose phrasing, and never asks a follow-up question.

    Three steps, in order:
      1. Exact match (fast, precise) -- e.g. "France".
      2. Fuzzy match (character-level, catches typos) -- e.g. "Mexcio"
         correctly resolves to Mexico. Vector/semantic search is the WRONG
         tool for this: embeddings match MEANING, not scrambled spelling,
         and a single garbled word carries no real semantic signal. A
         string-similarity check (difflib) is what actually solves typos.
      3. Semantic search (vector, ChromaDB) -- for genuinely different
         phrasing that isn't just a typo, e.g. "Mexican customs" or
         "tipping norms south of the US border".

    Args:
        country: Country name, e.g. "France". Doesn't need to be an exact
            spelling -- "Mexcio" resolves via fuzzy match, "Mexican
            customs" resolves via semantic search.
        service: Optional -- one of "restaurants", "taxis",
            "hotel_housekeeping", "tour_guides".

    Returns:
        Same shape as get_money_customs, plus:
          - "match_score": similarity score. None for an exact match;
            a difflib ratio (0..1) for a fuzzy match; a cosine similarity
            (0..1) for a semantic match.
          - "adjusted": a plain-language note if this is a corrected typo
            or a low-confidence approximate match rather than an exact
            hit -- None if the input matched exactly.
        "found" is only False if there is no usable data at all (e.g. the
        vector store itself is unavailable AND no fuzzy match existed).
    """
    # Step 1: try the exact lookup first -- fast, precise, no reflection needed.
    exact = get_money_customs(country, service=service)
    if exact.get("found"):
        exact["match_score"] = None
        exact["adjusted"] = None
        return exact

    # Step 2: fuzzy match against known country names -- catches typos like
    # "Mexcio" -> "mexico" that semantic search can't, since a scrambled
    # single word has no meaningful embedding signal to match against.
    FUZZY_CUTOFF = 0.75  # difflib ratio; higher = stricter typo tolerance
    close = difflib.get_close_matches(
        country.strip().lower(), MONEY_CUSTOMS_FACTS.keys(), n=1, cutoff=FUZZY_CUTOFF
    )
    if close:
        matched_key = close[0]
        facts = MONEY_CUSTOMS_FACTS[matched_key]
        ratio = round(
            difflib.SequenceMatcher(None, country.strip().lower(), matched_key).ratio(), 3
        )
        result = {
            "country": matched_key.title(),
            "found": True,
            "match_score": ratio,
            "adjusted": (
                f"Adjusted: interpreted '{country}' as {matched_key.title()} "
                f"(likely a typo, {ratio} character-similarity match)."
            ),
            **facts,
        }
        if service:
            service_key = service.strip().lower()
            note = facts["by_service"].get(service_key)
            if note is None:
                result["adjusted"] += (
                    f" No specific data for service '{service}' in {matched_key.title()}; "
                    f"showing general note instead."
                )
                result["by_service"] = {}
            else:
                result["by_service"] = {service_key: note}
        return result

    # Step 3: no exact or fuzzy match -- fall back to semantic search over
    # the same underlying data, for genuinely different phrasing (not typos).
    collection, error = _get_money_collection()
    if error:
        return {"country": country.strip(), "found": False, "error": error["error"],
                 "match_score": None, "adjusted": None}

    try:
        count = collection.count()
        results = collection.query(query_texts=[country], n_results=min(1, count))
    except Exception as exc:
        return {"country": country.strip(), "found": False,
                 "error": f"Semantic search failed: {exc}", "match_score": None, "adjusted": None}

    ids = (results.get("ids") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]
    if not ids:
        return {"country": country.strip(), "found": False,
                 "error": f"No customs data available at all for {country!r}.",
                 "match_score": None, "adjusted": None}

    best_id = ids[0]
    match_score = round(max(0.0, min(1.0, 1.0 - float(distances[0]))), 3)
    facts = MONEY_CUSTOMS_FACTS.get(best_id)
    if facts is None:
        return {"country": country.strip(), "found": False,
                 "error": "Internal error: matched entry missing from source data.",
                 "match_score": None, "adjusted": None}

    # REFLECTION: never fail or ask a question over low confidence -- return
    # the closest match anyway, and say plainly that it's an approximation.
    adjusted = None
    if match_score < CONFIDENCE_THRESHOLD:
        adjusted = (
            f"Adjusted: no country matched '{country}' with high confidence. "
            f"Showing the closest match, {best_id.title()} (similarity {match_score}), "
            f"as a best-guess approximation -- verify before relying on it."
        )

    result = {
        "country": best_id.title(),
        "found": True,
        "match_score": match_score,
        "adjusted": adjusted,
        **facts,
    }

    if service:
        service_key = service.strip().lower()
        note = facts["by_service"].get(service_key)
        if note is None:
            extra = f"No specific data for service '{service}' in {best_id.title()}; showing general note instead."
            result["adjusted"] = f"{adjusted} {extra}" if adjusted else f"Adjusted: {extra}"
            result["by_service"] = {}
        else:
            result["by_service"] = {service_key: note}

    return result
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
