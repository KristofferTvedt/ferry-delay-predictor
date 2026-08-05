"""Build the modelling table: one row per sailing, weather joined, target set.

Reuses the stdlib join from ``analyze`` (so the timezone alignment lives in one
place) and lifts it into a pandas DataFrame with a binary target.

Target = "disrupted": departure delayed by >= DELAY_THRESHOLD_S, OR cancelled.
Cancellation is folded into the positive class here because from a passenger's
standpoint a cancelled sailing is the worst delay; kept separate in storage so
this choice stays reversible.

"Did not sail" rows (see ``analyze.IMPLAUSIBLE_DELAY_S``) stay in the positive
class for the same reason: a service that never ran is a disruption, whatever the
feed called it. That is only defensible for a binary target. Any future model of
delay *magnitude* has to drop or cap them, since their recorded minutes measure
how long the row lingered in the feed rather than how late the ferry was.
"""
from __future__ import annotations

import pandas as pd

from . import db
from .analyze import DELAY_THRESHOLD_S, build_rows
from .config import Config

# air_temp is not a hazard on this crossing; it stands in for how busy the ferry
# is. Warm summer days bring tourist traffic, loading takes longer, and departures
# slip. It is the strongest single correlate in the summer data, so leaving it out
# would hide the mechanism actually driving delays right now.
FEATURES = ["wind_speed", "wind_gust", "air_temp", "fog_fraction",
            "wave_height", "sea_current"]
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
