"""Build HTML + KML viewers from a Streets & Trips .est file.

Usage:
  python scripts/view_est_map.py path/to/map.est

Uses shift backup stops when available (begin/end, installed/skipped, field GPS).
"""
from __future__ import annotations

import os
import sys
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DATA_DIR = os.path.join(ROOT, "tds_data")


def _stops_for_est(est_path: str) -> list[dict]:
    import persistence
    from core.est_viewer import pushpins_from_est

    backup = os.path.join(DATA_DIR, "tds_backup_DEFAULT.json")
    data = persistence.load_state(backup, DATA_DIR) if os.path.isfile(backup) else {}
    stops = list(data.get("stops") or [])
    if not stops:
        return []
    try:
        site_ids = {str(p["site"]) for p in pushpins_from_est(est_path)}
    except Exception:
        return []
    return [s for s in stops if str(s.get("id", "")).strip() in site_ids]


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/view_est_map.py <file.est>")
        return 1
    est_path = sys.argv[1]
    if not os.path.isfile(est_path):
        print(f"Not found: {est_path}")
        return 1

    from core.est_viewer import sites_from_stops, write_viewer_files

    stops = _stops_for_est(est_path)
    paths = write_viewer_files(
        est_path,
        title=os.path.splitext(os.path.basename(est_path))[0],
        stops=stops or None,
    )
    count = len(sites_from_stops(stops)) if stops else paths["count"]
    print(f"Sites on map: {count}" + (" (from shift backup)" if stops else " (EST pins only)"))
    print(f"HTML: {paths['html']}")
    print(f"KML:  {paths['kml']}")
    if int(paths["count"] or 0) > 0:
        webbrowser.open(f"file:///{paths['html'].replace(os.sep, '/')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
