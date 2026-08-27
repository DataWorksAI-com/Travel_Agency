import truststore; truststore.inject_into_ssl()
import asyncio, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
assert os.getenv("TRAVEL_UI_AGENTS"), "TRAVEL_UI_AGENTS did not load"
print("orchestrator =", os.getenv("TRAVEL_UI_ORCHESTRATOR"))

from orchestrator import plan_trip
from ui.agent_seam import install_seam
from ui.request_parse import describe, parse_request

REQ = "Plan 5 nights in Cancun for 2 people from Boston in September, total budget $3000"
events = []
async def after(slot, mode, task, reply, elapsed):
    events.append((slot, mode, elapsed, task, reply))
    print("  [%-13s] %-11s %6.1fs  %d chars" % (slot, mode, elapsed, len(reply or "")), flush=True)

print("configured:", install_seam(after=after))
parsed = parse_request(REQ)
print(describe(parsed))
t0 = time.perf_counter()
out = asyncio.run(plan_trip(**{k: v for k, v in parsed.items() if not k.startswith("_")}))
total = time.perf_counter() - t0
print("\n" + "="*70)
print("TOTAL %.1fs   sum of slot wall-clock %.1fs" % (total, sum(e[2] for e in events)))
for s, m, el, task, reply in events:
    print("\n--- %s (%s, %.1fs)\n  TASK: %s\n  REPLY: %s" % (
        s, m, el, task[:260].replace("\n"," | "), (reply or "")[:500].replace("\n"," | ")))
print("\n" + "="*70 + "\nFINAL\n" + "="*70)
print(out)
