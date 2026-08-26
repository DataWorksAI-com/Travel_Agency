"""
direct_path.py — the control condition: same tools, no LLM.

This is what the Orchestrator would do if it called the budget tools directly
instead of going through a Deep Agent. It parses the task with regular
expressions, calls the same functions, and renders the result from a
template.

Because the tools are deterministic, this path cannot vary between runs. So
running the test jig against BOTH paths isolates exactly one thing: what the
LLM layer costs. Any difference in score is introduced by the agent wrapper,
not by the tools.

That is a measured answer to "when should something be an agent versus a
tool?" — a Week 2 learning objective, and the question raised in the Week 1
tracker that was never answered.

Fair-comparison note: the Orchestrator would normally pass structured
arguments, since it already knows the destination and budget in order to
route. Parsing here is a stand-in so both paths receive the identical input
the jig sends. Parsing failures are reported honestly rather than hidden.

    python evaluation/direct_path.py --task "4 nights in Barbados, budget 2000"
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from proposed_envelope_agent.corpus import Corpus            # noqa: E402
from proposed_envelope_agent.tools import allocate_budget    # noqa: E402

CORPUS = Corpus()

SCOPE_WORDS = ("recommend", "suggest", "which hotel", "nice hotel",
               "best hotel", "where should i stay")


def find_destination(task: str) -> tuple[str | None, bool]:
    """Return (name, found). Matches any country or post in the corpus."""
    low = task.lower()
    names: list[str] = []
    for country in CORPUS.countries():
        names.append(country)
        names.extend(CORPUS.posts(country))
    # Longest first, so "Bahamas, The" beats a stray "the".
    for name in sorted(set(names), key=len, reverse=True):
        cleaned = name.replace(", The", "").replace(",", "").strip()
        if len(cleaned) > 3 and cleaned.lower() in low:
            return name, True
    return None, False


def parse(task: str) -> dict:
    low = task.lower()

    nights = None
    m = re.search(r"(\d+)\s*night", low)
    if m:
        nights = int(m.group(1))
    else:
        m = re.search(r"(\d+)\s*day", low)
        if m:                              # a 5-day trip spans 4 nights
            nights = max(1, int(m.group(1)) - 1)

    travelers = 1
    m = re.search(r"(\d+)\s*(?:people|persons?|travell?ers?|adults?)", low)
    if m:
        travelers = int(m.group(1))

    budget = None
    m = re.search(r"(?:budget|under|below|max(?:imum)?)\D{0,12}(\d[\d,]*)", low)
    if not m:
        m = re.search(r"\$\s?(\d[\d,]*)", low)
    if m:
        budget = int(m.group(1).replace(",", ""))

    destination, found = find_destination(task)
    return {"nights": nights, "travelers": travelers, "budget": budget,
            "destination": destination, "destination_found": found}


def render(task: str) -> str:
    if any(w in task.lower() for w in SCOPE_WORDS):
        return ("Recommending accommodation is not this agent's job — another "
                "agent owns that. This agent sets and checks budgets. To do "
                "that it needs a total budget, a trip length and a party size.")

    p = parse(task)

    if not p["destination_found"]:
        return (f"That destination is not covered by the published cost data "
                f"available here. Covered destinations are: "
                f"{', '.join(CORPUS.countries())}.")

    if p["budget"] is None or p["nights"] is None:
        missing = [n for n, v in (("total budget", p["budget"]),
                                  ("trip length", p["nights"])) if v is None]
        return f"This needs a {' and a '.join(missing)} before it can be costed."

    r = allocate_budget(p["budget"], p["destination"],
                        nights=p["nights"], travelers=p["travelers"])

    if not r.get("covered", True):
        return (f"That destination is not covered. Covered destinations are: "
                f"{', '.join(CORPUS.countries())}.")

    env = r["envelopes"]
    head = (f"{p['nights']} nights in {r['destination']} for {p['travelers']} "
            f"traveller(s) on ${p['budget']}: {r['status']}.")

    if r["status"] == "infeasible":
        return (f"{head} Meals alone come to ${env['meals']}, which the budget "
                f"does not cover, so it is short by ${r['deficit']}. No lodging "
                f"choice changes that.")

    if r["status"] == "constrained":
        return (f"{head} It is workable only if lodging comes in at or below "
                f"${r['max_nightly_lodging']} per night. Meals are budgeted at "
                f"${env['meals']}, with ${env['reserve']} held back as reserve. "
                f"Nothing is left for activities or local transport.")

    return (f"{head} Lodging ${env['lodging']}, meals ${env['meals']}, "
            f"activities ${env['activities']}, local transport "
            f"${env['local_transport']}, reserve ${env['reserve']}.")


def main() -> int:
    args = sys.argv[1:]
    if "--task" in args:
        i = args.index("--task")
        task = " ".join(args[i + 1:])
    else:
        task = " ".join(args)
    if not task.strip():
        print('Usage: python evaluation/direct_path.py --task "your task"')
        return 1
    print(render(task))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
