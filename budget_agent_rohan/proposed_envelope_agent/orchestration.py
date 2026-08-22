"""
orchestration.py — a one-call helper for the orchestrator's pre-phase.

WHY THIS EXISTS

The orchestrator already runs a pre-phase: `_call_money_customs_context()`
executes before the parallel subagents and its output is prepended to their
task strings. This is the same shape, for spending ceilings.

Running Budget only at the end means it can report an overspend but never
prevent one — Flights and Restaurants have already chosen by then. Handing
them a ceiling first means they search inside a budget instead of proposing
options that get discarded. HiMAP-Travel (arXiv 2603.04750) measured this:
removing the up-front allocation cost 12.98 points of final pass rate,
mostly from budget failures.

DESIGN NOTES

No LLM. No API key. No network. This is a plain function over a committed
dataset, so it adds roughly 0.1s and cannot vary between runs. That matters
because the orchestrator's own guidance is that agents are for
decision-making and tools are for computation — splitting a budget is
computation.

FAIL-SAFE BY DESIGN. If the destination isn't covered, or trip length can't
be determined, this returns an empty string and the orchestrator prepends
nothing. Behaviour is then exactly as it is today. It can improve the task
strings; it can never break them.
"""

from __future__ import annotations

import re

from .corpus import Corpus
from .tools import allocate_budget

_corpus = Corpus()

WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "fourteen": 14, "a": 1, "an": 1,
}


def _count_before(text: str, unit: str) -> int | None:
    m = re.search(rf"(\d+)\s*{unit}", text)
    if m:
        return int(m.group(1))
    words = "|".join(WORD_NUMBERS)
    m = re.search(rf"\b({words})\s+{unit}", text)
    return WORD_NUMBERS[m.group(1)] if m else None


def _find_destination(text: str) -> str | None:
    """Match any country or post in the corpus. Longest name first, so
    'Bahamas, The' wins over a stray 'the'."""
    low = text.lower()
    names: list[str] = []
    for country in _corpus.countries():
        names.append(country)
        names.extend(_corpus.posts(country))
    for name in sorted(set(names), key=len, reverse=True):
        cleaned = name.replace(", The", "").replace(",", "").strip()
        if len(cleaned) > 3 and cleaned.lower() in low:
            return name
    return None


def _parse_budget(stated_budget: str, task: str) -> int | None:
    for source in (stated_budget or "", task or ""):
        m = re.search(r"(?:budget|under|below|max(?:imum)?)?\D{0,12}?\$?\s?"
                      r"(\d[\d,]{2,})", source)
        if m:
            return int(m.group(1).replace(",", ""))
    return None


def ceilings_for(task: str, stated_budget: str = "",
                 destination_country: str = "") -> str:
    """Return a short line for the orchestrator to prepend, or "".

    Args:
        task: the user's request, as passed to plan_trip
        stated_budget: plan_trip's stated_budget argument, e.g. "$2000"
        destination_country: plan_trip's destination_country argument.
            Used in preference to guessing from the task text.

    Returns:
        One plain-language line naming each category's ceiling, ready to
        prepend to a subagent's task string. Empty string if the
        destination isn't covered or the trip length is unknown — in which
        case the orchestrator should prepend nothing and carry on.
    """
    haystack = f"{destination_country} {task}"

    destination = _find_destination(haystack)
    if destination is None:
        return ""

    nights = _count_before(task.lower(), r"nights?")
    if nights is None:
        days = _count_before(task.lower(), r"days?")
        nights = max(1, days - 1) if days else None
    if nights is None and re.search(r"\b(a|one)\s+week\b", task.lower()):
        nights = 6
    if nights is None:
        return ""

    travelers = _count_before(
        task.lower(), r"(?:people|persons?|travell?ers?|adults?|guests?)") or 1

    budget = _parse_budget(stated_budget, task)
    if budget is None:
        return ""

    result = allocate_budget(budget, destination, nights=nights,
                             travelers=travelers)
    if not result.get("covered", False):
        return ""

    env = result["envelopes"]
    line = (
        f"BUDGET CEILINGS (do not exceed): lodging ${env['lodging']}, "
        f"meals ${env['meals']}, activities ${env['activities']}, "
        f"local transport ${env['local_transport']}. "
        f"${env['reserve']} is held back as reserve and is not available "
        f"to spend."
    )

    if result["status"] == "constrained":
        line += (f" This budget is tight: lodging must come in at or below "
                 f"${result['max_nightly_lodging']} per night.")
    elif result["status"] == "infeasible":
        line += (f" Note: this budget does not cover meals alone "
                 f"(short by ${result['deficit']}), so it is not workable "
                 f"at this destination.")

    if result.get("stale"):
        line += (" These figures come from a rate that has not been "
                 "re-surveyed recently, so treat them as approximate.")

    return line
