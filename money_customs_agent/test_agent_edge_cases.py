"""
test_agent_edge_cases.py -- covers the scenarios USD-only testing was
missing: ambiguous home currency (EUR), no currency given, a city name
as destination, a misspelled country, an unmapped country for income,
and an unsupported service.

Two tiers, matching the group's existing manual-script convention (no
pytest):

  PART 1 -- TOOL-LEVEL (money_tools.py directly)
    Deterministic-ish: no LLM involved, so these can genuinely assert
    pass/fail. Still hits live APIs (Frankfurter, World Bank, Open-Meteo),
    so needs network but NOT an API key.

  PART 2 -- AGENT-LEVEL (money_customs_agent.answer())
    The LLM decides the wording, so these can't be asserted as strictly.
    Each one prints the raw reply AND does a best-effort substring check
    for the specific disclosure line each Rule requires (Rule 2's "Note:
    I interpreted...", Rule 4's "Assumption:", Rule 9's "Note: no data
    was found..."). A failed substring check means "go read the reply
    yourself," not necessarily "the agent is broken" -- the LLM might
    have phrased it differently than expected.

Run directly: python test_agent_edge_cases.py
Requires OPENROUTER_API_KEY in the shared .env file for Part 2 (Part 1
will still run without it).
"""

import os
import sys

from money_tools import (
    get_comparative_context,
    get_income_context,
    resolve_location_country,
    search_money_customs,
)

PASS = "PASS"
FAIL = "FAIL"

results = []  # (label, PASS/FAIL, detail)


def record(label, condition, detail=""):
    results.append((label, PASS if condition else FAIL, detail))
    print(f"[{PASS if condition else FAIL}] {label}" + (f" -- {detail}" if detail and not condition else ""))


# ---------------------------------------------------------------------------
# PART 1 -- TOOL LEVEL
# ---------------------------------------------------------------------------

print("=" * 70)
print("PART 1: tool-level (money_tools.py directly, no LLM)")
print("=" * 70)

# 1. EUR is deliberately ambiguous (France vs Germany) -- home side must
#    be skipped entirely, not guessed.
r = get_comparative_context("EUR", "India")
record(
    "EUR home-currency ambiguity is skipped, not guessed",
    r["assumption"] is None and r["home_country"] is None and r["home_customs"] is None,
    f"got assumption={r['assumption']!r}, home_country={r['home_country']!r}",
)
record(
    "EUR case still populates the destination side",
    r["destination_customs"].get("found") is True,
    f"destination_customs={r['destination_customs']}",
)

# 2. An unmapped country for income context should fail cleanly, not guess.
r = get_income_context("Nepal")
record(
    "Unmapped country (Nepal) returns found=False for income context",
    r["found"] is False and "no country code mapping" in (r["error"] or "").lower(),
    f"got {r}",
)

# 3. City name resolution (Rule 9's recovery path).
r = resolve_location_country("Marrakech")
record(
    "resolve_location_country resolves Marrakech -> Morocco",
    r["resolved"] is True and r["country"] == "Morocco",
    f"got {r}",
)

# 4. Ambiguous city name (Paris exists in multiple countries) -- must NOT
#    resolve to a single guess.
r = resolve_location_country("Paris")
record(
    "resolve_location_country flags Paris as ambiguous rather than guessing",
    r["ambiguous"] is True and r["resolved"] is False,
    f"got {r}",
)

# 4b. A description is not a place name -- must find nothing, not a
#     look-alike attraction (Nominatim returned "United States" here).
r = resolve_location_country("south of the US border")
record(
    "resolve_location_country does not resolve a description ('south of the US border')",
    r["resolved"] is False and r["country"] is None,
    f"got {r}",
)

# 5. Misspelled country -- fuzzy tier should catch it and disclose via
#    'adjusted'.
r = search_money_customs("Franse")
record(
    "Misspelled 'Franse' resolves to France via fuzzy match, with 'adjusted' set",
    r.get("found") is True and r.get("country") == "France" and r.get("adjusted"),
    f"got {r}",
)

# 6. Unsupported service for a supported country -- should degrade
#    gracefully (found True, by_service empty, adjusted explains why),
#    not crash or invent a number.
r = search_money_customs("France", service="spa_treatments")
record(
    "Unsupported service degrades gracefully (found True, by_service empty, adjusted set)",
    r.get("found") is True and r.get("by_service") == {} and r.get("adjusted"),
    f"got {r}",
)


# ---------------------------------------------------------------------------
# PART 2 -- AGENT LEVEL (needs OPENROUTER_API_KEY)
# ---------------------------------------------------------------------------

print()
print("=" * 70)
print("PART 2: agent-level (money_customs_agent.answer(), needs OPENROUTER_API_KEY)")
print("=" * 70)

try:
    from money_customs_agent import answer  # loads .env on import
except ImportError as exc:
    print(f"Could not import money_customs_agent: {exc}")
    sys.exit(1)

# A local model (LLM_BACKEND=local) needs no OpenRouter key.
_local = (os.environ.get("LLM_BACKEND") or "").strip().lower() == "local"
_key = os.environ.get("OPENROUTER_API_KEY", "")
if not _local and (not _key or _key.startswith("sk-or-your-key-here")):
    print("OPENROUTER_API_KEY not set -- skipping Part 2. Put your key in "
          "the shared .env file and re-run to cover the agent/LLM-level "
          "scenarios.")
    sys.exit(0)

AGENT_SCENARIOS = [
    {
        "label": "EUR origin (ambiguous) -- agent should not invent a home country",
        "task": "I'm traveling from a Eurozone country to India. What's the "
                "exchange rate, tipping customs, and price scale?",
        "expect_absent": ["assumption: inferred home country"],
    },
    {
        "label": "Exchange rate asked, no home currency given -- agent must state an assumption (Rule 6)",
        "task": "What's the exchange rate in Japan, and should I tip there?",
        "expect_present": ["assumption"],
    },
    {
        "label": "City name as destination -- agent must retry via resolve_location_country (Rule 9)",
        "task": "What are the tipping customs in Marrakech?",
        "expect_present": ["note", "retried as"],
    },
    {
        "label": "Description, not a name -- agent must interpret it and disclose (Rule 10)",
        "task": "What are the tipping norms south of the US border?",
        "expect_present": ["interpreted", "mexico", "sources:", "not independently verified"],
        "expect_absent": ["united states", "18-20%"],
    },
    {
        "label": "Multi-country description -- agent must not pick one country (Rule 10)",
        "task": "What are the tipping customs in the Caribbean?",
        "expect_present": ["per country", "specific country", "each country", "country by country"],
        "match_any": True,
    },
    {
        "label": "Misspelled country -- agent must disclose the correction (Rule 2)",
        "task": "What are the tipping customs in Franse?",
        "expect_present": ["note", "interpreted"],
    },
    {
        "label": "Unmapped country for income context -- agent should say unavailable, not invent",
        "task": "What's the general price scale (income context) like in Nepal?",
        "expect_present": ["not available", "unavailable", "no ", "isn't available"],
        "match_any": True,
    },
    {
        "label": "Unsupported service in a supported country -- should not invent a number",
        "task": "Should I tip for spa treatments in France?",
        "expect_present": [],  # no strict check, read the reply manually
    },
]

for scenario in AGENT_SCENARIOS:
    print("-" * 70)
    print(scenario["label"])
    print(f"Task: {scenario['task']}")
    try:
        reply = answer(scenario["task"])
    except Exception as exc:
        # The model provider failed even after the agent's own retries
        # (e.g. "provider_overloaded"). That says nothing about the agent's
        # behaviour, so record it and move on instead of ending the run.
        record(f"  model call completed (not a behaviour check)", False,
               f"{type(exc).__name__}: {str(exc)[:120]} -- rerun this scenario later")
        continue
    print(f"Reply:\n{reply}\n")

    lowered = reply.lower()

    for phrase in scenario.get("expect_present", []):
        if scenario.get("match_any"):
            continue  # handled below as a group
        record(f"  contains expected phrase: {phrase!r}", phrase.lower() in lowered)

    if scenario.get("match_any") and scenario.get("expect_present"):
        any_hit = any(p.lower() in lowered for p in scenario["expect_present"])
        record(f"  contains at least one of: {scenario['expect_present']}", any_hit)

    for phrase in scenario.get("expect_absent", []):
        record(f"  does NOT contain: {phrase!r}", phrase.lower() not in lowered)


# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------

print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)
n_pass = sum(1 for _, status, _ in results if status == PASS)
n_fail = sum(1 for _, status, _ in results if status == FAIL)
for label, status, detail in results:
    print(f"[{status}] {label}")
print(f"\n{n_pass} passed, {n_fail} failed out of {len(results)} checks.")
if n_fail:
    print("Remember: agent-level FAILs may just mean the LLM phrased the "
          "disclosure differently than expected -- read the printed reply "
          "before assuming a real bug.")
