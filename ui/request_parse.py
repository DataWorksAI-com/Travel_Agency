"""
ui/request_parse.py -- turn one chat line into plan_trip()'s four arguments.

plan_trip (orchestrator.py:146-151) does not take free text alone. It takes
`task` plus `origin_country`, `destination_country` and `stated_budget` as
separate strings, and it only calls Money & Customs when BOTH countries are
non-empty (orchestrator.py:158). A chat box gives one line, so something has
to split it. That something belongs here, in the UI, not in the orchestrator.

This is deliberately dumb and deterministic -- no model, no network. It is
scaffolding for the orchestrator's current signature, and the honest place
for it is a visible step in the UI showing exactly what it extracted, so a
bad parse looks like a bad parse instead of a bad answer.

Known limit, not a bug in this file: plan_trip has no origin-CITY parameter
at all (measured as GAP 2 by sandbox/run_pipeline.py:97-101), so "from
Boston" can only be reduced to a country here. Nothing downstream can see
the city.
"""

from __future__ import annotations

import re
import unicodedata

# Only enough cities to resolve the ones a demo actually types. Anything not
# listed falls through to being treated as a country name, which is right
# far more often than not for this project's Caribbean destinations.
CITY_COUNTRY = {
    "boston": "USA",
    "new york": "USA",
    "nyc": "USA",
    "chicago": "USA",
    "los angeles": "USA",
    "san francisco": "USA",
    "miami": "USA",
    "seattle": "USA",
    "atlanta": "USA",
    "toronto": "Canada",
    "vancouver": "Canada",
    "london": "UK",
    "bridgetown": "Barbados",
    "oranjestad": "Aruba",
    "kingston": "Jamaica",
    "nassau": "Bahamas, The",
    "montego bay": "Jamaica",
    "cancun": "Mexico",
    "lisbon": "Portugal",
    "tokyo": "Japan",
    "paris": "France",
}

# A place name runs until punctuation or the next clause keyword.
_PLACE = (
    # A-Za-z alone cannot match an accented place name. On "a week in Cancun
    # [with the accent] from Boston in September", the first "in" matched as far
    # as "Canc", the lookahead failed on the accent, and the engine went on to
    # match the SECOND "in" -- reporting the destination country as "September".
    r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .'\-]{1,34}?)"
    r"(?=\s*(?:,|\.|;|$|\bfrom\b|\bfor\b|\bwith\b|\bbudget\b|\bon\b|\bunder\b"
    r"|\bbelow\b|\bwho\b|\bthat\b|\band\b|\bin\b|\bnext\b|\bduring\b))"
)

_DESTINATION_RE = re.compile(r"\b(?:to|in|visit(?:ing)?|towards?)\s+" + _PLACE, re.I)
_ORIGIN_RE = re.compile(r"\b(?:from|departing|leaving)\s+" + _PLACE, re.I)

# Same two patterns evaluation/direct_path.py:74-78 uses, so the UI and
# Budget's own parser agree on what "the budget" is.
_BUDGET_LABELLED_RE = re.compile(
    r"(?:budget|under|below|max(?:imum)?)\D{0,12}(\d[\d,]*)", re.I
)
_BUDGET_DOLLAR_RE = re.compile(r"\$\s?(\d[\d,]*)")


def _to_country(place: str | None) -> str:
    if not place:
        return ""
    cleaned = " ".join(place.split()).strip(" .,'-")
    if not cleaned:
        return ""
    # Accent-folded, so the accented and unaccented spellings of a city both
    # resolve. Without this "Cancun" mapped to Mexico but "Cancún" fell
    # through and was treated as if it were a country name.
    folded = "".join(
        c for c in unicodedata.normalize("NFKD", cleaned.lower())
        if not unicodedata.combining(c)
    )
    return CITY_COUNTRY.get(folded, cleaned)


def parse_request(text: str) -> dict:
    """Return the kwargs for plan_trip, plus the raw places for display."""
    task = (text or "").strip()

    dest_match = _DESTINATION_RE.search(task)
    origin_match = _ORIGIN_RE.search(task)

    destination_place = dest_match.group(1) if dest_match else None
    origin_place = origin_match.group(1) if origin_match else None

    budget_match = _BUDGET_LABELLED_RE.search(task) or _BUDGET_DOLLAR_RE.search(task)
    stated_budget = f"${budget_match.group(1).replace(',', '')}" if budget_match else ""

    return {
        "task": task,
        "origin_country": _to_country(origin_place),
        "destination_country": _to_country(destination_place),
        "stated_budget": stated_budget,
        "_origin_place": (origin_place or "").strip(),
        "_destination_place": (destination_place or "").strip(),
    }


def describe(parsed: dict) -> str:
    """A short markdown block for the UI's 'what I read' step."""
    def shown(value, fallback="_not detected_"):
        return value if value else fallback

    return (
        f"- **Destination country**: {shown(parsed['destination_country'])}\n"
        f"- **Origin country**: {shown(parsed['origin_country'])}\n"
        f"- **Stated budget**: {shown(parsed['stated_budget'])}\n"
    )
