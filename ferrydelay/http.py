"""Tiny HTTP helper: a shared session with retries and sane timeouts."""
from __future__ import annotations

import time

import requests

_TIMEOUT = 30
_RETRIES = 3
_BACKOFF = 2.0


def get_json(url: str, *, headers: dict | None = None, params: dict | None = None,
             auth: tuple | None = None) -> dict:
    last: Exception | None = None
    for attempt in range(_RETRIES):
        try:
            resp = requests.get(url, headers=headers, params=params, auth=auth,
                                timeout=_TIMEOUT)
            if resp.status_code == 429 or resp.status_code >= 500:
                resp.raise_for_status()
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last = exc
            if attempt < _RETRIES - 1:
                time.sleep(_BACKOFF * (attempt + 1))
    raise RuntimeError(f"GET {url} failed after {_RETRIES} attempts: {last}")


def post_json(url: str, *, json: dict, headers: dict | None = None) -> dict:
    last: Exception | None = None
    for attempt in range(_RETRIES):
        try:
            resp = requests.post(url, json=json, headers=headers, timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last = exc
            if attempt < _RETRIES - 1:
                time.sleep(_BACKOFF * (attempt + 1))
    raise RuntimeError(f"POST {url} failed after {_RETRIES} attempts: {last}")
