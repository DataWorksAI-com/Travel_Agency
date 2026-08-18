"""
agent.py — the Budget & Cost domain-expert agent.

Run it:
    python -m budget_agent.agent            interactive
    python -m budget_agent.agent --demo     no LLM, no API key, tools only

The --demo path exercises the tools directly. Use it to confirm the wiring
before spending tokens, and as the harness for the test jig later.

LangSmith tracing needs no code changes — set these in .env:
    LANGSMITH_TRACING=true
    LANGSMITH_API_KEY=lsv2_...
    LANGSMITH_PROJECT=budget-agent
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .corpus import Corpus
from .tools import allocate_budget as _allocate
from .tools import estimate_costs as _estimate
from .tools import verify_plan as _verify

load_dotenv()

_COUNTRIES = ", ".join(Corpus().countries())


# ---------------------------------------------------------------------------
# Agent-facing tools.
#
# These are thin wrappers. The logic lives in tools.py, which stays pure and
# unit tested; what changes here is the DOCSTRING, because the docstring is
# the only specification the model ever sees.
#
# Week 1 finding: when a tool's docstring did not state what it covered, an
# out-of-scope query produced 14 tool calls across 5 destinations the user
# never mentioned — the model was probing to find the boundary. Declaring
# coverage cut that to a mean of 1.71 calls over 7 runs (SD 0.49), and in 4
# of those 7 runs the tool was not called at all: the model read the spec and
# reasoned from it instead of testing it.
#
# So each docstring below states three things on purpose:
#   1. exactly which destinations are covered
#   2. an explicit instruction not to retry on failure
#   3. what the numbers mean, so they are not misreported as prices
# ---------------------------------------------------------------------------

def estimate_costs(destination: str, nights: int, travelers: int = 1) -> dict:
    """Estimate lodging and meal costs for a stay, from published per diem data.

    COVERAGE — this tool holds data for these countries ONLY:
    {countries}
    Accepts a country name or a major city name (e.g. "Nassau", "San Jose").

    If the destination is not covered the result has covered=false. That is a
    final answer, not a transient failure. DO NOT retry with a different
    spelling, a nearby country, or a different tool. Tell the user which
    destinations are covered and stop.

    IMPORTANT — what these numbers are: U.S. State Department per diem rates
    are the MAXIMUM a government traveller may be reimbursed for adequate
    accommodation. They are an upper bound, not a market price. A leisure
    traveller usually pays less. Present them as a ceiling, never as a quote.

    Args:
        destination: country or city, e.g. "BARBADOS" or "Nassau"
        nights: number of nights, at least 1
        travelers: number of people, at least 1
    """
    return _estimate(destination, nights, travelers)


def allocate_budget(total_budget: float, destination: str, nights: int,
                    travelers: int = 1) -> dict:
    """Split a total trip budget into per-category spending ceilings.

    Call this BEFORE the other domain agents search, so they look for options
    inside a budget instead of proposing options that are later discarded.

    COVERAGE — same destinations as estimate_costs:
    {countries}
    Not covered means covered=false. Do not retry with another name.

    Returns one of three states in "status":
      "feasible"    — the budget covers the full per diem envelope
      "constrained" — workable, but lodging must come in at or below
                      max_nightly_lodging. This is NOT a refusal. Pass that
                      figure to whoever is finding accommodation.
      "infeasible"  — the budget cannot cover meals, so no lodging choice
                      helps. Only this state means "no".

    Args:
        total_budget: the traveller's total budget in USD
        destination: country or city
        nights: number of nights, at least 1
        travelers: number of people, at least 1
    """
    return _allocate(total_budget, destination, nights, travelers)


def verify_plan(plan: dict, envelopes: dict) -> dict:
    """Check an assembled travel plan against its budget ceilings.

    Call this AFTER the other agents have returned their picks, with their
    real prices. This tool needs no per diem data and works for ANY
    destination — the coverage limit above does not apply here.

    plan and envelopes both map category name to dollars, e.g.
        {{"lodging": 1200, "meals": 400, "activities": 300}}

    Overspending in one category is NOT cancelled by underspending in
    another. A plan can be under budget overall and still fail, because the
    hotel is unaffordable even though the meals were cheap.

    Report the returned figures exactly. Do not recompute them yourself —
    the arithmetic here is exact and yours may not be.

    Args:
        plan: what each category actually costs
        envelopes: the ceiling for each category, from allocate_budget
    """
    return _verify(plan, envelopes)


# Inject the real coverage list into the docstrings, so it can never drift
# out of sync with the corpus. A hand-typed list would go stale silently.
for _fn in (estimate_costs, allocate_budget, verify_plan):
    if _fn.__doc__:
        _fn.__doc__ = _fn.__doc__.replace("{countries}", _COUNTRIES)

TOOLS = [estimate_costs, allocate_budget, verify_plan]


# ---------------------------------------------------------------------------
# System prompt.
#
# Dedicated to this sub-agent; never reuse the orchestrator's. Production
# guidance is consistent on this, and free-form delegation is a documented
# failure mode.
# ---------------------------------------------------------------------------

INSTRUCTIONS = f"""You are the Budget & Cost expert in a travel planning system.

Your job is money, and only money. You do two things:
1. Set spending ceilings for a trip before other agents search.
2. Check a finished plan against those ceilings.

You do NOT recommend destinations, hotels, restaurants, flights or
activities. Other agents own those. If asked, say so and hand back.

RULES

Never do arithmetic yourself. Call the tools and report what they return.
If a figure did not come from a tool, do not state it.

Your cost data is U.S. State Department per diem — the maximum reimbursable
for government travel. It is an UPPER BOUND, not a market price. Say so when
you quote it. Never present it as what a hotel will actually charge.

Coverage is limited to: {_COUNTRIES}
If a destination is not covered, say which ones are and stop. Do not guess,
do not substitute a nearby country, do not call the tool again with a
different spelling.

"constrained" is not a refusal. It means the trip works if lodging comes in
under a stated nightly rate. Give the user that number. Only "infeasible"
means the trip cannot happen.

If a tool reports stale=true, the underlying rate has not been surveyed in
years. Say so plainly rather than presenting it as current.

Answer in a few sentences. Lead with the number that answers the question.
"""


def build_agent():
    """Construct the deep agent.

    CHECK THESE TWO LINES against your working hello_agent.py — the model
    construction is the part that varies with the provider adapter, and I
    could not verify it against your installed deepagents version. Everything
    else in this file is independent of that choice.
    """
    from deepagents import create_deep_agent

    model = os.getenv("BUDGET_AGENT_MODEL",
                      "openrouter:inclusionai/ling-3.0-flash:free")

    return create_deep_agent(
        tools=TOOLS,
        instructions=INSTRUCTIONS,
        model=model,
    )


def ask(agent, question: str) -> str:
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    return result["messages"][-1].content


# ---------------------------------------------------------------------------
# Demo path — tools only, no model, no API key, no tokens.
# ---------------------------------------------------------------------------

def demo() -> None:
    fixture = Path(__file__).resolve().parent.parent / "fixtures" / "sample_plan.json"
    data = json.loads(fixture.read_text(encoding="utf-8"))
    req = data["request"]

    print(f"Corpus: {len(Corpus())} locations, "
          f"{len(Corpus().countries())} countries\n")

    print("1. estimate_costs")
    est = estimate_costs(req["destination"], req["nights"], req["travelers"])
    print(f"   {req['travelers']} people, {req['nights']} nights in "
          f"{req['destination']}: ${est['estimated_total']} "
          f"(lodging ${est['lodging_total']}, meals ${est['meals_total']})\n")

    print("2. allocate_budget")
    alloc = allocate_budget(req["total_budget"], req["destination"],
                            req["nights"], req["travelers"])
    print(f"   ${req['total_budget']} -> {alloc['status'].upper()}")
    for name, amount in alloc["envelopes"].items():
        print(f"     {name:<16} ${amount}")
    print()

    print("3. verify_plan — plan within budget")
    ok = verify_plan(data["plan"], alloc["envelopes"])
    print(f"   {ok['status']}  deficit ${ok['deficit']}\n")

    print("4. verify_plan — plan over budget")
    bad = verify_plan(data["over_budget_plan"], alloc["envelopes"])
    print(f"   {bad['status']}  deficit ${bad['deficit']}  "
          f"({bad['violation_type']})")
    for name, c in bad["per_category"].items():
        if not c["ok"]:
            print(f"     {name}: spent ${c['spent']} vs ceiling "
                  f"${c['ceiling']} — over by ${c['over_by']}")
    print()

    print("5. out-of-scope destination")
    miss = estimate_costs("MALDIVES", nights=3)
    print(f"   covered={miss['covered']} — {miss['reason'][:80]}...")


def main() -> int:
    if "--demo" in sys.argv:
        demo()
        return 0

    try:
        agent = build_agent()
    except Exception as exc:                      # noqa: BLE001
        print(f"Could not build the agent: {exc}\n"
              f"Check your .env and the model line in build_agent().\n"
              f"Run with --demo to exercise the tools without a model.")
        return 1

    print("Budget & Cost agent. Ctrl-C to quit.\n")
    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not question:
            continue
        print(f"\n{ask(agent, question)}\n")


if __name__ == "__main__":
    raise SystemExit(main())
