"""Turn the other subagents' prose into verified line items for Budget.

WHY THIS EXISTS

ORCHESTRATOR_DESIGN.md #5 calls this "the biggest unresolved gap in the whole
skeleton", and until now it was not closed: `_build_budget_task` concatenated
every subagent's free-text reply into one string and handed it to Budget
as-is. The objection raised in review is the correct reading of that -- passing one agent's
response into another agent's prompt is relaying, not orchestrating, and it
makes the orchestrator a message bus between subagents rather than the thing
that decides. It is also not the agreed architecture.

The design doc offered three routes:

  (a) an LLM call in the orchestrator that extracts structured line items
  (b) ask Flights/Restaurants/Activities to also emit a structured block,
      which breaks their "one self-contained message" contract
  (c) something else

This is (c), and it is chosen over (a) deliberately. (a) would add a second
model call whose job is to read prose and emit numbers -- a NEW place for
figures to be invented, introduced to fix a problem that is entirely about
invented figures. Budget already billed "$425/person RT from Boston" for a
flight Flights had just reported it could not find; an extraction model is
free to do the same, and nothing downstream could tell.

Currency amounts are mechanically findable, so extraction here is
deterministic and, more importantly, VERIFIABLE: every figure this module
emits is checked to appear verbatim in the reply it is attributed to
(`_verify`). A line item that cannot be traced back to its source text is
dropped rather than passed on. That is a guarantee an LLM extractor cannot
offer.

(b) is still worth doing eventually -- a structured block at the source beats
parsing prose downstream -- but it needs four other people to change their
agents' output contract, and this does not need anyone's permission.

WHAT BUDGET RECEIVES

Not transcripts. A JSON array of verified line items, each attributed to the
agent that produced it, plus an EXPLICIT list of categories for which no
figure exists and why. The absence list is the half that matters: Budget's
invented flight cost happened because "Flights returned nothing" was
indistinguishable from "nobody mentioned flights".
"""

import json
import re

# Slots that can produce a cost. Destination and Money & Customs are excluded
# on purpose: they return climate, holidays, exchange rates and tipping norms,
# and an exchange rate is a ratio, not a trip cost. Reading "1 USD = 16.93 MXN"
# as a line item is exactly the class of mistake this module exists to prevent.
PRICED_SLOTS = ("flights", "restaurants", "activities")

# Canonical category per slot, matching what Budget's aggregate_costs expects.
CATEGORY = {
    "flights": "flights",
    "restaurants": "food",
    "activities": "activities",
}

# Sentences an agent uses when it ran correctly but holds nothing for this
# request. NOT the same as a failure: "No flights found for these dates" is a
# correct answer. Shared with orchestrator_agent so there is one copy.
NO_DATA_PHRASES = (
    "no flight",
    "no cached flight",
    "hold no data",
    "no data for",
    "not covered",
    "outside my coverage",
    "not in this agent's curated corpus",
    "no activity in the corpus",
    "is not covered by local data",
    "could not find",
    "no results",
    # Money & Customs' own wording for the same thing. Its rule 7 says to
    # report that "the information isn't available for that country/service",
    # which none of the phrases above match -- so without these two, a genuine
    # no-data reply from that agent would be read as a priced answer and its
    # absence would never be declared to Budget.
    "isn't available for",
    "is not available for",
)

# A currency amount, symbol-first or ISO-suffixed. A bare number is never
# matched: "rated 4.4/5", "5 nights", "2 travellers" and "10-15%" must not
# become costs. Group 1/3 is the number, 2/4 the currency.
_AMOUNT = re.compile(
    r"[$£€]\s?(\d[\d,]*(?:\.\d{1,2})?)"                      # $1,400.00
    r"|(?<![\w/.])(\d[\d,]*(?:\.\d{1,2})?)\s?(USD|EUR|GBP|MXN|JPY|THB)\b",
    re.IGNORECASE,
)

_SYMBOL_CURRENCY = {"$": "USD", "£": "GBP", "€": "EUR"}

# A price written as a RANGE. "$80-120 per person", "$130 to $180", "$15–25".
#
# _AMOUNT alone gets this wrong in two different directions, and both understate
# the trip:
#
#   "$80-120"    -> matches $80 only. The second number has no symbol, so the
#                   high end is invisible and Budget prices the cheapest case.
#   "$80 - $120" -> matches BOTH, as two independent line items, so one activity
#                   is counted twice and neither is labelled a range.
#
# Systematically optimistic either way, in a system whose entire purpose is not
# making a trip look more affordable than it is. Ranges are found FIRST and
# their spans excluded from the single-amount pass, so a range yields exactly
# one item carrying both ends.
_RANGE = re.compile(
    r"[$£€]\s?(\d[\d,]*(?:\.\d{1,2})?)"
    r"\s*(?:-|–|—|to)\s*"
    r"[$£€]?\s?(\d[\d,]*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)

# "per person" / "per night" changes what a number MEANS, so it travels with
# it. Budget multiplying a per-person fare by party size is correct; doing it
# to a total is not, and the prose is the only place that distinction lives.
_PER_PATTERNS = (
    (re.compile(r"\bper\s+person\b|\beach\b|/\s*person\b|\bpp\b", re.I), "person"),
    (re.compile(r"\bper\s+night\b|/\s*night\b|\bnightly\b", re.I), "night"),
    (re.compile(r"\bper\s+day\b|/\s*day\b|\bdaily\b", re.I), "day"),
    (re.compile(r"\bfor\s+two\b|\btotal\b|\ball\s+in\b", re.I), "total"),
)


# Some sentences contain a currency amount that is NOT a price this system
# produced, and extracting them is worse than missing a real one: they arrive
# in Budget's task indistinguishable from a verified figure.
#
# Found live on 27 Aug 2026. Activities wrote, in passing:
#
#   "With $3,000 total budget for 2 travelers over 5 nights, you have
#    approximately $300/night for accommodation plus activities."
#
# and both numbers were handed to Budget as category "activities", per "night".
# The first was the TRAVELLER'S OWN BUDGET turned into a cost; the second was a
# lodging figure from an agent that does not price lodging. Budget rejected them
# ("malformed data artifacts") -- the honesty rules caught what this extractor
# let through, which is the right layer failing but the wrong one to rely on.
#
#   budget   -- a sentence reasoning ABOUT the budget is describing the
#               constraint, not pricing a good.
#   lodging  -- rule 3 of Budget's brief says no agent here prices lodging, so
#               a lodging amount from any slot came from the model.
_NOT_A_PRICE = (
    re.compile(r"\bbudgets?\b", re.I),
    re.compile(
        r"\b(lodging|accommodations?|hotels?|hostels?|resorts?|airbnbs?"
        r"|guesthouses?|room\s+rates?)\b",
        re.I,
    ),
)


def _is_not_a_price(line: str) -> bool:
    return any(pattern.search(line) for pattern in _NOT_A_PRICE)


# An agent can answer AND disclaim its own numbers in the same reply. Activities
# did exactly that on 27 Aug 2026:
#
#   "The list below is my own compilation of popular regional activities at
#    typical market pricing, not database-verified entries."
#
# ...and then listed prices. _verify passed every one of them, because _verify
# only asks whether the amount appears in the reply -- and it does; the agent
# typed it. Appearing in the reply is not the same as the agent standing behind
# it, and the difference is invisible to a regex looking at one line.
#
# Those figures reached Budget under the heading "PRICED INPUTS ... the
# orchestrator verified that every figure appears verbatim", which is the
# orchestrator asserting something the agent had explicitly denied. That is this
# module's claim to get right, not the agent's.
#
# Matched against the WHOLE reply, not per line: a disclaimer is written once,
# in prose, above or below the list it governs. Locating which lines it covers
# would need to be right about scope, and being wrong about scope here means
# silently costing disclaimed figures again.
#
# These phrases disclaim PROVENANCE ("where this number came from"), not
# precision. Numeric hedging -- "about $35", "approximately $80", "~$44" -- is
# how every agent here writes a real price, and must NOT match, or the guard
# eats the genuine figures it exists to protect.
_DISCLAIMED = re.compile(
    r"not\s+database[-\s]verified"
    r"|not\s+verified|unverified|not\s+sourced|unsourced"
    r"|own\s+compilation"
    r"|typical\s+(?:market\s+)?(?:pricing|prices|costs?)"
    r"|market\s+pricing"
    r"|(?:my|its|their)\s+own\s+knowledge|knowledge\s+base"
    r"|for\s+reference\s+only|general\s+reference"
    r"|not\s+(?:from|in)\s+the\s+database"
    r"|illustrative|indicative\s+pricing|ballpark"
    r"|rough\s+estimates?",
    re.I,
)


def disclaims_own_figures(reply: str) -> bool:
    """True if the agent told us not to trust the numbers it just gave us."""
    return bool(_DISCLAIMED.search(reply or ""))


def _amount_in(text: str) -> float | None:
    """The first currency amount in `text`, or None."""
    match = _AMOUNT.search(text or "")
    if not match:
        return None
    raw = match.group(1) or match.group(2)
    try:
        return float(raw.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def held_no_data(reply: str) -> bool:
    """True if the agent ran but reported it holds nothing for this request."""
    lowered = (reply or "").lower()
    return any(p in lowered for p in NO_DATA_PHRASES)


def _per_unit(text: str) -> str:
    for pattern, unit in _PER_PATTERNS:
        if pattern.search(text):
            return unit
    return ""


def _name_from(line: str) -> str:
    """What the money is for, taken from the start of its own line.

    Subagents write "Villa Toscana - Italian; approx. $44 per person" and
    "Catamaran snorkel cruise -- outdoor, around $110", so the part before the
    first dash is the thing being priced. Falls back to a truncation rather
    than to a guess.
    """
    head = re.split(r"\s+[-–—]{1,2}\s+|:\s+|;\s+", line.strip(), maxsplit=1)[0]
    head = re.sub(r"^[\s*\-•\d.)]+", "", head).strip()
    return (head[:60] or line.strip()[:60]) or "unnamed"


def _verify(cost_text: str, reply: str) -> bool:
    """The extracted amount must be findable in the source reply.

    The whole point of this module: a figure Budget prices has to be traceable
    to the agent that reported it. Compared with separators stripped so that
    "$1,400" matching a reply written "$1400" is not treated as invention.
    """
    norm = lambda s: re.sub(r"[,\s]", "", s)
    return norm(cost_text) in norm(reply)


def extract_line_items(slot: str, reply: str) -> list[dict]:
    """Verified line items from one agent's prose. Never raises."""
    if not reply or slot not in CATEGORY:
        return []
    if held_no_data(reply):
        # An agent saying "no flights found" may still mention a number in
        # passing; treating this reply as priced is how a non-answer becomes a
        # cost.
        return []

    disclaimed = disclaims_own_figures(reply)

    items, seen = [], set()
    for line in reply.splitlines():
        if _is_not_a_price(line):
            continue

        # Ranges first, and remember where they sat, so the single-amount pass
        # below cannot re-report either end as a price of its own.
        spans = []
        for match in _RANGE.finditer(line):
            low_text, high_text = match.group(1), match.group(2)
            if not (_verify(low_text, reply) and _verify(high_text, reply)):
                continue
            try:
                low, high = float(low_text.replace(",", "")), float(high_text.replace(",", ""))
            except ValueError:
                continue
            if low <= 0 or high < low:
                # "$120 to $80" is not a range, and neither is a match that ran
                # across two unrelated figures. Leave it to the pass below.
                continue
            spans.append(match.span())
            currency = _SYMBOL_CURRENCY.get(match.group(0).strip()[0], "USD")
            key = (low, currency, _name_from(line))
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "source": slot,
                "category": CATEGORY[slot],
                "name": _name_from(line),
                "cost": low,
                "cost_high": high,
                "currency": currency,
                "per": _per_unit(line),
                "unverified": disclaimed,
                "quote": line.strip()[:200],
            })

        for match in _AMOUNT.finditer(line):
            if any(s <= match.start() < e for s, e in spans):
                continue
            raw = match.group(1) or match.group(2)
            currency = (
                _SYMBOL_CURRENCY.get(match.group(0).strip()[0])
                or (match.group(3) or "USD").upper()
            )
            try:
                cost = float(raw.replace(",", ""))
            except ValueError:
                continue
            if cost <= 0:
                continue
            if not _verify(match.group(0), reply):
                continue
            key = (cost, currency, _name_from(line))
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "source": slot,
                "category": CATEGORY[slot],
                "name": _name_from(line),
                "cost": cost,
                "currency": currency,
                "per": _per_unit(line),
                "unverified": disclaimed,
                "quote": line.strip()[:200],
            })
    return items


def absences(replies: dict[str, str], is_failure) -> list[dict]:
    """Priced categories with no figure, and why. The half that stops invention.

    `is_failure` is passed in rather than imported so this module stays free of
    a dependency on the seam.
    """
    out = []
    for slot in PRICED_SLOTS:
        reply = replies.get(slot)
        if reply is None:
            out.append({"category": CATEGORY[slot], "source": slot,
                        "reason": "the agent was not called"})
        elif is_failure(reply):
            out.append({"category": CATEGORY[slot], "source": slot,
                        "reason": "the agent did not run"})
        elif held_no_data(reply):
            out.append({"category": CATEGORY[slot], "source": slot,
                        "reason": "the agent ran and reported it holds no data for this request"})
        elif not extract_line_items(slot, reply):
            out.append({"category": CATEGORY[slot], "source": slot,
                        "reason": "the agent answered but published no prices"})
    return out


def build_budget_brief(
    task: str,
    replies: dict[str, str],
    is_failure,
    stated_budget: str = "",
    trip_facts: str = "",
) -> str:
    """Budget's task: decided inputs, not other agents' transcripts."""
    items = [i for slot in PRICED_SLOTS for i in extract_line_items(slot, replies.get(slot, ""))]

    # Second, independent guard on the same failure. _NOT_A_PRICE drops the
    # sentence; this drops the VALUE, wherever it appears and however it was
    # phrased. The traveller's own budget is the one number in the whole run
    # that provably came from the traveller and not from an agent, and this is
    # the only function that knows it -- so costing it is always wrong, and it
    # is cheap to make certain of that here rather than trust one regex.
    budget_amount = _amount_in(stated_budget)
    if budget_amount is not None:
        items = [i for i in items if i["cost"] != budget_amount]

    missing = absences(replies, is_failure)

    # `quote` is dropped HERE, and this is the whole point rather than a detail.
    #
    # The quote is the sentence a figure was found in, kept on the line item so
    # the orchestrator can audit its own extraction and so a human can trace a
    # number back to the agent that said it. But putting it in Budget's task
    # would send another subagent's prose into a subagent's prompt, which is
    # precisely the relaying this module was written to stop -- caught by
    # test_orchestrator_costs, which found "A romantic trattoria noted for
    # handmade pasta" reaching Budget through this field.
    #
    # Budget gets the decision (what, how much, per what, from whom). It does
    # not get the transcript.
    # Split before rendering. An agent that disclaimed its own figures must not
    # have them appear under a heading that calls them verified -- that heading
    # is the orchestrator vouching for them, and here it would be vouching
    # against the source's own words.
    disclaimed = [i for i in items if i.get("unverified")]
    items = [i for i in items if not i.get("unverified")]

    _render = lambda rows: [
        {k: v for k, v in row.items() if k not in ("quote", "unverified")}
        for row in rows
    ]
    for_budget = _render(items)

    parts = [f"Traveler's request: {task}"]
    if trip_facts:
        parts.append(trip_facts)
    if stated_budget:
        parts.append(f"Stated budget: {stated_budget}")

    parts.append(
        "PRICED INPUTS. The orchestrator extracted these from the specialist "
        "agents' replies and verified that every figure appears verbatim in the "
        "reply it is attributed to. This is the complete set of costs known to "
        "this system.\n"
        + (json.dumps(for_budget, indent=2) if for_budget else "[]  (no priced inputs at all)")
    )

    if disclaimed:
        sources = sorted({i["source"] for i in disclaimed})
        parts.append(
            "FIGURES THE SOURCE AGENT DISCLAIMED. These came from "
            + ", ".join(sources)
            + ", which stated in its own reply that these numbers are not "
            "verified data -- typical or illustrative pricing rather than "
            "anything it looked up. They are listed so you can mention them as "
            "rough context, clearly labelled as unverified. Do NOT add them to "
            "any total.\n"
            + json.dumps(_render(disclaimed), indent=2)
        )

    if missing:
        parts.append(
            "NO FIGURE AVAILABLE for these categories:\n"
            + "\n".join(f"- {m['category']} ({m['source']}): {m['reason']}." for m in missing)
        )

    parts.append(
        "RULES\n"
        "1. Cost ONLY the priced inputs above. Do not add, estimate, benchmark or "
        "recall a figure for anything else -- not from comparable cities, not from "
        "your knowledge base, not as a placeholder.\n"
        "2. For every category under NO FIGURE AVAILABLE, say plainly that it is "
        "unavailable and why. Leave it out of the total.\n"
        "3. Do not price lodging. No agent in this system provides accommodation "
        "costs, so any lodging figure would come from nowhere.\n"
        "4. Respect the 'per' field: 'person' multiplies by party size, 'night' by "
        "nights, 'total' by neither.\n"
        "5. If what remains is too incomplete to total honestly, say so instead of "
        "producing a total. An itinerary that reports what is missing is more "
        "useful than one with a confident wrong number.\n"
        "6. Anything under FIGURES THE SOURCE AGENT DISCLAIMED is not costed "
        "data. Keep it out of every total and subtotal. You may mention it as "
        "rough context, but say plainly that the agent did not stand behind it.\n"
        "7. An item with 'cost_high' was quoted as a RANGE, from 'cost' to "
        "'cost_high'. Show the range. When you total, use 'cost_high' -- a "
        "traveller misled downwards discovers it at the destination, with no "
        "way to recover; one misled upwards finds money left over. Never "
        "present 'cost' alone as the price of a ranged item."
    )
    return "\n\n".join(parts)
