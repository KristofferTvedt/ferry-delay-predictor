"""SQLite storage for weather observations and ferry sailings.

The two tables are the raw material for Phase 3 modelling:

  weather  — one row per poll, physical conditions on the crossing.
  sailings — one row per scheduled departure; ``delay_seconds`` (expected minus
             aimed) is the label. Rows are UPSERTed as each departure is polled
             repeatedly, so the expected time firms up toward the real one.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS weather (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    route_name    TEXT    NOT NULL,
    observed_at   TEXT    NOT NULL,            -- ISO UTC, forecast/obs valid time
    fetched_at    TEXT    NOT NULL,            -- ISO UTC, when we polled
    source        TEXT    NOT NULL,            -- 'locationforecast' | 'oceanforecast' | 'frost'
    wind_speed    REAL,                        -- m/s
    wind_gust     REAL,                        -- m/s
    wind_dir      REAL,                        -- degrees
    air_temp      REAL,                        -- degC
    fog_fraction  REAL,                        -- 0..100, proxy for visibility
    wave_height   REAL,                        -- m, significant wave height
    wave_dir      REAL,                        -- degrees
    sea_current   REAL,                        -- m/s
    UNIQUE(route_name, observed_at, source)
);

CREATE TABLE IF NOT EXISTS sailings (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    route_name          TEXT    NOT NULL,
    stop_place_id       TEXT    NOT NULL,
    service_journey_id  TEXT    NOT NULL,
    line                TEXT,
    destination         TEXT,
    aimed_departure     TEXT    NOT NULL,       -- ISO, scheduled
    expected_departure  TEXT,                   -- ISO, real-time estimate
    realtime            INTEGER DEFAULT 0,      -- 1 if expected is real-time data
    cancelled           INTEGER DEFAULT 0,
    delay_seconds       INTEGER,                -- expected - aimed
    first_seen_at       TEXT    NOT NULL,
    last_seen_at        TEXT    NOT NULL,
    UNIQUE(service_journey_id, aimed_departure)
);

CREATE INDEX IF NOT EXISTS ix_sailings_aimed ON sailings(aimed_departure);
CREATE INDEX IF NOT EXISTS ix_weather_observed ON weather(observed_at);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(SCHEMA)
    return conn


def upsert_weather(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO weather (route_name, observed_at, fetched_at, source,
            wind_speed, wind_gust, wind_dir, air_temp, fog_fraction,
            wave_height, wave_dir, sea_current)
        VALUES (:route_name, :observed_at, :fetched_at, :source,
            :wind_speed, :wind_gust, :wind_dir, :air_temp, :fog_fraction,
            :wave_height, :wave_dir, :sea_current)
        ON CONFLICT(route_name, observed_at, source) DO UPDATE SET
            fetched_at=excluded.fetched_at,
            wind_speed=excluded.wind_speed, wind_gust=excluded.wind_gust,
            wind_dir=excluded.wind_dir, air_temp=excluded.air_temp,
            fog_fraction=excluded.fog_fraction, wave_height=excluded.wave_height,
            wave_dir=excluded.wave_dir, sea_current=excluded.sea_current
        """,
        {**{k: None for k in (
            "wind_speed", "wind_gust", "wind_dir", "air_temp", "fog_fraction",
            "wave_height", "wave_dir", "sea_current")}, **row},
    )


def upsert_sailing(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO sailings (route_name, stop_place_id, service_journey_id, line,
            destination, aimed_departure, expected_departure, realtime, cancelled,
            delay_seconds, first_seen_at, last_seen_at)
        VALUES (:route_name, :stop_place_id, :service_journey_id, :line,
            :destination, :aimed_departure, :expected_departure, :realtime,
            :cancelled, :delay_seconds, :now, :now)
        ON CONFLICT(service_journey_id, aimed_departure) DO UPDATE SET
            expected_departure=excluded.expected_departure,
            realtime=excluded.realtime,
            cancelled=excluded.cancelled,
            delay_seconds=excluded.delay_seconds,
            last_seen_at=excluded.last_seen_at
        """,
        row,
    )
