"""
corpus.py — load and query the committed per diem corpus.

This module is deliberately dumb. It reads a JSON file and looks things up.
It has no fallbacks, no fuzzy guessing, and no default rate: an unknown
destination returns None and the caller must say so out loud.

That rule exists because of a Week 1 finding — a tool that returned a nominal
price for unknown destinations caused the agent to report a fabricated figure
in the same confident register as a real one. The model cannot tell a
retrieved value from a default. So we never manufacture one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CORPUS = Path(__file__).resolve().parent.parent / "data" / "perdiem.json"


@dataclass(frozen=True)
class Rate:
    """One resolved per diem rate for a place."""
    country: str
    post: str
    lodging: int          # max nightly lodging, USD
    mie: int              # meals & incidental expenses per day, USD
    total: int            # published combined daily ceiling, USD
    seasonal: bool        # does this location have multiple seasons?
    stale: bool           # was this rate last surveyed a long time ago?
    season_begin: str | None
    season_end: str | None


class Corpus:
    def __init__(self, path: Path | str = DEFAULT_CORPUS):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(
                f"Corpus not found at {self.path}. Run build_corpus.py first."
            )
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.meta: dict = raw["_meta"]
        self._locations: dict = raw["locations"]

    # -- introspection -----------------------------------------------------

    def countries(self) -> list[str]:
        """Every country in the corpus, sorted. Use this in error messages."""
        return sorted({v["country"] for v in self._locations.values()})

    def posts(self, country: str) -> list[str]:
        """Every post within one country."""
        target = country.strip().upper()
        return sorted(
            v["post"] for v in self._locations.values()
            if v["country"].upper() == target
        )

    def __len__(self) -> int:
        return len(self._locations)

    # -- lookup ------------------------------------------------------------

    def lookup(self, country: str, post: str | None = None) -> Rate | None:
        """Find a rate. Returns None if not covered — never a substitute.

        Resolution order:
          1. exact country + post
          2. the country's "Other" row, if it has one
          3. the country's only post, if it has exactly one
          4. None
        """
        if not country:
            return None
        target = country.strip().upper()

        candidates = {
            k: v for k, v in self._locations.items()
            if v["country"].upper() == target
        }
        if not candidates:
            return None

        chosen = None
        if post:
            wanted = post.strip().upper()
            for v in candidates.values():
                if v["post"].upper() == wanted:
                    chosen = v
                    break
        if chosen is None:
            for v in candidates.values():
                if v["post"].upper() == "OTHER":
                    chosen = v
                    break
        if chosen is None and len(candidates) == 1:
            chosen = next(iter(candidates.values()))
        if chosen is None:
            return None

        return self._to_rate(chosen)

    def resolve(self, name: str, post: str | None = None) -> Rate | None:
        """Look up by country OR by city/post name.

        The other domain agents emit city names, not country names — the
        Destination agent returns "Nassau", not "BAHAMAS, THE". Country-only
        lookup would report our best-covered destinations as uncovered.

        Order: try it as a country, then as a post name. A post name is only
        accepted if it matches exactly one location across the whole corpus;
        ambiguity returns None rather than a guess. "Other" is never matched
        by name — it is a fallback row, not a place.
        """
        if not name:
            return None

        found = self.lookup(name, post)
        if found is not None:
            return found

        target = name.strip().upper()
        if target == "OTHER":
            return None
        matches = [v for v in self._locations.values()
                   if v["post"].upper() == target]
        if len(matches) == 1:
            return self._to_rate(matches[0])
        return None

    def _to_rate(self, entry: dict) -> Rate:
        d = entry["default"]
        return Rate(
            country=entry["country"],
            post=entry["post"],
            lodging=d["lodging"],
            mie=d["mie"],
            total=d["total"],
            seasonal=entry["seasonal"],
            stale=d["stale"],
            season_begin=d.get("season_begin"),
            season_end=d.get("season_end"),
        )
