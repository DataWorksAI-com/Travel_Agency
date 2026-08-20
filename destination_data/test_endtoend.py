"""End-to-end test for the destination data layer.

Proves the four tools chain together the way the Destination Agent will call
them. This is a DATA-LAYER test: no LLM, no agent, no orchestration. It imports
the existing tools and calls them in sequence - it reimplements nothing.

Covers:
  Case 1  - user named a city          -> resolve_place -> climate + holidays
  Case 2  - user gave preferences      -> recommend_destinations -> climate + holidays
  Case 3  - graceful failure           -> a country the holiday source does not cover

Every tool call is checked for an {"error": ...} return. A failing stage is
reported and the script continues; nothing here is allowed to raise.

Run:
    $env:PYTHONIOENCODING='utf-8'
    .\.venv\Scripts\python.exe test_endtoend.py
"""

# truststore MUST be injected before anything imports requests or opens HTTPS.
# The tool modules each do this too, but this file must not depend on import order.
import truststore

truststore.inject_into_ssl()

from climate import get_climate
from holidays import get_holidays
from recommend import recommend_destinations
from resolve_place import resolve_place

HOLIDAYS_TO_SHOW = 5
PREFERENCES = ["warm", "coastal", "Asia"]

# Tally of stage outcomes, printed at the end.
_results = []


# ---------------------------------------------------------------------------
# printing helpers
# ---------------------------------------------------------------------------

def section(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def stage(title):
    print(f"\n--- {title} ---")


def record(label, ok, detail=""):
    _results.append((label, ok, detail))


def is_error(result):
    """Tools signal failure by returning a dict containing an 'error' key."""
    return isinstance(result, dict) and "error" in result


def safe_call(label, func, *args, **kwargs):
    """Call a tool and normalise every outcome into (ok, result).

    The tools are contracted never to raise, so the except branch here is a
    belt-and-braces check on that contract rather than expected behaviour.
    """
    try:
        result = func(*args, **kwargs)
    except Exception as exc:  # a tool raising is itself a test failure
        print(f"  [RAISED] {label} raised {type(exc).__name__}: {exc}")
        print("           (tools are contracted never to raise - this is a bug)")
        record(label, False, f"raised {type(exc).__name__}")
        return False, None

    if is_error(result):
        print(f"  [ERROR]  {label}: {result['error']}")
        record(label, False, result["error"])
        return False, result

    print(f"  [OK]     {label}")
    record(label, True)
    return True, result


def show_place(place):
    print(f"  name         : {place.get('name')}")
    print(f"  country_code : {place.get('country_code')}")
    print(f"  lat, lon     : {place.get('lat')}, {place.get('lon')}")


def show_climate(climate):
    best = climate.get("best_months") or []
    avoid = climate.get("avoid_months") or []
    period = climate.get("period") or {}
    print(f"  period       : {period.get('start_date')} to {period.get('end_date')}")
    print(f"  best_months  : {', '.join(best) if best else '(none by the current thresholds)'}")
    print(f"  avoid_months : {', '.join(avoid) if avoid else '(none by the current thresholds)'}")
    print(f"  note         : {climate.get('note')}")


def show_holidays(holidays):
    print(f"  {len(holidays)} public holidays this year; first {HOLIDAYS_TO_SHOW}:")
    for holiday in holidays[:HOLIDAYS_TO_SHOW]:
        local = holiday.get("local_name")
        suffix = f"  ({local})" if local and local != holiday.get("name") else ""
        print(f"    {holiday.get('date')}  {holiday.get('name')}{suffix}")


def enrich(label, lat, lon, country_code):
    """Run the two enrichment tools for a resolved place. Returns (climate, holidays)."""
    stage(f"{label}: get_climate(lat={lat}, lon={lon})")
    climate_ok, climate = safe_call("get_climate", get_climate, lat, lon)
    if climate_ok:
        show_climate(climate)

    stage(f"{label}: get_holidays(country_code={country_code!r})")
    holidays_ok, holidays = safe_call("get_holidays", get_holidays, country_code)
    if holidays_ok:
        show_holidays(holidays)
    else:
        print("  -> continuing without holiday data (this is a normal outcome)")

    return (climate if climate_ok else None, holidays if holidays_ok else None)


# ---------------------------------------------------------------------------
# Case 1 - the user named a city, so the RAG is skipped entirely
# ---------------------------------------------------------------------------

def case_one():
    section("CASE 1 - user named a city (RAG skipped)")
    city = "Tokyo"
    print(f"User input: \"I want to go to {city}.\"")
    print("Tokyo is deliberately NOT in the corpus - this proves the live lookup path.")

    stage(f"resolve_place({city!r})")
    ok, place = safe_call("resolve_place", resolve_place, city)
    if not ok:
        print("  -> cannot continue Case 1 without coordinates")
        return
    show_place(place)

    climate, holidays = enrich("Case 1", place["lat"], place["lon"], place["country_code"])

    stage("Case 1 combined summary")
    print(f"  Destination  : {place['name']} ({place['country_code']})")
    if climate:
        best = climate.get("best_months") or []
        avoid = climate.get("avoid_months") or []
        print(f"  Best months  : {', '.join(best) if best else '(none)'}")
        print(f"  Avoid months : {', '.join(avoid) if avoid else '(none)'}")
    else:
        print("  Climate      : unavailable")
    if holidays:
        print(f"  Holidays     : {len(holidays)} this year, e.g. "
              f"{', '.join(h.get('name') or '?' for h in holidays[:3])}")
    else:
        print("  Holidays     : unavailable")


# ---------------------------------------------------------------------------
# Case 2 - the user gave preferences, so the RAG picks the candidates
# ---------------------------------------------------------------------------

def case_two():
    section("CASE 2 - user gave preferences (RAG)")
    print(f"User input: preferences = {PREFERENCES}")

    stage(f"recommend_destinations({PREFERENCES})")
    ok, shortlist = safe_call("recommend_destinations", recommend_destinations, PREFERENCES)
    if not ok:
        print("  -> cannot continue Case 2 without a shortlist")
        return
    if not shortlist:
        print("  -> shortlist was empty, cannot continue Case 2")
        record("recommend_destinations returned candidates", False, "empty list")
        return

    stage("Full shortlist")
    for rank, candidate in enumerate(shortlist, start=1):
        print(f"  {rank}. {candidate.get('name')} ({candidate.get('country_code')})"
              f"  match_score={candidate.get('match_score')}")
        print(f"     {candidate.get('description')}")

    # The list already comes back ranked, but pick explicitly by score so the
    # test does not silently depend on the ordering.
    top = max(shortlist, key=lambda c: c.get("match_score") or 0)

    stage("Top candidate")
    show_place(top)
    print(f"  match_score  : {top.get('match_score')}")
    print("  (match_score is semantic similarity - a relative rank, not a quality rating)")

    climate, holidays = enrich("Case 2", top["lat"], top["lon"], top["country_code"])

    stage("Case 2 combined summary")
    print(f"  Top pick     : {top['name']} ({top['country_code']}) "
          f"from {len(shortlist)} candidates")
    if climate:
        best = climate.get("best_months") or []
        avoid = climate.get("avoid_months") or []
        print(f"  Best months  : {', '.join(best) if best else '(none)'}")
        print(f"  Avoid months : {', '.join(avoid) if avoid else '(none)'}")
    else:
        print("  Climate      : unavailable")
    if holidays:
        print(f"  Holidays     : {len(holidays)} this year, e.g. "
              f"{', '.join(h.get('name') or '?' for h in holidays[:3])}")
    else:
        print("  Holidays     : unavailable")


# ---------------------------------------------------------------------------
# Case 3 - a source that has no data must degrade, not derail
# ---------------------------------------------------------------------------

def case_three():
    section("CASE 3 - graceful failure (holiday source has no coverage)")
    city = "Bangkok"
    print(f"User input: \"I want to go to {city}.\"")
    print("Nager.Date does not cover Thailand. Climate must still come through,")
    print("and the missing holidays must be reported as unavailable, not crash.")

    stage(f"resolve_place({city!r})")
    ok, place = safe_call("resolve_place", resolve_place, city)
    if not ok:
        print("  -> cannot continue Case 3 without coordinates")
        return
    show_place(place)

    stage(f"get_climate(lat={place['lat']}, lon={place['lon']})")
    climate_ok, climate = safe_call("get_climate", get_climate, place["lat"], place["lon"])
    if climate_ok:
        show_climate(climate)

    stage("get_holidays('TH')  <- expected to return an error dict")
    holidays_ok, holidays = safe_call("get_holidays", get_holidays, "TH")

    stage("Case 3 verdict")
    if climate_ok and not holidays_ok:
        print("  PASS - climate came through, holidays reported unavailable, no crash.")
        print("  This is the degraded-but-useful result the agent should expect.")
        record("Case 3 degrades gracefully", True)
    elif climate_ok and holidays_ok:
        print("  NOTE - holidays for TH unexpectedly succeeded.")
        print("  Not a failure: the source may have added coverage. Chain still worked.")
        record("Case 3 degrades gracefully", True, "TH holidays now covered")
    else:
        print("  FAIL - climate did not come through, so the chain did not degrade usefully.")
        record("Case 3 degrades gracefully", False, "climate unavailable")

    print(f"\n  Reached the end of Case 3 with {place['name']} still usable: "
          f"{'yes' if climate_ok else 'no'}")


# ---------------------------------------------------------------------------

def summary():
    section("SUMMARY")
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)

    for label, ok, detail in _results:
        mark = "OK  " if ok else "FAIL"
        line = f"  [{mark}] {label}"
        if detail:
            line += f" - {detail}"
        print(line)

    print(f"\n  {passed}/{total} stages succeeded.")
    if passed != total:
        print("  Stages reported FAIL above returned an error dict; none of them")
        print("  stopped the run. Check whether each is expected (e.g. TH holidays)")
        print("  or a genuine problem.")


def main():
    print("End-to-end test - destination data layer")
    print("Tools only: no LLM, no agent, no orchestration.")
    try:
        case_one()
        case_two()
        case_three()
    except Exception as exc:  # nothing is allowed to escape this script
        print(f"\n[UNHANDLED] {type(exc).__name__}: {exc}")
        print("This should not happen - the tools are contracted never to raise.")
        record("run completed without unhandled exception", False, type(exc).__name__)
    else:
        record("run completed without unhandled exception", True)

    try:
        summary()
    except Exception as exc:
        print(f"\n[UNHANDLED in summary] {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
