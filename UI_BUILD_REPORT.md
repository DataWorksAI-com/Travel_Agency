# UI Build Report — Chainlit over the orchestrator

Rohan Shivakumar · ALY6980 capstone · sponsor DataWorksAI
Built and verified 2026-08-21 on the merged tree, **no API keys**.

Every claim below is tagged:
**[RUN]** verified by running · **[CODE]** read in code · **[INF]** inference.

---

## 0. Where this was built

| | |
|---|---|
| Worktree | `C:\Users\rohan\Documents\wt-sandbox` |
| Branch created | `ui_chainlit_rohan`, off `sandbox-integration` at `fcb5f4c` **[RUN]** |
| Venv | `wt-sandbox/.venv`, Python 3.11.5 (`.venv/` is already in `.gitignore`) **[RUN]** |

**Heads-up:** `wt-sandbox` was on `sandbox-integration` when I started; I left it
on `ui_chainlit_rohan`. `git checkout sandbox-integration` there puts it back.

Step 0 gate, before touching anything: **[RUN]**

```
python sandbox/run_pipeline.py     -> exit 0, no exceptions, no keys
```

It needs **zero third-party packages** — every slot is a stdlib stand-in. (At the
time of that run, budget ran the envelope agent's stdlib-only direct path:
`budget_agent_rohan/proposed_envelope_agent/corpus.py:16-18`, `tools.py:25-29`.) **[CODE]**

---

## 1. The exact run command

```powershell
cd C:\Users\rohan\Documents\wt-sandbox
.\.venv\Scripts\Activate.ps1
chainlit run app.py -w
```

The target is the repo-root `app.py`, quoted from its own docstring
(`app.py:14-15`, unchanged from the original at `app.py:7-8`). **[CODE]**
`-w` = "Reload the app when the module changes"; `-h/--headless` suppresses the
browser auto-open — both from `chainlit run --help`. **[RUN]**

I verified with `--headless --port 812x` so the run was scriptable; `-w` is the
flag Rohan wants interactively. Note `-w` matters more than usual here: without
it the server does **not** pick up edits, which cost me one confusing cycle.

### What `app.py` drove before, and what it drives now

- **Before:** only Destination. `from destination_agent.destination_agent import
  run_destination_agent` (`app.py:33`), called at `app.py:105`. No orchestrator,
  no other agent. Confirmed — this matches the diagram. **[CODE]**
- **Now:** the whole pipeline through one call, `plan_trip`
  (`orchestrator.py:146`), invoked at `app.py:151`. **[CODE]**

`plan_trip`'s signature is **not** one free-text argument
(`orchestrator.py:146-151`): **[CODE]**

```python
async def plan_trip(task: str, origin_country: str = "",
                    destination_country: str = "", stated_budget: str = "") -> str
```

It returns one assembled string (`orchestrator.py:132-143`, via
`_assemble_itinerary`). Money & Customs is only called when **both** country
arguments are non-empty (`orchestrator.py:158`). Because a chat box supplies one
line, `ui/request_parse.py` splits it — deterministic regex, no model, and the
split is displayed as its own step so a bad parse looks like a bad parse.

---

## 2. Dependency split

### Fakes path — what I actually installed **[RUN]**

```powershell
pip install chainlit truststore
```

`chainlit 2.11.1`, `truststore 0.10.4`, plus their transitive tree (fastapi,
uvicorn, python-socketio, pydantic, opentelemetry/traceloop, literalai…).
That is the **complete** requirement for the UI on the fakes path — proven by the
server importing `app.py` cleanly and answering `GET /` with **HTTP 200**. **[RUN]**

Deliberately **not** installed: `deepagents`, `langchain*`, `langchain-cohere`,
`chromadb`, `langchain-ollama`, any provider SDK. The fakes path stays key-free.

### Live path — the deferred stack, **not installed**

Measured, not guessed: I forced all six slots to `real` and read what each one
actually failed on. **[RUN]**

| Slot | What blocks it today |
|---|---|
| `destination` | `No module named 'deepagents'` |
| `flights` | `'TRAVELPAYOUTS_TOKEN'` — a **key**, so its deps are already satisfied |
| `restaurants` | `No module named 'deepagents'` |
| `activities` | `No module named 'activities_agent'` (import path, not a dep — see finding 4) |
| `budget` | `No module named 'langchain'` |
| `money_customs` | `No module named 'langchain_cohere'` |

Plus, from the committed manifests: `requirements.txt` (`requests`, `deepagents`,
`langchain-cohere`, `chromadb`), `flights_requirements.txt`,
`restaurant_agent/requirements.txt`, `budget_agent/requirements.txt`. **[CODE]**

---

## 3. Seam design

### The one idea

`app.py` → `plan_trip` → `get_client(slot)` → an agent. Real-vs-dummy is decided
at that **third** arrow, never in the UI. There is no reference to a fake, dummy
or stand-in anywhere in `app.py` — grep it.

### Mechanism

`ui/agent_seam.py:install_seam()` rebinds the module attribute
`orchestrator.get_client`. That is the same single intervention
`sandbox/run_pipeline.py:56` uses, and it works because `orchestrator.py:30` does
`from orchestrator_config import get_client`, binding the name into the
`orchestrator` module namespace. **[CODE]**

**`orchestrator_config.py` is not edited.** When a slot is `real`, the
seam calls her own public `get_client(name)` and uses whatever it builds.

### Why the UI can't use `orchestrator_config.get_client` unchanged

Two error-string escape hatches, either of which would land in the browser: **[CODE]**

| Source | String | When |
|---|---|---|
| `orchestrator_config.py:130` | `[{name} unavailable] {error_message}` | builder raised |
| `subagent_client.py:98` | `[subagent error] {exc}` | the call raised |
| `subagent_client.py:182` | `[subagent unreachable over SLIM] {exc}` | SLIM stub |

Note for the inventory: the `[subagent error]` string lives at
**`subagent_client.py:98`**, not `orchestrator_config.py:~108`. The line near
`orchestrator_config.py:116-130` is the *build*-failure wrapper, which emits the
different `[{name} unavailable]` shape. The seam catches **both**.

`ui/agent_seam.py:_looks_like_error()` matches those shapes; a match routes to
that slot's stand-in and reports effective mode `dummy` to the UI.

### Modes

`ui/agent_seam.py:MODES` — one entry per slot, matching the six keys of
`orchestrator_config._BUILDERS` (`orchestrator_config.py:99-106`): **[CODE]**

| Mode | Meaning |
|---|---|
| `real` | built via `orchestrator_config.get_client()`; needs branch + deps + key |
| `dummy` | the deterministic stand-in in `sandbox/fakes.py` |

Defaults: **everything `dummy`**, budget included. There were three modes: a
`direct` mode routed the budget slot to the per-diem envelope proposer
(`evaluation/direct_path.render`) with no model and no key. That agent is now
`proposed_envelope_agent` and is **proposed future work, not an orchestrator
option** — so the mode was removed outright, not just defaulted off, since
leaving it selectable would let a stray `TRAVEL_UI_AGENTS` value put unreleased
work in front of a user.

The budget slot's `real` path is **Shashank's repo-root RAG cost estimator**
(`budget_agent/agent.py:86`, wired at `_build_budget_client`) — the only budget
agent the orchestrator can reach. **Consequence: no slot is live today; the
honest count of real agents in the UI is zero.**

**The fakes' prose is untouched.** `sandbox/fakes.py` was not edited. `fakes.REPLIES`
has no Budget key, so the seam keeps its own one-line Budget fallback in
`agent_seam.py` rather than adding an entry to `fakes.py`.

### Observability

`install_seam(after=...)` takes an async hook called once per agent with
`(slot, effective_mode, task, reply)`. `app.py:_on_agent_done` turns each into a
`cl.Step` labelled `Flights (sample data)` / `Destination (live agent)`.
The UI supplies the label; it never learns *how* the mode was decided.

Each step is opened and closed inside that one coroutine, not held open across
the agent call, because Flights/Restaurants/Activities run concurrently
(`orchestrator.py:76-80`) and Chainlit tracks step nesting in a contextvar
(`chainlit/step.py:459-471`) — three steps held open across that `gather` would
nest arbitrarily. **[CODE]**

### Silent degradation is logged

A fallback prints `[seam] <slot>: falling back to stand-in -- <why>` plus the
traceback to the terminal (`ui/agent_seam.py:_log_fallback`). The browser gets
the stand-in; the terminal gets the truth. I added this *because* my first build
hid a genuine `ModuleNotFoundError` behind plausible sample data — see finding 3.

---

## 4. Acceptance evidence

Reproduce the headless checks with `python ui/verify_seam.py` (all checks
pass **[RUN]**). Browser-level evidence came from a socket.io client that speaks
Chainlit's own protocol (`client_message` in, `new_message`/`update_message` out
— `chainlit/socket.py:407`, `chainlit/emitter.py:221,225`), i.e. exactly the
events the browser renders.

| # | Requirement | Result | Evidence |
|---|---|---|---|
| 1 | UI renders and accepts a query | **PASS** | `GET /` → HTTP 200; `/project/settings` → 200; server log "Your app is available at http://localhost:8125"; the query below was accepted and answered over the live socket **[RUN]** |
| 2 | Real query returns an assembled plan | **PASS** | *"Plan a week in Aruba from Boston, budget $3000"* → one `assistant_message` with all five `=== … ===` sections **[RUN]** |
| 3 | No unhandled exceptions | **PASS** | run completes; zero tracebacks in the transcript; `ui/verify_seam.py` asserts the assembled plan is free of all three error shapes **[RUN]** |
| 4 | Intermediate agent steps visible | **PASS** | 7 steps per run: `Request parsed`, then `Money & Customs`, `Destination`, `Flights`, `Restaurants`, `Activities`, `Budget` — each with its input and output, appearing as it completes **[RUN]** |
| 5 | Failing case degrades gracefully | **PASS** | three sub-cases below **[RUN]** |

### #4 — what the browser actually received

```
[tool] Request parsed
         - **Destination country**: Aruba
         - **Origin country**: USA
         - **Stated budget**: $3000
[tool] Money & Customs (sample data)   1 USD = 2.00 BBD …
[tool] Destination (sample data)       Recommended destination: Bridgetown, Barbados …
[tool] Flights (sample data)           B6: $538, 5h10m, direct, arrives BGI …
[tool] Restaurants (sample data)       Champers -- seafood, waterfront, around $95 for two …
[tool] Activities (sample data)        Catamaran snorkel cruise -- outdoor, around $110 …
[tool] Budget (sample data)            Sample allocation: lodging $1,400, meals $760 …
[assistant_message] === Destination === … === Budget ===
```

### #5a — every agent forced to `real` while unconnected

`$env:TRAVEL_UI_AGENTS = "destination=real,flights=real,restaurants=real,activities=real,money_customs=real,budget=real"`, then the same query: **[RUN]**

Browser showed **six stand-in steps and zero error strings** — `grep -c "subagent
error|unavailable]|unreachable|Traceback"` over the transcript returned **0**.
The terminal recorded the truth:

```
[seam] money_customs: falling back to stand-in -- [money_customs unavailable] No module named 'langchain_cohere'
[seam] destination:    falling back to stand-in -- [destination unavailable] No module named 'deepagents'
[seam] flights:        falling back to stand-in -- [flights unavailable] 'TRAVELPAYOUTS_TOKEN'
[seam] restaurants:    falling back to stand-in -- [subagent error] No module named 'deepagents'
[seam] activities:     falling back to stand-in -- [activities unavailable] No module named 'activities_agent'
[seam] budget:         falling back to stand-in -- [budget unavailable] No module named 'langchain'
```

Both error shapes occurred naturally in one run (`[… unavailable]` ×5,
`[subagent error]` ×1) and both were absorbed. This is the acceptance test the
seam exists for.

### #5b — the envelope agent's refusals *(no longer part of the UI's surface)*

This sub-case asserted that the envelope proposer's refusal paths render as prose
rather than raising — `covered=False` and missing budget/length, both verified at
the time **[RUN]**. That agent (`proposed_envelope_agent`) is now proposed future
work and is not wired to any slot, so its behaviour is no longer a UI guarantee
and `ui/verify_seam.py` no longer asserts it. Its own checks live in
`budget_agent_rohan/tests/` and `sandbox/run_envelope_test.py`.

The `covered=False` path was also unreachable through the pipeline — worth fixing
before the agent is ever wired in, not papered over in the UI.

### #5c — unparseable input

Query `asdkjfh ????` → no crash; `Request parsed` step honestly shows
`_not detected_` ×3; Money & Customs is correctly **skipped** (both countries
empty, `orchestrator.py:158`), so five agent steps appear instead of six. The UI
renders the orchestrator's real behaviour rather than faking a sixth. **[RUN]**

---

## 5. The swap — one line, no UI edit

**Option A — no file edit at all** (per-run, best for a demo): **[RUN]**

```powershell
$env:TRAVEL_UI_AGENTS = "flights=real"
chainlit run app.py -w
```

**Option B — the default** (`ui/agent_seam.py:MODES`), one character changed:

```python
"flights": DUMMY,   ->   "flights": REAL,
```

Precedence is `MODES` → env var → explicit `overrides=` argument
(`ui/agent_seam.py:resolve_modes`). Anything left alone stays on `dummy`, so a
half-merged team never shows an error string.

That is the whole swap. `app.py` is untouched, `orchestrator.py` is untouched,
`orchestrator_config.py` is untouched. Checklist for the teammate doing it:

1. Agent's branch merged so its import path in `orchestrator_config.py` resolves.
2. Its live-path deps installed **into this venv**.
3. Its key exported (table in §7).
4. Flip the one value, restart, confirm the step header reads `(live agent)`
   instead of `(sample data)`.

If step 4 still says `sample data`, the terminal `[seam]` line names the exact
reason — that is what it is for.

---

## 6. Push — deliberately not done

**Nothing was pushed. `main` is untouched.** Confirmed by reading the branches: **[RUN]**

- `origin/main` contains `app.py` but **no** `orchestrator.py`,
  `orchestrator_config.py` or `subagent_client.py`.
- `origin/exchange_rate_emily` contains all three, and **no** `app.py`.

So `app.py` as written here — `from orchestrator import plan_trip` (`app.py:38`) —
**cannot import on `main` as it stands**. Pushing it there would break `main` for
everyone at import time, before any agent is even reached.

**Answering the flag directly: yes.** The UI's real home is a branch off
`exchange_rate_emily`, not `main`. That is the only branch where the import
resolves. `main` gets it when the orchestrator does.

Conditions for a safe push, in order:

1. `orchestrator.py` + `orchestrator_config.py` + `subagent_client.py` reach `main`
   (i.e. `exchange_rate_emily` merges).
2. Enough agents reach `main` that `real` is meaningful for at least one slot.
3. Owner approval recorded on the PR for `orchestrator_config.py`, and
   this UI depends on its `get_client` contract even though it doesn't edit it.
4. `chainlit` + `truststore` added to `requirements.txt` (§2).

Work is a clean diff on `ui_chainlit_rohan`: `app.py` rewritten, `ui/` added,
this report. This file is untracked by request.

---

## 7. Deferred — go-live reference (written down, not acted on)

### Keys, per agent **[CODE]**

| Agent | Key | Supplied how |
|---|---|---|
| Destination | `ANTHROPIC_API_KEY`; `GEOAPIFY_API_KEY` | env / `.env` |
| Flights | `TRAVELPAYOUTS_TOKEN`; `OPENROUTER_API_KEY` | env |
| Restaurants | `GEOAPIFY_API_KEY`; `OPENROUTER_API_KEY` (or local Ollama, no key) | env |
| Activities | `OPENTRIPMAP_API_KEY`; `GEOAPIFY_API_KEY`; `OPENROUTER_API_KEY` | env |
| Budget (Rohan) — *not wired, future work* | `OPENROUTER_API_KEY` — agent path only; the no-LLM path needs none | env |
| Money & Customs | `COHERE_API_KEY` / `CEREBRAS_API_KEY` (two variants exist) | `.env`, see `.env.example` |
| Optional | `LANGSMITH_API_KEY` | tracing only |

`.env.example` currently documents **only** `CEREBRAS_API_KEY` — it is well
behind the code. Worth fixing before anyone else tries to go live. **[CODE]**

### External REST APIs **[CODE]**

| Host | Used by |
|---|---|
| `api.geoapify.com` | Destination, Restaurants, Activities (geocoding/places) |
| `date.nager.at` | Destination (public holidays) |
| `archive-api.open-meteo.com`, `geocoding-api.open-meteo.com`, `marine-api.open-meteo.com` | Destination / climate |
| `api.travelpayouts.com`, `autocomplete.travelpayouts.com` | Flights |
| `overpass-api.de`, `nominatim.openstreetmap.org` | Restaurants / Activities (OSM) |
| `api.frankfurter.dev` | Money & Customs (exchange rate) |
| `allowances.state.gov` | Budget (per-diem corpus source — fetched offline, not at runtime) |
| `api.worldbank.org` | referenced in agent code |
| `openrouter.ai`, `console.anthropic.com` | model providers |

### Model strings set today — **and which look stale** **[CODE]**

| Slot | Where | String today | Flag |
|---|---|---|---|
| **Coordinator** | `orchestrator.py` | *none — no model anywhere in the file* | correct as-is |
| Destination | `destination_agent/destination_agent.py:347` | `claude-haiku-4-5` | **OK** — a current model ID |
| Flights | `flights_agent.py:192` | `openrouter:anthropic/claude-sonnet-4.5` | **VERIFY** — previous-generation ID |
| Flights (fallback) | `subagent_client.py:81` | `openrouter:anthropic/claude-sonnet-4.5` | **VERIFY** — duplicated default |
| Restaurants | `restaurant_agent/restaurant_agent_ollama.py:96` | `ollama:lfm2.5` | **STALE-RISK** — needs local Ollama *and* `ollama pull lfm2.5`; dies on any machine without it |
| Activities | `activities-agent-limeng/activities_agent.py:78` | `openrouter:z-ai/glm-5.2` | **VERIFY** — confirm this slug exists on OpenRouter |
| Activities (dup) | `activities/local_activity_docs/activities_agent.py:187` | `openrouter:z-ai/glm-5.2` | duplicate copy of the agent |
| Budget (Rohan) | `budget_agent_rohan/proposed_envelope_agent/agent.py:232` | `openrouter:openai/gpt-oss-20b:free` | **VERIFY** — free tier; `:free` slugs get retired |
| Budget (Shashank) | `budget_agent/config.py:35,40` | `claude-sonnet-4-6` / `anthropic/claude-sonnet-4.5` | **VERIFY** — previous-generation IDs |
| Money & Customs | `money_customs_agent.py:32` | `command-r-plus-08-2024` (Cohere) | **VERIFY** |
| Money & Customs (dup) | `agent.py:31` | `gpt-oss-120b` (Cerebras) | **CONFLICT** — two files, two different providers/defaults for the same agent |

Every string is `os.environ.get(...)`-overridable except Destination's
(`destination_agent.py:347`, hardcoded) and Flights' (`flights_agent.py:192`,
hardcoded). Those two can't be repointed without a code edit — worth fixing. **[CODE]**

The current Claude generation is Claude 5 (Opus/Sonnet/Fable 5) plus Haiku 4.5,
so `claude-sonnet-4.5` and `claude-sonnet-4-6` are prior-generation IDs. I have
**not** hit any provider to confirm which still resolve — do that before go-live.
A dead string is a live failure, and with the seam in place it now fails as
`(sample data)` plus a `[seam]` log line rather than as a browser error. **[INF]**

### Proposed per-agent model assignment — **awaiting Rohan's approval, nothing changed**

Capability matched to task, not one model everywhere:

| Slot | Proposal | Why |
|---|---|---|
| **Coordinator / orchestrator** | **capable model** *if* it ever needs one | Today it needs **none** — `orchestrator.py` is pure Python sequencing. It only needs a model if decision #6 (structured extraction from the three prose replies, `orchestrator.py:94-107`) is solved with an LLM. Prefer solving it without one. |
| Destination eval | capable | judgment: ranking places against vague preferences |
| Restaurants | capable | judgment: taste, fit, price-tier reasoning from prose |
| Activities | capable | judgment: matching interests, handling `price tier unknown` |
| Flights | fast/cheap | lookup-and-format over cached Travelpayouts rows |
| Money & Customs | fast/cheap | lookup-and-format: one rate + one tipping norm |
| Holidays / climate | fast/cheap | pure lookup-and-format |
| **Budget allocation** | **no model at all** | It is arithmetic. The envelope proposer runs it with no model and no key — demonstrated, though now unwired as future work. This is the tools-not-a-sub-agent argument in its concrete form; note it argues against Shashank's RAG-plus-model budget agent, which is what the slot actually points at. |

Two things I'd want settled alongside this: pick **one** Money & Customs
implementation (the `agent.py` / `money_customs_agent.py` conflict above), and
one Activities copy — the model choice can't be enforced while each exists twice.

---

## 8. Findings — flagged, not fixed

Each of these is outside the "UI files, seam shim, report" boundary I was given,
so I have reported rather than touched them.

**1. Budget's scope guard false-positives on orchestrator-composed text.**
`direct_path.render` refuses if any of `SCOPE_WORDS` appears anywhere in the task
(`evaluation/direct_path.py:88`, list at `:38` — it includes `"recommend"`). But
`_build_budget_task` embeds Destination's whole reply
(`orchestrator.py:110`), and that reply begins *"**Recommended** destination:"*
(`sandbox/fakes.py:25`). So Budget returns *"Recommending accommodation is not
this agent's job…"* on **every** pipeline run. **[RUN]**
Consequence: `covered=False` and the real allocation are both unreachable
end-to-end. The guard should be applied to the **user's request**, not to text the
orchestrator composed from other agents. This is my file — happy to fix on the
budget branch on your say-so.

**2. ~~`budget_agent` is an ambiguous import name.~~ FIXED — renamed.** Two
different packages claimed it: `budget_agent/` at the repo root (Shashank's RAG
cost estimator — `config.py`, `tools/`, `data/`) and, formerly,
`budget_agent_rohan/budget_agent/` (mine — the per-diem envelope proposer). Which
one `import budget_agent` resolved to depended purely on `sys.path` **and
`sys.modules`** order: whichever package was imported first won the name for the
whole process. It worked only because `direct_path.py:32` inserts its own parent
at position 0 — but that is defeated once the root package is already in
`sys.modules`, e.g. after forcing `budget=real` in the same session, at which
point Budget's direct path died on `No module named 'budget_agent.corpus'` and
silently degraded to a stand-in. **[CODE]**

Mine is now **`proposed_envelope_agent`** (`budget_agent_rohan/proposed_envelope_agent/`).
`budget_agent` unambiguously means the root RAG agent, noted at
`orchestrator_config.py:67-75`. Verified by importing the root package *first*
and confirming the envelope path still renders a real allocation. **[RUN]**

**3. `sys.path.insert(0, …)` is unsafe under Chainlit.** `chainlit/config.py:592`
inserts the app's directory at index 0, then `:624` does an **unconditional**
`sys.path.pop(0)` after `exec_module`. Anything a module inserts at index 0 while
`app.py` is importing is what that pop removes — and the entry it removes on a
clean run is the repo root itself, so a *lazy* import can fail later even though
startup looked fine. **[RUN]** — this cost me a real debug cycle: Budget silently
showed sample data because `evaluation` had vanished from `sys.path`.
Fixed in my layer by appending and re-asserting (`ui/agent_seam.py:_ensure_paths`).
Anyone else adding a path in `app.py`'s import chain will hit the same thing.

**4. `orchestrator_config`'s Activities import can never resolve.**
`orchestrator_config.py:53` does `from activities_agent import build_agent`, but
the module lives at `activities-agent-limeng/activities_agent.py` — a directory
with hyphens, which is not an importable package name, and the directory itself
isn't on `sys.path`. **[RUN]** (`No module named 'activities_agent'`.) It needs
either a rename or a real package location.

**5. The three gaps `run_pipeline.py` already measured still hold.** The resolved
destination, the origin city, and the budget all fail to reach
Flights/Restaurants/Activities (`orchestrator.py:68-70` forwards the raw `task`
plus the money blurb, nothing else). **[RUN]** The UI now makes this *visible* —
each step shows the exact string that agent received — but it does not fix it.
`plan_trip` has no origin-city parameter at all.

---

## 9. Files changed

| File | Change |
|---|---|
| `app.py` | rewritten: drives `plan_trip`, emits a step per agent. No fake referenced. |
| `ui/__init__.py` | new |
| `ui/agent_seam.py` | new — the seam: modes, dummy fallback, error-string absorption, hooks |
| `ui/request_parse.py` | new — one chat line → `plan_trip`'s four arguments |
| `ui/verify_seam.py` | new — browser-free acceptance harness |
| `UI_BUILD_REPORT.md` | this file (untracked by request) |

Not touched: `orchestrator.py`, `orchestrator_config.py`, `subagent_client.py`,
`sandbox/fakes.py`, `sandbox/run_pipeline.py`, and every agent's code.

Committed as `dd071b0` on `ui_chainlit_rohan`. Nothing pushed.

### One thing that needs your decision

**The branch is not self-contained yet.** `ui/agent_seam.py` imports
`sandbox.fakes`, but `sandbox/` is **untracked** in this worktree — it is your
harness and you had not committed it. So a teammate checking out
`ui_chainlit_rohan` gets a seam that imports a package that isn't there. **[RUN]**

I did not commit `sandbox/` for you, because that is your call, not mine. Either:

- `git add sandbox/ && git commit` — makes the branch stand alone (my
  recommendation, since `run_pipeline.py` is also the evidence for the
  integration audit); or
- move the six stand-in strings into `ui/` so the UI layer owns its own
  fallbacks and `sandbox/` stays a private scratch harness.

Until one of those happens, this UI runs only in *your* `wt-sandbox`.
