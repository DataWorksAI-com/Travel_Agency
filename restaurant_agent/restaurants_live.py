# =============================================================================
# ALY 6980 CAPSTONE - RESTAURANT AGENT
# Live data source: real restaurants from OpenStreetMap, via the Overpass API.
#
# Vrushti Shah, Northeastern University, August 2026
#
# WHY THIS FILE EXISTS
# --------------------
# The agent has been built on 28 hand-written records shaped like a real
# provider's response. That was deliberate: a mock that never rate-limits, never
# changes between runs, and cannot fail during a demo. But "one function body
# away from live" is a claim, and an untested claim is worth nothing.
#
# This file makes the claim true. It calls a real, public, key-free API and
# returns records in EXACTLY the shape restaurants_data.RESTAURANTS uses, so the
# retrieval engine, the filters and the reflection step all work on live data
# with no changes anywhere else.
#
# WHY OPENSTREETMAP AND NOT GOOGLE PLACES
# ---------------------------------------
# Overpass needs no API key, no billing account and no sign-up, so it can be run
# and verified by anyone marking this work. It is also the only free source that
# carries DIETARY tags natively - OpenStreetMap has diet:vegan, diet:vegetarian
# and diet:gluten_free as first-class fields, which is precisely what this agent
# filters on.
#
# THE HONEST LIMITATION, MEASURED RATHER THAN ASSUMED
# ---------------------------------------------------
# OpenStreetMap does NOT carry price or star rating. Those two fields are what
# the budget filter and the rating floor need. So live records come back with
# price and rating set to None, and nothing is invented to fill them - the same
# rule the rest of this agent follows.
#
# Run field_coverage() to see exactly how many fields the live source can supply
# against how many the agent needs. That number is the argument for why the mock
# is shaped like a richer commercial provider, and what a production deployment
# would have to buy.
# =============================================================================

import json
import ssl
import urllib.error
import urllib.request

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
TIMEOUT_SECONDS = 45


def _ssl_context():
    """Build an SSL context that works on a stock macOS Python install.

    Measured on 15 Aug 2026: the first live run failed with
    CERTIFICATE_VERIFY_FAILED, "unable to get local issuer certificate". That is
    not a network problem and not a problem with the API. Python installed on
    macOS does not always use the system keychain, so it has no trusted root
    certificates of its own until it is pointed at a bundle. certifi ships that
    bundle and is already present here as a dependency of the other packages.

    If certifi is somehow missing, fall back to the default context rather than
    disabling verification. Turning verification off would make the call succeed
    while silently accepting any certificate, which is not a trade worth making
    to fetch a restaurant list.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()

# The five fields the retrieval engine and the hard filters actually consume.
REQUIRED_FIELDS = ("city", "cuisine", "price", "rating", "dietary")


# The six destinations this agent covers, with a centre point and a search
# radius in metres. Coordinates rather than a name lookup, deliberately:
# measured on 15 Aug 2026, searching OpenStreetMap by administrative area name
# returned zero results for both Honolulu and San Juan, because the boundary
# relation is not named the way a traveller says the city. A fixed centre point
# is unambiguous, reproducible between runs, and cannot silently return nothing
# because of a naming mismatch.
CITY_COORDS = {
    "Aruba":       (12.5240, -70.0270, 6000),
    "San Juan":    (18.4655, -66.1057, 5000),
    "Honolulu":    (21.3069, -157.8583, 5000),
    "Cancun":      (21.1619, -86.8515, 6000),
    "Nassau":      (25.0443, -77.3504, 5000),
    "Montego Bay": (18.4762, -77.8939, 6000),
}


def _query(city, limit):
    """An Overpass query for restaurants near a known city centre."""
    lat, lon, radius = CITY_COORDS[city]
    return f"""
    [out:json][timeout:30];
    (
      node(around:{radius},{lat},{lon})["amenity"="restaurant"]["name"];
      way(around:{radius},{lat},{lon})["amenity"="restaurant"]["name"];
    );
    out tags {int(limit)};
    """


def _diet_flag(tags, key):
    """OpenStreetMap records diet tags as yes / only / no / limited."""
    return str(tags.get(key, "")).strip().lower() in ("yes", "only")


def _to_record(element, city):
    """Convert one OpenStreetMap element into this agent's record shape.

    Price and rating are set to None because the source does not carry them.
    They are NOT guessed. A downstream filter can then treat them as unknown
    rather than silently trusting an invented number.
    """
    tags = element.get("tags", {})
    cuisine = (tags.get("cuisine") or "").split(";")[0].replace("_", " ").strip()
    return {
        "id": f"osm{element.get('id')}",
        "name": tags.get("name", "").strip(),
        "city": city,
        "cuisine": cuisine.title() if cuisine else "Unlisted",
        "price": None,      # not published by OpenStreetMap
        "rating": None,     # not published by OpenStreetMap
        "vegetarian": _diet_flag(tags, "diet:vegetarian"),
        "vegan": _diet_flag(tags, "diet:vegan"),
        "gluten_free": _diet_flag(tags, "diet:gluten_free"),
        "description": _describe(tags, city),
        "source": "openstreetmap",
    }


def _describe(tags, city):
    """Build the sentence that gets embedded, from whatever the source gives."""
    parts = []
    cuisine = (tags.get("cuisine") or "").split(";")[0].replace("_", " ").strip()
    if cuisine:
        parts.append(f"{cuisine.title()} restaurant in {city}")
    else:
        parts.append(f"Restaurant in {city}")
    if tags.get("outdoor_seating") == "yes":
        parts.append("outdoor seating")
    if tags.get("takeaway") == "yes":
        parts.append("takeaway available")
    if tags.get("delivery") == "yes":
        parts.append("delivery available")
    diets = [label for label, key in (("vegetarian", "diet:vegetarian"),
                                      ("vegan", "diet:vegan"),
                                      ("gluten-free", "diet:gluten_free"))
             if _diet_flag(tags, key)]
    if diets:
        parts.append("dietary options: " + ", ".join(diets))
    return ". ".join(parts) + "."


def fetch_live_restaurants(city, limit=40):
    """Fetch real restaurants for one city. Returns (records, error_or_None).

    Never raises. A network failure returns an empty list and a plain reason, so
    a caller can fall back to the mock dataset without the whole agent breaking -
    the same degradation rule answer() already follows.
    """
    if city not in CITY_COORDS:
        return [], (f"{city} is not one of the six destinations this agent "
                    f"covers ({', '.join(sorted(CITY_COORDS))})")
    try:
        request = urllib.request.Request(
            OVERPASS_URL,
            data=_query(city, limit).encode("utf-8"),
            headers={"User-Agent": "ALY6980-capstone-restaurant-agent"},
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS,
                                    context=_ssl_context()) as response:
            payload = json.load(response)
    except urllib.error.URLError as error:
        return [], f"could not reach the live source ({error.reason})"
    except Exception as error:  # malformed payload, timeout, anything else
        return [], f"live source returned something unusable ({error})"

    records = [_to_record(e, city) for e in payload.get("elements", [])]
    records = [r for r in records if r["name"]]
    if not records:
        return [], f"the live source returned no named restaurants for {city}"
    return records, None


def field_coverage(records):
    """How many of the fields this agent needs does the live source supply?

    Returns a dict of field name to the percentage of records carrying a real
    value. This is the measurement behind the claim that a free source is not
    enough for a product that filters on budget and rating.
    """
    if not records:
        return {}
    total = len(records)
    coverage = {
        "name": sum(1 for r in records if r["name"]) / total,
        "city": 1.0,
        "cuisine": sum(1 for r in records if r["cuisine"] != "Unlisted") / total,
        "price": sum(1 for r in records if r["price"] is not None) / total,
        "rating": sum(1 for r in records if r["rating"] is not None) / total,
        "any dietary tag": sum(1 for r in records
                               if r["vegetarian"] or r["vegan"] or r["gluten_free"]) / total,
    }
    return coverage


if __name__ == "__main__":
    print()
    print("=" * 74)
    print("  LIVE DATA SOURCE CHECK - OpenStreetMap via Overpass, no API key")
    print("=" * 74)
    print()

    any_success = False
    for city in ("Honolulu", "San Juan"):
        print(f"--- {city} ---")
        records, error = fetch_live_restaurants(city, limit=40)
        if error:
            print(f"    FAILED: {error}")
            print("    The agent would fall back to its own dataset and say so.\n")
            continue
        any_success = True

        print(f"    {len(records)} real restaurants returned.")
        for r in records[:3]:
            diets = [d for d, on in (("vegetarian", r["vegetarian"]),
                                     ("vegan", r["vegan"]),
                                     ("gluten-free", r["gluten_free"])) if on]
            print(f"      {r['name']}  |  {r['cuisine']}  |  "
                  f"diet: {', '.join(diets) if diets else 'none listed'}")

        print("\n    Field coverage from this live source:")
        for field, share in field_coverage(records).items():
            flag = "" if share > 0 else "   <-- NOT PUBLISHED BY THIS SOURCE"
            print(f"      {field:<16} {share:>6.0%}{flag}")
        print()

    print("-" * 74)
    if any_success:
        print("  Reading of this result:")
        print("  The live call works. Real, named restaurants come back from a real")
        print("  public API with no key. What they do NOT come back with is most of")
        print("  what this agent filters on. Measured on 15 Aug 2026 over 40 real")
        print("  San Juan records: name 100%, cuisine 28%, price 0%, rating 0%, and")
        print("  a dietary tag on 2%.")
        print()
        print("  That last number is worth stating plainly, because this source was")
        print("  chosen ON THE ASSUMPTION that its dietary tags would be useful.")
        print("  They are not. OpenStreetMap supports diet:vegan, diet:vegetarian")
        print("  and diet:gluten_free as fields, but almost nobody fills them in.")
        print("  Supporting a field and populating it are different things, and only")
        print("  running the call showed the difference.")
        print()
        print("  So the conclusion is stronger than 'the mock was convenient'. A free")
        print("  crowd-sourced source can supply one of the five fields this agent")
        print("  needs. Dietary filtering - the whole point of this agent - would")
        print("  fail on live data for 98% of restaurants. A production deployment")
        print("  needs a commercial provider that guarantees these fields, and that")
        print("  is a purchasing decision, not an engineering one.")
    else:
        print("  NO CITY SUCCEEDED. Nothing about the live source is demonstrated")
        print("  by this run - the failures above are the only finding. Do not")
        print("  claim a working live integration on the strength of this output.")
    print("-" * 74)
    print()
