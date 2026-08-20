"""Historical climate tool for the Destination Agent data layer.

Source: Open-Meteo Historical Weather API - ERA5 reanalysis archive (free, keyless)
    https://archive-api.open-meteo.com/v1/archive

This is the ARCHIVE endpoint: real observed past weather. It is deliberately not
the /v1/climate endpoint, which serves model projections.

Contract:
  - returns plain Python dicts/lists, never JSON strings
  - never raises: every failure path returns {"error": "..."}
  - reports only what the API returns; nothing is filled in from model knowledge
  - output is framed as historical typical conditions, never a forecast
"""

# truststore MUST be injected before requests is imported, or HTTPS calls on
# this network hang ~5 minutes behind the intercepting proxy certificate.
import truststore

truststore.inject_into_ssl()

import datetime
import statistics

import requests

API_URL = "https://archive-api.open-meteo.com/v1/archive"
TIMEOUT_SECONDS = 60
YEARS_OF_HISTORY = 5

# --------------------------------------------------------------------------
# Best / avoid month thresholds - tune these freely, the rules below are literal.
#
# Rainfall is judged RELATIVE to the location's own year, not against a global
# millimetre constant. An absolute cut-off cannot work for both a wet/dry-split
# climate and an equatorial one: Singapore's driest month is ~101 mm, so a
# "drier than 100 mm" rule made best_months permanently empty there while
# marking two thirds of the year as avoid.
#
# Temperature stays absolute, because "comfortable" really is a fixed human
# range - but it is only a filter on which months can be "best", never a veto
# that empties the list on its own.
# --------------------------------------------------------------------------
COMFORT_MIN_C = 15.0       # a "best" month must be at least this warm on average
COMFORT_MAX_C = 32.0       # ...and no warmer than this on average

HARD_COLD_C = 8.0          # counts toward "avoid": monthly mean at or below this
HARD_HOT_C = 34.0          # counts toward "avoid": monthly mean at or above this

# A month counts as "wet for this place" when its rainfall is at least this
# multiple of the location's own median month. 1.3 = 30% wetter than typical.
WET_RATIO = 1.3

BEST_MONTHS_MAX = 4        # report at most this many best months
AVOID_MONTHS_MAX = 4       # hard cap, so "avoid" is never most of the year

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

NOTE = (
    f"Historical typical conditions averaged over the last {YEARS_OF_HISTORY} "
    "complete years (ERA5 reanalysis via Open-Meteo). Best and avoid months are "
    "ranked relative to this location's own year, so they describe the better and "
    "worse months for this place rather than an absolute standard. This is not a "
    "forecast and not a guarantee of conditions in any future month."
)


def _pick_best_months(months):
    """The driest months among those in the comfortable temperature range.

    "Driest" is relative: the months are ranked against each other, so a place
    that rains every month still has a best few. Returns calendar order.
    """
    comfortable = [
        m for m in months if COMFORT_MIN_C <= m["avg_temp_c"] <= COMFORT_MAX_C
    ]
    # No comfortable month is a real answer, not a failure - a destination whose
    # warmest month is 12 C has no "best time to visit" on a comfort basis.
    if not comfortable:
        return []

    driest = sorted(comfortable, key=lambda m: (m["avg_precip_mm"], m["month_number"]))
    chosen = driest[:BEST_MONTHS_MAX]
    return [m["month"] for m in sorted(chosen, key=lambda m: m["month_number"])]


def _pick_avoid_months(months, median_precip_mm):
    """The location's genuinely worst months, capped so it is never most of the year.

    Temperature extremes rank first (they rule a trip out more decisively than
    rain), then the months that are wettest relative to this location's median.
    Returns calendar order.
    """
    # Coldest first, then hottest first - worst offender leads each group.
    too_cold = sorted(
        (m for m in months if m["avg_temp_c"] <= HARD_COLD_C),
        key=lambda m: (m["avg_temp_c"], m["month_number"]),
    )
    too_hot = sorted(
        (m for m in months if m["avg_temp_c"] >= HARD_HOT_C),
        key=lambda m: (-m["avg_temp_c"], m["month_number"]),
    )

    too_wet = []
    if median_precip_mm and median_precip_mm > 0:
        wet_threshold = median_precip_mm * WET_RATIO
        too_wet = sorted(
            (m for m in months if m["avg_precip_mm"] >= wet_threshold),
            key=lambda m: (-m["avg_precip_mm"], m["month_number"]),
        )

    ranked = []
    for group in (too_cold, too_hot, too_wet):
        for month in group:
            if month["month_number"] not in {m["month_number"] for m in ranked}:
                ranked.append(month)

    chosen = ranked[:AVOID_MONTHS_MAX]
    return [m["month"] for m in sorted(chosen, key=lambda m: m["month_number"])]


def get_climate(lat, lon):
    """Return typical historical climate by month for a location.

    Args:
        lat: latitude, -90..90.
        lon: longitude, -180..180.

    Returns:
        On success, a dict with "monthly" (12 entries of month / avg_temp_c /
        avg_precip_mm), "best_months", "avoid_months", "period", "source" and
        "note". On any failure, a dict {"error": "..."}.
    """
    # --- validate coordinates -------------------------------------------------
    if isinstance(lat, bool) or isinstance(lon, bool):
        return {"error": "lat and lon must be numbers, got a boolean"}
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return {"error": f"lat and lon must be numbers, got lat={lat!r}, lon={lon!r}"}
    if not -90.0 <= lat <= 90.0:
        return {"error": f"Latitude {lat} is out of range (must be between -90 and 90)"}
    if not -180.0 <= lon <= 180.0:
        return {"error": f"Longitude {lon} is out of range (must be between -180 and 180)"}

    # --- last N complete calendar years --------------------------------------
    last_complete_year = datetime.date.today().year - 1
    first_year = last_complete_year - YEARS_OF_HISTORY + 1
    start_date = f"{first_year}-01-01"
    end_date = f"{last_complete_year}-12-31"

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": "temperature_2m_mean,precipitation_sum",
        "timezone": "UTC",
    }

    # --- call the archive -----------------------------------------------------
    try:
        response = requests.get(API_URL, params=params, timeout=TIMEOUT_SECONDS)
    except requests.exceptions.Timeout:
        return {"error": f"Climate data unavailable: Open-Meteo archive timed out after {TIMEOUT_SECONDS}s"}
    except requests.exceptions.RequestException as exc:
        return {"error": f"Climate data unavailable: network error contacting Open-Meteo ({exc})"}

    try:
        payload = response.json()
    except ValueError:
        return {"error": f"Climate data unavailable: Open-Meteo returned non-JSON (HTTP {response.status_code})"}

    if response.status_code != 200:
        # Open-Meteo reports problems as {"error": true, "reason": "..."}
        reason = payload.get("reason") if isinstance(payload, dict) else None
        if reason:
            return {"error": f"Climate data unavailable: Open-Meteo rejected the request ({reason})"}
        return {"error": f"Climate data unavailable: Open-Meteo returned HTTP {response.status_code}"}

    if not isinstance(payload, dict):
        return {"error": f"Climate data unavailable: expected a JSON object, got {type(payload).__name__}"}

    daily = payload.get("daily")
    if not isinstance(daily, dict):
        return {"error": "Climate data unavailable: Open-Meteo response contained no 'daily' block"}

    dates = daily.get("time")
    temps = daily.get("temperature_2m_mean")
    precips = daily.get("precipitation_sum")
    if not isinstance(dates, list) or not isinstance(temps, list) or not isinstance(precips, list):
        return {"error": "Climate data unavailable: Open-Meteo response was missing daily time/temperature/precipitation arrays"}
    if not dates:
        return {"error": f"No historical climate data returned for lat={lat}, lon={lon} ({start_date} to {end_date})"}
    if not (len(dates) == len(temps) == len(precips)):
        return {"error": "Climate data unavailable: Open-Meteo daily arrays had mismatched lengths"}

    # --- aggregate by calendar month -----------------------------------------
    # Temperature: mean of all daily means falling in that month, across years.
    # Precipitation: total per (year, month), then averaged across years, so the
    # figure reads as "typical rainfall in that month".
    temp_sums = {m: 0.0 for m in range(1, 13)}
    temp_counts = {m: 0 for m in range(1, 13)}
    precip_year_totals = {}  # (year, month) -> mm

    for day, temp, precip in zip(dates, temps, precips):
        try:
            year = int(day[0:4])
            month = int(day[5:7])
        except (TypeError, ValueError, IndexError):
            continue
        if not 1 <= month <= 12:
            continue

        if temp is not None:
            temp_sums[month] += float(temp)
            temp_counts[month] += 1
        if precip is not None:
            precip_year_totals[(year, month)] = precip_year_totals.get((year, month), 0.0) + float(precip)

    monthly = []

    for month in range(1, 13):
        if temp_counts[month] > 0:
            avg_temp = round(temp_sums[month] / temp_counts[month], 1)
        else:
            avg_temp = None

        month_totals = [mm for (_, m), mm in precip_year_totals.items() if m == month]
        if month_totals:
            avg_precip = round(sum(month_totals) / len(month_totals), 1)
        else:
            avg_precip = None

        name = MONTH_NAMES[month - 1]
        monthly.append(
            {
                "month": name,
                "month_number": month,
                "avg_temp_c": avg_temp,
                "avg_precip_mm": avg_precip,
            }
        )

    if all(entry["avg_temp_c"] is None and entry["avg_precip_mm"] is None for entry in monthly):
        return {"error": f"No usable historical climate values returned for lat={lat}, lon={lon}"}

    # Classification runs across the whole year at once, because "dry" and "wet"
    # are now judged against this location's own months rather than a constant.
    complete = [
        entry
        for entry in monthly
        if entry["avg_temp_c"] is not None and entry["avg_precip_mm"] is not None
    ]
    median_precip_mm = (
        statistics.median(entry["avg_precip_mm"] for entry in complete) if complete else None
    )

    best_months = _pick_best_months(complete)
    avoid_months = _pick_avoid_months(complete, median_precip_mm)

    # A month cannot be both. Temperature comfort wins: if a month is warm
    # enough and among the driest here, being wetter than median does not
    # disqualify it in a climate where every month is wet.
    avoid_months = [name for name in avoid_months if name not in best_months]

    return {
        "monthly": monthly,
        "best_months": best_months,
        "avoid_months": avoid_months,
        "period": {"start_date": start_date, "end_date": end_date, "years": YEARS_OF_HISTORY},
        "source": "Open-Meteo Historical Weather API (ERA5 reanalysis archive)",
        "note": NOTE,
    }


if __name__ == "__main__":
    tests = [
        ("Bangkok, Thailand (tropical, monsoon split)", 13.7563, 100.5018),
        ("Paris, France (temperate)", 48.8566, 2.3522),
        ("Invalid latitude", 999, 0),
    ]

    for label, lat, lon in tests:
        print(f"\n=== {label}  (lat={lat}, lon={lon}) ===")
        result = get_climate(lat, lon)

        if "error" in result:
            print(result)
            continue

        print(f"period: {result['period']['start_date']} to {result['period']['end_date']}")
        print(f"{'month':<10} {'avg temp C':>11} {'avg precip mm':>15}")
        for entry in result["monthly"]:
            print(f"{entry['month']:<10} {str(entry['avg_temp_c']):>11} {str(entry['avg_precip_mm']):>15}")
        print(f"best_months : {result['best_months']}")
        print(f"avoid_months: {result['avoid_months']}")
        print(f"note: {result['note']}")
