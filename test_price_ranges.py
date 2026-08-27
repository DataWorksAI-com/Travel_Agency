"""A price quoted as a range must arrive as one item carrying both ends.

Before this, _AMOUNT got ranges wrong in two opposite ways, and both understated
the trip:

  "$80-120"     -> $80 only. The high end has no currency symbol, so it was
                   invisible and Budget priced the cheapest case.
  "$80 - $120"  -> two independent line items. One activity counted twice, and
                   neither labelled a range.

In a system built to avoid making a trip look more affordable than it is, that
is the wrong direction to be wrong in.
"""
import sys

sys.path.insert(0, ".")
from orchestrator_costs import extract_line_items, build_budget_brief

passed = failed = 0


def check(label, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print("  [PASS] %s" % label)
    else:
        failed += 1
        print("  [FAIL] %s\n         got  %r\n         want %r" % (label, got, want))


def only(text, slot="activities"):
    items = extract_line_items(slot, text)
    return items


# --- the forms agents actually write -----------------------------------------
for text, low, high in [
    ("Tulum guided day trip $80-120 per person.\n", 80.0, 120.0),
    ("Reef snorkeling $60 - $120 per person.\n", 60.0, 120.0),
    ("Cenote entry $15-25 each.\n", 15.0, 25.0),
    ("Xel-Ha park $130 to $180 per person.\n", 130.0, 180.0),
    ("Chichen Itza tour $120\u2013150 per person.\n", 120.0, 150.0),
]:
    items = only(text)
    label = text.strip()[:34]
    check("%-36s one item" % label, len(items), 1)
    if items:
        check("%-36s low/high" % label, (items[0]["cost"], items[0].get("cost_high")), (low, high))


# --- a plain price must be untouched -----------------------------------------
plain = only("Museum entry $30 per person.\n")
check("plain price still one item", len(plain), 1)
check("plain price has no cost_high", plain[0].get("cost_high"), None)
check("plain price value", plain[0]["cost"], 30.0)

rest = extract_line_items("restaurants", "El Muelle Seafood -- about $35 per person.\n")
check("real restaurant price unaffected", (len(rest), rest[0]["cost"], rest[0].get("cost_high")),
      (1, 35.0, None))

# --- no double counting -------------------------------------------------------
both = only("Reef trip $60 - $120 per person.\n")
check("dash-with-two-symbols is NOT two items", len(both), 1)
costs = [i["cost"] for i in both]
check("the high end is not a separate item", 120.0 in costs and len(costs) > 1, False)

# --- per-unit survives ---------------------------------------------------------
check("per person detected on a range", only("Tour $80-120 per person.\n")[0]["per"], "person")
check("per night detected on a range", only("Cabana $50-90 per night.\n")[0]["per"], "night")

# --- nonsense is left alone ----------------------------------------------------
check("reversed range is not treated as a range",
      only("Odd listing $120 to $80 per person.\n")[0].get("cost_high"), None)

# --- Budget is told what to do with it ----------------------------------------
brief = build_budget_brief(
    task="Plan 5 nights in Cancun for 2.",
    replies={"activities": "Tulum guided day trip $80-120 per person.\n"},
    is_failure=lambda r: False,
    stated_budget="$3000",
)
check("cost_high reaches Budget", '"cost_high": 120.0' in brief, True)
check("rule 7 present", "use 'cost_high'" in brief, True)
check("rule 7 forbids quoting the low end alone",
      "Never present 'cost' alone" in brief, True)

print()
print("%d/%d passing" % (passed, passed + failed))
sys.exit(1 if failed else 0)
