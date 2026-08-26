# Orchestrator Design — Open Decisions

This skeleton runs today (`python orchestrator.py`) against placeholder
imports, degrading every missing subagent to a plain `[X unavailable]`
message rather than crashing. That's deliberate — it means real subagents
can be wired in one at a time via `orchestrator_config.py` without the
whole thing ever being in a broken state.

The decisions below are the ones the code currently guesses at. Each is
marked with a `TODO` in the actual file it affects — this doc is the
one-page summary to bring to the group, not a replacement for reading
the code.

## 1. Ask vs. assume (system-wide)
**Status:** proposed, not yet agreed by everyone.
Budget and Restaurants already never ask follow-up questions. Destination
and Money & Customs don't have a stated policy. `_assemble_itinerary` in
`orchestrator.py` currently has no special handling for "Assumption:"
lines from subagents — worth deciding whether those should be surfaced
together in the final itinerary once every subagent adopts the policy.

## 2. Integration contract (callable vs. dict spec)
**Status:** worked around, not resolved.
`subagent_client.LocalFunctionClient.from_dict_spec()` is a stopgap
specifically for Flights' current `flights_subagent = {...}` shape. If the
group aligns Flights to expose `build_agent()`/`answer()` like every other
subagent, `orchestrator_config._build_flights_client()` gets simpler (see
the commented-out alternative already sitting in that function).

## 3. Where Money & Customs plugs in
**Status:** RESOLVED 26 Aug 2026 — its reply is no longer forwarded to any
other subagent. The guess below was confirmed in review, negatively: one agent's
response must not be passed into another agent's prompt. Every subagent now
talks to the orchestrator and to nobody else. Money & Customs instead gets its
own section in `_assemble_itinerary`, which it never had — previously its reply
was fetched, injected into Flights' and Restaurants' prompts, printed to DEBUG,
and never shown to the traveller at all.

The superseded reasoning, kept for the record:
The orchestrator calls Money & Customs once, in `_call_money_customs_context()`,
and folds the result into Flights' and Restaurants' task strings, but
NOT Activities'. Two things worth double-checking with the group:
  - Is Activities really the right one to exclude? (assumption, not fact)
  - Should the same blurb go to all three, or should each subagent get a
    more tailored slice (e.g. Restaurants gets tipping specifically,
    Flights gets nothing customs-related at all, just the exchange rate)?

## 4. Failure handling for the parallel subagents
**Status:** NOT implemented — currently just passes through whatever
came back, error message or not.
`_run_parallel_subagents()` in `orchestrator.py` has no policy yet for
"what if Flights/Restaurants/Activities comes back with a problem." Real
options: omit that section of the itinerary and say so plainly, retry
once, or something else. Whatever gets decided, it belongs in this one
function — not scattered across each subagent's own code.

## 5. The biggest unresolved gap: turning prose into Budget's line items
**Status:** RESOLVED 26 Aug 2026 via option (c) — see `orchestrator_costs.py`.
Budget receives a verified JSON array of `{source, category, name, cost,
currency, per}` line items plus an explicit list of categories with no figure
and why. Option (a), an LLM extraction call, was rejected: it would add a
second model whose job is to read prose and emit numbers, a new place for
figures to be invented, introduced to fix a problem entirely about invented
figures. Extraction is deterministic and every figure is verified to appear
verbatim in the reply it is attributed to. Option (b), a structured block at
the source, is still the better long-term answer and still needs group buy-in.

The superseded description, kept for the record:
Budget's actual tools (`aggregate_costs`, etc.) need structured
`{"category", "name", "cost"}` dicts, not prose. But every other subagent
returns natural-language text, per the shared "one self-contained message"
contract. Something has to bridge this gap. Three real options, worth a
real decision rather than defaulting to whichever is easiest to code:
  (a) An LLM call inside the orchestrator that extracts structured line
      items from the three subagents' text replies.
  (b) Ask Flights/Restaurants/Activities to also return a small
      structured block alongside their prose — this breaks their current
      "one message, no structure" contract, so it's not a small ask.
  (c) Something else (a shared schema all subagents adopt from the start,
      for instance).
This is probably the single highest-priority item to resolve next,
since it blocks Budget from ever running correctly against real
subagent output.

## 6. Model choice for the orchestrator itself
**Status:** not yet chosen — no model is wired in at this skeleton stage,
since none of the orchestrator's own logic currently calls an LLM directly
(everything above is deterministic Python control flow). If item #5 is
solved via option (a) above, that's the first place a model choice
actually matters for this file, and it's worth not defaulting to the
cheapest option, since a bad extraction here corrupts Budget's entire
input.

## 7. SLIM transport
**Status:** designed, not implemented.
`subagent_client.SlimSubagentClient` shows the real wiring shape (per
agntcy_app_sdk / slima2a), but every subagent in this repo currently lives
as a plain Python function, not a separately-running A2A server — so
there is nothing for a real SLIM connection to reach yet. This becomes
relevant only if/when the group actually deploys subagents as separate
services (e.g. Docker Compose, one container per subagent). Until then,
`LocalFunctionClient` is what actually runs.
