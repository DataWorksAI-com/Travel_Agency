"""Read airport transport facts without guessing missing information.

Each verified option must include mode, route, destination, price, currency,
duration_minutes, operating_hours, source_url and verified_on. Unknown prices
and durations should be null, never zero. This module does not calculate
arrival-time feasibility or offer live routing.
"""

import json
from datetime import date
from pathlib import Path

CORPUS_PATH = Path(__file__).with_name("transport.json")


def get_airport_transport(airport_code: str) -> dict:
    """Look up verified airport-to-city transport options by IATA airport code.

    City codes such as PAR are not airport codes. Empty records mean transport
    information has not been collected, not that transport does not exist.
    """
    if not isinstance(airport_code, str):
        return {"status": "error", "error": "Provide a three-letter airport code."}
    code = airport_code.strip().upper()
    if len(code) != 3 or not code.isascii() or not code.isalpha():
        return {"status": "error", "error": "Provide a three-letter airport code."}

    try:
        corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
        airports = corpus["airports"]
        if not isinstance(airports, dict):
            raise ValueError("Invalid airports mapping")
        record = airports.get(code)
        if record is not None and (
            not isinstance(record, dict) or not isinstance(record.get("options"), list)
        ):
            raise ValueError("Invalid airport record")
        for option in record.get("options", []) if record else []:
            required = {
                "mode", "route", "destination", "price", "currency",
                "duration_minutes", "operating_hours", "source_url", "verified_on",
            }
            if not isinstance(option, dict) or not required.issubset(option):
                raise ValueError("Incomplete transport option")
            if not isinstance(option["source_url"], str) or not option["source_url"].startswith("https://"):
                raise ValueError("Transport source is missing")
            date.fromisoformat(option["verified_on"])
            for field in ("price", "duration_minutes"):
                value = option[field]
                if value is not None and (
                    isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
                ):
                    raise ValueError("Invalid transport cost or duration")
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "error", "error": "Airport transport corpus could not be read."}

    if record is None:
        return {
            "status": "not_found",
            "airport_code": code,
            "options": [],
            "note": "This airport is not covered by the local transport corpus.",
        }

    result = {"airport_code": code, **record}
    if not record["options"]:
        return {
            "status": "not_found",
            **result,
            "note": "Transport details have not yet been verified. Do not infer routes, fares or service hours.",
        }
    return {
        "status": "ok",
        **result,
        "note": "Reference information from cited sources, not live availability. Check each option's verification date.",
    }
