"""Grab GPS — non-blocking snapshot + road snap helper."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from gps_reader import fix_from_snapshot, no_fix_message
from core import geo


def main() -> int:
    fails = 0

    if fix_from_snapshot(None) is not None:
        print("FAIL: fix_from_snapshot(None)")
        fails += 1
    else:
        print("OK: fix_from_snapshot none")

    if fix_from_snapshot({"fix": False, "lat": 1.0, "lon": 2.0}) is not None:
        print("FAIL: fix_from_snapshot no fix")
        fails += 1
    else:
        print("OK: fix_from_snapshot requires fix flag")

    pair = fix_from_snapshot({"fix": True, "lat": 33.7, "lon": -117.8})
    if pair != (33.7, -117.8):
        print(f"FAIL: fix_from_snapshot ok got {pair}")
        fails += 1
    else:
        print("OK: fix_from_snapshot ok")

    msg = no_fix_message({"connected": False})
    if "No GPS found" not in msg:
        print(f"FAIL: no_fix_message disconnected: {msg}")
        fails += 1
    else:
        print("OK: no_fix_message")

    lat, lon, snapped = geo.snap_field_gps(33.77, -117.94, ROOT + "/tds_data")
    if not isinstance(snapped, bool):
        print("FAIL: snap_field_gps shape")
        fails += 1
    else:
        print(f"OK: snap_field_gps snapped={snapped} ({lat:.5f}, {lon:.5f})")

    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
