"""
cases.py — test cases: a prompt plus what a correct answer must look like.

Ground truth comes from the deterministic tools, not from hand-typed numbers,
so the expectations can never drift out of sync with the corpus.

Each case declares:
    id            short name
    task          the prompt sent to the agent
    expect_refuse the agent must decline and name its coverage
    must_say      substrings that must appear (case-insensitive)
    must_not_say  substrings that must not appear
    allowed_money dollar figures the agent is permitted to state
    note          what this case is actually testing
"""

from __future__ import annotations

from proposed_envelope_agent.tools import allocate_budget, estimate_costs


def _money_from(*results: dict) -> set[int]:
    """Every dollar figure a tool actually produced, so anything else in the
    agent's reply is a fabrication."""
    allowed: set[int] = set()
    for r in results:
        for key in ("lodging_total", "meals_total", "estimated_total",
                    "daily_lodging_rate", "daily_mie_rate",
                    "max_nightly_lodging", "deficit", "total_budget"):
            v = r.get(key)
            if isinstance(v, (int, float)):
                allowed.add(int(v))
        for v in (r.get("envelopes") or {}).values():
            allowed.add(int(v))
    return allowed


def build_cases() -> list[dict]:
    cases: list[dict] = []

    # 1. Constrained. The headline behaviour: below per diem is NOT a refusal.
    est = estimate_costs("BARBADOS", nights=4, travelers=2)
    alloc = allocate_budget(2000, "BARBADOS", nights=4, travelers=2)
    cases.append({
        "id": "constrained_barbados",
        "task": "4 nights in Barbados for 2 people, budget 2000",
        "expect_refuse": False,
        "must_say": ["constrain", str(alloc["max_nightly_lodging"])],
        "must_not_say": ["impossible", "cannot afford", "not feasible"],
        "allowed_money": _money_from(est, alloc) | {2000},
        "note": "below per diem means 'find cheaper', not 'no'",
    })

    # 2. Comfortable budget.
    est2 = estimate_costs("BARBADOS", nights=4, travelers=2)
    alloc2 = allocate_budget(5000, "BARBADOS", nights=4, travelers=2)
    cases.append({
        "id": "feasible_barbados",
        "task": "4 nights in Barbados for 2 people, budget 5000",
        "expect_refuse": False,
        "must_say": ["feasib"],
        "must_not_say": ["impossible", "constrained"],
        "allowed_money": _money_from(est2, alloc2) | {5000},
        "note": "comfortable budget must read as feasible",
    })

    # 3. Genuinely impossible — cannot cover food.
    est3 = estimate_costs("BARBADOS", nights=4, travelers=2)
    alloc3 = allocate_budget(300, "BARBADOS", nights=4, travelers=2)
    cases.append({
        "id": "infeasible_barbados",
        "task": "4 nights in Barbados for 2 people, budget 300",
        "expect_refuse": False,
        "must_say": ["infeasible"],
        "must_not_say": [],
        "allowed_money": _money_from(est3, alloc3) | {300},
        "note": "only 'cannot cover meals' is a real no",
    })

    # 4. Out of scope. Must refuse once and name coverage.
    cases.append({
        "id": "out_of_scope_maldives",
        "task": "5 days in the Maldives, budget 3000",
        "expect_refuse": True,
        "must_say": ["not covered", "barbados"],
        "must_not_say": ["per night", "estimated total"],
        "allowed_money": {3000},
        "note": "Week 1 finding: declared coverage stops boundary probing",
    })

    # 5. City name, not country. Sibling agents emit cities.
    est5 = estimate_costs("Nassau", nights=3, travelers=1)
    alloc5 = allocate_budget(4000, "Nassau", nights=3, travelers=1)
    cases.append({
        "id": "city_name_nassau",
        "task": "3 nights in Nassau for 1 person, budget 4000",
        "expect_refuse": False,
        "must_say": [],
        "must_not_say": ["not covered"],
        "allowed_money": _money_from(est5, alloc5) | {4000},
        "note": "must resolve Nassau, not fall back to the Bahamas catch-all",
    })

    # 6. Scope boundary. Hotels belong to another agent.
    cases.append({
        "id": "scope_hotel_request",
        "task": "Recommend me a nice hotel in Nassau",
        "expect_refuse": False,
        "must_say": [],
        "must_not_say": ["i recommend staying at", "hotel is a great choice"],
        "allowed_money": set(),
        "note": "must hand back rather than recommend accommodation",
    })

    # --- scaling tests: where prose-derived numbers fall apart -------------

    # 7/8. Party size. Lodging barely moves, meals double.
    for n_trav in (1, 2):
        e = estimate_costs("BARBADOS", nights=4, travelers=n_trav)
        a = allocate_budget(6000, "BARBADOS", nights=4, travelers=n_trav)
        cases.append({
            "id": f"scale_travelers_{n_trav}",
            "task": f"4 nights in Barbados for {n_trav} "
                    f"{'person' if n_trav == 1 else 'people'}, budget 6000",
            "expect_refuse": False,
            "must_say": [],
            "must_not_say": [],
            "allowed_money": _money_from(e, a) | {6000},
            "note": "meals scale with people, lodging does not",
        })

    # 9. Duration. Doubling nights should roughly double the estimate.
    e9 = estimate_costs("BARBADOS", nights=8, travelers=2)
    a9 = allocate_budget(6000, "BARBADOS", nights=8, travelers=2)
    cases.append({
        "id": "scale_nights_8",
        "task": "8 nights in Barbados for 2 people, budget 6000",
        "expect_refuse": False,
        "must_say": [],
        "must_not_say": [],
        "allowed_money": _money_from(e9, a9) | {6000},
        "note": "cost must scale with trip length",
    })

    return cases


CASES = build_cases()
