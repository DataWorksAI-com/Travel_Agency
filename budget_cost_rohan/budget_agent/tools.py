"""
tools.py — the three budget tools.

THESE ARE YOURS TO WRITE. Each function has its contract in the docstring and
a matching test in tests/test_tools.py. Run the tests, read the failure, write
the body, run again.

    pytest -q

Design note, so the bodies make sense:

The agent runs at BOTH ENDS of the plan, not just the end.

  - allocate_budget runs FIRST. It splits the traveller's total into per-
    category ceilings and hands them out, so the other domain agents search
    inside a budget instead of proposing options that get thrown away.
  - verify_plan runs LAST. It checks the assembled plan against those
    ceilings with plain arithmetic.

This is the design in HiMAP-Travel (Bui, Li & Liu, 2026). Their ablation:
removing the up-front allocator cost 12.98 points of final pass rate, mostly
from budget failures. Post-hoc checking alone is measurably worse.
"""

from __future__ import annotations

import math

from .corpus import Corpus, Rate

# Share one loaded corpus rather than re-reading the file per call.
_corpus = Corpus()

# Fraction of the daily M&IE rate allowed on the first and last day of travel.
# This is the U.S. federal rule (GSA M&IE breakdown, "FirstLastDay").
FIRST_LAST_DAY_FACTOR = 0.75

# Share of the total budget held back and not allocated to any category.
RESERVE_FRACTION = 0.10


def estimate_costs(destination: str, nights: int, travelers: int = 1,
                   post: str | None = None) -> dict:
    """Estimate what lodging and meals will cost for a stay.

    `destination` may be a country ("BARBADOS") or a city ("Nassau") — the
    other domain agents emit cities. `post` narrows within a country when you
    know both, e.g. destination="BAHAMAS, THE", post="Nassau".

    Look the destination up in the corpus. If it is not there, say so
    explicitly — do not substitute a nearby country or a nominal figure.

    Lodging is charged per night, once per room; assume one room for up to
    two travellers, then one room per two travellers.
    Meals are charged per traveller per DAY, where days = nights + 1, and the
    first and last day are charged at FIRST_LAST_DAY_FACTOR of the daily rate.

    Returns on success:
        {"covered": True, "destination": str, "post": str,
         "nights": int, "travelers": int,
         "lodging_total": int, "meals_total": int, "estimated_total": int,
         "daily_lodging_rate": int, "daily_mie_rate": int,
         "stale": bool, "seasonal": bool}

    Returns when the destination is not in the corpus:
        {"covered": False, "destination": str,
         "reason": str, "available_countries": list[str]}

    Raises ValueError if nights < 1 or travelers < 1.
    """
    # Reject nonsense before touching data. A tool that quietly accepts
    # nights=0 will happily return a $0 estimate, and the agent will report it.
    if nights < 1:
        raise ValueError(f"nights must be at least 1, got {nights}")
    if travelers < 1:
        raise ValueError(f"travelers must be at least 1, got {travelers}")

    rate: Rate | None = _corpus.resolve(destination, post)

    # Not covered. Say so, and say what IS covered, so the agent stops probing
    # for a boundary it cannot see. Note there is no estimate in this branch —
    # no nominal figure, no nearest neighbour.
    if rate is None:
        return {
            "covered": False,
            "destination": destination,
            "reason": (
                f"No published per diem data for '{destination}'. This tool "
                f"covers only the {len(_corpus.countries())} countries listed "
                f"in available_countries. Do not retry with a different "
                f"spelling or a nearby country."
            ),
            "available_countries": _corpus.countries(),
        }

    # Lodging: one room per two travellers, charged per night.
    rooms = math.ceil(travelers / 2)
    lodging_total = rate.lodging * nights * rooms

    # Meals: charged per DAY, and a stay of N nights spans N+1 days.
    # The first and last day are part-days, so federal practice pays them at
    # 75% of the daily rate (GSA M&IE breakdown, "FirstLastDay").
    days = nights + 1
    full_days = days - 2                      # 0 when it is a one-night trip
    charged_days = full_days + 2 * FIRST_LAST_DAY_FACTOR

    # Round per traveller, then multiply. Rounding the combined figure instead
    # would make two solo trips cost a different amount from one trip for two.
    meals_per_traveler = round(rate.mie * charged_days)
    meals_total = meals_per_traveler * travelers

    return {
        "covered": True,
        "destination": rate.country,
        "post": rate.post,
        "nights": nights,
        "travelers": travelers,
        "lodging_total": lodging_total,
        "meals_total": meals_total,
        "estimated_total": lodging_total + meals_total,
        "daily_lodging_rate": rate.lodging,
        "daily_mie_rate": rate.mie,
        "stale": rate.stale,
        "seasonal": rate.seasonal,
    }


def allocate_budget(total_budget: float, destination: str, nights: int,
                    travelers: int = 1, post: str | None = None) -> dict:
    """Split a total trip budget into per-category ceilings.

    Method:
      1. Hold back RESERVE_FRACTION of the total as reserve.
      2. Anchor lodging and meals on the per diem estimate from
         estimate_costs — these are the two categories we have real data for.
      3. Whatever is left after lodging, meals and reserve is the
         discretionary pot. Split it evenly between activities and
         local_transport.
      4. If lodging + meals + reserve already exceeds the total budget, the
         trip is INFEASIBLE at this destination. Say so, and report by how
         much, rather than silently shrinking the lodging ceiling.

    Returns:
        {"feasible": bool,
         "destination": str, "total_budget": float,
         "envelopes": {"lodging": int, "meals": int, "activities": int,
                       "local_transport": int, "reserve": int},
         "deficit": int,            # 0 when feasible
         "basis": str,              # one sentence naming the data source
         "stale": bool}

    If the destination is not covered, return
        {"feasible": False, "reason": ..., "covered": False}
    """
    # Step 1 — what will the two categories we have real data for actually
    # cost? Everything else is derived from this, so if the destination is
    # unknown we stop right here and pass the refusal straight through.
    est = estimate_costs(destination, nights, travelers, post)
    if not est["covered"]:
        return {
            "feasible": False,
            "covered": False,
            "destination": destination,
            "reason": est["reason"],
            "available_countries": est["available_countries"],
        }

    lodging = est["lodging_total"]
    meals = est["meals_total"]

    # Step 2 — hold the reserve back off the top, before anything is spent.
    # Taken from the remainder instead, it would be the first thing squeezed
    # by an expensive hotel, which defeats the point of having a reserve.
    reserve = round(total_budget * RESERVE_FRACTION)

    committed = lodging + meals + reserve

    # Step 3 — the feasibility gate. THREE states, not two.
    #
    # Per diem lodging is a CEILING, not an expected price: it is what the
    # U.S. government will reimburse for adequate accommodation on official
    # travel. A leisure traveller normally pays less. So a budget that falls
    # below the per diem envelope does NOT mean the trip is impossible — it
    # means lodging has to come in under the government rate, which is
    # usually easy. Treating that as "infeasible" would tell users they
    # cannot afford trips they can comfortably afford.
    #
    # Meals are different. M&IE is much closer to what people actually
    # spend, and everyone has to eat, so we treat it as the real floor.
    #
    #   feasible    — budget covers the full per diem envelope
    #   constrained — covers meals and reserve, but lodging must beat the
    #                 government rate; we say what nightly rate is needed
    #   infeasible  — cannot even cover meals and reserve
    floor = meals + reserve

    if total_budget < floor:
        return {
            "status": "infeasible",
            "feasible": False,
            "covered": True,
            "destination": est["destination"],
            "total_budget": total_budget,
            "envelopes": {
                "lodging": 0, "meals": meals, "activities": 0,
                "local_transport": 0, "reserve": reserve,
            },
            "deficit": int(floor - total_budget),
            "max_nightly_lodging": 0,
            "basis": (
                f"Meals alone for {travelers} traveller(s) over "
                f"{nights + 1} day(s) in {est['destination']} come to "
                f"${meals}, plus a ${reserve} reserve. The budget does not "
                f"cover food, so no lodging choice can rescue this trip."
            ),
            "stale": est["stale"],
        }

    if committed > total_budget:
        # Tight, but workable. Report the nightly rate the Accommodation
        # agent has to beat — far more actionable than a refusal.
        lodging_envelope = int(total_budget - floor)
        rooms = math.ceil(travelers / 2)
        max_nightly = lodging_envelope // (nights * rooms)
        return {
            "status": "constrained",
            "feasible": True,
            "covered": True,
            "destination": est["destination"],
            "total_budget": total_budget,
            "envelopes": {
                "lodging": lodging_envelope, "meals": meals,
                "activities": 0, "local_transport": 0, "reserve": reserve,
            },
            "deficit": 0,
            "max_nightly_lodging": max_nightly,
            "basis": (
                f"Budget is below the U.S. State Department per diem ceiling "
                f"of ${est['daily_lodging_rate']}/night for "
                f"{est['destination']}. That ceiling is what the government "
                f"reimburses for business travel, not a market price, so "
                f"this is workable — lodging needs to come in at or below "
                f"${max_nightly}/night. Nothing is left for activities or "
                f"local transport."
            ),
            "stale": est["stale"],
        }

    # Step 4 — split what survives between the two discretionary categories.
    # Floor division on both halves, deliberately: it can leave one dollar
    # unallocated, which is harmless, whereas rounding both halves up would
    # let the envelopes total more than the budget they came from.
    discretionary = int(total_budget - committed)
    activities = discretionary // 2
    local_transport = discretionary // 2

    return {
        "status": "feasible",
        "feasible": True,
        "covered": True,
        "destination": est["destination"],
        "total_budget": total_budget,
        "envelopes": {
            "lodging": lodging,
            "meals": meals,
            "activities": activities,
            "local_transport": local_transport,
            "reserve": reserve,
        },
        "deficit": 0,
        "max_nightly_lodging": est["daily_lodging_rate"],
        "basis": (
            f"Lodging and meals anchored on U.S. State Department per diem "
            f"for {est['destination']} (${est['daily_lodging_rate']}/night "
            f"lodging, ${est['daily_mie_rate']}/day meals). Remainder split "
            f"evenly between activities and local transport after a "
            f"{int(RESERVE_FRACTION * 100)}% reserve."
        ),
        "stale": est["stale"],
    }


def verify_plan(plan: dict, envelopes: dict, reserve: int | None = None) -> dict:
    """Check an assembled plan against its budget envelopes.

    `plan` maps category name -> cost, e.g.
        {"lodging": 1200, "meals": 400, "activities": 300}
    Categories present in the plan but absent from `envelopes` are reported
    as an "uncategorised" violation rather than ignored.

    Pure arithmetic. No model calls, no rounding in your favour.

    THE RESERVE. allocate_budget returns "reserve" inside its envelopes dict.
    A reserve is contingency — it is NOT a spending ceiling, and counting it
    as one would let a plan quietly consume the buffer while still reporting
    as comfortably within budget. So it is pulled out of the ceilings here
    automatically, whether or not the caller separates it.

    But excluding it entirely is also wrong: that fails plans a contingency
    fund would comfortably absorb. The rule contingency actually follows is
    that a reserve may cover an overrun, but its use has to be VISIBLE.
    Hence a distinct status rather than a silent pass or a hard fail.

    Returns the HiMAP-style feedback shape, which is also what the shared
    sub-agent schema uses for failures:

        {"status": "feasible" | "covered_by_reserve" | "infeasible",
         "deficit": int,                 # total overspend, 0 if none
         "violation_type": str | None,   # "budget" | "uncategorised"
         |                               # | "reserve_used" | None
         "per_category": {name: {"spent": int, "ceiling": int,
                                 "over_by": int, "ok": bool}},
         "total_spent": int,
         "total_ceiling": int,           # spendable only, excludes reserve
         "reserve": int,
         "reserve_used": int,
         "reserve_remaining": int}
    """
    # Never let the reserve act as a ceiling, however it was passed in.
    envelopes = dict(envelopes)
    embedded_reserve = envelopes.pop("reserve", 0)
    reserve = int(embedded_reserve if reserve is None else reserve)

    per_category: dict[str, dict] = {}
    deficit = 0
    uncategorised: list[str] = []

    # Step 1 — check every category the plan actually spends on.
    for name, spent in plan.items():
        spent = int(spent)

        # A cost with no matching envelope is not free. It is unbudgeted, and
        # it must not be silently dropped from the total.
        if name not in envelopes:
            uncategorised.append(name)
            per_category[name] = {
                "spent": spent, "ceiling": None,
                "over_by": spent, "ok": False,
            }
            continue

        ceiling = int(envelopes[name])
        over_by = max(0, spent - ceiling)

        # THE IMPORTANT LINE. Accumulate each category's overspend separately.
        #
        # The natural-looking alternative is deficit = total_spent -
        # total_ceiling. It is wrong. Under-running on meals would then cancel
        # an over-run on lodging, and the plan would be reported as affordable
        # while the hotel is unaffordable. Money is not fungible across these
        # categories in practice -- you cannot pay for a room with the dinners
        # you skipped.
        #
        # This is what makes the tool a constraint rather than a summary.
        deficit += over_by

        per_category[name] = {
            "spent": spent, "ceiling": ceiling,
            "over_by": over_by, "ok": over_by == 0,
        }

    # Step 2 — classify. Unbudgeted spend is a different problem from
    # overspending, and an overrun the reserve absorbs is different again.
    # The orchestrator should be told which of the three it is.
    if uncategorised:
        status, violation_type = "infeasible", "uncategorised"
        reserve_used = 0
    elif deficit == 0:
        status, violation_type = "feasible", None
        reserve_used = 0
    elif deficit <= reserve:
        # Workable — but the contingency is being spent, and that is
        # reported rather than absorbed silently.
        status, violation_type = "covered_by_reserve", "reserve_used"
        reserve_used = deficit
    else:
        status, violation_type = "infeasible", "budget"
        reserve_used = reserve

    return {
        "status": status,
        "deficit": deficit,
        "violation_type": violation_type,
        "per_category": per_category,
        "total_spent": sum(int(v) for v in plan.values()),
        "total_ceiling": sum(int(v) for v in envelopes.values()),
        "reserve": reserve,
        "reserve_used": reserve_used,
        "reserve_remaining": reserve - reserve_used,
        "uncategorised": uncategorised,
    }
