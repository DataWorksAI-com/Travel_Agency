# UI — Status Update

**Branch:** `ui_chainlit_rohan` · **Date:** 2026-08-22 · **Owner:** Rohan

Answers the slide's three UI asks, then the question that follows from them:
*have you tested the code with all the different agents?*

Deep detail lives in [`UI_BUILD_REPORT.md`](UI_BUILD_REPORT.md); this is the
summary you can read out in a standup.

---

## 1. Against the requirement

| Ask | Status |
|---|---|
| Working UI for the orchestration | **Done** — Chainlit over `plan_trip`, all six agent slots, per-agent steps visible |
| Chainlit UI can be used | **Done** — `chainlit run app.py -w` |
| Fancy UI via Google a2ui (stretch) | **Not started** — deliberately, see §5 |

---

## 2. What is built

One command, no keys:

```powershell
cd C:\Users\rohan\Documents\wt-sandbox
.\.venv\Scripts\Activate.ps1
chainlit run app.py -w
```

**Before:** `app.py` drove a single agent — Destination, called directly
(`app.py:33` → `app.py:105` on the pre-change file).

**Now:** one chat line drives the whole pipeline through `plan_trip`
(`orchestrator.py:146`, invoked at `app.py:151`), and the browser shows 7 steps
per run — `Request parsed`, then Money & Customs, Destination, Flights,
Restaurants, Activities, Budget — each with its input and output, appearing as it
completes.

Three pieces were added:

- **`ui/request_parse.py`** — `plan_trip` does not take one free-text argument; it
  takes `task`, `origin_country`, `destination_country`, `stated_budget`. A chat
  box supplies one line, so this splits it with deterministic regex, no model. The
  split is shown as its own step, so a bad parse *looks* like a bad parse.
- **`ui/agent_seam.py`** — the real-vs-stand-in seam. The UI never chooses; it
  calls `plan_trip` and nothing else. One rebind of `orchestrator.get_client`
  decides per slot. `orchestrator_config.py` is **not** edited.
- **`ui/verify_seam.py`** — headless proof of the seam's guarantees, no browser.

**Why the seam exists, in one line:** the layers below have two error-string
escape hatches — `"[{name} unavailable] …"` (`orchestrator_config.py:130`) and
`"[subagent error] …"` (`subagent_client.py:98`). Unabsorbed, those land in the
browser as text that reads like a crash. "Flights: sample data" reads as
not-wired-yet; `Flights: [subagent error] No module named 'deepagents'` reads as
broken. The seam catches both shapes and falls back to that slot's stand-in.

**The swap is one line.** No UI edit, no orchestrator edit:

```powershell
$env:TRAVEL_UI_AGENTS = "flights=real,destination=real"
```

or flip a value in `ui/agent_seam.py:MODES`. Anything left alone stays on a
stand-in.

---

## 3. Have you tested it with all the different agents?

**Yes for all six slots — but through stand-ins. No agent has been exercised
against its real implementation.**

That distinction is the whole status, so being precise about it:

| Slot | Wired to the orchestrator | Exercised end-to-end in the UI | Real implementation exercised |
|---|---|---|---|
| Destination | yes | yes (stand-in) | **no** |
| Flights | yes | yes (stand-in) | **no** |
| Restaurants | yes | yes (stand-in) | **no** |
| Activities | yes | yes (stand-in) | **no** |
| Money & Customs | yes | yes (stand-in) | **no** |
| Budget | yes | yes (stand-in) | **no** |

**Budget's real path is Shashank's repo-root RAG cost estimator** — vector search
over city cost docs, total estimate, feasibility check (`budget_agent/agent.py:86`,
wired at `orchestrator_config._build_budget_client`). It is the only budget agent
the orchestrator can reach.

Earlier, the budget slot defaulted to a third mode, `direct`, which ran the
per-diem **envelope proposer** with no model and no key. That agent is **proposed
future work**, so it is no longer an orchestrator option and the `direct` mode is
gone rather than merely defaulted off — leaving it selectable would let a stray
`TRAVEL_UI_AGENTS` value put unreleased work in front of a user. The agent itself
is untouched and still runs standalone (`budget_agent_rohan/`,
`sandbox/run_envelope_test.py`).

**Consequence, stated plainly: every slot is now a stand-in, so the honest count
of live agents in the UI is zero.**

### What *was* tested, and how

- All six slots fire and are observable through the seam's `after` hook — the same
  hook `app.py` turns into Chainlit steps.
- Browser-level evidence came from a socket.io client speaking Chainlit's own
  protocol, i.e. the exact events the browser renders — not a mock of it.
- **All six forced to `real` while unconnected**, in one run: browser showed six
  stand-in steps and **zero** error strings; both error shapes occurred naturally
  (`[… unavailable]` ×5, `[subagent error]` ×1) and both were absorbed. The
  terminal logged every fallback with its cause.
- Unparseable input (`asdkjfh ????`): no crash, parse step honestly shows
  `_not detected_`, and Money & Customs is correctly *skipped* rather than faked
  (`orchestrator.py:158` needs both countries).
- Budget's refusal paths return prose, not exceptions.

### Why no live agent has been tested

Measured by forcing each slot to `real` and reading what it actually failed on —
not guessed:

| Slot | What blocks it today | Kind |
|---|---|---|
| `destination` | `No module named 'deepagents'` | dep |
| `restaurants` | `No module named 'deepagents'` (builds, fails on call) | dep |
| `budget` (Shashank's) | `No module named 'langchain'` | dep |
| `money_customs` | `No module named 'langchain_cohere'` | dep |
| `flights` | `KeyError: 'TRAVELPAYOUTS_TOKEN'` | **key only — deps satisfied** |
| `activities` | `No module named 'activities_agent'` | **import path, not a dep** |

The fakes path installs `chainlit` + `truststore` only, and stays key-free by
design. The live stack (`deepagents`, `langchain*`, `langchain-cohere`,
`chromadb`, provider SDKs) is **not** installed.

Budget needs a third thing beyond deps and a key: its Chroma vectorstore must be
built via `budget_agent/scripts/build_vectorstore.py`, which
`budget_agent/tools/rag_tools.py:33-37` enforces.

**So the honest claim is: the UI and the orchestration wiring are tested across
all six agents; the agents themselves are not.** Flights is the cheapest slot to
make genuinely live — it needs a token, nothing else.

---

## 4. Open items I am not papering over

1. ~~**Two packages named `budget_agent`.**~~ **Fixed.** There were two: the
   repo-root RAG cost estimator, and the per-diem envelope proposer under
   `budget_agent_rohan/`. `import budget_agent` resolved to whichever landed in
   `sys.modules` first, so *import order, not intent, picked the agent* — and
   once the root one won, Budget's direct path died on
   `No module named 'budget_agent.corpus'` and silently degraded to a stand-in
   for the rest of the process. Renamed the envelope proposer to
   **`proposed_envelope_agent`**; each name now means one agent. Verified by
   importing the root package *first* and confirming the envelope path still
   renders a real allocation — the sequence that used to fail.
2. **`activities` import path is wrong** at `orchestrator_config.py:53` —
   `activities_agent` does not match the on-disk `activities/local_activity_docs/`
   layout. Cheap fix, owned by the Activities branch.
3. **The envelope proposer's `covered=False` refusal was unreachable through the
   pipeline** — moot for now, since that agent is no longer wired to a slot.
   Worth fixing before it is wired in as future work.
4. **Model strings in the agent branches look stale** — listed in
   `UI_BUILD_REPORT.md` §7 with a proposed per-agent assignment. Nothing changed;
   awaiting a decision.

---

## 5. Next

- **Ready now:** demo on stand-ins; swap any slot to real with one env var.
- **Cheapest real slot:** Flights — add `TRAVELPAYOUTS_TOKEN`.
- **Then:** `pip install deepagents langchain langchain-cohere` unblocks four more,
  but that is a dependency and key decision for the group, not a UI change.
- **Proposed future work — the envelope proposer.** `proposed_envelope_agent`
  allocates a budget into per-category envelopes from published per-diem data and
  renegotiates them when a domain agent cannot work within one. It also ships an
  unwired `ceilings_for()` helper (`proposed_envelope_agent/orchestration.py:80`)
  intended for an orchestrator pre-phase — allocate budget *before* the domain
  agents search, rather than checking cost after. Deliberately not wired to a
  slot; the case for it is untested (`sandbox/run_envelope_test.py` is explicit
  that it proves plumbing, not that any agent searches differently given a
  ceiling).
- **a2ui stretch goal:** not started. It is a different rendering model — the
  agent emits interactive JavaScript as part of its response — so it belongs after
  at least one agent is genuinely live. Starting it now would mean building a
  fancier surface over sample data.
