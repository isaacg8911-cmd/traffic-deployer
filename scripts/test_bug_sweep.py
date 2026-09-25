"""Regression checks for the 2026-09-25 bug sweep (GPS, persistence, pickup, export)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

fails = 0


def check(cond: bool, label: str) -> None:
    global fails
    print(("  OK  " if cond else "  FAIL ") + label)
    if not cond:
        fails += 1


def test_gps_stale() -> None:
    print("[gps fix expiry]")
    import time
    import gps_reader

    s = gps_reader.GPSStream()
    if s._lock is None:
        print("  skip (pyserial missing)")
        return
    s._update(fix=True, lat=33.8, lon=-117.9, connected=True)
    s._last_fix_t = time.monotonic()
    check(s.latest()["fix"] is True, "fresh fix reported")
    s._last_fix_t = time.monotonic() - (gps_reader.FIX_STALE_S + 1)
    g = s.latest()
    check(g["fix"] is False and g.get("stale"), "fix older than FIX_STALE_S reported as no fix")
    check(gps_reader.fix_from_snapshot(g) is None, "Grab GPS refuses stale fix")

    class RMC:
        status, latitude, longitude = "V", 33.8, -117.9

    class GGA0:
        gps_qual, latitude, longitude = 0, 33.8, -117.9

    class GGA1:
        gps_qual, latitude, longitude = 1, 33.8, -117.9

    check(gps_reader._valid_fix(RMC()) is None and gps_reader._reports_no_fix(RMC()), "RMC V = no fix")
    check(gps_reader._valid_fix(GGA0()) is None, "GGA quality 0 = no fix")
    check(gps_reader._valid_fix(GGA1()) == (33.8, -117.9), "GGA quality 1 = fix")


def test_gps_skips_ftdi() -> None:
    print("[gps scan never probes counter FTDI port]")
    import gps_reader

    blobs = {"COM3": "usb serial port ftdi vid_0403", "COM4": "some other serial"}
    orig = (gps_reader.list_serial_ports, gps_reader._port_blob)
    gps_reader.list_serial_ports = lambda: list(blobs)
    gps_reader._port_blob = lambda p: blobs.get(p, "")
    try:
        check(gps_reader.candidate_gps_ports() == ["COM4"], "FTDI excluded from fallback scan")
    finally:
        gps_reader.list_serial_ports, gps_reader._port_blob = orig


def test_persistence_missing_key() -> None:
    print("[persistence: missing .tds_key must not wipe shift]")
    import persistence

    if not persistence.HAS_CRYPTO:
        print("  skip (cryptography missing)")
        return
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "tds_backup_T.json")
        persistence.save_state({"stops": [{"uid": "a", "installed": True}]}, p, d)
        os.remove(os.path.join(d, ".tds_key"))
        back = persistence.load_state(p, d)
        check(back == {}, "unreadable state loads empty (no crash)")
        check(not os.path.exists(os.path.join(d, ".tds_key")), "load did NOT invent a new key")
        kept = [f for f in os.listdir(d) if ".unreadable-" in f]
        check(bool(kept), "encrypted shift copied aside before any overwrite")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_export_serial() -> None:
    print("[export serial stays exact]")
    import pandas as pd
    from core import export

    for raw, want in (("0457", "0457"), ("22976.0", 22976.0), ("22976", 22976.0), ("AB12", "AB12")):
        df = pd.DataFrame({"Site": ["1"], "Serial": [None]}, dtype=object)
        export._merge_stop_into_ig_row(df, 0, {"id": "1", "serial": raw})
        got = df.at[0, "Serial"]
        check(got == want, f"serial {raw!r} -> {got!r}")


def test_pickup_pending_advance() -> None:
    print("[Mark picked up with 'Not picked up only' on]")
    from ui.controllers.pickup import PickupControllerMixin

    class Chk:
        def isChecked(self):
            return True

    class W(PickupControllerMixin):
        def __init__(self):
            self.state = type("S", (), {})()
            self.state.stops = [
                {"uid": u, "id": i, "installed": True} for i, u in enumerate("abc", start=1)]
            self.pickup_index = 0
            self.chk_pickup_pending = Chk()

        def _stops_matching_day_filter(self, items=None):
            return self.state.stops if items is None else items

        def _push_undo(self, *a, **k): pass
        def _snapshot_stop(self, s): return dict(s)
        def _persist_shift(self, quiet=True): pass
        def _counter_inventory_shift(self): pass
        def _refresh_pickup(self): pass
        def _push_state(self): pass
        def _refresh_audit(self): pass

    w = W()
    w._mark_pickup()
    items = w._installed_stops()
    check(items[w.pickup_index]["uid"] == "b", "next pending site is B (not skipped to C)")
    w._mark_pickup()
    items = w._installed_stops()
    check(items and items[w.pickup_index]["uid"] == "c", "then C")


def test_static_fixes() -> None:
    print("[static wiring]")
    import inspect
    import road_router
    from ui.controllers.install import InstallControllerMixin
    from ui.controllers.shortcuts import ShortcutsControllerMixin

    src = inspect.getsource(road_router)
    check("            maneuvers.extend(leg.get(\"maneuvers\")" not in src,
          "nav_plan appends each leg's maneuvers once")
    src = inspect.getsource(InstallControllerMixin._start_field_street_thread)
    check("_field_street_threads" in src and "finished.connect" in src,
          "street lookup threads kept alive until finished")
    src = inspect.getsource(ShortcutsControllerMixin._undo_last_action)
    check("self.current_index = idx" in src, "undo opens the undone site by uid")
    src = inspect.getsource(InstallControllerMixin._commit_install_body)
    check("already" in src and "exact_time" in src, "re-save keeps original install time")


def main() -> int:
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])  # noqa: F841
    test_gps_stale()
    test_gps_skips_ftdi()
    test_persistence_missing_key()
    test_export_serial()
    test_pickup_pending_advance()
    test_static_fixes()
    print("PASS" if not fails else f"FAIL ({fails})")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
