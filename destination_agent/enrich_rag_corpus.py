import json
from pathlib import Path

from destination_agent.geoapify_data import (
    get_or_build_destination_profile,
    profile_to_rag_text,
)


CORPUS_FILE = Path("destination_data/destinations.json")


def enrich_corpus():
    """
    Enrich the shared Destination RAG corpus
    with Geoapify travel features.
    """

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

    # TEST ONLY:
    # Process all destinations.
    enriched_count = 0
    failed_destinations = []
    for destination in destinations:

        name = destination.get("name")
        latitude = destination.get("lat")
        longitude = destination.get("lon")

        if not name:
            continue

        print(f"\nProcessing {name}...")

        name = destination.get("name")
        latitude = destination.get("lat")
        longitude = destination.get("lon")

        if not name:
            continue

        print(f"\nProcessing {name}...")

        # Use the coordinates already stored
        # in the shared corpus.
        profile = get_or_build_destination_profile(
            name,
            latitude=latitude,
            longitude=longitude
        )

        # Keep the original destination even if
        # Geoapify enrichment is unavailable.
        if not profile:
            print(
                f"No Geoapify enrichment for {name}."
            )
            failed_destinations.append(name)
            continue

        geoapify_text = profile_to_rag_text(
            profile
        )

        if not geoapify_text:
            continue

        # Keep the structured Geoapify data.
        destination["geoapify_profile"] = profile

        # Preserve the teammate's original description.
        original_description = destination.get(
            "description",
            ""
        )

        # Build enriched text for RAG embedding.
        destination["rag_text"] = (
            original_description
            + " "
            + geoapify_text
        ).strip()

        print(
            f"Enriched {name} successfully."
        )
        enriched_count += 1

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

    print("\nCorpus enrichment complete.")
    print(f"Enriched: {enriched_count}")
    print(f"Failed: {len(failed_destinations)}")

    if failed_destinations:
        print(
            "Failed destinations: "
            + ", ".join(failed_destinations)
        )


if __name__ == "__main__":
    enrich_corpus()