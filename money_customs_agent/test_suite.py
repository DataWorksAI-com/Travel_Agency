"""
test_suite.py -- consolidated test suite for the Money & Customs Agent setup.

Combines quick_test.py, retry_test.py, test_france.py, test_marrakech.py, and
test_new_countries.py into one file, organized by what each section actually
needs to run:

  SECTION A -- money_tools.py only. No API key, no LLM. Needs `requests` for
               live network calls and `chromadb` for the semantic-search tier.
  SECTION B -- money_customs_agent.py, full stack. Needs OPENROUTER_API_KEY
               in the shared .env file, plus langchain-openrouter and
               deepagents installed.

One correction made while merging: quick_test.py's third case labeled
Vietnam a "genuinely unsupported country" -- that was true when the file
was written, but Vietnam was added to the corpus in the same session
(now 22 countries total). Using it here would test the opposite of what
the comment claims, so that case now uses Kenya instead, which is
genuinely absent from the corpus.

retry_test.py was an exact duplicate of quick_test.py's second case
(same query, no loop) -- it reads like an attempt to check whether the
semantic-match phrasing resolves consistently across runs. Turned into an
actual 3x reliability loop in Section B instead of keeping a redundant
single-run duplicate.
"""

import json


# ===========================================================================
# SECTION A -- money_tools.py directly. No agent, no API key. A.2 and A.6
# use the semantic tier (needs chromadb). A.7 makes a live
# get_comparative_context call (needs network: Frankfurter + World Bank).
# ===========================================================================

def section_a():
    from money_tools import (
        get_money_customs,
        search_money_customs,
        get_comparative_context,
    )

    print("=== A.1: France -- exact match, invalid service, and a real typo ===")
    print(json.dumps(search_money_customs("France", service="beach clubs"), indent=2))
    print(json.dumps(search_money_customs("France", service="taxis"), indent=2))
    print(json.dumps(search_money_customs("Fracne"), indent=2))

    print("\n=== A.2: Marrakech -- semantic-tier confidence on a city, not a country ===")
    print(json.dumps(search_money_customs("Marrakech"), indent=2))

    print("\n=== A.3: Exact match on each of the 5 newly added countries ===")
    for country in ["Aruba", "Barbados", "Maldives", "Seychelles", "Vietnam"]:
        r = get_money_customs(country)
        print(f"{country}: found={r['found']}, tipping={r['tipping_expected']}, "
              f"haggling={r['haggling_expected']}")

    print("\n=== A.4: Confirm the two previously-bugged cases now resolve by exact match ===")
    print("(match_score should be null on both -- exact match, semantic tier never reached)")
    print(json.dumps(search_money_customs("Aruba"), indent=2))
    print(json.dumps(search_money_customs("Barbados"), indent=2))

    print("\n=== A.5: Typo fallback still works on a newly added country ===")
    print(json.dumps(search_money_customs("Vietnem"), indent=2))  # should resolve to Vietnam

    print("\n=== A.6: A genuinely unsupported country (not one of the 22) ===")
    # NOTE: this replaces quick_test.py's original Vietnam case -- Vietnam is
    # now supported, so it no longer demonstrates unavailable-data handling.
    print(json.dumps(search_money_customs("Kenya"), indent=2))

    print("\n=== A.7: Live network call -- needs internet + chromadb installed ===")
    print(json.dumps(get_comparative_context("USD", "Vietnam"), indent=2))


# ===========================================================================
# SECTION B -- money_customs_agent.py, full stack. Requires
# OPENROUTER_API_KEY in the shared .env file.
# ===========================================================================

def section_b():
    from money_customs_agent import answer, answer_with_trace

    print("=== B.1: Fuzzy match (typo) via the agent ===")
    print(answer("What are the money customs in Mexcio?"))

    print("\n=== B.2: A description, not a place name (Rule 10) -- reliability x3 ===")
    print("(expected every run: 'Note: I interpreted \"south of the US border\" as Mexico.'")
    print(" then Mexico's customs -- never US customs, never a follow-up question --")
    print(" ending with a 'Sources:' line that says the entry is not independently verified)")
    # Same query run 3 times: LLM tool-calling is stochastic, so this checks
    # whether the semantic-match resolution is consistent across runs rather
    # than a one-off. Uses answer_with_trace() instead of answer() so we can
    # see the ACTUAL string that reached search_money_customs each run --
    # the final text alone can't tell us whether the model retried with
    # "Mexico" after a failed literal attempt, or never tried at all.
    for i in range(3):
        print(f"\n--- Run {i + 1} ---")
        result = answer_with_trace("What are the tipping norms south of the US border?")
        print("Message:", result["message"])
        print("Tool calls:")
        for step in result["steps"]:
            print(f"  {step['tool']}(input={step['input']})")
            print(f"    -> {step['output']}")

    print("\n=== B.3: Genuinely unsupported country via the agent ===")
    print(answer("What are the money customs in Kenya?"))


if __name__ == "__main__":
    print("############################################")
    print("# SECTION A -- money_tools.py directly")
    print("############################################\n")
    section_a()

    print("\n\n############################################")
    print("# SECTION B -- full agent (needs OPENROUTER_API_KEY)")
    print("############################################\n")
    section_b()
