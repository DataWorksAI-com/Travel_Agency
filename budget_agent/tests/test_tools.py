"""
Unit tests for the Budget Agent's tools.

test_budget_tools: pure computation, no API key or vector store needed.
test_rag_tools: requires the vector store to be built first
    (python scripts/build_vectorstore.py) since it does real semantic
    search -- skipped automatically if the store isn't found.
Run with:
    pytest
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from budget_agent.tools.budget_tools import check_feasibility  # noqa: E402


def test_check_feasibility_within_budget():
    result = check_feasibility.invoke({"estimated_total_cost": 677, "budget": 700})
    assert result["status"] == "feasible"
    assert result["difference"] == 23


def test_check_feasibility_not_feasible():
    result = check_feasibility.invoke({"estimated_total_cost": 827, "budget": 700})
    assert result["status"] == "not_feasible"
    assert result["difference"] == -127


def test_retrieve_cost_info_returns_relevant_city():
    pytest.importorskip("langchain_chroma")
    chroma_dir = Path(__file__).resolve().parent.parent / "chroma_db"
    if not chroma_dir.exists():
        pytest.skip("Vector store not built yet -- run scripts/build_vectorstore.py first")

    from budget_agent.tools.rag_tools import retrieve_cost_info

    results = retrieve_cost_info.invoke({"query": "cheap tropical beach trip from Boston", "k": 3})
    assert len(results) > 0
    assert all("city" in r and "content" in r for r in results)
