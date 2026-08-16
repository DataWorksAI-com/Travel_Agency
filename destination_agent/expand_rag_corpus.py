import json
from pathlib import Path

from destination_data.resolve_place import resolve_place
from destination_agent.geoapify_data import (
    get_or_build_destination_profile,
    profile_to_rag_text,
)


CORPUS_FILE = Path("destination_data/destinations.json")


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

    # STEP 5: BUILD RAG TEXT

    geoapify_text = profile_to_rag_text(
        profile
    )

    if not geoapify_text:
        print(
            f"No usable travel information "
            f"was available for {name}."
        )

        return None

    # For dynamically added destinations,
    # the Geoapify profile is currently the main
    # travel-oriented knowledge source.
    rag_text = (
        f"{name} is a travel destination. "
        + geoapify_text
    )

    # STEP 6: CREATE CORPUS ENTRY

    new_destination = {
        "name": name,
        "country_code": country_code,
        "lat": latitude,
        "lon": longitude,
        "description": (
            f"{name} is a travel destination."
        ),
        "geoapify_profile": profile,
        "rag_text": rag_text,
        "_source_fields": {
            "dynamic": True,
            "source": "Geoapify + resolve_place"
        }
    }

    # STEP 7: SAVE TO SHARED CORPUS

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