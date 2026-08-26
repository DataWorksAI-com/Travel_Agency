"""
build_corpus.py — build the Budget Agent's cost corpus from U.S. Department of
State foreign per diem data.

This is a BUILD-TIME script. It runs once, writes data/perdiem.json, and that
JSON is committed to the repo. The agent never imports this file and never
touches the network at request time.

Why: (a) evaluation runs must be reproducible, so the corpus cannot change
between the before-condition and the after-condition; (b) a runtime fetch that
fails needs something to fill the gap, and whatever fills it gets reported to
the user with the same confidence as real data.

Source: U.S. Dept of State, Office of Allowances, DSSR 925
        https://allowances.state.gov/web920/per_diem.asp
Bulk:   https://catalog.data.gov/dataset/foreign-per-diem-rates-by-location

Usage (PowerShell):
    python build_corpus.py --input raw\perdiem_raw.xlsx --out data\perdiem.json
    python build_corpus.py --input raw\perdiem_raw.csv  --out data\perdiem.json --all
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

# --- Destination allowlist -------------------------------------------------
# Scoped deliberately, not exhaustively. Two reasons:
#   1. A small corpus can be eyeballed and diffed in a pull request.
#   2. Destinations NOT in this list become out-of-scope test cases for the
#      docstring-coverage finding. Keep this list in sync with what the
#      Destination Agent actually returns.
# Match is case-insensitive on the State Department's "Country Name" field.
TROPICAL_COUNTRIES = {
    "ANTIGUA AND BARBUDA",
    "ARUBA",
    "BAHAMAS, THE",
    "BARBADOS",
    "BELIZE",
    "CAYMAN ISLANDS",
    "COSTA RICA",
    "CURACAO",
    "DOMINICA",
    "DOMINICAN REPUBLIC",
    "GRENADA",
    "JAMAICA",
    "PANAMA",
    "SAINT KITTS AND NEVIS",
    "SAINT VINCENT AND THE GRENADINES",
    "ST LUCIA",
    "TRINIDAD AND TOBAGO",
    "TURKS AND CAICOS ISLANDS",
}

# Deliberately NOT in the corpus, so they can serve as out-of-scope test cases:
# Fiji, Maldives, Seychelles, Mauritius, Puerto Rico, U.S. Virgin Islands.
# (The last two are U.S. territories and are not in State's foreign per diem
# dataset at all — a real gap, documented in the README.)

# Rows older than this many years are flagged as stale. State leaves some
# "Other" rows un-surveyed for a decade or more.
STALE_AFTER_YEARS = 8

# State's published column headers -> our internal names.
COLUMN_MAP = {
    "country name": "country",
    "post name": "post",
    "season begin": "season_begin",
    "season end": "season_end",
    "maximum lodging rate": "lodging",
    "m & ie rate": "mie",
    "m&ie rate": "mie",
    "maximum per diem rate": "total",
    "footnote": "footnote",
    "effective date": "effective_date",
}

SOURCE_URL = "https://allowances.state.gov/web920/per_diem.asp"
SOURCE_NAME = "U.S. Department of State, Office of Allowances, DSSR 925"


def load_raw(path: Path) -> pd.DataFrame:
    """Read the raw State Department extract, as .xlsx/.xls or .csv."""
    if not path.exists():
        raise FileNotFoundError(f"Raw input not found: {path}")
    if path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path, dtype=str)
    elif path.suffix.lower() == ".csv":
        df = pd.read_csv(path, dtype=str)
    else:
        raise ValueError(f"Unsupported input type: {path.suffix}")
    return df


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map State's headers onto internal names, tolerating whitespace/case."""
    renamed = {}
    for col in df.columns:
        key = " ".join(str(col).strip().lower().split())
        if key in COLUMN_MAP:
            renamed[col] = COLUMN_MAP[key]
    df = df.rename(columns=renamed)

    required = {"country", "post", "lodging", "mie", "total"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Input is missing required columns: {sorted(missing)}. "
            f"Found columns: {list(df.columns)}"
        )
    return df


def to_int(value) -> int | None:
    """Coerce a rate cell to int. Returns None rather than guessing."""
    if value is None:
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    if text == "" or text.lower() in {"nan", "none", "n/a"}:
        return None
    try:
        return int(round(float(text)))
    except ValueError:
        return None


MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_season(value) -> str | None:
    """Keep the season string as State/Excel wrote it, or None."""
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() != "nan" else None


def season_to_md(text: str | None) -> tuple[int, int] | None:
    """Parse a season boundary into (month, day).

    Excel mangles State's dates on import, so accept every form seen in the
    wild: '01/01', '1/1', '1-May', 'May-1', '1 May'. Returns None if the
    string cannot be parsed -- the caller must treat that as an error, NOT as
    'matches everything'. A silent permissive default here would pick the
    wrong seasonal rate and report it with full confidence.
    """
    if not text:
        return None
    raw = text.strip().lower().replace("/", "-").replace(" ", "-")
    parts = [p for p in raw.split("-") if p]
    if len(parts) != 2:
        return None

    a, b = parts
    if a.isdigit() and b.isdigit():          # 01-01  (month-day)
        month, day = int(a), int(b)
    elif a.isdigit() and b[:3] in MONTHS:    # 1-May  (day-month)
        day, month = int(a), MONTHS[b[:3]]
    elif a[:3] in MONTHS and b.isdigit():    # May-1  (month-day)
        month, day = MONTHS[a[:3]], int(b)
    else:
        return None

    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return month, day


def season_covers(begin: str | None, end: str | None, ref: date) -> bool | None:
    """Does the season window contain the reference date?

    Returns True/False, or None if the window could not be parsed.
    Handles wrap-around windows such as 15-Dec .. 16-Jul.
    A row with no season at all covers the whole year.
    """
    if not begin and not end:
        return True
    start = season_to_md(begin)
    finish = season_to_md(end)
    if start is None or finish is None:
        return None

    point = (ref.month, ref.day)
    if start <= finish:
        return start <= point <= finish
    return point >= start or point <= finish


def parse_effective(text) -> date | None:
    """Parse State's effective date, which Excel may render several ways."""
    if text is None:
        return None
    raw = str(text).strip()
    if not raw or raw.lower() == "nan":
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d-%b-%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def build(df: pd.DataFrame, ref: date, use_allowlist: bool) -> tuple[dict, list[str]]:
    """Group rows into locations, keep every season, resolve one default."""
    problems: list[str] = []
    locations: dict[str, dict] = {}

    for _, row in df.iterrows():
        country = str(row.get("country", "")).strip()
        post = str(row.get("post", "")).strip()
        if not country or country.lower() == "nan":
            continue
        if use_allowlist and country.upper() not in TROPICAL_COUNTRIES:
            continue

        lodging = to_int(row.get("lodging"))
        mie = to_int(row.get("mie"))
        total = to_int(row.get("total"))

        key = f"{country.upper()}|{post.upper()}"

        # Validate at build time, not at answer time.
        if lodging is None or mie is None:
            problems.append(f"{key}: missing lodging or M&IE, row skipped")
            continue
        if total is None:
            total = lodging + mie
            problems.append(f"{key}: total was blank, derived as lodging + M&IE")
        elif lodging + mie != total:
            problems.append(
                f"{key}: lodging({lodging}) + mie({mie}) != total({total}) "
                f"-- kept State's published total"
            )

        effective = parse_effective(row.get("effective_date"))
        stale = False
        if effective is not None:
            age_years = (ref - effective).days / 365.25
            if age_years > STALE_AFTER_YEARS:
                stale = True
                problems.append(
                    f"{key}: rate last surveyed {effective.isoformat()} "
                    f"({age_years:.0f} years old) -- flagged stale"
                )

        season = {
            "season_begin": parse_season(row.get("season_begin")),
            "season_end": parse_season(row.get("season_end")),
            "lodging": lodging,
            "mie": mie,
            "total": total,
            "effective_date": effective.isoformat() if effective else None,
            "stale": stale,
            "footnote": (str(row.get("footnote")).strip()
                         if row.get("footnote") is not None
                         and str(row.get("footnote")).strip().lower()
                         not in {"nan", "n/a", "view", ""}
                         else None),
        }

        entry = locations.setdefault(
            key, {"country": country, "post": post, "seasons": []}
        )
        entry["seasons"].append(season)

    # Resolve a single default season per location for the reference date.
    for key, entry in locations.items():
        seasons = entry["seasons"]
        entry["seasonal"] = len(seasons) > 1

        matches, unparseable = [], 0
        for s in seasons:
            covered = season_covers(s["season_begin"], s["season_end"], ref)
            if covered is None:
                unparseable += 1
            elif covered:
                matches.append(s)

        if unparseable:
            problems.append(
                f"{key}: {unparseable} season window(s) could not be parsed "
                f"(begin/end format) -- excluded from matching"
            )

        if len(matches) == 1:
            chosen = matches[0]
        elif matches:
            chosen = matches[0]
            problems.append(
                f"{key}: {len(matches)} seasons match {ref.isoformat()}, took the first"
            )
        else:
            chosen = seasons[0]
            problems.append(
                f"{key}: NO season covers {ref.isoformat()}, fell back to the first "
                f"-- verify this location by hand"
            )
        entry["default"] = {
            "lodging": chosen["lodging"],
            "mie": chosen["mie"],
            "total": chosen["total"],
            "season_begin": chosen["season_begin"],
            "season_end": chosen["season_end"],
            "stale": chosen["stale"],
        }

    return locations, problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path,
                        help="Raw State Dept extract (.xlsx or .csv)")
    parser.add_argument("--out", default=Path("data/perdiem.json"), type=Path,
                        help="Output JSON path")
    parser.add_argument("--ref-date", default=None,
                        help="Reference date YYYY-MM-DD for resolving seasons")
    parser.add_argument("--all", action="store_true",
                        help="Keep every country, ignoring the tropical allowlist")
    args = parser.parse_args()

    ref = (datetime.strptime(args.ref_date, "%Y-%m-%d").date()
           if args.ref_date else date.today())

    df = normalise_columns(load_raw(args.input))
    locations, problems = build(df, ref, use_allowlist=not args.all)

    if not locations:
        print("ERROR: no locations matched. Check the allowlist against the "
              "country names in your input, or re-run with --all.", file=sys.stderr)
        return 1

    # Parse dates before comparing them -- string sort would rank
    # "9/1/2024" above "6/1/2026".
    effective = oldest = None
    if "effective_date" in df.columns:
        parsed = [d for d in (parse_effective(v) for v in df["effective_date"])
                  if d is not None]
        if parsed:
            effective = max(parsed).isoformat()
            oldest = min(parsed).isoformat()

    corpus = {
        "_meta": {
            "source": SOURCE_NAME,
            "source_url": SOURCE_URL,
            "retrieved": date.today().isoformat(),
            "rates_effective_newest": effective,
            "rates_effective_oldest": oldest,
            "reference_date": ref.isoformat(),
            "location_count": len(locations),
            "currency": "USD",
            "note": ("Per diem ceilings for U.S. government travellers. These are "
                     "maximum reimbursable rates, not observed market prices. "
                     "Suitable as budget envelopes; not a price quote."),
        },
        "locations": dict(sorted(locations.items())),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(corpus, indent=2), encoding="utf-8")

    print(f"Wrote {args.out}  ({len(locations)} locations)")
    if problems:
        print(f"\n{len(problems)} data issue(s) — review before committing:")
        for p in problems:
            print(f"  - {p}")
    else:
        print("Validation clean: every location has lodging, M&IE, and a total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
