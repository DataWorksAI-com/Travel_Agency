"""
Unit tests for the budget aggregation tools.

These test the pure computation logic directly -- no API key or
network access needed.
Run with:
    pytest
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from budget_agent.tools.budget_tools import (  # noqa: E402
    aggregate_costs,
    check_budget,
    suggest_adjustment,
)

SAMPLE_ITEMS = [
    {"category": "flights", "name": "JetBlue B6 204", "cost": 412},
    {"category": "restaurants", "name": "Verde Cancun", "cost": 65},
    {"category": "restaurants", "name": "La Habichuela", "cost": 80},
    {"category": "activities", "name": "Snorkeling tour", "cost": 120},
    {"category": "activities", "name": "Chichen Itza day trip", "cost": 150},
]


def test_aggregate_costs_sums_correctly():
    result = aggregate_costs.invoke({"line_items": SAMPLE_ITEMS})
    assert result["total_cost"] == 827.0
    assert result["item_count"] == 5
    assert result["by_category"]["flights"] == 412.0
    assert result["by_category"]["restaurants"] == 145.0
    assert result["by_category"]["activities"] == 270.0


def test_check_budget_within_budget():
    result = check_budget.invoke({"total_cost": 500, "budget": 700})
    assert result["status"] == "within_budget"
    assert result["difference"] == 200


def test_check_budget_over_budget():
    result = check_budget.invoke({"total_cost": 827, "budget": 700})
    assert result["status"] == "over_budget"
    assert result["difference"] == -127


def test_suggest_adjustment_covers_overage_without_touching_flights():
    suggestions = suggest_adjustment.invoke({"line_items": SAMPLE_ITEMS, "overage": 127})
    assert all(s["category"] != "flights" for s in suggestions)
    total_covered = sum(s["cost"] for s in suggestions)
    assert total_covered >= 127


def test_suggest_adjustment_returns_empty_when_not_over():
    suggestions = suggest_adjustment.invoke({"line_items": SAMPLE_ITEMS, "overage": 0})
    assert suggestions == []
