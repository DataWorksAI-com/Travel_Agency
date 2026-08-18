"""
test_tools.py — the contract for the three budget tools.

Run:  pytest -q
These fail until you write the bodies in budget_agent/tools.py.
Read each failure, write the smallest thing that makes it pass, run again.
"""

import pytest

from budget_agent.corpus import Corpus
from budget_agent.tools import (
    FIRST_LAST_DAY_FACTOR,
    RESERVE_FRACTION,
    allocate_budget,
    estimate_costs,
    verify_plan,
)

# Known values from the committed corpus (ref date 2026-08-13):
#   BARBADOS   -> lodging 210, M&IE 167   (May-Nov season)
#   COSTA RICA -> lodging 147, M&IE 153
#   PANAMA     -> Panama City 173 / 99, and a stale effective date
NASSAU_COUNTRY = "BAHAMAS, THE"


# --- corpus sanity ---------------------------------------------------------

def test_corpus_loads():
    c = Corpus()
    assert len(c) == 40
    assert len(c.countries()) == 18


def test_lookup_unknown_country_returns_none():
    """No fuzzy matching, no nearest neighbour, no default rate."""
    assert Corpus().lookup("MALDIVES") is None
    assert Corpus().lookup("Atlantis") is None


def test_lookup_falls_back_to_other_post():
    c = Corpus()
    rate = c.lookup("BELIZE", post="Somewhere That Does Not Exist")
    assert rate is not None
    assert rate.post.upper() == "OTHER"


def test_seasonal_location_resolves_to_august_season():
    """Antigua has Jan-Jun and Jun-Dec seasons. August must pick the cheaper."""
    rate = Corpus().lookup("ANTIGUA AND BARBUDA", post="Antigua and Barbuda")
    assert rate.lodging == 216
    assert rate.seasonal is True


def test_stale_rates_are_flagged():
    rate = Corpus().lookup("PANAMA", post="Panama City")
    assert rate.stale is True


# --- city-name resolution (the other agents emit cities, not countries) ----

def test_resolve_accepts_a_city_name():
    rate = Corpus().resolve("Nassau")
    assert rate is not None
    assert rate.country.upper() == "BAHAMAS, THE"
    assert rate.lodging == 432


def test_city_lookup_beats_the_country_other_row():
    """Nassau is $432; the Bahamas 'Other' fallback is $176. Big difference."""
    city = Corpus().resolve("Nassau")
    country_only = Corpus().resolve("BAHAMAS, THE")
    assert city.lodging > country_only.lodging


def test_resolve_refuses_the_other_row_by_name():
    assert Corpus().resolve("Other") is None


def test_estimate_accepts_a_city_name():
    out = estimate_costs("Nassau", nights=3)
    assert out["covered"] is True
    assert out["lodging_total"] == 432 * 3


# --- estimate_costs --------------------------------------------------------

def test_estimate_rejects_nonsense_input():
    with pytest.raises(ValueError):
        estimate_costs("BARBADOS", nights=0)
    with pytest.raises(ValueError):
        estimate_costs("BARBADOS", nights=3, travelers=0)


def test_estimate_uncovered_destination_says_so():
    out = estimate_costs("MALDIVES", nights=5)
    assert out["covered"] is False
    assert "available_countries" in out
    # The message must name the real coverage, so the agent stops guessing.
    assert "BARBADOS" in out["available_countries"]
    assert "estimated_total" not in out


def test_estimate_lodging_is_per_night_not_per_day():
    out = estimate_costs("BARBADOS", nights=4, travelers=1)
    assert out["covered"] is True
    assert out["lodging_total"] == 210 * 4


def test_estimate_meals_prorate_first_and_last_day():
    """5 days for 4 nights: 3 full days + 2 days at 75%."""
    out = estimate_costs("BARBADOS", nights=4, travelers=1)
    expected = round(167 * (3 + 2 * FIRST_LAST_DAY_FACTOR))
    assert out["meals_total"] == expected


def test_estimate_two_travelers_share_one_room():
    solo = estimate_costs("BARBADOS", nights=3, travelers=1)
    pair = estimate_costs("BARBADOS", nights=3, travelers=2)
    assert pair["lodging_total"] == solo["lodging_total"]      # same room
    assert pair["meals_total"] == solo["meals_total"] * 2      # two mouths


def test_estimate_four_travelers_need_two_rooms():
    solo = estimate_costs("BARBADOS", nights=3, travelers=1)
    quad = estimate_costs("BARBADOS", nights=3, travelers=4)
    assert quad["lodging_total"] == solo["lodging_total"] * 2


def test_estimate_propagates_stale_flag():
    out = estimate_costs("PANAMA", nights=2)
    assert out["stale"] is True


# --- allocate_budget -------------------------------------------------------

def test_allocate_envelopes_never_exceed_total():
    out = allocate_budget(5000, "BARBADOS", nights=4, travelers=2)
    assert out["feasible"] is True
    assert sum(out["envelopes"].values()) <= 5000


def test_allocate_holds_back_a_reserve():
    out = allocate_budget(5000, "BARBADOS", nights=4, travelers=2)
    assert out["envelopes"]["reserve"] == round(5000 * RESERVE_FRACTION)


def test_allocate_lodging_envelope_matches_per_diem():
    est = estimate_costs("BARBADOS", nights=4, travelers=2)
    out = allocate_budget(5000, "BARBADOS", nights=4, travelers=2)
    assert out["envelopes"]["lodging"] == est["lodging_total"]


def test_allocate_declares_infeasible_rather_than_shrinking():
    """$300 cannot even cover food for 2 people for 5 days. Genuinely impossible."""
    out = allocate_budget(300, "BARBADOS", nights=4, travelers=2)
    assert out["status"] == "infeasible"
    assert out["feasible"] is False
    assert out["deficit"] > 0


def test_allocate_below_per_diem_is_constrained_not_impossible():
    """Per diem is a CEILING. A budget under it means 'find cheaper', not 'no'.

    $2000 cannot cover the full per diem envelope for 4 nights in Barbados,
    but it comfortably covers food — so the trip is workable if lodging beats
    the government rate. Reporting this as infeasible would tell the user
    they cannot afford a trip they can afford.
    """
    out = allocate_budget(2000, "BARBADOS", nights=4, travelers=2)
    assert out["status"] == "constrained"
    assert out["feasible"] is True
    assert out["deficit"] == 0
    # Must say what rate the Accommodation agent has to beat.
    assert 0 < out["max_nightly_lodging"] < 210


def test_constrained_envelopes_still_fit_the_budget():
    out = allocate_budget(2000, "BARBADOS", nights=4, travelers=2)
    assert sum(out["envelopes"].values()) <= 2000


def test_allocate_uncovered_destination():
    out = allocate_budget(5000, "MALDIVES", nights=4)
    assert out["feasible"] is False
    assert out["covered"] is False


# --- verify_plan -----------------------------------------------------------

ENVELOPES = {"lodging": 1000, "meals": 500, "activities": 300}


def test_verify_passes_a_plan_within_budget():
    out = verify_plan({"lodging": 900, "meals": 400, "activities": 250}, ENVELOPES)
    assert out["status"] == "feasible"
    assert out["deficit"] == 0
    assert out["violation_type"] is None
    assert all(c["ok"] for c in out["per_category"].values())


def test_verify_catches_overspend_and_reports_the_deficit():
    out = verify_plan({"lodging": 1200, "meals": 400, "activities": 250}, ENVELOPES)
    assert out["status"] == "infeasible"
    assert out["violation_type"] == "budget"
    assert out["deficit"] == 200
    assert out["per_category"]["lodging"]["over_by"] == 200
    assert out["per_category"]["meals"]["ok"] is True


def test_verify_does_not_net_underspend_against_overspend():
    """Under budget on meals must NOT excuse being over on lodging."""
    out = verify_plan({"lodging": 1200, "meals": 100, "activities": 100}, ENVELOPES)
    assert out["status"] == "infeasible"
    assert out["deficit"] == 200


def test_verify_flags_categories_with_no_envelope():
    out = verify_plan({"lodging": 900, "souvenirs": 400}, ENVELOPES)
    assert out["status"] == "infeasible"
    assert out["violation_type"] == "uncategorised"


def test_verify_totals_are_reported():
    out = verify_plan({"lodging": 900, "meals": 400}, ENVELOPES)
    assert out["total_spent"] == 1300
    assert out["total_ceiling"] == 1800
