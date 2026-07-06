"""Entur real-time departures (the delay signal).

JourneyPlanner v3 GraphQL exposes ``estimatedCalls`` for a stop place, each with
``aimedDepartureTime`` (scheduled) and ``expectedDepartureTime`` (real-time).
Their difference is the departure delay we want to model. We filter to water
(ferry) transport so a multi-modal quay doesn't pollute the dataset.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .http import post_json

JOURNEY_PLANNER = "https://api.entur.io/journey-planner/v3/graphql"
GEOCODER = "https://api.entur.io/geocoder/v1/autocomplete"

_DEPARTURES_QUERY = """
query Departures($id: String!, $n: Int!) {
  stopPlace(id: $id) {
    id
    name
    estimatedCalls(numberOfDepartures: $n, timeRange: 86400, arrivalDeparture: departures) {
      realtime
      cancellation
      aimedDepartureTime
      expectedDepartureTime
      destinationDisplay { frontText }
      serviceJourney {
        id
        line { publicCode transportMode }
      }
    }
  }
}
"""


def _headers(client_name: str) -> dict:
    return {"ET-Client-Name": client_name, "Content-Type": "application/json"}


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def departures(client_name: str, stop_place_id: str, n: int = 40,
               destination_filter: str = "") -> list[dict]:
    """Return ferry departures for a stop place, delay computed per call.

    ``destination_filter`` (case-insensitive substring on the front text) keeps
    only sailings toward one destination — the Halhjem quay also serves other
    routes, and we only want the one the user actually travels.
    """
    data = post_json(
        JOURNEY_PLANNER,
        headers=_headers(client_name),
        json={"query": _DEPARTURES_QUERY,
              "variables": {"id": stop_place_id, "n": n}},
    )
    if "errors" in data:
        raise RuntimeError(f"Entur GraphQL error: {data['errors']}")
    sp = (data.get("data") or {}).get("stopPlace")
    if not sp:
        raise RuntimeError(f"No stop place found for id {stop_place_id!r}")

    out: list[dict] = []
    for call in sp.get("estimatedCalls", []):
        sj = call.get("serviceJourney") or {}
        line = sj.get("line") or {}
        if line.get("transportMode") != "water":
            continue
        dest = (call.get("destinationDisplay") or {}).get("frontText") or ""
        if destination_filter and destination_filter.lower() not in dest.lower():
            continue
        aimed = call.get("aimedDepartureTime")
        expected = call.get("expectedDepartureTime")
        delay = None
        if aimed and expected:
            delay = int((_parse(expected) - _parse(aimed)).total_seconds())
        out.append({
            "service_journey_id": sj.get("id"),
            "line": line.get("publicCode"),
            "destination": (call.get("destinationDisplay") or {}).get("frontText"),
            "aimed_departure": aimed,
            "expected_departure": expected,
            "realtime": 1 if call.get("realtime") else 0,
            "cancelled": 1 if call.get("cancellation") else 0,
            "delay_seconds": delay,
        })
    return out


def find_stop_places(client_name: str, text: str) -> list[dict]:
    """Geocoder autocomplete → candidate stop places (to fill STOP_PLACE_ID)."""
    from .http import get_json
    data = get_json(
        GEOCODER,
        headers={"ET-Client-Name": client_name},
        params={"text": text, "layers": "venue", "size": 10},
    )
    results = []
    for f in data.get("features", []):
        p = f.get("properties", {})
        results.append({
            "id": p.get("id"),
            "name": p.get("label"),
            "category": ",".join(p.get("category", [])),
        })
    return results


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
