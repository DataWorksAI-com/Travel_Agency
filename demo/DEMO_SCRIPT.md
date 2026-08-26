# Demo script — 25 Aug 2026

Read top to bottom. Bold text is what you say; indented text is what to point at.

---

## Before you start (30 seconds, to yourself)

Check the step labels on the first run. Each one reads `(mode, elapsed)`:

- `(live agent, 12.4s)` — real
- `(sample data, 0.0s)` — stand-in, that slot didn't get switched on
- `NOT CONNECTED — the X agent did not run` — real was requested and it failed

If two slots aren't live, **say so out loud in the opener rather than hoping nobody
notices.** It's a feature: the seam was deliberately built so a failed agent can
never silently become a stand-in. It reports the gap and carries the cause.

To go from 4 to 6: fix the env var and **restart Chainlit** — `TRAVEL_UI_AGENTS` is
read once at import, and a failed slot stays failed for the life of the process.

---

## Opener (60 seconds)

> **"This isn't a product demo. Six of us built one agent each, this is the first
> time they're all in one pipeline, and I want each of you to watch yours run and
> hear exactly how it behaves — what it retrieved, what it made up, and what it
> inherited broken from the agent upstream.**
>
> **One finding up front, because it reframes everything else. There is no
> destination that all six agents can actually answer for. Restaurants covers six
> Caribbean cities. Activities covers six temperate ones. The intersection is
> empty — not 'we haven't found a good city yet', literally empty. Budget is
> tropical-only. Money and Customs is seventeen hardcoded countries.**
>
> **So the best we can do tonight is five out of six, and I'll show you the three
> runs that map where the edges are."**

If a slot is dummy, add:

> **"Two slots are on sample data tonight — you'll see it in the step label,
> because a stand-in returns in zero-point-zero seconds. That's deliberate: the
> seam won't let a failed agent quietly pretend to be a real one."**

---

## Run 1 — `Plan a week in Cancún from Boston in September, budget $3000`

**Type the accent.** `Cancún`, not `Cancun`. This matters — see run 3.

### 0:00 — "Request parsed" step appears

> **"That parse is pure regex, no model. It knows about twenty-one cities and maps
> them to countries; anything else it passes through as if it were a country name.
> And note what's missing — `plan_trip` has no origin-city parameter at all. 'From
> Boston' collapses to 'USA'. Nobody downstream, including the Flights agent, ever
> learns the origin city."**

### 0:00–0:40 — nothing on screen. Dead air. Fill it.

> **"This gap is Money and Customs running alone, and it's worth explaining why it
> gets to go first and by itself. Its entire output — as prose, verbatim — gets
> pasted into both the Flights prompt and the Restaurants prompt. It's the only
> true fan-out in the system. There's no shared state object anywhere in this
> pipeline; context propagation is string concatenation into the next prompt. So
> if this agent is wrong, it's wrong in three places downstream and nothing checks
> it."**

### 0:40 — Money & Customs step

> **"The Money & Customs agent. Seventeen countries, hardcoded, and the file is honest about
> provenance — most entries say 'general knowledge, not independently verified.'
> Mexico is one of the seventeen, so what you're seeing is real.**
>
> **The thing to know is what happens when it isn't. This agent can never return
> 'not found.' Below a 0.55 confidence threshold it returns the nearest match
> anyway, with `found: True` and a prose warning the model is free to drop. You'll
> see that bite on run two.**
>
> **The ask for this agent is one line: let `found: False` exist."**

If time: the team already hit this class — a Vietnam query matched the Philippines
with false confidence. The fix scrubbed neighbour names out of the text but left
the always-return-nearest behaviour intact.

### 0:45 — Destination step → **Joel / jancapmoi**

> **"Joel's agent. Fifty-two cities in the RAG corpus, plus live Geoapify,
> Open-Meteo and holiday lookups. Cancún is a real entry, so this is real.**
>
> **Credit first, because this agent does something none of the others do: when the
> match is weak it relaxes its filters in a fixed documented order and tells you it
> did — returns `retrieval_confidence: low` with a note naming which preferences it
> dropped. That's the behaviour I want everywhere.**
>
> **The problem is what it writes. Every successful lookup gets appended back into
> the committed shared corpus. Hold that thought — it's run three."**

### 0:50–1:40 — Flights, Restaurants, Activities appear together

They're one `asyncio.gather`, so they arrive in completion order, not list order.

**Flights → Brinda**

> **"Brinda's agent. Travelpayouts. One caveat worth saying out loud so nobody reads
> that number as bookable: those prices are cached up to seven days. It's not live
> availability.**
>
> **Brinda, there's one thing I need you to fix and it's the highest-priority item
> in the whole repo. The API token is passed as a query parameter, and when a
> request fails the raw error string is returned to the caller. A `requests`
> HTTPError stringifies as the full URL — including `token=` and the token. That
> string goes to the seam, to `app.py`, and into the browser transcript. It also
> goes into Budget's prompt, because every upstream reply gets concatenated in
> there. Nothing on that path redacts anything.**
>
> **Strip credentials from the error strings, or move the token to a header."**

Second beat, if there's room — a good model-choice lesson:

> **"This slot was on llama-3.3-70b last week. Three identical prompts gave
> $2411, 'no available flights', and 'no cached data' — and it was citing 2024
> dates against a 2026 clock. gpt-4o-mini gave $256 three times in about four
> seconds. Same prompt, same tools. The model was the whole difference."**

**Restaurants → Vrushti**

> **"Vrushti's agent, and I want to be clear that this is the best-behaved agent in
> the system. Cancún is one of its six cities so you're seeing real records.**
>
> **What makes it the best-behaved is what it does when it *doesn't* have the city
> — you'll see that on run two. It refuses. It names its exact coverage and says
> nothing was invented. It also refuses to ever relax the city or the dietary
> filter, and the comment in the code is the right instinct: 'a restaurant in the
> wrong country is not a weaker answer, it is a broken itinerary.'**
>
> **It also accent-folds, which means it survives the exact Cancun-versus-Cancún
> mismatch that breaks the Destination agent. Vrushti got that right and Joel's
> agent didn't — same bug class, one agent handled it.**
>
> **My only ask is a cosmetic one: the import error message blames the wrong
> module. It says `No module named 'restaurant_finder'` when the real cause is a
> missing chromadb. Cost me twenty minutes."**

If it came back suspiciously fast with a "answered directly from the database" note,
Ollama isn't up — say so, it degrades to retrieval-only without the model.

**Activities → Limeng / Jainam**

> **"Limeng and Jainam's agent — and this is the one slot that had no chance
> tonight. The corpus is six cities: Boston, Chicago, New York, Kyoto, Paris, Rome.
> There is no Caribbean city in it. Cancún has zero coverage by construction, so
> nothing you're seeing here is retrieved.**
>
> **Two real defects. First, the semantic search has no distance threshold
> anywhere — it asks for the five nearest vectors and returns them regardless of
> how far away they are. The only thing stopping cross-city bleed is an optional
> city filter, and the docstring actively invites leaving it off. A 'beach day in
> Cancun' query can hand back the Colosseum labelled `city: multiple`, and the
> model never sees a score telling it the match is garbage.**
>
> **Second — and this is the same root cause as Joel's — the live expansion call
> has no country filter. We measured `name=Aruba` resolving to a town in Italy and
> returning Piedmont castles. And then it *saves* that, overwriting the city file,
> so tiers one and two serve it forever afterwards. Which means, plainly: an
> OpenTripMap key currently makes this agent worse. That's why the last commit left
> it unset.**
>
> **The ask is three small things: a score threshold, a required city filter, and a
> country filter on the geoname lookup."**

Optional laugh: `_is_food_request` is a substring match on `"eat"`, so it fires on
"theater" and "great."

### 1:40 — Budget step → **Shashank**

> **"Shashank's agent, and it goes last because it can only cost what the others
> produced. Cancún is one of its fifteen cost documents, so this number is real.**
>
> **Two things. The first is his, the second is mine.**
>
> **His: retrieval has no coverage check. It's a bare similarity search with k
> equals three and no score threshold, so it always returns three documents. Watch
> what that does on run two. And the mitigation right now is a line in the system
> prompt saying 'if the destination isn't in the knowledge base, say so clearly' —
> that's a prompt, not a guard. Worse, the agent is told to do a second retrieval
> pass as verification, which returns the same wrong documents and reads as
> confirmation.**
>
> **Mine: it gets five blobs of prose from my orchestrator when its tools want
> numbers. If an upstream agent failed, the string 'Not connected, the Flights
> agent did not run' arrives looking like data, and Budget will produce a confident
> total that silently omits airfare.**
>
> **Shashank — a similarity threshold, or a coverage check against your fifteen
> cities. Vrushti's agent already does exactly this; it's worth copying her
> approach."**

### Close run 1

> **"Five out of six. That's our ceiling, and the one that missed had no way to
> hit."**

---

## Run 2 — `Plan a week in Rome from Boston in September, budget $3000`

This is the mirror image. Set it up before you hit enter:

> **"Same pipeline, temperate city. Watch three things: Activities finally gets to
> use real data, Restaurants tells you the truth, and two agents lie to you with a
> straight face."**

**Activities** — now on curated Rome data. Credit Limeng and Jainam: this is the
agent working as designed.

**Restaurants** — the refusal. This is the slide-worthy moment:

> **"Read that. 'This restaurant agent holds records for Aruba, Cancun, Honolulu,
> Montego Bay, Nassau, San Juan only. Rome is outside that coverage, so no
> restaurant has been recommended and nothing has been invented.' That is a
> correct answer. That's what I want from an agent that doesn't know."**

**Budget** — and immediately contrast:

> **"Now Budget, same situation — Rome isn't in its fifteen cities either. Same
> problem, opposite behaviour. It returned the three nearest documents, which are
> tropical beach destinations, and costed a week in Rome off Bali and Cancún
> numbers. Nothing in that output tells you it missed.**
>
> **Two agents, identical predicament. One refused, one improvised. The difference
> is a score threshold."**

**Money & Customs** — Italy is not one of the seventeen:

> **"And Italy isn't in those seventeen either — so what you're reading is
> tipping and haggling advice for whichever country embedded closest. Probably
> France or Germany. Presented as the answer."**

---

## Run 3 — `Plan a week in Cancun from Boston in September, budget $3000`

**Drop the accent.** Before you hit enter, show a clean `git status`:

```powershell
git status --porcelain -uall   # prints nothing
```

> **"Same city as run one. One character different — I've dropped the accent off
> the u. Watch the repo."**

After the run:

```powershell
git status --porcelain -uall
```

> **"Two tracked files just changed and one new file appeared, because I asked a
> question.**
>
> **Here's what happened. The geocoder looks for an exact case-folded match.
> Open-Meteo's record is 'Cancún' with the accent. 'Cancun' doesn't match it, falls
> through to a line that just takes the API's first result, and lands on a village
> in Guangxi, China. Country code CN. Inland. The cached beach is 金沙滩, and the
> nature reserve it grabbed is in Jilin — about two thousand kilometres from the
> coordinates it geocoded.**
>
> **And the Destination agent writes that into `destinations.json`, which is
> committed on purpose because rebuilding it costs about a hundred and forty live
> API calls. So that entry is now in everyone's checkout the next time they pull.
> It sits right next to the correct Cancún/MX record — two entries, one city,
> because the cache key is case-insensitive but not accent-insensitive.**
>
> **Joel — accent-fold the cache key, and put the corpus write-back behind a
> confidence check. Right now it's unconditional: one query permanently edits
> everyone's data."**

Then restore in front of them:

```powershell
git restore destination_agent/destination_profiles.json destination_data/destinations.json
Remove-Item activities-agent/local_activity_docs/cancun.json -ErrorAction SilentlyContinue
git status --porcelain -uall
```

---

## Closing (90 seconds)

> **"Five things, ranked.**
>
> **One — strip credentials out of error strings. Flights and Activities. That's
> live, and it reaches the browser.**
>
> **Two — country filters, and stop writing to the shared corpus silently.
> Destination and Activities, same bug class in both.**
>
> **Three — score thresholds. Budget, Activities, Money and Customs. Three of our
> six agents currently cannot say 'I don't know', and Vrushti's agent already shows
> what the fix looks like.**
>
> **Four — mine. My orchestrator computes the resolved city and then never passes
> it to Flights, Restaurants or Activities. The docstring claims it does. It
> doesn't. And while I'm confessing: my seam test printed 'all checks passed' for a
> while when the two assertions that mattered had stopped running — they looped
> over the list of slots expected to fail, and once everything went live that list
> was empty.**
>
> **Five, and this is the one that needs a group decision. Our corpora don't
> overlap. Somebody has to pick — are we a tropical beach product or a city-break
> product? — and then all six of us cover the same six cities. Until that call gets
> made, five out of six is the ceiling, and it isn't any one person's fault."**

---

## If something breaks mid-demo

- **A slot goes NOT CONNECTED** — good. Read the cause aloud; that's the seam
  working. It was built specifically so a failed agent can't become a stand-in.
- **Restaurants returns instantly** with "answered directly from the database" —
  Ollama isn't running. Say it degrades to retrieval-only without the model.
- **Everything hangs past ~3 minutes** — kill it, restart Chainlit. A failed client
  is cached for the life of the process.
- **Do not** `git add -A` or `git commit -a` at any point tonight. The poisoned
  entries live in tracked files.
