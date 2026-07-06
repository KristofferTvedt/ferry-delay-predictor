"""met.no weather clients.

Two real-time products (no auth, just a User-Agent) drive Phase 1 collection:

  locationforecast  — wind, gust, temperature, fog fraction over the crossing.
  oceanforecast     — significant wave height, wave direction, sea current.

Frost (historical observations) needs a free client_id and is used for backfill
in Phase 2; kept here so the historical path exists from the start.
"""
from __future__ import annotations

from .http import get_json

LOCATIONFORECAST = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
OCEANFORECAST = "https://api.met.no/weatherapi/oceanforecast/2.0/complete"
FROST_OBS = "https://frost.met.no/observations/v0.jsonld"
FROST_SOURCES = "https://frost.met.no/sources/v0.jsonld"


def _headers(user_agent: str) -> dict:
    return {"User-Agent": user_agent, "Accept": "application/json"}


def locationforecast(user_agent: str, lat: float, lon: float) -> dict:
    """Nearest-hour atmospheric conditions at the given point."""
    data = get_json(
        LOCATIONFORECAST,
        headers=_headers(user_agent),
        params={"lat": round(lat, 4), "lon": round(lon, 4)},
    )
    entry = data["properties"]["timeseries"][0]
    details = entry["data"]["instant"]["details"]
    return {
        "observed_at": entry["time"],
        "source": "locationforecast",
        "wind_speed": details.get("wind_speed"),
        "wind_gust": details.get("wind_speed_of_gust"),
        "wind_dir": details.get("wind_from_direction"),
        "air_temp": details.get("air_temperature"),
        "fog_fraction": details.get("fog_area_fraction"),
    }


def oceanforecast(user_agent: str, lat: float, lon: float) -> dict:
    """Nearest-hour sea state at the given point."""
    data = get_json(
        OCEANFORECAST,
        headers=_headers(user_agent),
        params={"lat": round(lat, 4), "lon": round(lon, 4)},
    )
    entry = data["properties"]["timeseries"][0]
    details = entry["data"]["instant"]["details"]
    return {
        "observed_at": entry["time"],
        "source": "oceanforecast",
        "wave_height": details.get("sea_surface_wave_height"),
        "wave_dir": details.get("sea_surface_wave_from_direction"),
        "sea_current": details.get("sea_water_speed"),
    }


def frost_sources_near(client_id: str, lat: float, lon: float,
                       radius_km: float = 25) -> list[dict]:
    """Frost stations within ``radius_km`` of a point (needs a client_id)."""
    if not client_id:
        raise RuntimeError("FROST_CLIENT_ID not set; register at frost.met.no")
    data = get_json(
        FROST_SOURCES,
        auth=(client_id, ""),
        params={
            "types": "SensorSystem",
            "geometry": f"nearest(POINT({lon} {lat}))",
            "nearestmaxcount": 10,
        },
    )
    return data.get("data", [])
