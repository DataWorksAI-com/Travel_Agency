"""Corpus builder for the Destination Agent data layer.

Run this once to (re)generate destinations.json. It is deliberately a separate
script from the tools so the corpus can be rebuilt without touching them.

WHAT IS CURATED VS WHAT IS FETCHED
  Curated : the LIST of city names below (which places count as "well-known
            travel destinations" is a judgement call, not a fact in any API).
  Fetched : every FIELD attached to them. Nothing below is written from model
            knowledge - if a lookup fails, the clause is omitted, never guessed.

Sources (all free, keyless):
  - Open-Meteo Geocoding  https://geocoding-api.open-meteo.com/v1/search
        -> real name, country_code, latitude, longitude, population,
           admin1 (region), timezone (used for continent)
  - Open-Meteo Marine     https://marine-api.open-meteo.com/v1/marine
        -> coastal test: the marine grid only covers sea points, so a null
           wave height means the coordinate is not on open water
  - Open-Meteo Archive    https://archive-api.open-meteo.com/v1/archive
        -> annual mean temperature over the last 5 complete years (ERA5)

Usage:
    python build_corpus.py
"""

# truststore MUST be injected before requests is imported, or HTTPS calls on
# this network hang ~5 minutes behind the intercepting proxy certificate.
import truststore

truststore.inject_into_ssl()

import datetime
import json
import os
import time

import requests

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "destinations.json")
TIMEOUT_SECONDS = 60
YEARS_OF_HISTORY = 5
POLITE_DELAY_SECONDS = 0.3

# --- population size bands (largest first) --------------------------------
POPULATION_BANDS = [
    (5_000_000, "major city"),
    (1_000_000, "large city"),
    (250_000, "mid-sized city"),
    (50_000, "small city"),
    (0, "town"),
]

# --- annual mean temperature bands (warmest first) ------------------------
TEMPERATURE_BANDS = [
    (24.0, "a hot tropical climate, warm all year round"),
    (18.0, "a warm climate"),
    (10.0, "a mild temperate climate"),
    (-100.0, "a cool climate"),
]

# IANA timezone prefixes are mostly continents, but a few are oceans. This only
# rewords the prefix the API gave us - it does not reassign anywhere to a
# continent the data did not state.
TIMEZONE_REGION_LABELS = {
    "America": "the Americas",
    "Atlantic": "the North Atlantic region",
    "Indian": "the Indian Ocean region",
    "Pacific": "the Pacific region",
}

# Curated seed list: (city name, expected ISO country code).
# The country code disambiguates the geocoder (Paris FR, not Paris TX).
# Tokyo is deliberately absent - it is the "not in the corpus" test case.
CITY_SEEDS = [
    # Europe
    ("Paris", "FR"), ("Barcelona", "ES"), ("Rome", "IT"), ("Lisbon", "PT"),
    ("Amsterdam", "NL"), ("Prague", "CZ"), ("Vienna", "AT"), ("Athens", "GR"),
    ("Dubrovnik", "HR"), ("Reykjavik", "IS"), ("Edinburgh", "GB"), ("Copenhagen", "DK"),
    ("Venice", "IT"), ("Nice", "FR"),
    # Asia
    ("Bangkok", "TH"), ("Phuket", "TH"), ("Chiang Mai", "TH"), ("Kyoto", "JP"),
    ("Singapore", "SG"), ("Denpasar", "ID"), ("Hanoi", "VN"), ("Seoul", "KR"),
    ("Hong Kong", "HK"), ("Colombo", "LK"), ("Kathmandu", "NP"), ("Dubai", "AE"),
    ("Jaipur", "IN"), ("Malé", "MV"),
    # Oceania
    ("Sydney", "AU"), ("Auckland", "NZ"), ("Queenstown", "NZ"),
    # Africa
    ("Cape Town", "ZA"), ("Marrakesh", "MA"), ("Cairo", "EG"), ("Nairobi", "KE"),
    ("Zanzibar", "TZ"),
    # Americas
    ("Rio de Janeiro", "BR"), ("Buenos Aires", "AR"), ("Cusco", "PE"),
    ("Cartagena", "CO"), ("Mexico City", "MX"), ("Cancún", "MX"),
    ("Havana", "CU"), ("Vancouver", "CA"), ("San Francisco", "US"),
    ("New Orleans", "US"), ("Honolulu", "US"),
]


def _band(value, bands):
    """Return the label of the first band whose threshold the value clears."""
    for threshold, label in bands:
        if value >= threshold:
            return label
    return bands[-1][1]


def geocode(name, expected_country_code):
    """Look up one seed city. Returns the raw record, or None if not resolvable."""
    try:
        response = requests.get(
            GEOCODING_URL,
            params={"name": name, "count": 20, "language": "en", "format": "json"},
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            print(f"  ! {name}: geocoding HTTP {response.status_code}")
            return None
        results = response.json().get("results")
    except (requests.exceptions.RequestException, ValueError) as exc:
        print(f"  ! {name}: geocoding failed ({exc})")
        return None

    if not results:
        print(f"  ! {name}: no geocoding results")
        return None

    # Only accept a record from the expected country, so we never silently
    # attach the wrong city's coordinates to a famous name.
    in_country = [r for r in results if r.get("country_code") == expected_country_code]
    if not in_country:
        print(f"  ! {name}: no result in country {expected_country_code}")
        return None

    # Prefer an exact name match, or "Vancouver" resolves to the more populous
    # "Vancouver Island" - a different place, in the middle of a landmass.
    lowered = name.casefold()
    exact = [r for r in in_country if isinstance(r.get("name"), str) and r["name"].casefold() == lowered]
    pool = exact or in_country
    return max(pool, key=lambda r: r.get("population") or 0)


def is_coastal(lat, lon):
    """True/False from the marine grid, or None if the check could not run.

    The marine model only has data over water, so a null wave height at the
    city's own coordinate means it is not sitting on open sea.
    """
    try:
        response = requests.get(
            MARINE_URL,
            params={"latitude": lat, "longitude": lon, "daily": "wave_height_max", "forecast_days": 1},
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            return None
        values = response.json().get("daily", {}).get("wave_height_max")
    except (requests.exceptions.RequestException, ValueError, AttributeError):
        return None

    if not isinstance(values, list) or not values:
        return None
    return values[0] is not None


def annual_mean_temp(lat, lon):
    """Mean daily temperature over the last N complete years, or None."""
    last_complete_year = datetime.date.today().year - 1
    first_year = last_complete_year - YEARS_OF_HISTORY + 1

    try:
        response = requests.get(
            ARCHIVE_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": f"{first_year}-01-01",
                "end_date": f"{last_complete_year}-12-31",
                "daily": "temperature_2m_mean",
                "timezone": "UTC",
            },
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            return None
        temps = response.json().get("daily", {}).get("temperature_2m_mean")
    except (requests.exceptions.RequestException, ValueError, AttributeError):
        return None

    if not isinstance(temps, list):
        return None
    usable = [t for t in temps if t is not None]
    if not usable:
        return None
    return round(sum(usable) / len(usable), 1)


def build_description(record, coastal, avg_temp):
    """Compose a description string purely from fetched structured fields."""
    name = record["name"]
    country = record.get("country") or record.get("country_code")
    population = record.get("population")
    admin1 = record.get("admin1")
    timezone = record.get("timezone") or ""
    # IANA timezones are "Continent/City", so the prefix is the continent.
    continent = None
    if "/" in timezone:
        prefix = timezone.split("/")[0].replace("_", " ")
        continent = TIMEZONE_REGION_LABELS.get(prefix, prefix)

    if population:
        size = _band(population, POPULATION_BANDS)
    else:
        size = "destination"

    if coastal is True:
        size = f"coastal {size}"
    elif coastal is False:
        size = f"inland {size}"

    article = "an" if size[0].lower() in "aeiou" else "a"
    sentence = f"{name} is {article} {size}"
    if population:
        sentence += f" (population {population:,})"
    where = ", ".join(part for part in (admin1, country) if part)
    if where:
        sentence += f" in {where}"
    if continent:
        sentence += f", in {continent}"
    sentence += "."

    parts = [sentence]
    if avg_temp is not None:
        parts.append(
            f"Typical annual average temperature is {avg_temp}°C, {_band(avg_temp, TEMPERATURE_BANDS)}."
        )
    if coastal is True:
        parts.append("It sits on the sea, with beaches and coastal scenery.")
    elif coastal is False:
        parts.append("It is inland, away from the coast.")

    return " ".join(parts)


def main():
    print(f"Building corpus from {len(CITY_SEEDS)} seed destinations...\n")
    entries = []

    for name, country_code in CITY_SEEDS:
        record = geocode(name, country_code)
        time.sleep(POLITE_DELAY_SECONDS)
        if record is None:
            continue

        lat = record.get("latitude")
        lon = record.get("longitude")
        if lat is None or lon is None:
            print(f"  ! {name}: record had no coordinates")
            continue

        coastal = is_coastal(lat, lon)
        time.sleep(POLITE_DELAY_SECONDS)
        avg_temp = annual_mean_temp(lat, lon)
        time.sleep(POLITE_DELAY_SECONDS)

        entry = {
            "name": record.get("name"),
            "country_code": record.get("country_code"),
            "lat": lat,
            "lon": lon,
            "description": build_description(record, coastal, avg_temp),
            # Provenance for the fields the description was composed from.
            "_source_fields": {
                "country": record.get("country"),
                "admin1": record.get("admin1"),
                "population": record.get("population"),
                "timezone": record.get("timezone"),
                "elevation": record.get("elevation"),
                "coastal": coastal,
                "annual_avg_temp_c": avg_temp,
            },
        }
        entries.append(entry)
        print(f"  + {entry['name']} ({entry['country_code']})")

    payload = {
        "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "sources": [
            "Open-Meteo Geocoding API (GeoNames-derived)",
            "Open-Meteo Marine API (coastal test)",
            "Open-Meteo Historical Weather API / ERA5 archive (annual mean temperature)",
        ],
        "note": (
            "The list of city names is hand-picked; every field attached to them "
            "is fetched from the sources above. Missing lookups are omitted, never guessed."
        ),
        "destinations": entries,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    print(f"\nWrote {len(entries)} destinations to {OUTPUT_PATH}")
    skipped = len(CITY_SEEDS) - len(entries)
    if skipped:
        print(f"({skipped} seed(s) skipped - see '!' lines above)")


if __name__ == "__main__":
    main()
