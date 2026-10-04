"""One collection pass: poll weather + ferry departures, store to SQLite.

Run on a schedule (Windows Task Scheduler / cron), e.g. every 15 minutes:

    python -m ferrydelay.collector

Each pass upserts current weather for the crossing and every upcoming ferry
departure. Repeated passes converge each departure's expected time onto the
actual one, so the ``delay_seconds`` label is correct by the time it sails.

The scheduled task runs under ``pythonw`` so no console window appears, which
means ``sys.stdout`` is None and anything printed is lost. Every run is therefore
written to ``data/collector.log`` instead. Without it an outage is invisible: a
three week network failure in September looked identical to a dead task.
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from . import db, entur, metno
from .config import Config
from .entur import now_utc_iso


def setup_logging(cfg: Config) -> logging.Logger:
    log = logging.getLogger("ferrydelay.collector")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)

    path = cfg.db_path.parent / "collector.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3,
                                  encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)

    # Only mirror to the console when there is one; under pythonw there is not.
    if sys.stdout is not None:
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(stream)
    return log


def run_once(cfg: Config, log: logging.Logger) -> dict:
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
                log.warning("weather %s failed: %s", fetch.__name__, exc)

        if not cfg.stop_place_id:
            log.warning('STOP_PLACE_ID not set, skipping ferry poll. '
                        'Run: python -m ferrydelay.lookup stop "Halhjem"')
        else:
            try:
                for s in entur.departures(cfg.et_client_name, cfg.stop_place_id,
                                          destination_filter=cfg.destination_filter):
                    if not s.get("service_journey_id") or not s.get("aimed_departure"):
                        continue
                    s.update(route_name=cfg.route_name,
                             stop_place_id=cfg.stop_place_id, now=fetched)
                    db.upsert_sailing(conn, s)
                    counts["sailings"] += 1
            except Exception as exc:
                # Must not propagate: that would skip the commit below and throw
                # away the weather rows this pass already collected.
                log.warning("entur poll failed: %s", exc)

        conn.commit()
    finally:
        conn.close()
    return counts


def main() -> int:
    cfg = Config.load()
    log = setup_logging(cfg)
    try:
        counts = run_once(cfg, log)
    except Exception as exc:
        log.exception("run failed: %s", exc)
        return 1

    if not counts["weather"] and not counts["sailings"]:
        # Non-zero exit so Task Scheduler's LastTaskResult flags it too.
        log.error("collected nothing, both sources unreachable (network down?)")
        return 1

    log.info("ok route=%s weather=%d sailings=%d",
             cfg.route_name, counts["weather"], counts["sailings"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
