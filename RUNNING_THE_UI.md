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

## 4. ⚠️ The most important section: did my agent actually run?

**Seeing a plan does not mean your agent ran.**

If your agent can't start, the seam catches the failure and substitutes sample
data. The itinerary still renders and still looks plausible. This is deliberate —
it keeps a demo presentable — but it means **output is not evidence.**

Two places to look, and you need both:

### The step label

| Label | Meaning |
|---|---|
| `Flights (live agent)` | your agent ran and its words are on screen |
| `Flights (sample data)` | a fixed string from `sandbox/fakes.py` — **your agent did not run** |

If you set `flights=real` and the step still says **(sample data)**, your agent
failed. Go read the terminal.

### The terminal

Every fallback is announced in the terminal where you ran `chainlit`, with the
cause:

```
[seam] flights: falling back to stand-in -- error-shaped reply: [flights unavailable] 'TRAVELPAYOUTS_TOKEN'
```

plus a full traceback when there is one. The browser gets the stand-in; **the
terminal gets the truth.** Keep it visible while you test.

---

## 5. Reading the failure

Three message shapes, and they mean different things:

| Shape | Where it comes from | What it means |
|---|---|---|
| `[<slot> unavailable] …` | `orchestrator_config.py:130` | your agent could not be **built** — usually a missing import or a key read at import time |
| `[subagent error] …` | `subagent_client.py:98` | it built fine, then **raised during the call** |
| `[subagent unreachable over SLIM] …` | `subagent_client.py:182` | the SLIM/A2A transport stub — not wired to anything live yet |

Common causes and the fix:

| Message | Fix |
|---|---|
| `No module named 'deepagents'` | `pip install deepagents` |
| `No module named 'langchain'` | `pip install langchain` |
| `No module named 'langchain_cohere'` | `pip install langchain-cohere` |
| `KeyError: 'TRAVELPAYOUTS_TOKEN'` | set the key — see §6 |
| `No module named 'activities_agent'` | **known bug**, not yours to fix — see §7 |
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
| `restaurants` | none by default | Ollama running with `lfm2.5`; ~80 MB embedding download |
| `budget` | `ANTHROPIC_API_KEY` **or** `OPENROUTER_API_KEY` | **`python scripts/build_vectorstore.py` first** — hard error otherwise |
| `activities` | `OPENROUTER_API_KEY`; `OPENTRIPMAP_API_KEY` for tier 3 | vector build; `python` on `PATH` for the MCP subprocess |
| `money_customs` | `COHERE_API_KEY` | ~80 MB embedding download; index self-builds |

Full detail, with `file:line` for every variable: [`ENVIRONMENT.md`](ENVIRONMENT.md).

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
