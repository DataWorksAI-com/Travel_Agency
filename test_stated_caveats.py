"""Caveats an agent stated about its own answer survive the model's rewrite.

Real case, Rome run 27 Aug 2026: money_customs replied 'Note: I interpreted
"Italy" as Germany.' and the assembled itinerary presented Germany's tipping
norms as Italy's with the note gone.
"""

from orchestrator_agent import _stated_caveats

ROME_REPLY = (
    'Note: I interpreted "Italy" as Germany.\n\n'
    "Tipping is expected in Germany. Round up or add 5-10% in restaurants."
)


def test_dropped_caveat_is_reattached():
    final = "=== Money & Customs ===\nTipping: round up or add 5-10%.\nHaggling: not expected in Italy."
    out = _stated_caveats(final, {"money_customs": [ROME_REPLY]})
    assert 'Note: I interpreted "Italy" as Germany.' in out, out
    assert "Money & Customs" in out, out


def test_kept_caveat_is_not_repeated():
    final = 'Note: I interpreted "Italy" as Germany.\nTipping: round up.'
    assert _stated_caveats(final, {"money_customs": [ROME_REPLY]}) == ""


def test_no_caveats_appends_nothing():
    assert _stated_caveats("all good", {"flights": ["LH: $409, 3 stops"]}) == ""


if __name__ == "__main__":
    test_dropped_caveat_is_reattached()
    test_kept_caveat_is_not_repeated()
    test_no_caveats_appends_nothing()
    print("ok")
