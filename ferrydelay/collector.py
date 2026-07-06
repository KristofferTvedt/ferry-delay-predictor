"""One collection pass: poll weather + ferry departures, store to SQLite.

Run on a schedule (Windows Task Scheduler / cron), e.g. every 15 minutes:

    python -m ferrydelay.collector

Each pass upserts current weather for the crossing and every upcoming ferry
departure. Repeated passes converge each departure's expected time onto the
actual one, so the ``delay_seconds`` label is correct by the time it sails.
"""
from __future__ import annotations

import sys

from . import db, entur, metno
from .config import Config
from .entur import now_utc_iso


def run_once(cfg: Config) -> dict:
    conn = db.connect(cfg.db_path)
    fetched = now_utc_iso()
    counts = {"weather": 0, "sailings": 0}

    try:
        for fetch in (metno.locationforecast, metno.oceanforecast):
            try:
                w = fetch(cfg.metno_user_agent, cfg.route_lat, cfg.route_lon)
                w.update(route_name=cfg.route_name, fetched_at=fetched)
                db.upsert_weather(conn, w)
                counts["weather"] += 1
            except Exception as exc:  # one product failing shouldn't lose the other
                print(f"WARN weather {fetch.__name__}: {exc}", file=sys.stderr)

        if not cfg.stop_place_id:
            print("WARN STOP_PLACE_ID not set — skipping ferry poll. "
                  'Run: python -m ferrydelay.lookup stop "Halhjem"', file=sys.stderr)
        else:
            for s in entur.departures(cfg.et_client_name, cfg.stop_place_id,
                                      destination_filter=cfg.destination_filter):
                if not s.get("service_journey_id") or not s.get("aimed_departure"):
                    continue
                s.update(route_name=cfg.route_name,
                         stop_place_id=cfg.stop_place_id, now=fetched)
                db.upsert_sailing(conn, s)
                counts["sailings"] += 1

        conn.commit()
    finally:
        conn.close()
    return counts


def main() -> int:
    cfg = Config.load()
    counts = run_once(cfg)
    print(f"{now_utc_iso()} route={cfg.route_name} "
          f"weather={counts['weather']} sailings={counts['sailings']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
