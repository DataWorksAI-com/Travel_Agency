# Running the UI — a walkthrough for the team

How to start the UI, switch **your** agent on, tell whether it actually ran, and
read the failure when it didn't.

Builds on Joel's Chainlit UI from PR #10. Status and scope live in
[`UI_STATUS.md`](UI_STATUS.md); every environment variable the pipeline reads is
in [`ENVIRONMENT.md`](ENVIRONMENT.md).

---

## 0. First, a word about "sandbox"

The name is overloaded and it causes confusion:

- **`sandbox/`** is a directory of fixed fake replies (`fakes.py`) and two test
  harnesses. Not a container, not isolated, no magic.
- **`wt-sandbox`** is just the folder name of Rohan's working copy.

**The UI is not a sandbox. It is the real app.** When you set your slot to `real`,
the seam calls *your actual agent* through `orchestrator_config.py`, on your
machine, with your keys and your data.

So: **your agent will work here if it works standalone on your machine.** If it
doesn't work here, that is real information, not an artifact of a fake
environment.

---

## 1. Quick start — no keys, nothing to install but Chainlit

```powershell
git clone <repo> ; cd Travel_Agency      # or your existing checkout
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install chainlit truststore
chainlit run app.py -w
```

That is the **complete** dependency list for the default path. No API keys, no
vector stores, no Ollama. Your browser opens automatically; `-w` reloads on edit.

macOS/Linux: `source .venv/bin/activate`.

---

## 2. What you should see

Two messages on open: a welcome, then **"Agents currently connected"** listing all
six slots and what each is running. Read that list first — it tells you the
truth about the current configuration before you type anything.

Then ask for a trip:

> Plan a week in Aruba from Boston, budget $3000

You get **7 steps**, appearing as each finishes:

```
[tool] Request parsed                  how your sentence was split
[tool] Money & Customs (sample data)
[tool] Destination (sample data)
[tool] Flights (sample data)
[tool] Restaurants (sample data)
[tool] Activities (sample data)
[tool] Budget (sample data)
```

…followed by the assembled itinerary. Include a destination, an origin and a
budget — each message is planned on its own, there's no memory between turns.

Fewer than 7 steps is not necessarily a bug: Money & Customs only runs when
**both** countries are detected (`orchestrator.py:158`). If your phrasing hides
the origin, it is correctly skipped and you'll see 6.

---

## 3. Switching your agent on

One environment variable. No code change, no edit to anyone else's file:

```powershell
$env:TRAVEL_UI_AGENTS = "flights=real"
chainlit run app.py -w
```

Several at once, comma-separated:

```powershell
$env:TRAVEL_UI_AGENTS = "flights=real,restaurants=real"
```

Slot names — use these exactly:

| Slot | Agent | Owner |
|---|---|---|
| `destination` | Destination | Joel / Alice |
| `flights` | Flights | Brinda |
| `restaurants` | Restaurants | Vrushti |
| `activities` | Activities | Jainam / Limeng |
| `budget` | Budget (RAG cost estimator) | Shashank |
| `money_customs` | Money & Customs | `exchange_rate_emily` branch |

Modes are `real` and `dummy`. Anything else — including a typo — is ignored, and
that slot silently stays on `dummy`. **Check the "Agents currently connected"
message to confirm your value was accepted.**

---

## 3b. A known-good configuration

Verified end to end on 2026-08-24. Three agents live, all returning correct
Aruba data, whole run about 24 seconds. If you want to see the pipeline working
before you debug your own slot, start here.

```powershell
cd C:\path\to\Travel_Agency          # must be the repo root, see below
.\.venv\Scripts\Activate.ps1
python -c "import sys; print(sys.prefix)"   # must print your venv path

Remove-Item Env:TRAVEL_UI_AGENTS -ErrorAction SilentlyContinue
$env:TRAVEL_UI_AGENTS       = "restaurants=real,flights=real,budget=real"
$env:RESTAURANT_AGENT_MODEL = "ollama:qwen2.5:7b"
$env:DEEP_AGENT_MODEL       = "openrouter:openai/gpt-4o-mini"
$env:OPENROUTER_MODEL       = "openai/gpt-4o-mini"

chainlit run app.py -w
```

cmd.exe instead of PowerShell: use `activate.bat`, `set VAR=` to clear and
`set VAR=value` to set. **`Activate.ps1` does nothing in cmd and prints no
error** — it is how two diverged environments got created on this project.
Always confirm with the `sys.prefix` line above.

**Launch from the repository root.** Chainlit loads `.env` with
`load_dotenv(os.path.join(os.getcwd(), ".env"))` (`chainlit/__init__.py:8`), so
from any other directory your keys are silently absent.

### Why each of those three model variables exists

They are not decoration. Without them the pipeline looks broken for reasons
that have nothing to do with anyone's agent.

| Variable | Without it | Why |
|---|---|---|
| `RESTAURANT_AGENT_MODEL` | falls back to retrieval-only, no LLM | the default is `ollama:lfm2.5` (`restaurant_agent_ollama.py:96`) and most of us have `qwen2.5:7b` pulled instead |
| `DEEP_AGENT_MODEL` | Activities refused on `max_tokens`, or returned empty | its default `openrouter:z-ai/glm-5.2` requests 65536 tokens, which a low OpenRouter balance rejects |
| `OPENROUTER_MODEL` | Budget bills a paid Sonnet | the default is `anthropic/claude-sonnet-4.5` (`budget_agent/config.py:40`) |

### Do not use the free model tier for the pipeline

`openrouter/free` shares **one daily allowance** across every free-model call,
and `orchestrator.py:76-80` fires Flights, Restaurants and Activities
concurrently — so they race each other to exhaust it. Observed: all three
returned *"Rate limit exceeded: free-models-per-day"* in a single run.

Paid models have no daily cap and the cost is not the issue: **one full
six-agent run measured $0.0039.** A $5 balance is roughly 1,250 runs.

Model choice also affects correctness, not just speed. Same prompt, three runs
of the flights slot:

```
llama-3.3-70b : "AA: $2411" / "no available flights" / "no cached data"  (9-15s)
gpt-4o-mini   : "AA: $256, 7h 33m, 2 stops, arrives AUA"  x3             (4-5s)
```

llama was also inventing 2024 dates for a 2026 system clock. `gpt-4o-mini` is
the current recommendation for every OpenRouter slot.

---

## 4. ⚠️ The most important section: did my agent actually run?

**Seeing a plan does not mean your agent ran.**

This section changed. The seam **used to** absorb a failure and quietly show
sample data in its place, which meant a complete, believable itinerary could be
assembled entirely from agents that never executed. It no longer does that. A
slot set to `real` that cannot be reached now says so, in the browser, with the
cause. Nothing silently becomes a stand-in; `dummy` is only ever a choice.

### The step label

Three outcomes, and the difference between the last two is the whole point:

| Label | Meaning |
|---|---|
| `Flights (live agent, 7.8s)` | your agent ran and its words are on screen |
| `Flights (sample data, 0.0s)` | a fixed string from `sandbox/fakes.py` — **you asked for this** by leaving the slot on `dummy` |
| `Flights (NOT CONNECTED, 4.4s)` | you asked for `real` and it **could not be reached** — the step body carries the cause |

### The elapsed time is the evidence, not the label

The label says how the slot was *configured*. The number says what actually
happened, and a stand-in cannot fake it: `sandbox/fakes.py` is a dict lookup
returning in **0.0s**, while a real agent has to cross a network or a local
model and takes seconds. If a step ever claims `live agent` at `0.0s`, distrust
it and tell Rohan.

Real numbers from a working run, for calibration:

```
Flights      (live agent,  7.8s)     Destination     (sample data, 0.0s)
Restaurants  (live agent,  7.0s)     Activities      (sample data, 0.0s)
Budget       (live agent, 16.3s)     Money & Customs (sample data, 0.0s)
```

### The terminal

Every failure is announced in the terminal where you ran `chainlit`, with the
cause:

```
[seam] flights: NOT CONNECTED -- Rate limit exceeded: free-models-per-day
```

plus a full traceback when there is one. The browser gets one readable
sentence; **the terminal gets the whole story.** Keep it visible while you test.

**A failed slot stays failed until you restart.** `orchestrator_config.py:168`
caches the broken client for the life of the process, so fixing a key or waiting
out a quota changes nothing until you stop and relaunch `chainlit`. Likewise
`TRAVEL_UI_AGENTS` is read once at import (`app.py:127`), so changing it in a
running session has no effect.

---

## 5. Reading the failure

Three message shapes, and they mean different things:

| Shape | Where it comes from | What it means |
|---|---|---|
| `[<slot> unavailable] …` | `orchestrator_config.py:166` | your agent could not be **built** — usually a missing import or a key read at import time |
| `[subagent error] …` | `subagent_client.py:113` | it built fine, then **raised during the call** |
| `[subagent unreachable over SLIM] …` | `subagent_client.py:197` | the SLIM/A2A transport stub — not wired to anything live yet |

Common causes and the fix:

| Message | Fix |
|---|---|
| `No module named 'deepagents'` | `pip install deepagents` |
| `No module named 'langchain'` | `pip install langchain` |
| `No module named 'langchain_cohere'` | `pip install langchain-cohere` |
| `No module named 'langchain_mcp_adapters'` | `pip install langchain-mcp-adapters` (Activities) |
| `No module named 'langchain_chroma'` / `langchain_huggingface` | `pip install -r budget_agent/requirements.txt` (Budget) |
| `Rate limit exceeded: free-models-per-day` | not a bug — stop using `openrouter/free`, see §3b |
| `KeyError: 'TRAVELPAYOUTS_TOKEN'` | set the key — see §6 |
| `No module named 'activities_agent'` | **fixed** in `f23dc6f` — pull latest `ui_chainlit_rohan` |
| `RuntimeError: No API key found` | set `ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY` |
| a Chroma / vectorstore error | run that agent's build step first — see §6 |

Your agent's own `requirements.txt` is the authority on its dependencies. The
root `requirements.txt` does not cover everything.

---

## 6. Keys, and what each agent needs beyond them

**No `.env` file exists yet in this repo** — only `.env.example`. Copy it and
fill in what you need:

```powershell
Copy-Item .env.example .env
```

**One `.env` at the repository root is enough for every agent.** Verified: each
agent calls `load_dotenv()`, which walks *up* the directory tree and finds the
root file even from a nested package. You do not need a `.env` per agent.

`.env` is gitignored. **Never commit it.**

Beyond a key, several agents need a build or a service running first — this is
the step people miss:

| Slot | Credentials | Also needs |
|---|---|---|
| `flights` | `TRAVELPAYOUTS_TOKEN` | — (deps already satisfied; a token is the only blocker) |
| `destination` | `ANTHROPIC_API_KEY`; `GEOAPIFY_API_KEY` for Geoapify tools | ~80 MB embedding download on first corpus query |
| `restaurants` | none by default | Ollama running; set `RESTAURANT_AGENT_MODEL` to a tag you have actually pulled (`ollama list`) — the default `lfm2.5` is not the one most of us have |
| `budget` | `ANTHROPIC_API_KEY` **or** `OPENROUTER_API_KEY` | `pip install -r budget_agent/requirements.txt`, then **`python budget_agent/scripts/build_vectorstore.py`** — hard error otherwise |
| `activities` | `OPENROUTER_API_KEY`; `OPENTRIPMAP_API_KEY` for tier 3 | `pip install langchain-mcp-adapters`; set `DEEP_AGENT_MODEL` (see §3b) |
| `money_customs` | `COHERE_API_KEY` | ~80 MB embedding download; index self-builds |

Full detail, with `file:line` for every variable: [`ENVIRONMENT.md`](ENVIRONMENT.md).

> **A key can make an agent worse.** With `OPENTRIPMAP_API_KEY` set, Activities
> stops refusing unknown cities and starts answering them — but its geocode has
> no country filter, so `name=Aruba` resolves to a town in **Italy**
> (`country:"IT"`, Europe/Rome) and it returns Piedmont castles described as
> Aruba attractions, then caches them to `local_activity_docs/aruba.json` so
> every later query repeats it without re-querying. `name=Oranjestad` resolves
> correctly to `AW`. Reported to Limeng/Jainam; until it is fixed, leaving that
> key unset produces a more honest answer than setting it.

### You do not need everyone else's keys

This is the part people get wrong, because the instinct is to think the UI needs
the whole table above filled in before it is useful. It doesn't.

**To verify your own agent, you need exactly one key: yours.** Turn on your slot
and leave the other five as stand-ins:

```powershell
$env:TRAVEL_UI_AGENTS = "flights=real"     # your slot only
chainlit run app.py -w
```

Your agent is live, runs on your key, and you see it inside the real pipeline —
receiving the real task string the orchestrator composes, with its output landing
in the real assembled itinerary. The other five slots return fixed strings and
cost nothing. This is the intended daily workflow.

### Why the *full* pipeline is a different problem

Every agent is imported into one Python process today
(`orchestrator_config.py` → `LocalFunctionClient`). So running all six live at
once means one machine holding **all six agents' keys and all six agents'
dependencies simultaneously**.

That does not compose out of per-person `.env` files, and it has two consequences
worth knowing before anyone tries:

- **Keys.** Nobody can run the whole thing without collecting every teammate's
  credentials onto one machine — and whoever's key is used pays for the calls.
- **Dependencies.** Six stacks share one venv, so they can conflict for reasons
  nobody caused. The already-found example: `destination_data` builds its Chroma
  collection with `all-MiniLM-L6-v2` while the restaurant corpus uses Chroma's
  default embedding function, and two collections built with different embedding
  functions cannot share one index.

So: **per-slot for development, all-slots only for a rehearsed demo.** For the
demo, one machine assembles one `.env` once. If the team standardises the LLM
provider (an open question — see `UI_STATUS.md`), that shrinks to roughly one
model key plus the three domain API keys (Travelpayouts, Geoapify, OpenTripMap),
which are per-provider and unavoidable.

The longer-term fix is architectural, not a secrets problem: agents behind a
transport rather than imported, so each one carries its own deps and its own key
and the orchestrator holds neither. `subagent_client.py` already sketches that
path (`SlimSubagentClient`), and it is the reason the per-agent diagrams label
the orchestrator↔agent link A2A.

### Rules for keys

- `.env` is gitignored. **Never commit it**, and don't paste keys into Slack or
  into a source file — check `git diff` before you commit if you've been editing
  near config.
- If your agent reads a key at *import* time, a missing key shows up as
  `[<slot> unavailable]` rather than a runtime error. That's the `flights`
  behaviour today, and it's why a missing token looks like a build failure.

---

## 7. Known problems that are not your fault

1. **Activities is wired to the wrong import path.** `orchestrator_config.py:53`
   imports `activities_agent`, which matches neither on-disk copy
   (`activities/local_activity_docs/` and `activities-agent-limeng/`). Forcing
   `activities=real` will always fall back until the team settles on one copy and
   one path.
2. **`budget_agent` used to be ambiguous.** Two packages shared the name, and
   import order decided which one you got. Fixed — `budget_agent` now means
   Shashank's agent alone. If you have a stale checkout with odd budget import
   errors, pull.
3. **A stale `TRAVEL_UI_AGENTS` in your shell will mislead you.** It persists for
   the whole terminal session. If the UI asks for a key you didn't expect, or a
   slot is live when you didn't ask, clear it:
   ```powershell
   Remove-Item Env:TRAVEL_UI_AGENTS -ErrorAction SilentlyContinue
   ```
4. **Without `-w`, edits are not picked up.** You will edit a file, see no
   change, and doubt yourself.

---

## 8. Checking things without a browser

```powershell
python ui/verify_seam.py        # asserts the seam's guarantees, all six slots
python sandbox/run_pipeline.py  # shows the exact task string each agent receives
```

`run_pipeline.py` is the useful one when your agent runs standalone but
misbehaves in the pipeline — it prints the precise text the orchestrator hands
you, so you can see whether the input is what your prompt expects.

Neither needs a key or a browser.

---

## 9. Deployment — not yet, and here's why

Nothing is deployed and nothing needs to be. Every agent is currently a stand-in,
so a shared URL would serve sample data to everyone — no value over running it
locally.

Options when we do want one:

- **Just localhost** (now): each person runs their own. Best for development.
- **Share over LAN** (zero effort): `chainlit run app.py --host 0.0.0.0 --port 8000`,
  then teammates hit `http://<your-ip>:8000`. Fine for a live demo. Your machine,
  your keys, your bill.
- **Real hosting** (later): it's a normal FastAPI/uvicorn app, so Render, Fly,
  Spaces etc. all work. Two things to settle first — keys move into a secret
  store rather than `.env`, and **every visitor's query can spend money** on live
  model calls. Worth deciding only once at least one agent is live.

---

## 10. Reporting back

If your agent falls back and the cause isn't obvious, paste:

1. the `TRAVEL_UI_AGENTS` value you used,
2. the `[seam]` line and traceback from the terminal,
3. what the step label said.

That's enough to tell a wiring problem from an agent problem.
