"""Storm climatology for the crossing, from Frost history.

Answers "how often does it actually blow hard here, and when" using observed
hourly gusts at Slåtterøy fyr (the exposed lighthouse) over the past few years.
No ferry data needed — this is here to sanity-check the collection timeline:
if rough weather is a November thing, a September checkpoint will still be calm.

    python -m ferrydelay.climatology                 # default station, 3 years
    python -m ferrydelay.climatology --years 5 --source SN48330
"""
from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from datetime import datetime, timezone

from .config import Config
from .http import get_json

OBS = "https://frost.met.no/observations/v0.jsonld"
GUST = "max(wind_speed_of_gust PT1H)"

# Beaufort-ish gust thresholds (m/s) relevant to ferry disruption.
THRESHOLDS = [15, 20, 25]


def _year_chunks(start_year: int, end_year: int):
    for y in range(start_year, end_year):
        yield f"{y}-01-01T00:00:00Z", f"{y + 1}-01-01T00:00:00Z"


def fetch_hourly_gusts(client_id: str, source: str, years: int) -> list[tuple[str, float]]:
    now = datetime.now(timezone.utc)
    out: list[tuple[str, float]] = []
    for lo, hi in _year_chunks(now.year - years, now.year + 1):
        try:
            data = get_json(OBS, auth=(client_id, ""), params={
                "sources": source, "elements": GUST, "referencetime": f"{lo}/{hi}"})
        except RuntimeError as exc:
            print(f"  (no data {lo[:4]}: {exc})")
            continue
        for rec in data.get("data", []):
            t = rec["referenceTime"]
            for ob in rec.get("observations", []):
                if ob.get("value") is not None:
                    out.append((t, float(ob["value"])))
    return out


def daily_max(hourly: list[tuple[str, float]]) -> dict[str, float]:
    days: dict[str, float] = defaultdict(float)
    for t, v in hourly:
        day = t[:10]
        if v > days[day]:
            days[day] = v
    return dict(days)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=3)
    ap.add_argument("--source", default="SN48330")
    args = ap.parse_args()

    cfg = Config.load()
    if not cfg.frost_client_id:
        print("FROST_CLIENT_ID not set in .env")
        return 1

    print(f"Fetching {args.years}y of hourly gusts from {args.source} "
          f"(Slåtterøy fyr) ...")
    hourly = fetch_hourly_gusts(cfg.frost_client_id, args.source, args.years)
    if not hourly:
        print("No gust data returned.")
        return 1
    days = daily_max(hourly)
    vals = sorted(days.values())
    n = len(vals)

    def pct(p: float) -> float:
        return vals[min(n - 1, int(p / 100 * n))]

    print(f"\n{n} days, {len(hourly)} hourly obs\n")
    print("Daily-max gust distribution (m/s):")
    print(f"  median {statistics.median(vals):.1f}   p90 {pct(90):.1f}   "
          f"p99 {pct(99):.1f}   max {vals[-1]:.1f}")
    print("\nDays exceeding gust thresholds:")
    for th in THRESHOLDS:
        c = sum(1 for v in vals if v >= th)
        print(f"  >= {th:>2} m/s : {c:>4} days ({c / n:.1%})  ~{c / args.years:.0f}/year")

    print("\nBy month (mean daily-max gust, and % of days >= 15 m/s):")
    by_month: dict[int, list[float]] = defaultdict(list)
    for day, v in days.items():
        by_month[int(day[5:7])].append(v)
    names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for m in range(1, 13):
        vs = by_month.get(m, [])
        if not vs:
            continue
        rough = sum(1 for v in vs if v >= 15) / len(vs)
        bar = "#" * round(statistics.mean(vs))
        print(f"  {names[m]}  mean {statistics.mean(vs):4.1f}  rough {rough:4.0%}  {bar}")

    out_csv = cfg.db_path.parent / "climatology_daily_gust.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "max_gust_ms"])
        w.writerows(sorted(days.items()))
    print(f"\nwrote {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
