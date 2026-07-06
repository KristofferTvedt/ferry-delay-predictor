"""Phase 2 EDA: join each sailing to the weather at its departure hour and
print a first look at delay vs conditions. Also writes ``data/joined.csv``.

The join is the whole point of this pass — getting timezone alignment right on a
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
        "SELECT aimed_departure, expected_departure, delay_seconds, cancelled "
        "FROM sailings WHERE delay_seconds IS NOT NULL"
    ):
        s = dict(s)
        w = weather.get(utc_hour(s["aimed_departure"]), {})
        rows.append({
            "aimed_departure": s["aimed_departure"],
            "delay_seconds": s["delay_seconds"],
            "cancelled": s["cancelled"],
            "wind_speed": w.get("wind_speed"),
            "wind_gust": w.get("wind_gust"),
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

    print(f"sailings analysed : {len(rows)}")
    print(f"matched to weather: {matched} ({matched/len(rows):.0%})  "
          f"<- unmatched means a missing weather hour, investigate if high")
    print(f"delay median/max  : {statistics.median(delays)/60:.1f} / "
          f"{max(delays)/60:.1f} min")
    print(f"delayed >={DELAY_THRESHOLD_S//60}min    : {delayed} "
          f"({delayed/len(rows):.0%})")
    print()
    print("correlation of delay with (Pearson r; tiny-n, treat as directional):")
    for feat in ("wind_speed", "wind_gust", "fog_fraction", "wave_height",
                 "sea_current"):
        r = _corr(rows, feat)
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
