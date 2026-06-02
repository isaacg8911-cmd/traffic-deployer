"""Lightweight online checks (hints only — never used in field/offline mode)."""
from __future__ import annotations

import time

from core.offline_policy import internet_features_allowed

try:
    import requests

    _HAS_REQUESTS = True
except Exception:
    _HAS_REQUESTS = False

_UA = "TrafficDeployer-Desktop/1.0"
_CACHE_TTL = 45.0
_last: dict[str, object] = {"t": 0.0, "ok": None}


def geocode_hosts_reachable(*, timeout: float = 2.0) -> bool | None:
    """True/False if a geocoding host responds; None if skipped or requests unavailable."""
    if not internet_features_allowed() or not _HAS_REQUESTS:
        return None
    now = time.time()
    if now - float(_last["t"]) < _CACHE_TTL and _last["ok"] is not None:
        return bool(_last["ok"])
    ok = False
    for url in (
        "https://geocoding.geo.census.gov/geocoder/",
        "https://nominatim.openstreetmap.org/",
    ):
        try:
            r = requests.get(url, headers={"User-Agent": _UA}, timeout=timeout)
            if r.status_code < 500:
                ok = True
                break
        except Exception:
            continue
    _last["t"] = now
    _last["ok"] = ok
    return ok
