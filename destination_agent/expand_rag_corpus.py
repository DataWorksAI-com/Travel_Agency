import json
from pathlib import Path

from destination_data.resolve_place import resolve_place
from destination_agent.geoapify_data import (
    get_or_build_destination_profile,
    profile_to_rag_text,
)

# PROTOTYPE (Fix #1): reuse the seed-corpus field logic instead of duplicating
# it, so a dynamically added destination is described from the same fetched
# fields as a seed city. destination_data/ is a sibling namespace package,
# imported exactly the way resolve_place is above.
try:
    from destination_data.build_corpus import (
        annual_mean_temp,
        build_description,
        geocode,
        is_coastal,
    )

    STRUCTURED_FIELDS_AVAILABLE = True
except ImportError as import_error:
    print(
        f"Structured field enrichment unavailable ({import_error}); "
        f"dynamic entries will fall back to minimal descriptions."
    )
    STRUCTURED_FIELDS_AVAILABLE = False


# Anchor the corpus path to this file's location, not the working directory.
# destination_agent/ and destination_data/ are siblings under the repo root, so
# parents[1] is the repo root. The previous relative path only resolved when the
# script happened to be run from the repo root.
REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_FILE = REPO_ROOT / "destination_data" / "destinations.json"


def _fetch_structured_fields(
        name: str,
        country_code: str,
        latitude: float,
        longitude: float
    ):
    """Fetch the same structured fields build_corpus.py attaches to seed cities.

    Returns (description, source_fields). Both are None when the fields could
    not be fetched - the caller then keeps the previous minimal entry rather
    than inventing values. Never raises.

    Sources are the same free, keyless APIs the seed corpus uses:
      - Open-Meteo Geocoding : population, admin1, country, timezone, elevation
      - Open-Meteo Marine    : coastal / inland
      - Open-Meteo Archive   : annual mean temperature (ERA5)
    """

    if not STRUCTURED_FIELDS_AVAILABLE:
        return None, None

    try:
        record = geocode(name, country_code)
    except Exception as exc:
        print(
            f"Structured geocoder lookup failed for {name} ({exc})."
        )
        return None, None

    if not record:
        print(
            f"No structured geocoder record for {name}; "
            f"keeping the minimal description."
        )
        return None, None

    try:
        coastal = is_coastal(latitude, longitude)
        avg_temp = annual_mean_temp(latitude, longitude)
        description = build_description(record, coastal, avg_temp)
    except Exception as exc:
        print(
            f"Structured enrichment failed for {name} ({exc})."
        )
        return None, None

    # dynamic/source are kept: these entries are still runtime-added. The rest
    # mirrors the seed-entry shape so both kinds are field-complete.
    source_fields = {
        "dynamic": True,
        "source": "Geoapify + resolve_place",
        "country": record.get("country"),
        "admin1": record.get("admin1"),
        "population": record.get("population"),
        "timezone": record.get("timezone"),
        "elevation": record.get("elevation"),
        "coastal": coastal,
        "annual_avg_temp_c": avg_temp,
    }

    return description, source_fields


def add_destination_to_shared_corpus(
        destination_name: str,
        place: dict = None,
        profile: dict = None
    ):
    """
    Add a new destination to the shared Destination RAG corpus.

    The destination is added only when:
    - it can be resolved successfully
    - valid coordinates and country code are available
    - a Geoapify travel profile can be built
    - it does not already exist in the corpus
    """

    # STEP 1: LOAD CURRENT CORPUS

    with open(
        CORPUS_FILE,
        "r",
        encoding="utf-8"
    ) as file:
        data = json.load(file)

    destinations = data.get(
        "destinations",
        []
    )

    # STEP 2: CHECK WHETHER IT ALREADY EXISTS

    for destination in destinations:

        if (
            destination.get("name", "").lower()
            == destination_name.strip().lower()
        ):
            print(
                f"{destination_name} already exists "
                f"in the shared corpus."
            )

            return destination

    # STEP 3: RESOLVE THE DESTINATION

    # Resolve only if existing place data was not provided.
    if place is None:

        place = resolve_place(
            destination_name
        )

    if (
        isinstance(place, dict)
        and "error" in place
    ):
        print(
            f"Could not resolve {destination_name}: "
            f"{place['error']}"
        )

        return None

    name = place["name"]
    country_code = place["country_code"]
    latitude = place["lat"]
    longitude = place["lon"]

    # STEP 4: BUILD GEOAPIFY PROFILE

    # Build the Geoapify profile only if an existing
    # profile was not already provided by the Agent.
    if profile is None:

        profile = get_or_build_destination_profile(
            name,
            latitude=latitude,
            longitude=longitude,
            country_code=country_code
        )

    if not profile:
        print(
            f"Could not build a Geoapify profile "
            f"for {name}."
        )

        return None

    # STEP 5: FETCH STRUCTURED FIELDS (same logic as the seed corpus)

    structured_description, structured_source_fields = _fetch_structured_fields(
        name,
        country_code,
        latitude,
        longitude
    )

    # STEP 6: BUILD RAG TEXT

    geoapify_text = profile_to_rag_text(
        profile
    )

    if not geoapify_text:
        print(
            f"No usable travel information "
            f"was available for {name}."
        )

        return None

    # Prefer the structured description so the entry carries climate, region,
    # population and coastal signal. Fall back to the minimal sentence when the
    # structured lookup returned nothing - never invent the missing values.
    description = (
        structured_description
        or f"{name} is a travel destination."
    )

    # Same composition enrich_rag_corpus.py uses for seed entries:
    # description first, Geoapify travel detail appended.
    rag_text = (
        description
        + " "
        + geoapify_text
    ).strip()

    source_fields = structured_source_fields or {
        "dynamic": True,
        "source": "Geoapify + resolve_place"
    }

    # STEP 7: CREATE CORPUS ENTRY

    new_destination = {
        "name": name,
        "country_code": country_code,
        "lat": latitude,
        "lon": longitude,
        "description": description,
        "geoapify_profile": profile,
        "rag_text": rag_text,
        "_source_fields": source_fields,
    }

    # STEP 8: SAVE TO SHARED CORPUS

    destinations.append(
        new_destination
    )

    data["destinations"] = destinations

    with open(
        CORPUS_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False
        )

    print(
        f"Added {name} to the shared RAG corpus."
    )

    return new_destination


if __name__ == "__main__":
    result = add_destination_to_shared_corpus(
        "Aruba"
    )

    print("\nRESULT:\n")
    print(result)