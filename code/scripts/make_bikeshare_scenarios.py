"""HW7 Part 4 - build the two acceptance-case CSVs from a public Bay Wheels monthly trip file.

Download one month first (public, from https://s3.amazonaws.com/baywheels-data/index.html), e.g.
    curl -O https://s3.amazonaws.com/baywheels-data/202509-baywheels-tripdata.csv.zip
then, from code/:
    python scripts/make_bikeshare_scenarios.py ~/Downloads/202509-baywheels-tripdata.csv.zip

Writes (inputs)  reports/hw07/cases/part4/scenario_membership.csv, scenario_paygo.csv
       (raw)     reports/hw07/raw/part4/scenario_summaries.json

Scenario "membership" (membership should win): 600 real trips from the month, kept in their real month,
  weighted toward longer rides (all trips >= 30 min are kept, the rest sampled) -> many rides + surcharges.
Scenario "paygo" (pay-per-use should win): 520 real SHORT classic-bike trips (<= 20 min) from the same file,
  re-dated to model a light rider: 5 rides per calendar month over the 104 months ending with the source
  month. Durations, bikes, stations and time-of-day are unchanged; only the calendar date is moved. This is a
  documented construction, because one public month never contains "few rides" with >= 500 rows.
Sampling uses SEED = 1066 so the files are reproducible.
"""

import argparse
import csv
import io
import json
import random
import statistics
import sys
import zipfile
from datetime import datetime
from pathlib import Path

SEED = 1066
CODE_DIR = Path(__file__).resolve().parents[1]
CASES_DIR = CODE_DIR.parent / "reports" / "hw07" / "cases" / "part4"
RAW_DIR = CODE_DIR.parent / "reports" / "hw07" / "raw" / "part4"
FMTS = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S")


def parse(ts: str) -> datetime | None:
    for f in FMTS:
        try:
            return datetime.strptime(ts.strip(), f)
        except ValueError:
            pass
    return None


def read_rows(path: Path) -> tuple[list[str], list[dict]]:
    """Read the monthly CSV (plain or .zip)."""
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith(".csv") and not n.startswith("__MACOSX"))
            text = z.read(name).decode("utf-8", errors="ignore")
    else:
        text = path.read_text(encoding="utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader.fieldnames or []), list(reader)


def minutes(r: dict) -> float | None:
    s, e = parse(r.get("started_at", "")), parse(r.get("ended_at", ""))
    return (e - s).total_seconds() / 60 if s and e and e >= s else None


def summarize(rows: list[dict], how: str, src: str) -> dict:
    durs = [m for m in (minutes(r) for r in rows) if m is not None]
    starts = sorted(parse(r["started_at"]) for r in rows)
    months = {d.strftime("%Y-%m") for d in starts}
    ebikes = sum(1 for r in rows if "electric" in r.get("rideable_type", ""))
    return {"rows": len(rows), "source_file": src, "construction": how, "seed": SEED,
            "first_ride": starts[0].isoformat(sep=" "), "last_ride": starts[-1].isoformat(sep=" "),
            "months": len(months), "rides_per_month": round(len(rows) / len(months), 1),
            "ebike_rides": ebikes, "classic_rides": len(rows) - ebikes,
            "duration_min": {"mean": round(statistics.mean(durs), 1), "median": round(statistics.median(durs), 1),
                             "max": round(max(durs), 1), "over_30": sum(d > 30 for d in durs),
                             "over_45": sum(d > 45 for d in durs)},
            "member_casual": {k: sum(1 for r in rows if r.get("member_casual") == k) for k in ("member", "casual")}}


def main() -> None:
    """Build both scenario CSVs and their summaries."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("month_file", type=Path, help="Bay Wheels monthly trip CSV or .csv.zip")
    args = ap.parse_args()
    fields, rows = read_rows(args.month_file)
    if "started_at" not in fields:
        sys.exit("This builder expects the 2020+ Bay Wheels schema (ride_id, rideable_type, started_at, ...).")
    rows = [r for r in rows if (m := minutes(r)) is not None and 1 <= m <= 180]
    rng = random.Random(SEED)

    long_rides = [r for r in rows if minutes(r) >= 30]
    rest = [r for r in rows if minutes(r) < 30]
    take_long = long_rides[:] if len(long_rides) <= 150 else rng.sample(long_rides, 150)
    membership = sorted(take_long + rng.sample(rest, 600 - len(take_long)), key=lambda r: r["started_at"])

    short_classic = [r for r in rows if "classic" in r.get("rideable_type", "") and minutes(r) <= 20]
    picked = rng.sample(short_classic, 520)
    last = parse(max(r["started_at"] for r in rows))
    month_starts = []
    y, m = last.year, last.month
    for _ in range(104):
        month_starts.append(datetime(y, m, 1))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    paygo = []
    for i, r in enumerate(picked):
        base = month_starts[i // 5]
        nxt = datetime(base.year + (base.month == 12), base.month % 12 + 1, 1)
        day = rng.randrange((nxt - base).days)
        s, e = parse(r["started_at"]), parse(r["ended_at"])
        new_s = datetime(base.year, base.month, 1 + day, s.hour, s.minute, s.second)
        out = dict(r)
        out["started_at"] = new_s.strftime("%Y-%m-%d %H:%M:%S")
        out["ended_at"] = (new_s + (e - s)).strftime("%Y-%m-%d %H:%M:%S")
        paygo.append(out)
    paygo.sort(key=lambda r: r["started_at"])

    CASES_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for name, data in (("scenario_membership.csv", membership), ("scenario_paygo.csv", paygo)):
        with (CASES_DIR / name).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(data)
    summary = {
        "scenario_membership": summarize(membership, "600 real trips from one month; all >=30-min trips kept (max 150), rest random", args.month_file.name),
        "scenario_paygo": summarize(paygo, "520 real short classic trips (<=20 min), re-dated to 5 rides/month over 104 months", args.month_file.name),
    }
    (RAW_DIR / "scenario_summaries.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {CASES_DIR / 'scenario_membership.csv'} and {CASES_DIR / 'scenario_paygo.csv'}")


if __name__ == "__main__":
    main()
