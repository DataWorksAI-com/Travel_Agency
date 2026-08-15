"""Public holidays tool for the Destination Agent data layer.

Source: Nager.Date v3 (free, keyless)
    https://date.nager.at/api/v3/PublicHolidays/{year}/{countryCode}

Contract:
  - returns plain Python lists/dicts, never JSON strings
  - never raises: every failure path returns {"error": "..."}
  - returns only what the source provides; nothing is filled in from model knowledge
"""

# truststore MUST be injected before requests is imported, or HTTPS calls on
# this network hang ~5 minutes behind the intercepting proxy certificate.
import truststore

truststore.inject_into_ssl()

import datetime

import requests

API_URL = "https://date.nager.at/api/v3/PublicHolidays/{year}/{country_code}"
TIMEOUT_SECONDS = 20


def get_holidays(country_code, year=None):
    """Return public holidays for a country in a given year.

    Args:
        country_code: 2-letter ISO country code, e.g. "FR".
        year: 4-digit year. Defaults to the current year.

    Returns:
        On success, a list of {"date", "name", "local_name"} dicts.
        On any failure, a dict {"error": "..."}.
    """
    if not isinstance(country_code, str):
        return {"error": f"country_code must be a 2-letter string, got {type(country_code).__name__}"}

    code = country_code.strip().upper()
    if len(code) != 2 or not code.isalpha():
        return {"error": f"Invalid country code {country_code!r}: expected 2 letters, e.g. 'FR'"}

    if year is None:
        year = datetime.date.today().year
    try:
        year = int(year)
    except (TypeError, ValueError):
        return {"error": f"Invalid year {year!r}: expected a 4-digit year, e.g. 2026"}
    if not 1900 <= year <= 2100:
        return {"error": f"Year {year} is out of the supported range (1900-2100)"}

    url = API_URL.format(year=year, country_code=code)

    try:
        response = requests.get(url, timeout=TIMEOUT_SECONDS)
    except requests.exceptions.Timeout:
        return {"error": f"Holiday data unavailable: request to Nager.Date timed out after {TIMEOUT_SECONDS}s"}
    except requests.exceptions.RequestException as exc:
        return {"error": f"Holiday data unavailable: network error contacting Nager.Date ({exc})"}

    if response.status_code == 404:
        return {"error": f"No holiday data for country code {code!r} in {year} (Nager.Date returned 404)"}
    if response.status_code == 204 or not response.content:
        # Nager.Date answers 204 with an empty body for country codes it does
        # not cover (e.g. TH), and for covered countries outside its year range.
        return {"error": f"Nager.Date has no holiday coverage for country code {code!r} ({year})"}
    if response.status_code != 200:
        return {"error": f"Holiday data unavailable: Nager.Date returned HTTP {response.status_code}"}

    try:
        payload = response.json()
    except ValueError:
        return {"error": "Holiday data unavailable: Nager.Date returned a response that was not valid JSON"}

    if not isinstance(payload, list):
        return {"error": f"Holiday data unavailable: expected a JSON array from Nager.Date, got {type(payload).__name__}"}

    holidays = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        holidays.append(
            {
                "date": item.get("date"),
                "name": item.get("name"),
                "local_name": item.get("localName"),
            }
        )

    if not holidays:
        return {"error": f"No holidays reported for {code} in {year}"}

    return holidays


if __name__ == "__main__":
    for test_code in ("FR", "TH", "ZZ"):
        result = get_holidays(test_code)
        print(f"--- {test_code} ---")
        if isinstance(result, dict):
            print(result)
        else:
            print(f"{len(result)} holidays")
            for holiday in result[:5]:
                print(f"  {holiday['date']}  {holiday['name']}  ({holiday['local_name']})")
