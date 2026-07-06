"""Runtime configuration loaded from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    metno_user_agent: str
    frost_client_id: str
    et_client_name: str
    route_name: str
    stop_place_id: str
    destination_filter: str
    route_lat: float
    route_lon: float
    frost_source_id: str
    db_path: Path

    @classmethod
    def load(cls) -> "Config":
        ua = os.getenv("METNO_USER_AGENT", "").strip()
        if not ua:
            raise RuntimeError(
                "METNO_USER_AGENT is required (met.no rejects requests without a "
                "User-Agent). Copy .env.example to .env and fill it in."
            )
        db = os.getenv("DB_PATH", "data/ferry.db").strip()
        db_path = Path(db)
        if not db_path.is_absolute():
            db_path = ROOT / db_path
        return cls(
            metno_user_agent=ua,
            frost_client_id=os.getenv("FROST_CLIENT_ID", "").strip(),
            et_client_name=os.getenv("ET_CLIENT_NAME", "ferry-delay-predictor").strip(),
            route_name=os.getenv("ROUTE_NAME", "unknown").strip(),
            stop_place_id=os.getenv("STOP_PLACE_ID", "").strip(),
            destination_filter=os.getenv("DESTINATION_FILTER", "").strip(),
            route_lat=float(os.getenv("ROUTE_LAT", "60.075")),
            route_lon=float(os.getenv("ROUTE_LON", "5.360")),
            frost_source_id=os.getenv("FROST_SOURCE_ID", "").strip(),
            db_path=db_path,
        )
