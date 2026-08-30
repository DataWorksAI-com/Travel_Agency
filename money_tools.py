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
    # Tropical destinations added for the assignment's actual scope.
    "jamaica": "JAM",
    "dominican republic": "DOM",
    "bahamas": "BHS",
    "thailand": "THA",
    "bali": "IDN",  # World Bank tracks Indonesia; Bali has no separate national data
    "philippines": "PHL",
    "costa rica": "CRI",
    "belize": "BLZ",
    "fiji": "FJI",
    "hawaii": "USA",  # a US state, not a separate country -- reuses the USA figure
    "aruba": "ABW",
    "barbados": "BRB",
    "maldives": "MDV",
    "seychelles": "SYC",
    "vietnam": "VNM",
}

# Countries whose key.title() would produce something wrong (acronyms,
# multi-word names, etc.) -- checked first before falling back to .title().
_DISPLAY_NAME_OVERRIDES = {
    "usa": "USA",
}


def _display_name(country_key: str) -> str:
    """Country key -> human-readable display name, handling acronyms
    (.title() alone would turn 'usa' into 'Usa', not 'USA')."""
    return _DISPLAY_NAME_OVERRIDES.get(country_key, country_key.title())


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
                     "found": False, "error": f"No rate found for {frm} to {to}.",
                     "match_score": None}
        return {"from": frm, "to": to, "rate": rate, "date": data.get("date"),
                 "found": True, "error": None, "match_score": None}
    except requests.exceptions.RequestException as exc:
        return {"from": frm, "to": to, "rate": None, "date": None,
                 "found": False, "error": str(exc), "match_score": None}
    except (KeyError, ValueError):
        return {"from": frm, "to": to, "rate": None, "date": None,
                 "found": False, "error": "Unexpected response format from provider.",
                 "match_score": None}


# ---------------------------------------------------------------------------
# TOOL 2: Money customs, broken down per service
# ---------------------------------------------------------------------------
# Static knowledge today. Structured per-service rather than one flat
# sentence, so an agent can answer "what about taxis specifically" as well
# as "should I tip in general".

MONEY_CUSTOMS_FACTS = {
    "france": {
        "tipping_expected": False,
        "general_note": "A service charge (service compris) is typically included in restaurant bills; French diners rarely tip beyond rounding up.",
        "by_service": {
            "restaurants": "not expected; round up the bill, or add a few euros only if service was exceptional",
            "taxis": "round up the fare; a euro or two extra if the driver helps with luggage",
            "hotel_housekeeping": "small optional tip on departure if desired; no fixed amount is customary",
            "tour_guides": "small-group walking tour: 2-5 EUR per person; private guide (a few hours): 10-20 EUR for the whole group",
        },
        "haggling_expected": False,
        "haggling_note": "Prices in shops and markets are fixed; haggling is not customary.",
        "source": "Rick Steves -- ricksteves.com/travel-tips/money/tipping-in-europe and community.ricksteves.com forum threads on French tipping.",
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
        "source": "General knowledge, not independently verified -- see README.",
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
        "source": "General knowledge, not independently verified -- see README.",
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
        "source": "General knowledge, not independently verified -- see README.",
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
        "source": "General knowledge, not independently verified -- see README.",
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
        "source": "General knowledge, not independently verified -- see README.",
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
        "source": "General knowledge, not independently verified -- see README.",
    },
    # -----------------------------------------------------------------
    # Tropical destinations, added to match the assignment's actual scope
    # (a travel agent for tropical vacation tours).
    # -----------------------------------------------------------------
    "jamaica": {
        "tipping_expected": True,
        "general_note": "Common in tourist areas, though many all-inclusive resorts (notably Sandals and Couples Resorts) prohibit tipping outright -- check the resort's policy first.",
        "by_service": {
            "restaurants": "10-15% of the bill unless a service charge is already included",
            "taxis": "around 10% of the fare",
            "hotel_housekeeping": "about $2 USD per bag for porters; a few dollars per day for housekeeping is appreciated",
            "tour_guides": "discretionary, based on service quality -- tip roughly as you would at home",
        },
        "haggling_expected": True,
        "haggling_note": "Haggling is common in craft markets and with street vendors; not in resorts or fixed-price stores.",
        "source": "Corroborated across multiple travel guides (Travel Noire, Yahoo Lifestyle, Resort Flock, Travel80) -- not a single named authority like the France entry.",
    },
    "dominican republic": {
        "tipping_expected": True,
        "general_note": "Culturally expected, especially at resorts; tipping norms are similar in practice to Mexico.",
        "by_service": {
            "restaurants": "10-15% of the bill",
            "taxis": "around 10% of the fare",
            "hotel_housekeeping": "$1-2 USD per bag for porters; a few dollars per day for housekeeping",
            "tour_guides": "around 10% of the tour cost, split with the driver if separate",
        },
        "haggling_expected": True,
        "haggling_note": "Haggling is common in markets and with street vendors; not in resorts or fixed-price stores.",
        "source": "Corroborated across multiple travel guides (Travel Noire, Resort Flock, WeGetToTravel) -- not a single named authority.",
    },
    "bahamas": {
        "tipping_expected": True,
        "general_note": "Many restaurants automatically add a 15% gratuity to the bill -- check before tipping extra.",
        "by_service": {
            "restaurants": "often a 15% gratuity is already included; add more only for exceptional service",
            "taxis": "10-15% of the fare",
            "hotel_housekeeping": "about $2 USD per bag for porters",
            "tour_guides": "discretionary, based on service quality",
        },
        "haggling_expected": True,
        "haggling_note": "Haggling is common in straw markets; not in resorts or fixed-price stores.",
        "source": "Corroborated across multiple travel guides (Yahoo Lifestyle Caribbean guide, WhereToStay Magazine) -- not a single named authority.",
    },
    "thailand": {
        "tipping_expected": True,
        "general_note": "Not mandatory, but small tips for good service are increasingly appreciated, especially in tourist areas.",
        "by_service": {
            "restaurants": "5-10% of the bill if not already included; not expected at street food stalls",
            "taxis": "not typically tipped; rounding up is common since small change can be scarce",
            "hotel_housekeeping": "20-50 baht for porters; a similar small amount for housekeeping",
            "tour_guides": "roughly $2-5 USD for drivers, $5-10 USD for guides, per excursion",
        },
        "haggling_expected": True,
        "haggling_note": "Haggling is expected in markets and with street vendors; not in malls or fixed-price stores.",
        "source": "Corroborated across multiple sources including Lonely Planet's tipping customs guide (a well-regarded travel authority), PhilStar Life, and TourCompass.",
    },
    "bali": {
        "tipping_expected": True,
        "general_note": "Not compulsory, but appreciated and increasingly expected in tourist areas, especially where a service charge isn't included.",
        "by_service": {
            "restaurants": "many restaurants add a 5-10% service charge; add a bit more for exceptional service if not",
            "taxis": "not mandatory; rounding up is common",
            "hotel_housekeeping": "roughly 50,000-100,000 IDR per stay, often pooled and shared among staff",
            "tour_guides": "roughly 50,000-100,000 IDR per day for guides and drivers",
        },
        "haggling_expected": True,
        "haggling_note": "Haggling is expected in local markets; not in malls, resorts, or fixed-price stores.",
        "source": "Corroborated across multiple sources (Agoda, Finns Beach Club, Inivie, The Wonder Space) -- not a single named authority.",
    },
    "philippines": {
        "tipping_expected": True,
        "general_note": "Appreciated though not always mandatory; tour guides and drivers commonly receive a combined tip.",
        "by_service": {
            "restaurants": "10% is a reasonable tip if service isn't already included",
            "taxis": "not typically expected; rounding up is common",
            "hotel_housekeeping": "a small daily amount is appreciated, similar to other Southeast Asian destinations",
            "tour_guides": "guide and driver together typically receive about 10% of the total tour cost",
        },
        "haggling_expected": True,
        "haggling_note": "Haggling is common in markets; not in malls or fixed-price stores.",
        "source": "Corroborated across Lonely Planet's Asia tipping guide and PhilStar Life.",
    },
    "costa rica": {
        "tipping_expected": True,
        "general_note": "By law, restaurant bills include a mandatory 10% service charge plus 13% tax; additional tipping is optional but increasingly expected in tourist areas.",
        "by_service": {
            "restaurants": "the 10% service charge is already included by law; an additional 5-10% for great service is appreciated",
            "taxis": "rounding up the fare is the norm",
            "hotel_housekeeping": "about $1-2 USD per bag for porters; $2 USD per day for housekeeping",
            "tour_guides": "roughly $10 per person for a half-day tour, $20 for a full-day tour",
        },
        "haggling_expected": False,
        "haggling_note": "Haggling is not a strong tradition in Costa Rica; prices in shops and tours are generally fixed.",
        "source": "Corroborated across multiple sources (Wise, Radical Storage, Costa Rica Guide, Editoire, Upgraded Points' worldwide tipping guide).",
    },
    "belize": {
        "tipping_expected": True,
        "general_note": "Not standardized, but commonplace, especially at upscale restaurants and hotels.",
        "by_service": {
            "restaurants": "many upscale restaurants and bars add a 10-15% service charge; leave more for exceptional service",
            "taxis": "not typically expected",
            "hotel_housekeeping": "many hotels add a 10% service charge at checkout",
            "tour_guides": "discretionary, based on service quality",
        },
        "haggling_expected": True,
        "haggling_note": "Haggling is common in local markets; not in fixed-price stores or resorts.",
        "source": "Upgraded Points' worldwide tipping guide -- a single source, weaker corroboration than most other entries.",
    },
    "fiji": {
        "tipping_expected": False,
        "general_note": "Uncommon and not expected; Fijian culture emphasizes communal sharing over individual reward. Some hotels use a shared 'staff fund' box instead.",
        "by_service": {
            "restaurants": "not expected; 10-15% is a generous gesture if there's no service charge and service was excellent",
            "taxis": "not expected",
            "hotel_housekeeping": "5-10 FJD per day is a generous, appreciated gesture, not an expectation",
            "tour_guides": "10-15% is appreciated for tours and spa services, but not required",
        },
        "haggling_expected": False,
        "haggling_note": "Haggling is not a common practice in Fiji; prices are generally treated as fixed.",
        "source": "Corroborated across multiple sources (Trip Masters, Fiji Travel Pro, Fiji Pocket Guide).",
    },
    "hawaii": {
        "tipping_expected": True,
        "general_note": "Tipping norms mirror the mainland USA; the higher cost of living means a 'good' tip elsewhere may be closer to the minimum expected in Hawaii.",
        "by_service": {
            "restaurants": "15-20% of the bill, same as the mainland US",
            "taxis": "10-20% of the fare",
            "hotel_housekeeping": "$1-5 USD per day; $1 USD per bag for bellhops",
            "tour_guides": "15-20% for private tours; around $5 per person for free/donation-based tours",
        },
        "haggling_expected": False,
        "haggling_note": "Haggling is not customary in Hawaii, same as the mainland US.",
        "source": "Corroborated across multiple sources (Waikiki Resort Hotel, Maui Tickets For Less, Vincent Vacations). Hawaii is a US state, not a separate country -- income context reuses the USA entry.",
    },
    "aruba": {
        "tipping_expected": True,
        "general_note": "Not legally required, but customary and generally expected across the tourist-facing service industry; always check the bill for an already-included service charge before adding more.",
        "by_service": {
            "restaurants": "15-20% if no service charge is included; many restaurants add a 10-15% service charge automatically",
            "taxis": "not required -- fares are government-set and posted at the airport; rounding up or a small tip for help with luggage is appreciated",
            "hotel_housekeeping": "$2-5 USD per day, left in the room daily rather than pooled at checkout",
            "tour_guides": "10-20% of the tour cost, or a similar cash tip for guides and drivers",
        },
        "haggling_expected": True,
        "haggling_note": "Accepted, even expected, at flea markets and with street vendors (e.g. Oranjestad's Local Market and Wharfside Market); considered impolite in Aruba's regular shops and malls.",
        "source": "Corroborated across multiple sources (Frommer's and TravelAge West for haggling norms; OneHappyIsland, FamilyDestinationsGuide, and GiveHowMuch for tipping norms) -- no single named authority like Lonely Planet or Rick Steves covers Aruba specifically.",
    },
    "barbados": {
        "tipping_expected": True,
        "general_note": "Not mandatory, but well established; many restaurants and hotels already add a 10-15% service charge, so always check the bill before tipping further.",
        "by_service": {
            "restaurants": "10-15% if no service charge is included; many restaurants add one automatically -- check the bill first",
            "taxis": "not required -- fares are typically agreed before the ride; rounding up or ~10% for good service is appreciated",
            "hotel_housekeeping": "BBD 2-5 (roughly USD 1-2.50) per day, left in the room",
            "tour_guides": "10-20% of the tour cost is customary for a private guide or driver",
        },
        "haggling_expected": False,
        "haggling_note": "Not a widely documented custom; most shopping happens in duty-free malls, department stores, and craft villages with posted prices rather than markets where bargaining is the norm.",
        "source": "Corroborated across multiple sources (Barbados.org, Barbados Revealed, Travel80, Tripadvisor community reports) for tipping; no source found describing haggling as a local custom, unlike several other entries in this data.",
    },
    "maldives": {
        "tipping_expected": True,
        "general_note": "Not obligatory, but appreciated; a roughly 10% service charge is added to nearly all resort bills by law, so extra tipping is discretionary rather than expected.",
        "by_service": {
            "restaurants": "service charge (~10%) is added almost everywhere; an extra 5-10% cash tip for great service is appreciated but not required",
            "taxis": "no land taxis on most islands -- travel is by boat or seaplane transfer; tipping the crew isn't expected but a small cash tip is welcomed",
            "hotel_housekeeping": "$1-5 USD per day, or $10-20 USD per week if tipping in one lump sum",
            "tour_guides": "around 10% of the tour cost, or roughly $10-20 USD for a full-day excursion",
        },
        "haggling_expected": True,
        "haggling_note": "Expected at local markets such as Male Local Market and Chaandhanee Magu, where reducing the asking price by 20-30% is common; not practiced in resort boutiques or fixed-price shops.",
        "source": "Corroborated across multiple sources (Wise, ExperienceTravelGroup, aMaldives) for tipping; multiple travel-guide sites (PickYourTrail, Acko, TravelTriangle) for haggling norms.",
    },
    "seychelles": {
        "tipping_expected": False,
        "general_note": "Not typically expected; restaurant and hotel bills usually already include a 5-10% service charge, and staff generally don't expect additional tips.",
        "by_service": {
            "restaurants": "not expected -- a 5-10% service charge is usually already included; an extra tip for exceptional service is appreciated, not required",
            "taxis": "fares generally include a service fee, so tipping isn't necessary; rounding up is a common courtesy",
            "hotel_housekeeping": "small discretionary tip, roughly SCR 10-12/day if desired",
            "tour_guides": "around $5 USD for a half-day tour, $10 USD for a full-day tour",
        },
        "haggling_expected": False,
        "haggling_note": "Sources conflict here: some describe Victoria's Sir Selwyn Selwyn-Clarke market as having little real bargaining, closer to fixed local prices; others describe haggling as routine. Treat this one with more caution than most entries in this data.",
        "source": "Corroborated across multiple sources (ExpertAfrica, TripMasters, SeyVillas) for tipping; haggling norms are contested between sources and not confidently resolved here.",
    },
    "vietnam": {
        "tipping_expected": True,
        "general_note": "Not a traditional local custom, but has grown quickly with tourism, especially in cities like Hanoi and Ho Chi Minh City; less expected in rural areas or small local eateries.",
        "by_service": {
            "restaurants": "5-10% at mid-range and upscale restaurants if no service charge is included; not expected at street food stalls or local pho shops",
            "taxis": "not expected for metered rides; rounding up to the nearest 10,000-20,000 VND is a common courtesy",
            "hotel_housekeeping": "20,000-50,000 VND (roughly $1-2 USD) per day, left in the room",
            "tour_guides": "one of the few categories where a tip is genuinely expected -- roughly 100,000-200,000 VND for a guide and 50,000-150,000 VND for a driver, per day",
        },
        "haggling_expected": True,
        "haggling_note": "Very common and expected in markets, street stalls, and with tailors -- opening counter-offers of 40-50% of the asking price are typical; not practiced in supermarkets, malls, or restaurants with posted prices.",
        "source": "Corroborated across multiple sources (Vietcetera, BestPrice Travel, Wise, VietnamSpot) for both tipping and haggling norms.",
    },
}


# ---------------------------------------------------------------------------
# Geographic context, used ONLY to give the semantic search corpus real
# location signal to match against (e.g. "south of the US border"). Not
# used anywhere else -- this is not a source of truth for any factual
# claim, just embedding context.
# ---------------------------------------------------------------------------
GEOGRAPHY = {
    # NOTE: only name a neighboring country if it is ALSO one of our 17
    # supported destinations. Naming an unsupported neighbor (e.g. writing
    # "east of Vietnam" for the Philippines, when Vietnam isn't in our
    # data) creates a false-positive semantic match -- someone asking
    # about that unsupported country would get matched here purely
    # because the literal name appears in this text, not because of any
    # genuine conceptual similarity. Found this exact bug during testing:
    # Philippines' old text named Vietnam, and a "Vietnam" query matched
    # Philippines with false confidence instead of correctly reporting
    # "not found."
    "france": "Located in Western Europe, bordering Germany (in our data) and several other European countries.",
    "india": "Located in South Asia, on the Indian subcontinent, in the eastern hemisphere.",
    "usa": "Located in North America, bordering Mexico (in our data) to the south.",
    "japan": "An island nation in East Asia, in the western Pacific.",
    "mexico": "Located in North America, directly south of the United States (in our data), also bordering Belize (in our data) to the south.",
    "morocco": "Located in North Africa, on the Mediterranean and Atlantic coasts.",
    "germany": "Located in Central Europe, bordering France (in our data) and several other European countries.",
    "jamaica": "A Caribbean island in the Greater Antilles.",
    "dominican republic": "A Caribbean nation sharing an island with another country, in the Greater Antilles.",
    "bahamas": "An archipelago in the Atlantic, near Florida in the southeastern United States (in our data).",
    "thailand": "In mainland Southeast Asia, near the Gulf of Thailand.",
    "bali": "An Indonesian island in Southeast Asia, part of the Indonesian archipelago.",
    "philippines": "An archipelago nation in Southeast Asia, in the western Pacific.",
    "costa rica": "In Central America, on the isthmus between North and South America.",
    "belize": "In Central America on the Caribbean coast, bordering Mexico (in our data).",
    "fiji": "An island nation in the South Pacific, in Melanesia.",
    "hawaii": "A US state (part of the USA, in our data), an island chain in the central Pacific Ocean.",
    # No neighboring country in this text: Aruba sits off Venezuela's coast
    # in the southern Caribbean, and Venezuela isn't one of our 17
    # countries -- naming it would create the same false-positive risk the
    # Vietnam/Philippines bug above already burned us on.
    "aruba": "A Dutch Caribbean island in the southern Caribbean Sea, just north of Venezuela, part of the ABC islands.",
    "barbados": "An island in the eastern Caribbean, in the Lesser Antilles, in the Atlantic just east of the main Caribbean island chain.",
    # Maldives really is close to India -- genuine proximity, not the
    # false-positive pattern the Vietnam/Philippines bug created.
    "maldives": "An archipelago nation in the Indian Ocean, southwest of India (in our data).",
    "seychelles": "An archipelago in the western Indian Ocean, off the coast of East Africa, northeast of Madagascar.",
    # Vietnam is the country whose ABSENCE caused the original geography
    # bug (see the note above the Philippines entry). It's added for real
    # now, so the old false-positive risk from naming it before it existed
    # in the corpus no longer applies -- but it still doesn't share a land
    # border with Thailand or the Philippines, so that's stated honestly
    # rather than overclaiming adjacency just because both are in our data.
    "vietnam": "In mainland Southeast Asia, on the eastern Indochina Peninsula along the South China Sea -- in the same broader region as Thailand and the Philippines (in our data), though it shares a land border with neither.",
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
                 "error": f"No money-customs data for '{country}' yet.",
                 "match_score": None, "adjusted": None}

    # match_score=None here means "exact dict key, no fuzzy/semantic step
    # involved" -- the same convention search_money_customs uses for its
    # own exact-match branch. Consumers (e.g. an Orchestrator) can treat
    # None as full confidence and any non-null number as "verify this."
    result = {"country": country.strip(), "found": True,
              "match_score": None, "adjusted": None, **facts}

    if service:
        service_key = service.strip().lower()
        note = facts["by_service"].get(service_key)
        if note is None:
            return {"country": country.strip(), "found": False,
                     "error": f"No data for service '{service}' in {country}. "
                              f"Available services: {list(facts['by_service'].keys())}",
                     "match_score": None, "adjusted": None}
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
# The CONFIDENCE CHECK: if even the best semantic match is a weak one (low
# cosine similarity), this does NOT silently guess -- it returns found=False
# and says plainly that no data is held for what was actually asked, naming
# the closest candidate only as context for why. (Earlier versions of this
# function always returned the closest match regardless of confidence,
# reasoning it should never "fail" the way a follow-up question would --
# but a wrong country's facts spread into the result is not a stated
# assumption the way a follow-up question is; it's fabricated content
# wearing the requested country's name. Found this the hard way: an early
# version answered a Rome query with Germany's tipping norms, silently.)

CONFIDENCE_THRESHOLD = 0.55  # below this cosine similarity, treat as "no match"

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
    # existing entries and leave a stale index in place forever. Includes
    # GEOGRAPHY so adding/editing location context also triggers a rebuild.
    fingerprint = hashlib.sha256(
        "\n".join(
            f"{key}|{facts['general_note']}|{facts['haggling_note']}|{GEOGRAPHY.get(key, '')}"
            for key, facts in entries
        ).encode("utf-8")
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
                    f"{_display_name(key)}. {GEOGRAPHY.get(key, '')} {facts['general_note']} "
                    f"{facts['haggling_note']} "
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
            "country": _display_name(matched_key),
            "found": True,
            "match_score": ratio,
            "adjusted": (
                f"Adjusted: interpreted '{country}' as {_display_name(matched_key)} "
                f"(likely a typo, {ratio} character-similarity match)."
            ),
            **facts,
        }
        if service:
            service_key = service.strip().lower()
            note = facts["by_service"].get(service_key)
            if note is None:
                result["adjusted"] += (
                    f" No specific data for service '{service}' in {_display_name(matched_key)}; "
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

    # CONFIDENCE CHECK: below the threshold, refuse rather than guess -- the
    # closest match is named only so an error is legible, never spread into
    # the result as if it were the requested country's own facts.
    if match_score < CONFIDENCE_THRESHOLD:
        return {
            "country": country.strip(),  # what was asked, not what matched
            "found": False,
            "match_score": match_score,
            "adjusted": None,
            "error": (f"No money-customs data held for '{country.strip()}'. The closest "
                      f"entry is {_display_name(best_id)} (similarity {match_score}), too "
                      f"weak to answer with. Say the information is unavailable."),
        }

    result = {
        "country": _display_name(best_id),
        "found": True,
        "match_score": match_score,
        "adjusted": None,
        **facts,
    }
    adjusted = None  # confident semantic match reaching here has nothing to disclose yet

    if service:
        service_key = service.strip().lower()
        note = facts["by_service"].get(service_key)
        if note is None:
            extra = f"No specific data for service '{service}' in {_display_name(best_id)}; showing general note instead."
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
                 "note": note, "match_score": None}

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
                 "error": f"World Bank lookup failed: {exc}", "note": note,
                 "match_score": None}
    except ValueError:
        return {"country": country.strip(), "gni_per_capita_usd": None,
                 "year": None, "found": False,
                 "error": "World Bank returned a response that was not valid JSON.",
                 "note": note, "match_score": None}

    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        return {"country": country.strip(), "gni_per_capita_usd": None,
                 "year": None, "found": False,
                 "error": f"World Bank returned no records for '{country}' ({iso3}).",
                 "note": note, "match_score": None}

    # Records are newest-first; take the first one with a non-null value.
    latest = next((r for r in payload[1] if r.get("value") is not None), None)
    if latest is None:
        return {"country": country.strip(), "gni_per_capita_usd": None,
                 "year": None, "found": False,
                 "error": f"World Bank had no non-null GNI per capita values for '{country}'.",
                 "note": note, "match_score": None}

    return {
        "country": country.strip(),
        "gni_per_capita_usd": round(latest["value"], 2),
        "year": latest.get("date"),
        "found": True,
        "error": None,
        "note": note,
        "match_score": None,
    }


# ---------------------------------------------------------------------------
# TOOL 4: Comparative context (home vs. destination)
# ---------------------------------------------------------------------------
# A traveller's OWN currency can sometimes imply their home country -- e.g.
# "USD" overwhelmingly means the traveller is from the USA. That inference
# is only safe when a currency maps to exactly ONE country. EUR is
# deliberately excluded: this same data covers both France and Germany, so
# guessing between them from "EUR" alone would be a real guess, not a
# reasonable assumption -- the honest move is to skip the comparison
# rather than pick one arbitrarily.

CURRENCY_TO_COUNTRY = {
    "usd": "usa",
    "jpy": "japan",
    "inr": "india",
    "mxn": "mexico",
    "mad": "morocco",
    # "eur" intentionally omitted -- ambiguous between France and Germany.
    "jmd": "jamaica",
    "dop": "dominican republic",
    "bsd": "bahamas",
    "thb": "thailand",
    "idr": "bali",
    "php": "philippines",
    "crc": "costa rica",
    "bzd": "belize",
    "fjd": "fiji",
    # Hawaii uses USD -- already covered by the "usd" mapping above.
    "awg": "aruba",
    "bbd": "barbados",
    "mvr": "maldives",
    "scr": "seychelles",
    "vnd": "vietnam",
}


def get_comparative_context(from_currency: str, destination_country: str) -> dict:
    """Compare customs and rough price scale between a traveller's likely
    home country (inferred from their currency, where unambiguous) and
    their destination -- e.g. "tipping is expected here, unlike at home."

    Args:
        from_currency: The traveller's own currency code, e.g. "USD".
        destination_country: Country name for the destination, e.g. "Japan".

    Returns:
        {
          "assumption": note explaining the inferred home country, or None
              if the currency doesn't map to exactly one country (e.g. EUR)
              -- in that case home_* fields are all None, and only the
              destination fields are populated.
          "home_country", "home_customs", "home_income_context": as above
          "destination_country", "destination_customs", "destination_income_context"
        }
    """
    home_key = CURRENCY_TO_COUNTRY.get(from_currency.strip().lower())

    assumption = None
    home_country = None
    home_customs = None
    home_income = None

    if home_key:
        home_country = _display_name(home_key)
        assumption = (
            f"Assumption: inferred home country as {home_country} based on "
            f"currency '{from_currency.strip().upper()}'."
        )
        home_customs = get_money_customs(home_key)
        home_income = get_income_context(home_key)
    # else: currency doesn't map to exactly one country (e.g. EUR) --
    # deliberately skip the home-side comparison rather than guess.

    destination_customs = search_money_customs(destination_country)
    destination_income = get_income_context(destination_country)

    # If the destination side wasn't found, a populated home side sitting
    # next to it is not "a comparison with one side missing" -- the model
    # has no destination facts to compare against, so nothing here should
    # look like a comparison at all. Drop the home side too rather than
    # let the LLM reach for the only populated facts in the payload and
    # attribute them to the destination by association. Caught this the
    # hard way: an early version answered a low-confidence Italy query by
    # copying the USA's haggling_note verbatim as Italy's.
    if not destination_customs.get("found"):
        assumption = None
        home_country = None
        home_customs = None
        home_income = None

    return {
        "assumption": assumption,
        "home_country": home_country,
        "home_customs": home_customs,
        "home_income_context": home_income,
        "destination_country": destination_country.strip(),
        "destination_customs": destination_customs,
        "destination_income_context": destination_income,
    }


# ---------------------------------------------------------------------------
# Quick manual test -- run this file directly, no agent or LLM required.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(get_exchange_rate("USD", "EUR"))
    print(get_money_customs("France"))
    print(get_money_customs("India", service="taxis"))
    print(get_income_context("Mexico"))
    print(get_comparative_context("USD", "Japan"))
    print(get_comparative_context("EUR", "India"))  # EUR: no home comparison expected
