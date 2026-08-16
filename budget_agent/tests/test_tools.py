"""
Unit tests for the standalone budget/cost-estimation tools.

These test the pure computation logic directly -- no API key or
network access needed.
Run with:
    pytest
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from budget_agent.tools.budget_tools import (  # noqa: E402
    check_feasibility,
    get_cost_estimate,
)


def test_get_cost_estimate_known_destination():
    result = get_cost_estimate.invoke({"destination": "Cancun"})
    assert result["flight_roundtrip"] == 450
    assert "lodging_per_day" in result


def test_get_cost_estimate_unknown_destination():
    result = get_cost_estimate.invoke({"destination": "Atlantis"})
    assert "error" in result


def test_check_feasibility_within_budget():
    result = check_feasibility.invoke({"destination": "Cancun", "budget": 1000, "days": 3})
    assert result["status"] == "feasible"
    assert result["difference"] >= 0


def test_check_feasibility_not_feasible():
    result = check_feasibility.invoke({"destination": "Maui", "budget": 500, "days": 3})
    assert result["status"] == "not_feasible"
    assert result["difference"] < 0


def test_check_feasibility_default_days():
    result = check_feasibility.invoke({"destination": "Phuket", "budget": 2000})
    assert result["days"] == 3
