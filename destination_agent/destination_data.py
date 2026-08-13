import os
import json
from pathlib import Path

import requests
from dotenv import load_dotenv


# ============================================================
# ENVIRONMENT SETUP
# ============================================================

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

def geocode_destination(destination_name: str):
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
        "format": "json",
        "apiKey": GEOAPIFY_API_KEY
    }

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
    limit: int = 10
):
    """
    Search for places near a destination using
    the Geoapify Places API.

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

        limit:
            Maximum number of places to return.

    Returns:
        A list of place dictionaries.
    """

    if not GEOAPIFY_API_KEY:
        raise ValueError(
            "GEOAPIFY_API_KEY is not configured in the .env file."
        )

    url = "https://api.geoapify.com/v2/places"

    params = {
        "categories": category,
        "limit": limit,
        "apiKey": GEOAPIFY_API_KEY
    }
    # If Geoapify provides a place boundary,
    # search inside the entire destination.
    if place_id:
        params["filter"] = f"place:{place_id}"

    # Fallback:
    # If no place boundary is available,
    # search within 20 km of the coordinates.
    else:
        params["filter"] = (
            f"circle:{longitude},{latitude},20000"
        )

        params["bias"] = (
            f"proximity:{longitude},{latitude}"
        )

    

    try:
        response = requests.get(
            url,
            params=params,
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        places = []

        for feature in data.get("features", []):
            properties = feature.get(
                "properties",
                {}
            )

            name = properties.get("name")

            # Ignore places without a usable name.
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

        return places

    except requests.RequestException as error:
        print(
            f"Places request failed for category "
            f"{category}: {error}"
        )

        return []


# ============================================================
# BUILD ONE DESTINATION PROFILE
# ============================================================

def build_destination_profile(destination_name: str):
    """
    Build a travel-oriented profile for one destination
    using live Geoapify data.

    The current Destination Agent focuses on:
    - beaches
    - tourist attractions
    - nature reserves
    - diving

    Climate information is intentionally excluded because
    it belongs to another agent in the multi-agent system.

    Args:
        destination_name:
            Name of the destination.

    Returns:
        A structured destination profile dictionary.

        Returns None if the destination cannot be found.
    """

    # Step 1:
    # Convert the destination name into coordinates.
    destination = geocode_destination(
        destination_name
    )

    if not destination:
        return None

    latitude = destination["latitude"]
    longitude = destination["longitude"]
    place_id = destination.get("place_id")

    # Map user-friendly feature names to
    # Geoapify category names.
    category_map = {
        "beaches": "beach",
        "attractions": "tourism.attraction",
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
            place_id
        )

        if not places:
            continue

        # Only add a feature when Geoapify
        # actually returned places for it.
        profile["features"].append(
            feature_name
        )

        # Extract the place names.
        place_names = [
            place["name"]
            for place in places
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
    destination_name: str
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

    # --------------------------------------------------------
    # STEP 1: CHECK CACHE
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # STEP 2: CACHE MISS -> CALL GEOAPIFY
    # --------------------------------------------------------

    print(
        f"No cached profile found for "
        f"{lookup_name}."
    )

    print(
        f"Building new profile for "
        f"{lookup_name}..."
    )

    profile = build_destination_profile(
        lookup_name
    )

    if not profile:
        print(
            f"Could not build a profile for "
            f"{lookup_name}."
        )

        return None

    # --------------------------------------------------------
    # STEP 3: SAVE NEW DESTINATION
    # --------------------------------------------------------

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
