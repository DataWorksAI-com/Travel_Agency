# Budget & Cost Agent

Domain-expert agent for the DataWorksAI travel agency multi-agent system.
Owner: Rohan Shivakumar · ALY6980 Capstone · Week 2

Budget is the one constraint every other agent's output has to satisfy. This
agent owns it at both ends: it sets per-category spending ceilings *before*
the other domain agents search, and it checks the assembled plan *after*.

---

## Why both ends, and not just a final check

Sequential planners drift away from global constraints as the plan gets
longer. In HiMAP-Travel (Bui, Li & Liu, 2026) a sequential baseline held 98%
budget satisfaction on day 1 of a trip and **42% by day 5**; the authors call
this *constraint drift under long tool traces*. Their fix is a coordinator
that pre-allocates per-category budget envelopes before the worker agents
run. Their ablation: **removing that coordinator cost 12.98 points of final
pass rate, mostly from budget failures.**

Checking only at the end is also wasteful — four agents generate options that
get discarded. Allocating first means Restaurants, Flights and Activities
search inside a ceiling rather than against one.

---

## Knowledge source

**U.S. Department of State, Office of Allowances — Foreign Per Diem Rates
(DSSR 925).** <https://allowances.state.gov/web920/per_diem.asp>

Real published government data covering 18 Caribbean and Central American
countries / 40 locations. No API key, no rate limit, works offline.

The corpus is **built once and committed** (`data/perdiem.json`). The agent
never fetches at request time. Two reasons:

1. Evaluation runs must be reproducible — the corpus cannot be allowed to
   change between a before-condition and an after-condition.
2. A runtime fetch that fails needs *something* to fill the gap, and whatever
   fills it gets reported to the user with the same confidence as real data.

### Two honest limitations

**These are reimbursement ceilings, not market prices.** They are the maximum
a U.S. government traveller may claim. They are a sound basis for a budget
*envelope*; they are not a price quote, and the agent must not present them
as one.

**Some rates are very old.** 17 of 46 source rows were last surveyed between
9 and 18 years ago — all of Panama, and Antigua's "Other" row still reads $37
per night with an effective date of May 2008. These are live rows on a
current government page. `build_corpus.py` flags anything older than 8 years
with `"stale": true`, and that flag propagates through to the tool output so
the agent can caveat it.

**Not covered:** Puerto Rico and the U.S. Virgin Islands are U.S.
territories and are absent from State's *foreign* per diem dataset entirely,
despite being two of the most obvious tropical destinations from Boston.
Fiji, the Maldives, the Seychelles and Mauritius are excluded deliberately,
to serve as out-of-scope test cases.

---

## Functions

| Tool | Does |
|---|---|
| `estimate_costs` | What will lodging and meals cost for N nights and M travellers |
| `allocate_budget` | Split a total budget into per-category ceilings |
| `verify_plan` | Check an assembled plan against those ceilings |

`verify_plan` returns the failure shape used by the shared sub-agent
contract: `{status, deficit, violation_type}`.

---

## Setup

Windows / PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` (gitignored) with your OpenRouter key:

```
OPENROUTER_API_KEY=sk-or-...
```

## Rebuild the corpus

Only needed if the raw data changes. The output is committed, so a fresh
clone does not need to run this.

```powershell
python build_corpus.py --input raw\perdiem_raw.csv --out data\perdiem.json --ref-date 2026-08-13
```

The script validates as it goes: it flags rows where lodging + M&IE does not
match the published total, skips incomplete rows rather than filling gaps,
and reports stale rates. Expect 17 staleness warnings — they are
informational, not failures.

## Run the tests

```powershell
python -m pytest -q
```

## Run the agent

```powershell
python -m proposed_envelope_agent.agent
```

---

## Layout

```
budget_agent_rohan/
├── build_corpus.py         build-time only; not imported by the agent
├── raw/perdiem_raw.csv     source data as transcribed from State
├── data/perdiem.json       committed corpus + provenance
├── proposed_envelope_agent/
│   ├── corpus.py           load and query the corpus
│   ├── tools.py            the three tools
│   └── agent.py            deepagents wrapper
├── fixtures/sample_plan.json   mock domain-agent output, so this runs standalone
└── tests/test_tools.py
```

---

## Design notes

**No silent fallbacks.** An unknown destination returns
`{"covered": False, ...}` with the list of countries that *are* covered. It
never substitutes a nearby country or a nominal figure. This follows a Week 1
finding: a tool that returned a default price for unknown destinations caused
the agent to report that fabricated number in the same confident register as
a real one. The model cannot distinguish a retrieved value from a default.

**Tool docstrings declare their coverage.** Also from Week 1 — when a tool's
docstring did not state what it covered, an out-of-scope query produced 14
tool calls across 5 destinations the user never mentioned. Declaring coverage
reduced this to a mean of 1.71 calls over 7 runs (SD 0.49).

**The arithmetic is not done by the model.** All budget maths lives in plain
Python and is unit tested. The agent decides *when* to check; it never
computes the numbers itself.

**No vector database, deliberately.** A per diem lookup is an exact-match
table lookup. There is no semantic gap between "Barbados" and the Barbados
row, so embeddings would add cost and a failure mode without adding recall.
Agents whose queries are genuinely fuzzy — "somewhere quiet and romantic" —
need retrieval; this one does not.

---

## Status

- [x] Corpus built and validated — 40 locations, 18 countries
- [x] Corpus loader, no-fallback lookup, city-name resolution
- [x] Three tools implemented — 28 tests green
- [x] deepagents wrapper, system prompt, coverage-declaring docstrings
- [x] `--demo` path runs the full tool chain with no model and no API key
- [ ] LangSmith tracing (env vars only)
- [ ] Test jig and black-box scoring loop
- [ ] Week 3: live hotel MCP, and measure the gap between the per diem
      ceiling and real market rates across all 18 destinations

## References

Bui, T. V., Li, W., & Liu, Y. (2026). *HiMAP-Travel: Hierarchical multi-agent
planning for long-horizon constrained travel.* arXiv:2603.04750

Zhang, Y., et al. (2026). *DeepPlanning: Benchmarking long-horizon agentic
planning with verifiable constraints.* Qwen Team, Alibaba Group.
arXiv:2601.18137

U.S. Department of State, Office of Allowances. (2026). *Foreign per diem
rates by location (DSSR 925).* Retrieved 13 August 2026.

---

*AI assistance disclosure: repository scaffolding, the corpus build script,
and the test suite were drafted with AI assistance. The domain choice,
architecture, allocation policy, and tool implementations are my own.*
