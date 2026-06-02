"""In-app home Wi‑Fi checks (P32) — no calls when field mode is on."""
from __future__ import annotations

import os
import urllib.request

from core import connectivity
from core.offline_policy import internet_features_allowed

_UA = "TrafficDeployer-Desktop/1.0"


def _probe(url: str, timeout: float = 8.0) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read(128)
            return True, f"HTTP {r.status}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:80]


def run_checks(*, data_dir: str, app_dir: str) -> list[dict]:
    """Each row: {label, ok, detail}. Empty if field mode blocks network tests."""
    if not internet_features_allowed():
        return [{
            "label": "Field mode",
            "ok": True,
            "detail": "Network tests skipped — resume online mode at home",
        }]

    rows: list[dict] = []
    pmtiles = os.path.join(data_dir, "california.pmtiles")
    if os.path.isfile(pmtiles) and os.path.getsize(pmtiles) >= 100 * 1024 * 1024:
        mb = os.path.getsize(pmtiles) / (1024 * 1024)
        rows.append({"label": "California offline map", "ok": True, "detail": f"{mb:.0f} MB local"})
    else:
        rows.append({
            "label": "California offline map",
            "ok": False,
            "detail": "Run START.bat on home Wi‑Fi once",
        })

    try:
        import road_router

        if road_router.has_graph(data_dir):
            g = road_router.load_graph(data_dir)
            n = len(g.nodes) if g else 0
            rows.append({"label": "Road routing graph", "ok": n > 0, "detail": f"{n:,} nodes local"})
        else:
            rows.append({
                "label": "Road routing graph",
                "ok": False,
                "detail": "Download or import after files loaded",
            })
        any_ov = False
        for row in road_router.probe_all_mirrors()[:4]:
            if row.get("ok"):
                any_ov = True
        rows.append({
            "label": "Road download (Overpass)",
            "ok": any_ov,
            "detail": "At least one mirror OK" if any_ov else "Try hotspot or import .graphml",
        })
    except Exception as exc:  # noqa: BLE001
        rows.append({"label": "Road routing", "ok": False, "detail": str(exc)[:60]})

    geo = connectivity.geocode_hosts_reachable(timeout=4.0)
    if geo is True:
        rows.append({"label": "Address search", "ok": True, "detail": "Geocoding hosts reachable"})
    elif geo is False:
        rows.append({
            "label": "Address search",
            "ok": False,
            "detail": "Blocked — use GPS, coordinates, or phone hotspot",
        })
    else:
        rows.append({"label": "Address search", "ok": False, "detail": "requests library missing"})

    web_index = os.path.join(app_dir, "web", "index.html")
    rows.append({
        "label": "Map UI files",
        "ok": os.path.isfile(web_index),
        "detail": "web/index.html" if os.path.isfile(web_index) else "missing",
    })
    return rows
