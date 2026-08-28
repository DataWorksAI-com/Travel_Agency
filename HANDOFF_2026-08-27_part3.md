# Handoff — orchestrator and seam, part 3, 27 Aug 2026

Continues `HANDOFF_2026-08-27.md` and `HANDOFF_2026-08-27_part2.md`. Read both
first. Written for a fresh session with no memory of this one.

Working directory: `C:/Users/rohan/Documents/wt-ui`
Branch: `ui_chainlit_rohan`, **pushed**, 0 ahead / 0 behind at `99e5338`.

---

## 0. YOUR FIRST TASK, AND THE ORDER IT MUST BE DONE IN

The job is to **produce an Orchestrator Agent architecture diagram in Miro**
(via the Miro MCP connector), to sit alongside the six agent diagrams the team
already has on the "Travel Agents" board.

Do it in this order. The order is the point.

1. Read `HANDOFF_2026-08-27.md`, then `_part2.md`, then this file.
2. **Then read the live code and derive the architecture yourself.**
3. **Only then** look at `docs/orchestrator_architecture.svg`, and treat it as a
   suspect to check rather than a source to copy.
4. Build the Miro diagram from what the code says.

### Do not trust the SVG, and do not trust this document's summary either

`docs/orchestrator_architecture.svg` was produced in the previous session. It
carries a DRAFT banner because it is **not verified**. Two structural errors
were already found in it and fixed *after* it was first drawn:

- it showed the deterministic path flowing into the deep agent. It does not —
  `_plan_trip_fixed` calls `ask_slot` directly and never enters
  `orchestrator_agent`.
- it showed the budget slot running *before* the ordering gate. The real order
  is gate → `build_budget_brief` → `ask_slot`.

Both errors came from drawing what the system *looks like* rather than tracing
the call order. Assume more remain. The same caution applies to the prose
below: it was written by the session that made those mistakes.

**Read these files and derive the flow from them, not from any diagram:**

```
orchestrator.py          plan_trip, _plan_trip_fixed, ask_slot, _gate, scrub_secrets
orchestrator_agent.py    SYSTEM_PROMPT, _new_run (ask_agent/ask_agents/record_trip_state),
                         _OnlyOurTools, _floor, _unsourced_figures_note, plan_trip_agentic
orchestrator_config.py   get_client, _BUILDERS, SLOT_MODEL_ENV, _FallbackClient
orchestrator_costs.py    build_budget_brief, absences, extract_line_items, PRICED_SLOTS
ui/agent_seam.py         install_seam, LABELS, real-vs-dummy
ui/request_parse.py      parse_request
```

Useful check: `e2e_run.py` prints a live per-slot timeline, so a real run will
confirm or contradict any ordering claim. `./.venv/Scripts/python.exe -u
e2e_run.py "<query>"` — about 2 minutes and $0.0025.

---

## 1. State

- **248 tests across 13 files, all passing.** `test_agent.py` is a 14th file
  that dies on a missing `langchain_cerebras`; pre-existing, unrelated, not part
  of the 248.
  ```
  for t in test_*.py; do ./.venv/Scripts/python.exe $t; done
  ```
- Limeng's `activities-agent/test_jig.py` is **18/20**, unchanged all session.
  The two failures are his Paris case and a pre-existing scuba case.
- Tree clean. `PR_BODY.md` and `evaluation/results/*` are untracked on purpose.

### The 12 commits pushed this session (oldest first)

```
df35330  Orchestrator: confirm the fan-out is used, and size the gate to the batch
fd54e4a  Activities: one accent-folded city slug for the reader and the writer
ec15682  Harness: let the timeline survive a slot reply containing emoji
52c9d5e  Orchestrator: the unsourced-figures note under-reported, two ways
705e7af  Demo: a second working city, and let the harness take a request
b8be366  Money & Customs: correct the note about match_score, and say who it blocks
a408fb7  Request parse: stop guessing, because a guess arrives as a stated fact
c2fb279  Activities: read DEEP_AGENT_MODEL when the agent is built, not when imported
fe6edfb  Orchestrator: refuse the built-in tools, do not merely hide them
3b3a805  Activities: curate the two demo cities from sourced OpenTripMap descriptions
22f5e1e  Activities: give Honolulu the beach and nature entries it was asked for
99e5338  Demo notes: the two working queries, the latency floor, and the Ollama caveat
```

**Commit messages are the design record.** Each states the failure it fixes and
what was deliberately left alone. Read the relevant one before changing anything.

---

## 2. What changed, in one line each

- **The unsourced-figures floor under-reported twice** (`52c9d5e`). The lodging
  caveat was gated behind another slot failing, so on a fully green run the
  orchestrator could write "$376 per night for accommodation" with no caveat.
  And the note hand-rolled a worse copy of `orchestrator_costs.absences()`,
  which already had a fourth branch (`not extract_line_items`) that catches what
  the phrase list misses. Closes part2 §7.1.
- **`request_parse` stopped guessing** (`a408fb7`). Its output is prepended to
  every agent task as a stated fact, so a wrong value is a confident lie. Four
  defects fixed, `test_request_parse.py` added (28 checks).
- **Built-in tools are now refused, not just hidden** (`fe6edfb`).
- **Activities model read at build time** (`c2fb279`) — its provider fallback was
  wired but inert.
- **`.env` gained `DESTINATION_AGENT_MODEL`** (gitignored, not in any commit).
  Unset, it defaulted to a dead Anthropic key, so every run burned a
  guaranteed-to-fail call on the first slot. Now 0 provider failures per run.
- **Two demo corpora curated** (`3b3a805`, `22f5e1e`) — descriptions generated by
  script from OpenTripMap `/xid` Wikipedia extracts, not hand-written.

---

## 3. The demo

Two queries, both verified live on the pushed code, all six agents real:

```
Plan 5 nights in Honolulu for 2 people from Boston in September, total budget $3000
Plan 5 nights in Cancun for 2 people from Boston in September, total budget $3000
```

Honolulu first — Cancun's destination agent flags September as an "avoid month".
See `DEMO_NOTES.md` (committed) for the coverage matrix, the latency numbers and
the Ollama caveat. Restaurants under-answered in 1 run of 13; two hypotheses
(accented city name, budget constraint in the task) were both **falsified** by
direct test, so do not re-chase them.

---

## 4. THE MIRO TASK

### The board

"Travel Agents", `miro.com/app/board/uXjVH1rtHa4=/`. The user's plan is on free
tier: **board-level export offers only CSV and Embed**, no image export. A CSV
of all board text was exported to `C:\Users\rohan\Downloads\Travel Agents.csv`
(110 lines) — read it, it contains every label on the board.

Existing frames: one per agent, plus two master frames (overview and expanded).
Frames are named like `5   Restaurants Agent - Vrushti`, so name the new one to
match: **`6 — Orchestrator Agent - Rohan`** (confirm the numbering against the
board first).

### The board's visual conventions, taken from its own legend

```
Solid line = runtime data flow      Dashed line = conditional / update flow
Cylinder   = data source / at rest  Diamond     = decision
Rectangle  = process / tool
```
Colours in use: lavender = orchestrator, cream/yellow = agents, green = tools,
red/pink = external services, grey = user chat, blue tint = grouping container.
The board uses "A2A" to mean **orchestrator ↔ sub-agent**, not agent ↔ agent.

### Scope

Build **only** the orchestrator's own frame. Do not touch anyone's individual
agent diagram.

The two **master** frames do need changes, but ask the user before editing them.
Four mismatches with the live code were found (re-verify each yourself):

1. Master overview shows **Money & Customs as step 1, "RUNS FIRST — injects
   context downstream"**. That relay was deliberately removed; see the comment
   in `orchestrator._run_parallel_subagents`. It also contradicts the board's own
   note "Sub-agents never call each other."
2. **Execution order** is stale. Check it against `SYSTEM_PROMPT` and a live run.
3. **"3a, 3b and 3c run concurrently"** — check how many actually do now.
4. **"no tool calling of its own"** — true of the deterministic path, check
   whether it is true of the agent path.

Also on the board and worth checking against code: Activities is labelled
"ollama v3.2" (check `.env`), and Budget Knowledge is still speculative
("Could be… or MCP to a REST API like Numbeo") when the answer is now settled.

Two labels that ARE accurate and should be preserved: the Money & Customs
thresholds (fuzzy 0.75 / semantic 0.55 — they match `money_tools.py` exactly),
and the Flights note about Travelpayouts returning cached prices up to 7 days
old rather than live availability.

---

## 5. Open items, none blocking the demo

- **Deterministic path has no floor.** `_floor` is only called from
  `orchestrator_agent`, so `_plan_trip_fixed` emits no unsourced-figures block.
  Fix is a move, not an addition: `orchestrator_costs` is dependency-free,
  already holds `absences()`, and `orchestrator.py` already imports it.
- **`nights` and `travelers` are model-dependent.** They reach agents only if the
  model calls `record_trip_state`, yet Budget's brief rule 4 multiplies by them.
  It has done so in every observed run, so this is latent, not observed.
- **money_customs gates Budget** via the `ask_agents` gather although nothing
  reads its reply. Measured saving if removed: 0.3s on one demo run, 16.6s on the
  other. A coin flip; the long pole alternates.
- **A transient retry re-runs successful slots.** `ask_agent`'s memo only
  short-circuits failures. Never observed firing.
- **Money & Customs `found=True` is unconditional.** "Aruba" resolves to Fiji at
  0.286, "Narnia" to Morocco at 0.169. Not reachable on either demo city (both
  are exact matches). Fixed by data, not code.

### Messages drafted but NOT sent

Replies to **Limeng** (four changes to his agent: two code, two data, plus a
finding that API duplicates regenerate and cannot be auto-deduped safely) and to
**Emily** (add Aruba, plus Barbados / Maldives / Seychelles / Vietnam; do not
add more, the bottleneck is elsewhere). Both are in the previous session's
transcript. Ask the user before sending anything.

---

## 6. Standing constraints

- **Ownership.** `activities-agent/`, `activities/`, `destination_agent/`,
  `destination_data/`, `restaurant_agent/`, `budget_agent/`, `flights_agent.py`,
  `money_customs_agent.py`, `money_tools.py` belong to five other people. Do not
  edit without the user's explicit go-ahead. Where this session did edit them, it
  was on his instruction and the commit says so.
- **Do not weaken an honesty guarantee for speed or brevity.**
- If a change breaks a test, the change is wrong until argued otherwise — the
  tests encode observed production failures.
- Nothing is pushed or sent without explicit confirmation.
- **Verify before asserting.** This session twice reported a cause it had not
  tested (the restaurants accent, then the budget constraint) and was wrong both
  times; and drew two errors into the diagram. Test the claim, then make it.
