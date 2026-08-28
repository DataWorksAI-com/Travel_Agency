# Demo notes — orchestrator and seam, 27 Aug 2026

For the team before the demo. Short on purpose. `HANDOFF_2026-08-27_part2.md`
and the commit messages are the long form; the commits are the design record.

## The two queries that work end to end, right now

```
Plan 5 nights in Honolulu for 2 people from Boston in September, total budget $3000
Plan 5 nights in Cancun for 2 people from Boston in September, total budget $3000
```

Both return **all six agents live** — destination, flights, restaurants,
activities, budget, money & customs. No stand-ins. 14 live runs today, zero
silent substitutions, zero slot failures.

Run **Honolulu first**: Cancun's own destination agent flags September as an
"avoid month, hurricane season", so that itinerary opens by advising against the
trip. Honolulu's says September is one of the best months.

```
cd wt-ui && ./.venv/Scripts/python.exe -m chainlit run app.py --port 8000
```

Do **not** pass `-w`. The file watcher reloaded mid-request during a live run
and truncated it, which read as an agent failure. Check the banner says "live
agent" and not "sample data". A run costs about $0.0025.

Scripted, with a per-slot timeline and no browser:

```
./.venv/Scripts/python.exe -u e2e_run.py "<your query>"
```

## Why these two, and only these two

Coverage is the constraint, not the code. A city needs **all six** agents to
hold data for it, and the binding limit is Restaurants, which has six cities
(`restaurant_agent/restaurants_live.py` `CITY_COORDS`). Every candidate in the
system, checked against all six agents plus a live fare from Boston:

| city | dest | rest | acts | budget | money | flights |
|---|---|---|---|---|---|---|
| **Cancun** | Y | Y | Y | Y | Y | $154 |
| **Honolulu** | Y | Y | Y | Y | Y | $325 |
| Aruba | Y | Y | Y | – | – | $256 |
| Nassau | – | Y | – | – | Y | $132 |
| San Juan | – | Y | – | – | – | $169 |
| Montego Bay | – | Y | – | Y | Y | **none** |

Aruba is the cheapest third: it needs one Money & Customs country and one Budget
city doc. Montego Bay cannot work whatever anyone adds — Travelpayouts has no
cached BOS→MBJ fare at all.

## Why the speed cannot be meaningfully improved

Measured over 14 live runs today. **Total 98.7s – 249.5s, mean 149.7s.**

| slot | min | max | mean |
|---|---|---|---|
| flights | 4.8s | 12.5s | 7.3s |
| destination | 5.8s | 39.2s | 13.0s |
| activities | 9.3s | 28.9s | 14.5s |
| restaurants | 6.1s | 40.4s | 24.7s |
| money_customs | 21.9s | **100.7s** | 42.5s |
| budget | 26.9s | 76.7s | 45.3s |
| **orchestrator's own** | 34.9s | 81.5s | 45.6s |

Four reasons the number is what it is:

1. **The orchestrator is not the bottleneck.** Its own model time averages 45.6s
   of a 149.7s run — under a third. The rest is the six agents.
2. **The agents are already run 4-wide.** `ask_agents` fans flights,
   restaurants, activities and money_customs out concurrently with
   `asyncio.gather`, and it is enforced in code, not asked for in the prompt —
   confirmed in every run (all four start within ~2.5s of each other).
   `TRAVEL_UI_MAX_CONCURRENCY=4` matches the batch.
3. **Budget must be last, by design.** It prices what the others found, and the
   orchestrator *refuses* to call it before flights, restaurants and activities
   have returned. That refusal exists because Budget once billed $425 for a
   flight Flights had just said it could not find. So the run is at minimum
   destination → batch → budget, serially.
4. **The variance is the providers', not ours.** Same code, same query: one
   Cancun run took 98.7s and another 249.5s. money_customs alone ranged 21.9s to
   100.7s. Its `ChatCohere` is constructed inside that agent, so no config can
   move it, and its four tools take ~1.3s in total — the time is Cohere's.

There is one known scheduling win left, and it is deliberately **not** taken:
money_customs sits in the same `ask_agents` batch, so `gather` makes it gate
Budget even though nothing downstream reads its reply. Measured on the two demo
runs, removing it from the batch saves **0.3s** (restaurants was the long pole)
and **16.6s** (money_customs was). A coin flip for up to ~15%, needing
`create_task` plumbing through `_new_run`, `ask_agents` and assembly, against the
same ledger the honesty floor reads. Not worth doing before a demo. The
deterministic path already has the pattern to copy.

## The Ollama issue (Restaurants)

Restaurants runs on a **local** model, `ollama:qwen2.5:7b` — free, offline, no
API key, which is why it was chosen. Two consequences:

1. **It occasionally under-answers.** Measured today: **1 run in 13** came back
   with "No restaurants in Cancún meet the criteria" instead of the usual three
   places. I could not reproduce it deliberately — I tested the accented city
   name (`Cancun` vs `Cancún`) and the budget constraint in the task, and
   **both hypotheses were falsified**: each returns results reliably on demand.
   It is variance in a 7B model, with no trigger I can name, so nothing was
   changed on a guess. **If a section comes back thin during the demo, re-run
   it** — 12 of 13 runs were fine.
2. **When it does under-answer, the system says so** rather than inventing
   restaurants. The unsourced-figures block reported
   `- Restaurants: the agent answered but published no prices.` That is the
   project working, not failing, and it is worth pointing at rather than
   apologising for.

Not switching that slot to a cloud model before the demo: it would mean swapping
a model that works 12 times in 13 for one that has never run that agent.

Separately, `restaurant_agent_ollama.py:96` reads `RESTAURANT_AGENT_MODEL` at
**import**, so the mid-run provider fallback cannot move that slot. Harmless
today — a local Ollama has no provider to die — and it is that owner's line to
change. Activities had the identical bug and it mattered there, so it was fixed
(`c2fb279`).

## Other notes, briefly

- **The honesty floor is the point of the demo.** After the model finishes, an
  "Unsourced figures" block is appended deterministically, so it cannot be
  paraphrased away. It fired on every run today. Verified figure by figure on
  the Honolulu itinerary: every flight and restaurant number traces verbatim to
  the agent that produced it; Budget's lodging ($900, "~$180/night") and
  activities ($300) came from no agent — and the block says exactly that.
- **No agent prices lodging**, so any accommodation figure is always flagged,
  including on a fully successful run. That gap was open until today.
- **Budget's honesty varies run to run.** Same code, same prompt: one run wrote
  a clean "remaining for accommodation: $1,882", another invented
  "$150–175/night". The floor is what makes that variance safe.
- **The orchestrator has exactly three tools** — `ask_agent`, `ask_agents`,
  `record_trip_state`. The nine deepagents built-ins (`execute`, `write_file`,
  `delete`, `task`, …) are hidden from the model *and* refused at execution.
- **Ownership.** Everything under another owner's agent was changed either with
  their written agreement or on Rohan's explicit instruction, and each such
  commit says which. Limeng's `test_jig.py` is 18/20 before and after every
  change to Activities — the two failures are his Paris case and a pre-existing
  scuba one.
- **Tests: 248 across 13 files**, all passing. `test_agent.py` is a 14th file
  that dies on a missing `langchain_cerebras` module — pre-existing, unrelated,
  not part of the 248.
