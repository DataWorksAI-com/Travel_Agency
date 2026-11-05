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
Destination and Money & Customs don't have a stated policy. `_assemble_itinerary` in
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
**Status:** implemented as a provisional guess, worth confirming.
The orchestrator calls Money & Customs once, in `_call_money_customs_context()`,
and folds the result into Flights' task string. Worth double-checking with
the group:
  - Should Flights get the whole blurb, or a more tailored slice (e.g.
    nothing customs-related at all, just the exchange rate)?

## 4. Failure handling for the parallel subagents
**Status:** NOT implemented — currently just passes through whatever
came back, error message or not.
`_run_parallel_subagents()` in `orchestrator.py` has no policy yet for
"what if Flights comes back with a problem." Real
options: omit that section of the itinerary and say so plainly, retry
once, or something else. Whatever gets decided, it belongs in this one
function — not scattered across each subagent's own code.

## 5. Model choice for the orchestrator itself
**Status:** not yet chosen — no model is wired in at this skeleton stage,
since none of the orchestrator's own logic currently calls an LLM directly
(everything above is deterministic Python control flow).

## 6. SLIM transport
**Status:** designed, not implemented.
`subagent_client.SlimSubagentClient` shows the real wiring shape (per
agntcy_app_sdk / slima2a), but every subagent in this repo currently lives
as a plain Python function, not a separately-running A2A server — so
there is nothing for a real SLIM connection to reach yet. This becomes
relevant only if/when the group actually deploys subagents as separate
services (e.g. Docker Compose, one container per subagent). Until then,
`LocalFunctionClient` is what actually runs.
