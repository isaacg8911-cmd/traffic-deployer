"""Network checks for work-laptop setup (run while on work Wi‑Fi).

    .venv\\Scripts\\python.exe scripts\\diagnose_network.py

Only probes remote hosts when the matching local asset is missing.
Already-cached basemap / road graph → no noisy WARNs and no mirror timeouts.
"""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DATA = os.path.join(ROOT, "tds_data")
PMTILES = os.path.join(DATA, "california.pmtiles")
ROAD_GRAPH = os.path.join(DATA, "road_graph.graphml")
_UA = "TrafficDeployer-NetDiag/1.0 (field laptop; +https://github.com/isaacg8911-cmd/traffic-deployer)"


def _probe(url: str, timeout: float = 12.0) -> tuple[bool, str]:
    """GET first bytes; some CDNs reject HEAD with 403 even when downloads work."""
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read(256)
            return r.status == 200, f"HTTP {r.status}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def main() -> int:
    print("Traffic Deployer — network diagnostic\n")
    fails = 0

    has_basemap = os.path.isfile(PMTILES) and os.path.getsize(PMTILES) >= 100 * 1024 * 1024
    if has_basemap:
        mb = os.path.getsize(PMTILES) / (1024 * 1024)
        print(f"  [OK] Local basemap: {mb:.0f} MB at tds_data\\california.pmtiles")
    elif os.path.isfile(PMTILES):
        print("  [FAIL] california.pmtiles incomplete — delete and re-run START.bat on good Wi-Fi")
        fails += 1
    else:
        print("  [FAIL] No california.pmtiles — START.bat will download ~1.4 GB on first run")
        fails += 1

    has_roads = False
    if os.path.isfile(ROAD_GRAPH):
        mb = os.path.getsize(ROAD_GRAPH) / (1024 * 1024)
        try:
            import road_router

            data_dir = os.path.dirname(ROAD_GRAPH)
            if road_router.has_graph(data_dir):
                g = road_router.load_graph(data_dir)
                nodes = len(g.nodes) if g else 0
                print(f"  [OK] Local road graph: {mb:.1f} MB ({nodes:,} nodes, routing offline)")
                has_roads = True
            else:
                print(
                    f"  [WARN] road_graph.graphml on disk ({mb:.1f} MB) but will not load — "
                    "run START.bat (.venv) or re-import from home PC"
                )
        except Exception as exc:  # noqa: BLE001
            print(f"  [WARN] road_graph.graphml ({mb:.1f} MB) — load check failed: {exc}")
    else:
        print("  [WARN] No road_graph.graphml — Setup → Download road map (needs Overpass)")

    # --- remote probes only when the local asset is missing -------------------
    print("\nMap download hosts (only if refreshing / first-time basemap):")
    if has_basemap:
        print("  [OK] skipped — local basemap present (Protomaps / CDN not needed in field)")
    else:
        for label, url in (
            # Root listing often 403; unpkg + GitHub cover setup_maps vendor path.
            ("MapLibre CDN", "https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.js"),
            ("PMTiles CDN", "https://unpkg.com/pmtiles@4.1.0/dist/pmtiles.js"),
            ("GitHub releases", "https://api.github.com/"),
        ):
            ok, detail = _probe(url)
            mark = "OK" if ok else "FAIL"
            print(f"  [{mark}] {label}: {detail}")
            if not ok:
                fails += 1
        print("  → Protomaps tile extract needs home/hotspot Wi-Fi if build.protomaps.com is blocked.")

    print("\nOpenStreetMap road download (Setup button):")
    if has_roads:
        print("  [OK] skipped — local road graph present (Overpass not needed in field)")
    else:
        try:
            import road_router

            any_ok = False
            for row in road_router.probe_all_mirrors():
                mark = "OK" if row["ok"] else "WARN"
                host = row["base"].replace("https://", "")
                print(f"  [{mark}] {host}: {row['detail']}")
                if row["ok"]:
                    any_ok = True
            if not any_ok:
                fails += 1
                err = road_router.probe_roads_internet() or "no mirror reachable"
                print(f"\n  → {err}")
            else:
                print("  → At least one mirror works — try Download road map in Setup.")
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAIL] Could not test Overpass: {exc}")
            fails += 1

    print("\nAddress search (home setup only — unused in field mode):")
    geocoders = (
        ("US Census", "https://geocoding.geo.census.gov/geocoder/"),
        ("Nominatim", "https://nominatim.openstreetmap.org/"),
        ("Photon", "https://photon.komoot.io/api/?q=test&limit=1"),
    )
    ok_names: list[str] = []
    for label, url in geocoders:
        ok, _detail = _probe(url)
        if ok:
            ok_names.append(label)
    if ok_names:
        print(f"  [OK] {', '.join(ok_names)} reachable")
    else:
        print("  [WARN] no geocoder reachable — home address search may fail (field OK without it)")

    if not has_roads:
        print("\nIf every Overpass mirror fails on work Wi-Fi:")
        print("  1. Phone hotspot → Download road map, OR")
        print("  2. Copy tds_data\\road_graph.graphml from home → Setup → Import road map from file.")
    print()
    if fails:
        print(f"Result: {fails} issue(s) — fix before field or use copied tds_data.")
        return 1
    print("Result: local maps OK — field-ready on this PC.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
