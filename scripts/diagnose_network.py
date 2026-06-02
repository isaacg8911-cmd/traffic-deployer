"""Network checks for work-laptop setup (run while on work Wi‑Fi).

    .venv\\Scripts\\python.exe scripts\\diagnose_network.py

Tests the same hosts START.bat and "Download road map" need.
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


def _probe(url: str, timeout: float = 12.0) -> tuple[bool, str]:
    """GET first bytes; some CDNs reject HEAD with 403 even when downloads work."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read(256)
            return r.status == 200, f"HTTP {r.status}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def main() -> int:
    print("Traffic Deployer — network diagnostic\n")
    fails = 0

    if os.path.isfile(PMTILES):
        mb = os.path.getsize(PMTILES) / (1024 * 1024)
        ok = mb >= 100
        mark = "OK" if ok else "FAIL"
        print(f"  [{mark}] Local basemap: {mb:.0f} MB at tds_data\\california.pmtiles")
        if not ok:
            fails += 1
            print("         Incomplete - delete file and re-run START.bat on good Wi-Fi.")
    else:
        print("  [WARN] No california.pmtiles - START.bat will download ~1.4 GB on first run.")
        fails += 1

    if os.path.isfile(ROAD_GRAPH):
        mb = os.path.getsize(ROAD_GRAPH) / (1024 * 1024)
        try:
            import road_router

            data_dir = os.path.dirname(ROAD_GRAPH)
            if road_router.has_graph(data_dir):
                g = road_router.load_graph(data_dir)
                nodes = len(g.nodes) if g else 0
                print(f"  [OK] Local road graph: {mb:.1f} MB ({nodes:,} nodes, routing offline)")
            else:
                print(
                    f"  [WARN] road_graph.graphml on disk ({mb:.1f} MB) but will not load — "
                    "run START.bat (.venv) or re-import from home PC"
                )
        except Exception as exc:  # noqa: BLE001
            print(f"  [WARN] road_graph.graphml ({mb:.1f} MB) — load check failed: {exc}")
    else:
        print("  [WARN] No road_graph.graphml - use Setup -> Download road map (needs Overpass)")

    need_basemap = not (os.path.isfile(PMTILES) and os.path.getsize(PMTILES) >= 100 * 1024 * 1024)
    print("\nHosts used by START.bat (California map):")
    for label, url in (
        ("Protomaps build", "https://build.protomaps.com/"),
        ("MapLibre CDN", "https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.js"),
        ("GitHub releases", "https://api.github.com/"),
    ):
        ok, detail = _probe(url)
        mark = "OK" if ok else ("FAIL" if need_basemap else "WARN")
        print(f"  [{mark}] {label}: {detail}")
        if not ok and need_basemap:
            fails += 1

    print("\nOpenStreetMap road download (Setup button):")
    need_roads = not os.path.isfile(ROAD_GRAPH)
    try:
        import road_router

        any_ok = False
        for row in road_router.probe_all_mirrors():
            mark = "OK" if row["ok"] else ("FAIL" if need_roads else "WARN")
            host = row["base"].replace("https://", "")
            print(f"  [{mark}] {host}: {row['detail']}")
            if row["ok"]:
                any_ok = True
        if not any_ok:
            err = road_router.probe_roads_internet() or "no mirror reachable"
            if need_roads:
                fails += 1
            print(f"\n  → {err}")
        elif need_roads:
            print("  → At least one mirror works — try Download road map in Setup.")
    except Exception as exc:  # noqa: BLE001
        print(f"  [FAIL] Could not test Overpass: {exc}")
        if need_roads:
            fails += 1

    print("\nIf every mirror fails on work Wi-Fi:")
    print("  1. Phone hotspot -> Download road map, OR")
    print("  2. Copy tds_data\\road_graph.graphml from home -> Setup -> Import road map from file.")
    print()
    if fails:
        print(f"Result: {fails} issue(s) — fix before field or use copied tds_data.")
        return 1
    print("Result: network looks OK for downloads.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
