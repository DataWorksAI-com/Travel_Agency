from destination_agent.geoapify_data import (
    geocode_destination,
    build_destination_profile,
    get_or_build_destination_profile,
    load_destination_profiles
)


def run_test(name, func):
    print("\n" + "=" * 60)
    print(name)
    print("=" * 60)

    try:
        result = func()

        print("Result:")
        print(result)

        if result:
            print("\nStatus: PASS")
            return True

        print("\nStatus: FAIL")
        return False

    except Exception as error:
        print("\nStatus: FAIL")
        print("Error:", error)
        return False


passed = 0
total = 0


# ============================================================
# TEST 1 - GEOCODING
# ============================================================

total += 1

if run_test(
    "TEST 1 - Geocode a valid destination",
    lambda: geocode_destination(
        "Amsterdam",
        country_code="NL"
    )
):
    passed += 1


# ============================================================
# TEST 2 - BUILD PROFILE FROM LIVE GEOAPIFY DATA
# ============================================================

total += 1

if run_test(
    "TEST 2 - Build destination profile",
    lambda: build_destination_profile(
        "Fiji"
    )
):
    passed += 1


# ============================================================
# TEST 3 - CACHE-FIRST LOOKUP
# ============================================================

total += 1

if run_test(
    "TEST 3 - Get or build cached profile",
    lambda: get_or_build_destination_profile(
        "Aruba"
    )
):
    passed += 1


# ============================================================
# TEST 4 - VERIFY CACHE CONTENT
# ============================================================

def test_cache():

    profiles = load_destination_profiles()

    print(
        "Cached destinations:",
        len(profiles)
    )

    # Aruba should already exist in the shared cache.
    return any(
        name.lower() == "aruba"
        for name in profiles
    )


total += 1

if run_test(
    "TEST 4 - Verify destination cache",
    test_cache
):
    passed += 1


# ============================================================
# TEST 5 - INVALID DESTINATION
# ============================================================

def test_invalid_destination():

    result = geocode_destination(
        "zzzzzzzz_invalid_destination_12345"
    )

    # Correct behavior is graceful failure,
    # not an exception.
    return result is None


total += 1

if run_test(
    "TEST 5 - Invalid destination handled gracefully",
    test_invalid_destination
):
    passed += 1


# ============================================================
# TEST SUMMARY
# ============================================================

print("\n" + "=" * 60)
print("TEST SUMMARY")
print("=" * 60)

print(
    f"Passed: {passed}/{total}"
)

print(
    f"Failed: {total - passed}/{total}"
)