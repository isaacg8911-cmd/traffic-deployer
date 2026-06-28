"""Grab GPS must never block the UI thread (no get_fix in _grab_gps_here)."""
from __future__ import annotations

import inspect
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import gps_reader  # noqa: E402
import main as main_mod  # noqa: E402


def run() -> int:
    grab_src = inspect.getsource(main_mod.MainWindow._grab_gps_here)
    origin_src = inspect.getsource(main_mod.MainWindow._origin_from_gps)
    if "get_fix" in grab_src:
        print("FAIL: _grab_gps_here still calls get_fix()")
        return 1
    if "get_fix" in origin_src:
        print("FAIL: _origin_from_gps still calls get_fix()")
        return 1
    if gps_reader.fix_from_snapshot(None) is not None:
        print("FAIL: fix_from_snapshot(None) should be None")
        return 1
    if gps_reader.fix_from_snapshot({"fix": False, "lat": 1.0, "lon": 2.0}) is not None:
        print("FAIL: fix_from_snapshot without fix")
        return 1
    pair = gps_reader.fix_from_snapshot({"fix": True, "lat": 33.7, "lon": -117.8})
    if pair != (33.7, -117.8):
        print(f"FAIL: fix_from_snapshot returned {pair!r}")
        return 1
    msg = gps_reader.no_fix_message({"connected": False})
    if "No GPS found" not in msg:
        print("FAIL: no_fix_message disconnected")
        return 1
    print("OK: grab GPS uses stream only — no COM port scan on UI thread")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
