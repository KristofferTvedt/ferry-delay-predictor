"""Phase 2 EDA: join each sailing to the weather at its departure hour and
print a first look at delay vs conditions. Also writes ``data/joined.csv``.

The join is the whole point of this pass: getting timezone alignment right on a
small, hand-checkable dataset now beats debugging it on thousands of rows later.
Sailing departure times are local (+02:00); weather is hourly UTC. We floor each
departure to its UTC hour and match on that.
"""
from __future__ import annotations

import csv
import statistics
from datetime import datetime, timezone

from . import db
from .config import Config

DELAY_THRESHOLD_S = 180  # 3 min: what we'll call "delayed" for a first cut

# Entur's estimatedCalls only lists *upcoming* departures, so a sailing drops out
# of the feed once it leaves. The final reading is therefore the last estimate
# before departure, and for an overdue sailing the feed keeps pushing that
# estimate forward ("any minute now") until the row ages out. Two consequences:
#
#   * A delayed sailing's recorded delay is a LOWER BOUND. We saw it still
#     pending at that point; it left then or later.
#   * A sailing that never ran at all looks like an enormous delay rather than a
#     cancellation, because nothing in the feed ever marks it cancelled.
#
# Beyond this threshold "delayed" stops being credible: the following scheduled
# sailing would have overtaken it, so the service almost certainly did not run.
IMPLAUSIBLE_DELAY_S = 7200  # 2 h


def utc_hour(iso_ts: str) -> str:
    dt = datetime.fromisoformat(iso_ts).astimezone(timezone.utc)
    return dt.replace(minute=0, second=0, microsecond=0).strftime(
        "%Y-%m-%dT%H:00:00Z")


def load_weather_by_hour(conn) -> dict[str, dict]:
    """hour -> merged weather (both met.no products flattened into one dict)."""
    out: dict[str, dict] = {}
    for r in conn.execute("SELECT * FROM weather"):
        r = dict(r)
        hour = utc_hour(r["observed_at"])
        merged = out.setdefault(hour, {})
        for k in ("wind_speed", "wind_gust", "wind_dir", "air_temp",
                  "fog_fraction", "wave_height", "wave_dir", "sea_current"):
            if r.get(k) is not None:
                merged[k] = r[k]
    return out


def build_rows(conn) -> list[dict]:
    weather = load_weather_by_hour(conn)
    rows = []
    for s in conn.execute(
        "SELECT aimed_departure, expected_departure, delay_seconds, cancelled, "
        "last_seen_at FROM sailings WHERE delay_seconds IS NOT NULL"
    ):
        s = dict(s)
        w = weather.get(utc_hour(s["aimed_departure"]), {})
        # Still pending at our final reading, so the true delay is >= this one.
        censored = False
        if s["expected_departure"]:
            gap = (datetime.fromisoformat(s["expected_departure"])
                   - datetime.fromisoformat(s["last_seen_at"])).total_seconds()
            censored = abs(gap) <= 120 and s["delay_seconds"] >= DELAY_THRESHOLD_S
        rows.append({
            "aimed_departure": s["aimed_departure"],
            "delay_seconds": s["delay_seconds"],
            "cancelled": s["cancelled"],
            "censored": censored,
            "did_not_sail": s["delay_seconds"] >= IMPLAUSIBLE_DELAY_S,
            "wind_speed": w.get("wind_speed"),
            "wind_gust": w.get("wind_gust"),
            "air_temp": w.get("air_temp"),
            "fog_fraction": w.get("fog_fraction"),
            "wave_height": w.get("wave_height"),
            "sea_current": w.get("sea_current"),
            "matched_weather": bool(w),
        })
    return rows


def _corr(rows: list[dict], feature: str) -> float | None:
    pairs = [(r[feature], r["delay_seconds"]) for r in rows
             if r.get(feature) is not None]
    if len(pairs) < 3:
        return None
    xs, ys = zip(*pairs)
    if len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    return statistics.correlation(xs, ys)


def main() -> int:
    cfg = Config.load()
    conn = db.connect(cfg.db_path)
    try:
        rows = build_rows(conn)
    finally:
        conn.close()

    if not rows:
        print("No sailings with a delay value yet.")
        return 1

    matched = sum(r["matched_weather"] for r in rows)
    delays = [r["delay_seconds"] for r in rows]
    delayed = sum(1 for d in delays if d >= DELAY_THRESHOLD_S)
    sailed = [r for r in rows if not r["did_not_sail"]]

    print(f"sailings analysed : {len(rows)}")
    print(f"matched to weather: {matched} ({matched/len(rows):.0%})  "
          f"<- unmatched means a missing weather hour, investigate if high")
    print(f"delay median/max  : {statistics.median(delays)/60:.1f} / "
          f"{max(d['delay_seconds'] for d in sailed)/60:.1f} min"
          f"   (max excludes did-not-sail rows)")
    print(f"delayed >={DELAY_THRESHOLD_S//60}min    : {delayed} "
          f"({delayed/len(rows):.0%})")

    censored = [r for r in rows if r["censored"]]
    never = [r for r in rows if r["did_not_sail"]]
    print()
    print("data quality:")
    print(f"  censored delays : {len(censored)} of {delayed} delayed sailings were "
          f"still pending at the final reading,")
    print(f"                    so those delays are lower bounds, not exact times.")
    print(f"  did not sail    : {len(never)} row(s) over "
          f"{IMPLAUSIBLE_DELAY_S//3600} h, treated as a service that never ran "
          f"rather than a delay:")
    for r in never:
        print(f"                    {r['aimed_departure'][:16]} "
              f"({r['delay_seconds']/60:.0f} min)")

    print()
    print("correlation of delay with (Pearson r; tiny-n, treat as directional;")
    print("did-not-sail rows excluded so they can't dominate the magnitude):")
    for feat in ("wind_speed", "wind_gust", "air_temp", "fog_fraction",
                 "wave_height", "sea_current"):
        r = _corr(sailed, feat)
        print(f"  {feat:<13}: {'n/a' if r is None else f'{r:+.2f}'}")

    out_csv = cfg.db_path.parent / "joined.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
