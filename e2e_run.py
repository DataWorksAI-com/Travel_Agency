import truststore; truststore.inject_into_ssl()
import asyncio, os, sys, time
# Windows console is cp1252; run 7 finished all six slots and then died printing
# the report, because Budget's reply contained a U+2705. Lost the whole run.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(HERE, ".env"))
assert os.getenv("TRAVEL_UI_AGENTS"), "env did not load"

from orchestrator import plan_trip
from ui.agent_seam import install_seam
from ui.request_parse import describe, parse_request

REQ = "Plan 5 nights in Cancun for 2 people from Boston in September, total budget $3000"
T0 = time.perf_counter()
spans, order = {}, []

async def before(slot, mode, task):
    spans.setdefault(slot, {})["start"] = time.perf_counter() - T0
    order.append(("START", slot, time.perf_counter() - T0))
    print("  %6.1fs START %s" % (time.perf_counter() - T0, slot), flush=True)

async def after(slot, mode, task, reply, elapsed):
    now = time.perf_counter() - T0
    spans[slot].update(end=now, mode=mode, elapsed=elapsed, reply=reply or "", task=task)
    print("  %6.1fs END   %-13s %-8s %6.1fs  %d chars" % (now, slot, mode, elapsed, len(reply or "")), flush=True)

print("orchestrator =", os.getenv("TRAVEL_UI_ORCHESTRATOR"), " concurrency =", os.getenv("TRAVEL_UI_MAX_CONCURRENCY"))
print("configured:", install_seam(before=before, after=after), flush=True)
parsed = parse_request(REQ)
out = asyncio.run(plan_trip(**{k: v for k, v in parsed.items() if not k.startswith("_")}))
TOTAL = time.perf_counter() - T0

print("\n" + "=" * 78)
print("TIMELINE (each row is one slot; # = busy)   TOTAL %.1fs" % TOTAL)
print("=" * 78)
scale = 74.0 / max(TOTAL, 0.001)
for slot, s in sorted(spans.items(), key=lambda kv: kv[1]["start"]):
    a, b = int(s["start"] * scale), max(int(s["end"] * scale), int(s["start"] * scale) + 1)
    print("%-14s|%s%s%s| %5.1f-%5.1fs (%.1fs) %s" % (
        slot, " " * a, "#" * (b - a), " " * (74 - b), s["start"], s["end"], s["elapsed"], s["mode"]))
busy = sum(s["elapsed"] for s in spans.values())
# union of busy intervals = wall time actually spent inside agents
iv = sorted((s["start"], s["end"]) for s in spans.values())
union, cur_a, cur_b = 0.0, None, None
for a, b in iv:
    if cur_b is None or a > cur_b: union += (cur_b - cur_a) if cur_b else 0; cur_a, cur_b = a, b
    else: cur_b = max(cur_b, b)
union += (cur_b - cur_a) if cur_b else 0
print("\n  sum of slot time      %6.1fs" % busy)
print("  wall time in agents   %6.1fs   (parallel saving %.1fs)" % (union, busy - union))
print("  orchestrator's own    %6.1fs   (total minus agent wall time)" % (TOTAL - union))
for slot, s in sorted(spans.items(), key=lambda kv: -kv[1]["elapsed"]):
    print("\n--- %s  %.1fs  %s\n  TASK : %s\n  REPLY: %s" % (
        slot, s["elapsed"], s["mode"], s["task"][:200].replace("\n", " | "),
        s["reply"][:350].replace("\n", " | ")))
print("\n" + "=" * 78 + "\nFINAL\n" + "=" * 78)
print(out)
