import os
import json
import time
from pathlib import Path

# truststore MUST be injected before requests is imported. This network
# intercepts HTTPS with a certificate Windows trusts but Python does not;
# without the injection, Geoapify calls hang ~5 minutes and then fail with no
# useful error. This mirrors the pattern used across destination_data/.
import truststore

truststore.inject_into_ssl()

import requests
from dotenv import load_dotenv

# ENVIRONMENT SETUP

# Load environment variables from the .env file.
load_dotenv()

# Geoapify API key.
GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY")

# JSON file used as the local destination knowledge cache.
#
# Using __file__ makes sure the JSON file is always stored
# in the same folder as destination_data.py.
PROFILE_FILE = Path(__file__).parent / "destination_profiles.json"


# ============================================================
# GEOAPIFY: DESTINATION GEOCODING
# ============================================================

def geocode_destination(
    destination_name: str,
    country_code: str = None
):
    """
    Convert a destination name into latitude and longitude
    using the Geoapify Geocoding API.

    Args:
        destination_name:
            Name of the destination, for example
            Aruba, Jamaica, Barbados, or Fiji.

    Returns:
        A dictionary containing the formatted destination name,
        latitude, and longitude.

        Returns None if the destination cannot be found.
    """

    if not GEOAPIFY_API_KEY:
        raise ValueError(
            "GEOAPIFY_API_KEY is not configured in the .env file."
        )

    url = "https://api.geoapify.com/v1/geocode/search"

    params = {
        "text": destination_name,
        "type": "city",
        "format": "json",
        "bias": "countrycode:none",
        "apiKey": GEOAPIFY_API_KEY
    }

    if country_code:
        params["filter"] = (
            f"countrycode:{country_code.lower()}"
        )

    try:
        response = requests.get(
            url,
            params=params,
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        results = data.get("results", [])

        if not results:
            return None

        # Use the first matching location returned by Geoapify.
        first_result = results[0]

        return {
            "name": first_result.get(
                "formatted",
                destination_name
            ),
            "latitude": first_result.get("lat"),
            "longitude": first_result.get("lon"),
            "place_id": first_result.get("place_id"),
            "result_type": first_result.get("result_type"),
            "bbox": first_result.get("bbox")
        }

    except requests.RequestException as error:
        print(
            f"Geocoding request failed for "
            f"{destination_name}: {error}"
        )

        return None


# ============================================================
# GEOAPIFY: PLACE SEARCH
# ============================================================

def search_places(
    latitude: float,
    longitude: float,
    category: str,
    place_id: str = None,
    bbox: dict = None,
    limit: int = 10
):
    """
    Search for places near a destination using
    the Geoapify Places API.

    The function tries several spatial search strategies:
    1. City bounding box
    2. Geoapify place boundary
    3. 20 km coordinate circle

    If one strategy fails because of a network/API error,
    the next strategy is attempted.

    Args:
        latitude:
            Latitude of the destination.

        longitude:
            Longitude of the destination.

        category:
            Geoapify category to search for.
            Examples:
            - beach
            - tourism.attraction
            - leisure.park.nature_reserve
            - sport.dive_centre

        place_id:
            Optional Geoapify place boundary ID.

        bbox:
            Optional destination bounding box.

        limit:
            Maximum number of places to return.

    Returns:
        A list of place dictionaries.

        Returns [] when the request succeeds but no places
        are found.

        Returns None only when every spatial search strategy
        fails.
    """

    if not GEOAPIFY_API_KEY:
        raise ValueError(
            "GEOAPIFY_API_KEY is not configured in the .env file."
        )

    url = "https://api.geoapify.com/v2/places"

    params = {
        "categories": category,
        # Unnamed records are useless in an itinerary -- there is nothing for a
        # traveller to look up or walk to.
        "conditions": "named",
        "limit": limit,
        "apiKey": GEOAPIFY_API_KEY
    }

    # --------------------------------------------------------
    # BUILD SEARCH STRATEGIES
    # --------------------------------------------------------

    search_filters = []

    # 1. City bounding box
    if bbox:
        search_filters.append(
            (
                "bbox",
                (
                    f"rect:"
                    f"{bbox['lon1']},"
                    f"{bbox['lat1']},"
                    f"{bbox['lon2']},"
                    f"{bbox['lat2']}"
                )
            )
        )

    # 2. Geoapify place boundary
    if place_id:
        search_filters.append(
            (
                "place",
                f"place:{place_id}"
            )
        )

    # 3. Coordinate fallback
    search_filters.append(
        (
            "circle",
            f"circle:{longitude},{latitude},20000"
        )
    )

    # --------------------------------------------------------
    # TRY EACH SEARCH STRATEGY
    # --------------------------------------------------------

    max_attempts = 3

    for filter_name, spatial_filter in search_filters:

        request_params = params.copy()

        request_params["filter"] = spatial_filter

        # Bias is only needed for the circle search.
        if filter_name == "circle":
            request_params["bias"] = (
                f"proximity:{longitude},{latitude}"
            )

        # Retry the current strategy up to 3 times.
        for attempt in range(
            1,
            max_attempts + 1
        ):

            try:
                response = requests.get(
                    url,
                    params=request_params,
                    timeout=15
                )

                response.raise_for_status()

                data = response.json()

                places = []

                for feature in data.get(
                    "features",
                    []
                ):
                    properties = feature.get(
                        "properties",
                        {}
                    )

                    name = properties.get("name")

                    if not name:
                        continue

                    places.append(
                        {
                            "name": name,
                            "categories": properties.get(
                                "categories",
                                []
                            ),
                            "formatted": properties.get(
                                "formatted"
                            )
                        }
                    )

                # [] is still a successful API response.
                return places

            except requests.RequestException as error:

                print(
                    f"{category} search using "
                    f"{filter_name} failed "
                    f"(attempt "
                    f"{attempt}/{max_attempts}): "
                    f"{error}"
                )

                if attempt < max_attempts:
                    time.sleep(2)

        # Current spatial strategy failed all retries.
        print(
            f"{category} search using "
            f"{filter_name} failed. "
            f"Trying next spatial filter..."
        )

    # Every spatial strategy failed.
    return None

# ============================================================
# BUILD ONE DESTINATION PROFILE
# ============================================================

def build_destination_profile(
        destination_name: str,
        latitude: float = None,
        longitude: float = None,
        country_code: str = None
    ):
    """
    Build a travel-oriented profile for one destination
    using live Geoapify data.

    The current Destination Agent focuses on:
    - beaches
    - points of interest near the centre
    - nature reserves
    - diving

    These are the nearest matching places to the city centre, NOT a ranked or
    curated list of highlights: Geoapify offers no notability filter, so a
    memorial plaque a few hundred metres away outranks a landmark across town.
    Present them as "points of interest near the centre", never as "the top
    attractions", and do not imply the list is exhaustive or ordered by
    importance.

    Climate and public-holiday data are handled separately
    by the shared destination data layer.
    """

    # Step 1:
    # Convert the destination name into coordinates.

    place_id = None
    bbox = None

    # Use Geoapify geocoding to obtain the correct
    # destination boundary information.
    destination = geocode_destination(
        destination_name,
        country_code
    )

    if destination:

        place_id = destination.get("place_id")
        bbox = destination.get("bbox")

        # Only use Geoapify coordinates when coordinates
        # were not already supplied by the shared data layer.
        if latitude is None or longitude is None:
            latitude = destination["latitude"]
            longitude = destination["longitude"]

    # If neither source can provide coordinates,
    # the profile cannot be built.
    if latitude is None or longitude is None:
        return None

    # Map user-friendly feature names to
    # Geoapify category names.
    # "tourism.sights" rather than "tourism.attraction": the latter includes
    # artwork and street art, which is how Rome came back as "Guerrilla spam,
    # Il coniglio, Street Art di Mauro Sgarbi" and Cancun as "clips, Condominio
    # Bellamar". Measured on the same coordinates, sights returns Piazza del
    # Campidoglio / Tabularium / Tempio di Vespasiano for Rome and El Meco for
    # Cancun.
    #
    # This is an improvement, not a fix. Geoapify has no notability ranking --
    # "wiki_and_media" is rejected as an unsupported condition -- so results
    # remain ordered by distance from the city centre and a nearby memorial
    # plaque still outranks the Colosseum. Paris is slightly worse under this
    # category than the old one. The output wording below is deliberately
    # "points of interest near the centre" rather than "attractions", so the
    # reply stops implying a curated list it cannot produce.
    category_map = {
        "beaches": "beach",
        "attractions": "tourism.sights",
        "nature": "leisure.park.nature_reserve",
        "diving": "sport.dive_centre"
    }

    # Base structure for one destination.
    profile = {
        "destination": destination_name,
        "features": [],
        "places": {}
    }

    # Step 2:
    # Search Geoapify for each travel feature.
    for feature_name, api_category in category_map.items():

        places = search_places(
            latitude,
            longitude,
            api_category,
            place_id=place_id,
            bbox=bbox
        )

        # API request failed.
        # Do not treat this as "no places exist".
        if places is None:
            print(
                f"Could not complete {feature_name} lookup "
                f"for {destination_name}."
            )
            return None

        # API worked, but no places were found.
        if not places:
            continue

        # Only add a feature when Geoapify
        # actually returned places for it.
        profile["features"].append(
            feature_name
        )

        # Extract the place names.
        #
        # Names of one or two characters are dropped: Geoapify tags Roman
        # milestone markers and similar as named sights, so Rome came back
        # listing "I" and "VII" as points of interest. Nothing a traveller can
        # look up or navigate to has a one-character name.
        place_names = [
            place["name"]
            for place in places
            if len(place.get("name", "").strip()) > 2
        ]

        # Remove duplicate place names while
        # preserving their original order.
        unique_place_names = list(
            dict.fromkeys(place_names)
        )

        profile["places"][
            feature_name
        ] = unique_place_names

    return profile

# ============================================================
# CONVERT PROFILE TO RAG TEXT
# ============================================================

def profile_to_rag_text(profile: dict) -> str:
    """
    Convert a Geoapify destination profile into concise text
    that can be added to the Destination RAG corpus.
    """

    if not profile:
        return ""

    parts = []

    features = profile.get("features", [])

    if features:
        parts.append(
            "Travel features: "
            + ", ".join(features)
            + "."
        )

    for feature, places in profile.get("places", {}).items():

        if not places:
            continue

        # Keep only a few examples so the RAG text
        # stays concise.
        examples = places[:5]

        parts.append(
            f"{feature.title()}: "
            + ", ".join(examples)
            + "."
        )

    return " ".join(parts)

# ============================================================
# LOCAL CACHE: LOAD DESTINATION PROFILES
# ============================================================

def load_destination_profiles():
    """
    Load previously generated destination profiles
    from destination_profiles.json.

    Returns:
        A dictionary containing cached destination profiles.
    """

    # If the file has not been created yet,
    # start with an empty knowledge cache.
    if not PROFILE_FILE.exists():
        return {}

    try:
        with open(
            PROFILE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    except (
        json.JSONDecodeError,
        OSError
    ) as error:

        print(
            f"Could not load destination profiles: "
            f"{error}"
        )

        return {}


# ============================================================
# LOCAL CACHE: SAVE DESTINATION PROFILES
# ============================================================

def save_destination_profiles(profiles):
    """
    Save destination profiles to
    destination_profiles.json.

    Args:
        profiles:
            Dictionary containing all cached
            destination profiles.
    """

    with open(
        PROFILE_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            profiles,
            file,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# CACHE-FIRST DESTINATION LOOKUP
# ============================================================

def get_or_build_destination_profile(
    destination_name: str,
    latitude: float = None,
    longitude: float = None,
    country_code: str = None
):
    """
    Get destination information from the local cache first.

    If the destination does not already exist:
    1. Call Geoapify.
    2. Build a new destination profile.
    3. Save the profile to destination_profiles.json.
    4. Return the newly created profile.

    This avoids repeatedly calling Geoapify for destinations
    that have already been collected.

    Args:
        destination_name:
            Name of the destination requested by the Agent.

    Returns:
        Destination profile dictionary or None.
    """

    # Remove unnecessary spaces.
    lookup_name = destination_name.strip()

    # Load current destination knowledge.
    profiles = load_destination_profiles()

    # STEP 1: CHECK CACHE

    # Case-insensitive comparison allows:
    #
    # Aruba
    # aruba
    # ARUBA
    #
    # to all find the same saved destination.
    for saved_name, profile in profiles.items():

        if (
            saved_name.lower()
            == lookup_name.lower()
        ):
            print(
                f"Using cached profile for "
                f"{saved_name}"
            )

            return profile

    # STEP 2: CACHE MISS -> CALL GEOAPIFY

    print(
        f"No cached profile found for "
        f"{lookup_name}."
    )

    print(
        f"Building new profile for "
        f"{lookup_name}..."
    )

    profile = build_destination_profile(
        lookup_name,
        latitude=latitude,
        longitude=longitude,
        country_code=country_code
    )

    if not profile:
        print(
            f"Could not build a profile for "
            f"{lookup_name}."
        )

        return None

    # STEP 3: SAVE NEW DESTINATION

    # Do not cache an empty destination profile.
    if not profile["features"]:
        print(
            f"No usable travel data was found for "
            f"{lookup_name}. Profile was not cached."
        )

        return None

    profiles[lookup_name] = profile

    save_destination_profiles(
        profiles
    )

    print(
        f"Saved new destination profile for "
        f"{lookup_name}."
    )

    return profile
