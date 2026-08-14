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

import requests

API_URL = "https://archive-api.open-meteo.com/v1/archive"
TIMEOUT_SECONDS = 60
YEARS_OF_HISTORY = 5

# --------------------------------------------------------------------------
# Best / avoid month thresholds - tune these freely, the rule below is literal.
# --------------------------------------------------------------------------
COMFORTABLE_MIN_C = 18.0   # a "best" month is at least this warm on average
COMFORTABLE_MAX_C = 30.0   # ...and no warmer than this on average
WET_MONTH_MM = 100.0       # ...and drier than this in total monthly rainfall

TOO_COLD_C = 10.0          # avoid: monthly mean at or below this
TOO_HOT_C = 32.0           # avoid: monthly mean at or above this
VERY_WET_MONTH_MM = 200.0  # avoid: monthly rainfall at or above this

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

NOTE = (
    f"Historical typical conditions averaged over the last {YEARS_OF_HISTORY} "
    "complete years (ERA5 reanalysis via Open-Meteo). This is not a forecast "
    "and not a guarantee of conditions in any future month."
)


def _classify_month(avg_temp_c, avg_precip_mm):
    """Label one month as 'best', 'avoid', or None. Deliberately literal."""
    if avg_temp_c is None or avg_precip_mm is None:
        return None

    is_best = (
        COMFORTABLE_MIN_C <= avg_temp_c <= COMFORTABLE_MAX_C
        and avg_precip_mm < WET_MONTH_MM
    )
    if is_best:
        return "best"

    is_avoid = (
        avg_temp_c <= TOO_COLD_C
        or avg_temp_c >= TOO_HOT_C
        or avg_precip_mm >= VERY_WET_MONTH_MM
    )
    if is_avoid:
        return "avoid"

    return None


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
    best_months = []
    avoid_months = []

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

        label = _classify_month(avg_temp, avg_precip)
        if label == "best":
            best_months.append(name)
        elif label == "avoid":
            avoid_months.append(name)

    if all(entry["avg_temp_c"] is None and entry["avg_precip_mm"] is None for entry in monthly):
        return {"error": f"No usable historical climate values returned for lat={lat}, lon={lon}"}

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
