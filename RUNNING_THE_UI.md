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

## 7b. Findings from the 25 Aug agentic-orchestrator runs

Everything below was observed in live runs while building `orchestrator_agent.py`,
not read off the code. Where it is fixed, the fix is named.

### One bug class, found in three different agents

**An unfiltered nearest-neighbour lookup always returns something, and every
agent here treated that something as an answer.**

| Agent | What it returned | Cause | Status |
|---|---|---|---|
| Activities | 2 cinemas + 2 Pentecostal churches as the Cancún activity plan | OpenTripMap radius search with no `kinds` and no importance filter | **fixed** — `rate=2`, a `kinds` whitelist, 25 km radius. Now returns El Meco, Cancun Underwater Museum, MUSA, EL REY ruins |
| Activities | Piedmont castles for Aruba | `/geoname` matched on city name alone; `Aruba` resolves to a town in **Italy** | **fixed** — country code passed *and verified*; a mismatch refuses rather than caches |
| Destination | `Beaches: Le Palme`, `Attractions: Guerrilla spam, Il coniglio, Street Art di Mauro Sgarbi` for **Rome** — no Colosseum, no Vatican, no Trevi | Geoapify POI radius search, same shape, no importance filter | **open** — Joel's agent needs the equivalent of `rate=2` |
| Destination | `Cancun` cached as a village in Guangxi, China, and written into the committed RAG corpus | `resolve_place._pick_best` fell through to `usable[0]`; the exact-match test was not accent-folded, so `Cancun` never matched Open-Meteo's `Cancún` | **fixed** — accent-folded comparison |
| Budget | Bali/Cancún cost documents returned for Rome | `similarity_search(k=3)` with no score threshold | **open** — but see below, it now discloses the gap when given evidence |
| Money & Customs | German tipping rules served as Italian | nearest-match returned with `found: True` below the confidence threshold | **fixed** — `"found": match_score >= CONFIDENCE_THRESHOLD` |

### Fixing the tool is necessary but not sufficient

The sharpest result of the day. After Money & Customs correctly returned
`found: False` for Italy, one run said *"I couldn't find any information on
tipping norms for Italy"* — and the **next identical run invented Italian tipping
norms from the model's own knowledge**, while quoting the USA record verbatim
alongside them.

The tool told the truth; the agent above it filled the gap anyway, and did so
non-deterministically. A truthful `found: False` only helps if the prompt also
forbids answering from priors. Rule 7 in `money_customs_agent.py` was widened to
say so explicitly, and to state that returning only the exchange rate is a
complete answer.

The next Rome run returned exactly:

> *"I hold no data for tipping norms and haggling information in Italy.
> Exchange rate: 1 USD = 0.85749 EUR (as of 2026-08-25)."*

**That was a lucky sample, and calling it "confirmed" was wrong.** The jig
(below) later failed one of two Rome runs with *"said 'germany'; said 'german'"*.
The prompt reduces the behaviour; it does not eliminate it. Treat any
single-run confirmation of a probabilistic fix as unproven.

**Generalisation for the other agents:** a coverage signal is only as good as the
instruction that consumes it. Adding a threshold without also forbidding the
fallback moves the fabrication one layer up, where it is harder to see.

### Evidence in the prompt changes what an agent will admit

Budget, same model, same corpus, same prompt — the only variable was whether the
orchestrator forwarded the other agents' replies in its task:

| | Without the upstream replies | With them |
|---|---|---|
| Flights had reported "no data found" | *"Round-Trip Flight: $425"*, stated as fact | *"The flights agent returned no live data. The $425 estimate comes from the knowledge base (range $350–$500). Verify before booking."* |

On Rome it went further unprompted: *"Rome is not in the cost knowledge base...
figures are informed estimates, not knowledge-base-verified numbers."* Budget was
never modified. It disclosed the gap because it could see the gap.

### Self-expanding corpora overwrite curated data

A single Rome run **destroyed five hand-written activity entries** (Colosseum,
Vatican Museums, Trastevere, Villa Borghese, Trevi) by expanding a city that
already had coverage — `save_activities_for_city` opens the file in `"w"`.
`activities-agent/README.md:113-116` documented this behaviour and nothing
guarded it. `expand_activities_corpus` now refuses to expand a covered city.

Related, unresolved and **for Limeng and Jainam to decide**: the self-expanding
corpus and `run_tests_offline.py` contradict each other. Every live run adds a
city; the tests assert exactly six. Either expanded cities belong in a separate
untracked layer, or the assertion should be "at least the curated six."

### The parse step was reading the wrong word

`Request parsed` reported `Destination country: September` for *"a week in Cancún
from Boston in September"*. `_PLACE` allowed only `[A-Za-z]`, so the first `in`
matched as far as `Canc`, failed on the accent, and the engine went on to match
the second `in` — where the comma satisfied the lookahead. Fixed by widening the
class to `À-ÿ` and accent-folding the city lookup.

### What the agentic orchestrator changed, concretely

- **The resolved city now reaches the other agents.** `orchestrator.py` computes
  `destination_result` and never passes it on; the agent records it and it is
  prepended to every subsequent task string by code, not by instruction.
- **So does the origin city.** `plan_trip` has no origin-city parameter at all,
  so "from Boston" was previously unreachable. Flights now receives it.
- **A deterministic floor catches what the model omits.** On its first live run it
  caught a silently skipped Money & Customs; later it caught a skipped Destination
  that the model had nonetheless written a confident section for.
- **Budget must be called after the others.** The model emitted all six tool calls
  in one parallel batch, so Budget's task was assembled from an empty ledger.
  `ask_agent` now refuses Budget until Flights, Restaurants and Activities have
  returned.

### Measured: agentic vs deterministic orchestrator

`evaluation/run_orchestrator_jig.py`, 6 cases x 2 orchestrators x 2 runs, all six
agents live, `ORCHESTRATOR_MODEL=openrouter:openai/gpt-4o-mini`. Raw rows in
`evaluation/results/live_20260825_223114.csv`.

| | coverage | propagation | honesty | grounding | passed | median |
|---|---|---|---|---|---|---|
| agent | 0.986 | **0.938** | **0.917** | 0.75 | **7/12** | 109.8s |
| deterministic | 1.0 | 0.542 | 0.833 | **1.0** | 4/12 | **74.4s** |

**Propagation is the honest headline, and it is narrower than the average
suggests.** For a named city both score 1.0, because the city is already in the
raw request text the fixed pipeline forwards. The columns only diverge where the
resolved city differs from what the user typed:

- `vague` ("somewhere warm"): agent **1.0, 1.0** vs deterministic **0.0, 0.0**
  — *"city 'Honolulu' never reached: activities, flights, restaurants"*
- `accent`: deterministic 0.25 twice; agent 1.0 then 0.25

Caveat against our own number: deterministic `cancun` scored 0.0 with *"no city
resolved from destination's reply"*, which is the jig's regex failing on that
reply format, not a real propagation failure. 0.542 flatters the agent slightly.

**Grounding is where the agent is worse, and the reason is structural.** The
fixed pipeline concatenates text, so it *cannot* invent a figure. The agent
synthesises, so it can:

- `agent cancun run 2` — never called Budget, then stated **13,730**
- `agent vague` — invented a `$10` figure on both runs

Stated plainly: **the planning layer buys propagation and costs grounding.**

**Both orchestrators are non-deterministic.** Four `INCONSISTENT` flags, two of
them on the *deterministic* path (`rome` said "germany" on run 2; `tokyo` said
"bali" on run 2). "Deterministic" describes the sequencing only — the pipeline is
not reproducible, because the six agents are not. Do not treat the fixed path as
a stable control; treat it as a fixed-order condition.

**The Activities guards held under load.** Across 24 runs the corpus expanded to
five new cities with no junk and no curated data lost: `aruba.json` = Sero
Jamanota, Hooiberg (not Piedmont castles); `rome.json` still Colosseum, Vatican,
Trastevere.

### How often the honesty failures actually happen

`--cases rome --runs 5` on both orchestrators, plus the two Rome runs in the
matrix above — 14 Rome runs in total
(`evaluation/results/rome_variance_20260825_230559.csv`).

| | agent | deterministic |
|---|---|---|
| coverage / propagation / grounding | 1.0 | 1.0 |
| honesty | **0.8** | **0.8** |
| the one failure | *said 'germany'* (Money & Customs) | *said 'bali'* (Budget) |

Pooled across all 14 Rome runs:

| Failure | Agent responsible | Rate |
|---|---|---|
| German tipping rules presented as Italian | Money & Customs | 2/14 ≈ **14%** |
| Bali cost figures in a Rome itinerary | Budget | 1/14 ≈ **7%** |
| any honesty failure | | 3/14 ≈ **21%** |

**Two conclusions worth carrying into the writeup.**

1. **The orchestrator design does not move this number.** Both paths score 0.8,
   for different reasons. Coordination can guarantee that an agent was *called*
   and that its output *reached* the next agent — the floor and the propagation
   mechanism both do this reliably. Neither can stop an agent that runs
   successfully and states something no tool returned. Fabrication has to be
   fixed where it originates.

2. **A ~1-in-6 failure rate is the dangerous kind.** It passes a demo, passes
   manual testing, and passes a single-run "confirmation" — which is exactly the
   mistake made above when the Money & Customs prompt fix was called confirmed
   off one clean Rome run. Any fix to probabilistic behaviour needs `--runs 5`
   before it is believed.

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
