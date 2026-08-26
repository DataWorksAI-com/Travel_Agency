"""
Standalone coverage check for the Money & Customs agent.

Calls search_money_customs() directly -- no Cohere, no API key, no orchestrator,
no Chainlit, no cost. It only touches the local ChromaDB store.

    python money_customs_coverage_check.py

What to look for: the "found" column. For any country NOT in
MONEY_CUSTOMS_FACTS, the tool currently reports found=True and hands back a
different country's etiquette. The agent's own system prompt (rule 7) says
"if a tool returns found=False, say plainly that the information is
unavailable" -- but that rule can never fire, because the low-confidence
branch hardcodes found=True.

Run this before the fix and after it. Only the COVERED rows should say True.
"""

from money_tools import (
    search_money_customs,
    MONEY_CUSTOMS_FACTS,
    CONFIDENCE_THRESHOLD,
)

# Countries the corpus really holds -- these SHOULD come back found=True.
COVERED = ["france", "japan", "mexico", "thailand", "jamaica"]

# Countries the corpus does NOT hold -- these SHOULD come back found=False.
# Today every one of them returns found=True with someone else's data.
UNCOVERED = ["italy", "spain", "vietnam", "brazil", "egypt", "portugal"]


def check(country: str, expected_found: bool) -> bool:
    r = search_money_customs(country)
    found = r.get("found")
    matched = r.get("country")
    score = r.get("match_score")
    adjusted = r.get("adjusted")

    ok = found is expected_found
    print(f"  [{'ok ' if ok else 'BUG'}] {country:<10} -> "
          f"found={str(found):<5} matched={str(matched):<22} "
          f"score={score if score is not None else '-'}")
    if not expected_found and found:
        tip = (r.get("tipping_note") or r.get("general_note") or "")[:88]
        print(f"          returned {matched}'s advice for a {country.title()} question:")
        print(f"          \"{tip}...\"")
        print(f"          adjusted field: {'set (prose only)' if adjusted else 'NONE'}")
    return ok


def main():
    print()
    print(f"Corpus holds {len(MONEY_CUSTOMS_FACTS)} countries. "
          f"CONFIDENCE_THRESHOLD = {CONFIDENCE_THRESHOLD}")
    print()

    print("COVERED -- these should all be found=True:")
    cov = [check(c, True) for c in COVERED]

    print()
    print("NOT IN THE CORPUS -- these should all be found=False:")
    unc = [check(c, False) for c in UNCOVERED]

    print()
    passed = sum(cov) + sum(unc)
    total = len(cov) + len(unc)
    print(f"  {passed}/{total} behaved correctly.")
    if sum(unc) != len(unc):
        print()
        print("  The agent cannot currently say 'I don't know'.")
        print("  Fix: in money_tools.search_money_customs, the low-confidence")
        print("  return near the end hardcodes \"found\": True. Change it to")
        print()
        print("      \"found\": match_score >= CONFIDENCE_THRESHOLD,")
        print()
        print("  Keep returning the closest match and the 'adjusted' text --")
        print("  nothing is lost. The caller just gets told the truth in a")
        print("  field it can branch on, instead of only in prose a model")
        print("  is free to drop.")
    print()


if __name__ == "__main__":
    main()
