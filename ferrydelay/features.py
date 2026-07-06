"""Build the modelling table: one row per sailing, weather joined, target set.

Reuses the stdlib join from ``analyze`` (so the timezone alignment lives in one
place) and lifts it into a pandas DataFrame with a binary target.

Target = "disrupted": departure delayed by >= DELAY_THRESHOLD_S, OR cancelled.
Cancellation is folded into the positive class here because from a passenger's
standpoint a cancelled sailing is the worst delay; kept separate in storage so
this choice stays reversible.
"""
from __future__ import annotations

import pandas as pd

from . import db
from .analyze import DELAY_THRESHOLD_S, build_rows
from .config import Config

FEATURES = ["wind_speed", "wind_gust", "fog_fraction", "wave_height", "sea_current"]
TARGET = "disrupted"


def load_frame(cfg: Config | None = None) -> pd.DataFrame:
    cfg = cfg or Config.load()
    conn = db.connect(cfg.db_path)
    try:
        rows = build_rows(conn)
    finally:
        conn.close()

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["aimed_departure"] = pd.to_datetime(df["aimed_departure"], utc=True)
    df = df.sort_values("aimed_departure").reset_index(drop=True)
    df[TARGET] = (
        (df["delay_seconds"] >= DELAY_THRESHOLD_S) | (df["cancelled"] == 1)
    ).astype(int)
    # Only sailings we could pair with weather are usable for modelling.
    df = df[df["matched_weather"]].reset_index(drop=True)
    return df


def xy(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    return df[FEATURES], df[TARGET]
