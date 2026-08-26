"""Rebuild every cached destination profile from live Geoapify data.

WHY THIS EXISTS

Commit 26d5e2c changed the Geoapify query that builds a profile: category
tourism.attraction -> tourism.sights, conditions=named, and a minimum name
length. It did not change any profile already sitting in
destination_profiles.json, because get_or_build_destination_profile is
cache-first by design -- a cached city is returned without a lookup.

So the fix only reached cities nobody had queried yet. Every seeded city kept
its pre-fix values, and the agent still answered Cancun with "Gran Puerto,
Condominio Bellamar" and Rome with "Guerrilla spam, Street Art di Mauro
Sgarbi" -- the exact strings the commit was written to remove. A query-layer
fix and a data-layer cache have to be reconciled explicitly; this is that
step.

It also repairs mojibake. The committed file contains "Mal�" and
"Mazzalupetto � Quarto degli Ebrei" -- U+FFFD, the replacement character,
meaning those bytes were decoded wrongly and re-saved lossily at some earlier
point. The information is gone and cannot be repaired in place; only a refetch
restores it. save_destination_profiles already writes utf-8 with
ensure_ascii=False, so a rebuild comes back clean.

USAGE

    python -m destination_agent.rebuild_profiles --dry-run   # report, write nothing
    python -m destination_agent.rebuild_profiles             # rebuild all
    python -m destination_agent.rebuild_profiles --only Rome Cancun

Needs GEOAPIFY_API_KEY. Roughly four Geoapify calls per destination plus one
geocode, so ~250 for the full 52-city set -- inside the free daily tier, but
not free of consequence if run in a loop.

SAFETY

A destination is replaced only if its rebuild actually returns places. A city
whose lookup fails or comes back empty keeps its existing profile and is
reported as SKIPPED, so a transient network failure degrades the corpus by
nothing rather than blanking a city. Nothing is written until every
destination has been attempted.
"""

import argparse
import json
import sys
from pathlib import Path

# truststore before anything imports requests, matching
# destination_data/build_corpus.py -- without it HTTPS hangs for minutes
# behind an intercepting proxy certificate on some networks.
import truststore

truststore.inject_into_ssl()

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from destination_agent.geoapify_data import (  # noqa: E402
    PROFILE_FILE,
    build_destination_profile,
    load_destination_profiles,
    save_destination_profiles,
)

# The categories whose contents 26d5e2c changed. Reported separately so the
# diff is legible: "attractions" is the one that was actually broken, and a
# reviewer should be able to see that beaches/nature/diving stayed put.
WATCHED = "attractions"


def _places(profile: dict) -> dict:
    return (profile or {}).get("places", {}) or {}


def _count(profile: dict) -> int:
    return sum(len(v) for v in _places(profile).values() if isinstance(v, list))


def _has_replacement_char(profile: dict) -> bool:
    """U+FFFD anywhere in the profile means it was decoded lossily."""
    return "�" in json.dumps(profile, ensure_ascii=False)


def rebuild(only=None, dry_run=False) -> int:
    profiles = load_destination_profiles()
    if not profiles:
        print(f"No profiles found at {PROFILE_FILE}. Nothing to rebuild.")
        return 1

    names = list(profiles)
    if only:
        wanted = {n.casefold() for n in only}
        names = [n for n in names if n.casefold() in wanted]
        missing = wanted - {n.casefold() for n in names}
        if missing:
            print(f"Not in the cache, skipping: {', '.join(sorted(missing))}")
        if not names:
            return 1

    print(f"Rebuilding {len(names)} of {len(profiles)} destination(s) from live Geoapify data.")
    if dry_run:
        print("DRY RUN -- nothing will be written.\n")

    rebuilt, skipped, mojibake_fixed = {}, [], []

    for i, name in enumerate(names, 1):
        old = profiles[name]
        print(f"[{i}/{len(names)}] {name} ... ", end="", flush=True)
        try:
            new = build_destination_profile(name)
        except Exception as exc:
            print(f"SKIPPED (lookup failed: {type(exc).__name__}: {str(exc)[:80]})")
            skipped.append(name)
            continue

        if not _count(new):
            # Never trade a populated profile for an empty one: a rate limit or
            # a DNS blip would otherwise silently blank a city.
            print("SKIPPED (rebuild returned no places; keeping existing)")
            skipped.append(name)
            continue

        was_broken = _has_replacement_char(old)
        if was_broken and not _has_replacement_char(new):
            mojibake_fixed.append(name)

        old_w, new_w = _places(old).get(WATCHED, []), _places(new).get(WATCHED, [])
        dropped = [p for p in old_w if p not in new_w]
        print(
            f"ok  {WATCHED}: {len(old_w)} -> {len(new_w)}"
            + (f", dropped {len(dropped)}" if dropped else "")
            + ("  [encoding repaired]" if was_broken else "")
        )
        if dropped:
            print(f"        dropped: {', '.join(dropped[:5])}" + (" ..." if len(dropped) > 5 else ""))

        rebuilt[name] = new

    print(f"\n{'-' * 70}")
    print(f"rebuilt: {len(rebuilt)}   skipped: {len(skipped)}")
    if mojibake_fixed:
        print(f"encoding repaired: {', '.join(mojibake_fixed)}")
    if skipped:
        print(f"kept as-is: {', '.join(skipped)}")

    if dry_run:
        print("\nDRY RUN -- destination_profiles.json unchanged.")
        return 0
    if not rebuilt:
        print("\nNothing rebuilt; leaving the file untouched.")
        return 1

    profiles.update(rebuilt)
    save_destination_profiles(profiles)
    print(f"\nWrote {PROFILE_FILE}")
    print("Next: python -m destination_agent.enrich_rag_corpus  (propagates into destinations.json)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", nargs="+", metavar="CITY", help="rebuild just these")
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()
    sys.exit(rebuild(only=args.only, dry_run=args.dry_run))
