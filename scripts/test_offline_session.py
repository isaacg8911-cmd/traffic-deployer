"""Assert field mode performs no public HTTP (offline contract).

    .venv\\Scripts\\python.exe scripts\\test_offline_session.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DATA = os.path.join(ROOT, "tds_data")
APP = ROOT


def main() -> int:
    from core import connectivity, geo, offline_policy, setup_network

    offline_policy.set_field_mode(True)
    try:
        if geo.geocode_candidates("1 Main St, Garden Grove, CA"):
            print("FAIL: geocode should return empty in field mode")
            return 1
        if geo.street_from_coords(33.77, -117.94):
            print("FAIL: reverse geocode should be empty in field mode")
            return 1
        if connectivity.geocode_hosts_reachable() is not None:
            print("FAIL: connectivity probe should be skipped in field mode")
            return 1
        rows = setup_network.run_checks(data_dir=DATA, app_dir=APP)
        if not rows or "Field mode" not in rows[0].get("label", ""):
            print("FAIL: setup_network should skip external tests in field mode")
            return 1
    finally:
        offline_policy.set_field_mode(False)

    print("OK: offline session contract (no public HTTP entry points)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
