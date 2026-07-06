"""Resolve real IDs instead of hard-coding them.

    python -m ferrydelay.lookup stop "Halhjem"      # -> STOP_PLACE_ID candidates
    python -m ferrydelay.lookup station             # -> nearest Frost stations
"""
from __future__ import annotations

import sys

from . import entur, metno
from .config import Config


def _stops(cfg: Config, text: str) -> int:
    for r in entur.find_stop_places(cfg.et_client_name, text):
        print(f"{r['id']:<28} {r['name']}  [{r['category']}]")
    return 0


def _stations(cfg: Config) -> int:
    if not cfg.frost_client_id:
        print("FROST_CLIENT_ID not set. Register (free): "
              "https://frost.met.no/auth/requestCredentials.html", file=sys.stderr)
        return 1
    for s in metno.frost_sources_near(cfg.frost_client_id, cfg.route_lat, cfg.route_lon):
        print(f"{s.get('id'):<12} {s.get('name')}")
    return 0


def main(argv: list[str]) -> int:
    cfg = Config.load()
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    if cmd == "stop":
        if len(argv) < 2:
            print('usage: lookup stop "<name>"', file=sys.stderr)
            return 1
        return _stops(cfg, argv[1])
    if cmd == "station":
        return _stations(cfg)
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
