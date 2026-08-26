"""
test_agent.py -- manual test cases for the Money & Customs agent.

Run directly, no pytest required (matches the rest of the group's style):

    python test_agent.py

This prints each question and the agent's answer so you can eyeball
correctness -- same manual-verification approach used in Activities' and
Restaurants' own test blocks elsewhere in the repo.
"""

from agent import answer
from money_tools import get_exchange_rate


def _print_case(title: str, question: str):
    print(f"\n=== {title} ===")
    print(f"Q: {question}")
    print(f"A: {answer(question)}")


if __name__ == "__main__":

    # --- Regression test: the date-substitution bug -----------------------
    # The agent once reported get_exchange_rate's "rate" correctly but wrote
    # its OWN (wrong, ~2-years-stale) date instead of the tool's real "date"
    # field. This check surfaces that immediately if it ever creeps back:
    # compare the tool's raw, ground-truth date against what the agent says.
    print("\n=== REGRESSION: date must come verbatim from the tool ===")
    raw = get_exchange_rate("USD", "EUR")
    print(f"Ground truth from money_tools directly: {raw}")
    print(f"Agent's answer for the same pair:")
    print(answer("What's the current USD to EUR exchange rate?"))
    print(
        f"\n>>> Manually confirm the date above matches the tool's "
        f"real date ({raw['date']}). If it doesn't, the date-substitution "
        f"bug has come back -- check the system prompt's rule about "
        f"reporting fields verbatim."
    )

    # --- Hello world --------------------------------------------------------
    _print_case(
        "Hello world",
        "Just say hello world so I know you're running.",
    )

    # --- Happy path: fully covered country ----------------------------------
    _print_case(
        "Happy path (France, fully covered)",
        "I'm traveling from the USA to France. What's the current exchange "
        "rate, should I tip at restaurants and hotels, and what's the "
        "general price scale like there?",
    )

    # --- Unsupported country: tests the "never invent" rule ------------------
    _print_case(
        "Unsupported country (money customs)",
        "What are the money customs in Brazil?",
    )

    # --- Service-specific filter, through the agent (not just the raw tool) --
    _print_case(
        "Service-specific filter (taxis in India)",
        "Should I tip taxi drivers in India?",
    )

    # --- Income context for a country outside COUNTRY_ISO3 -------------------
    _print_case(
        "Income context, unmapped country",
        "What's the general price scale like in Brazil?",
    )

    # --- Multi-tool query: all three tools in one ask -------------------------
    _print_case(
        "Multi-tool (Morocco)",
        "I'm going from the US to Morocco -- exchange rate, tipping norms, "
        "and general price scale please.",
    )

    print("\n\nAll test cases ran. Review each answer above for correctness "
          "-- this file does not auto-assert pass/fail, same as the rest "
          "of the group's test blocks.")
