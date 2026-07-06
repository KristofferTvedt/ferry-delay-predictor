"""Is the collector still alive?

Prints OK / STALE based on how long ago the last row was written, and exits
non-zero when stale so a scheduler can act on it.

    python -m ferrydelay.healthcheck            # 40 min default threshold
    python -m ferrydelay.healthcheck --max 60
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from . import db
from .config import Config


def latest_write(conn) -> datetime | None:
    rows = [
        conn.execute("SELECT max(fetched_at) FROM weather").fetchone()[0],
        conn.execute("SELECT max(last_seen_at) FROM sailings").fetchone()[0],
    ]
    stamps = [datetime.fromisoformat(r) for r in rows if r]
    return max(stamps) if stamps else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=40,
                    help="minutes before the collector is considered stale")
    args = ap.parse_args()

    cfg = Config.load()
    conn = db.connect(cfg.db_path)
    try:
        last = latest_write(conn)
    finally:
        conn.close()

    now = datetime.now(timezone.utc)
    if last is None:
        print("STALE: database is empty — collector has never written.")
        return 1

    age_min = (now - last).total_seconds() / 60
    stamp = last.astimezone().strftime("%Y-%m-%d %H:%M")
    if age_min > args.max:
        print(f"STALE: last write {stamp} local ({age_min:.0f} min ago, "
              f"threshold {args.max}). Check the FerryDelayCollector task.")
        return 1
    print(f"OK: last write {stamp} local ({age_min:.0f} min ago).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
