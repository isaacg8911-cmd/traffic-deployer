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


def test_pick_pauses_on_install() -> None:
    """RTE-5: Install must not keep route-pick clicks. Route restores the order."""
    print("[RTE-5 pick pauses when leaving Route]")
    from ui.controllers.map_sync import MapSyncControllerMixin
    from ui.controllers.route import RouteControllerMixin
    from ui.page_indices import NAV_PAGE_COUNT
    from ui.shell.topbar import ShellTopbarMixin

    class Pages:
        def __init__(self) -> None:
            self.i = 1

        def currentIndex(self) -> int:
            return self.i

        def setCurrentIndex(self, i: int) -> None:
            self.i = i

    class Btn:
        def setChecked(self, _on: bool) -> None:
            return

        def setText(self, text: str) -> None:
            self.text = text

        def setObjectName(self, _name: str) -> None:
            return

        def style(self):
            return self

        def unpolish(self, _w) -> None:
            return

        def polish(self, _w) -> None:
            return

    class Win(ShellTopbarMixin, RouteControllerMixin, MapSyncControllerMixin):
        def __init__(self) -> None:
            self.pages = Pages()
            self._route_pick_mode = True
            self._route_pick_uids = ["u1"]
            self._route_pick_sides = {"u1": "begin"}
            self._route_pick_section = "Day 1"
            self._route_pick_by_map = {"Day 2": {"uids": ["u9"], "sides": {"u9": "end"}}}
            self._route_pick_suspended = None
            self._route_pick_dialog = None
            self._manual_grab_mode = False
            self._map_js_ready = False
            self._map_preview_stops = []
            self._pick_layout_active = False
            self._pick_splitter_saved = None
            self._gps_follow = False
            self._pick_side_mode = "begin"
            self.messages: list[str] = []
            self.selected: list[int] = []
            self.chk_show_segments = type("C", (), {"isChecked": lambda _s: False})()
            stops = [
                {
                    "uid": "u1", "id": "1", "street": "First",
                    "begin_lat": 33.80, "begin_lon": -117.90,
                    "end_lat": 33.81, "end_lon": -117.90,
                },
                {
                    "uid": "u2", "id": "2", "street": "Second",
                    "begin_lat": 33.82, "begin_lon": -117.91,
                    "end_lat": 33.83, "end_lon": -117.91,
                },
            ]
            self.state = type("S", (), {
                "offline_mode": False,
                "stops": stops,
                "home": (33.7, -117.8),
                "route": {"polyline": [], "miles": 0.0, "graph": False},
                "map_day_filter": "All days",
                "active_files": [],
                "routes_by_map": {},
            })()
            self.state.index_of = lambda uid, rows=stops: next(
                (i for i, s in enumerate(rows) if s["uid"] == uid), -1)
            for j in range(NAV_PAGE_COUNT):
                setattr(self, f"_navbtn_{j}", Btn())
            self.btn_start = Btn()
            self.bridge = type("B", (), {"set_follow": lambda *_a, **_k: None})()

        def statusBar(self):
            return self

        def showMessage(self, msg: str, _ms: int = 0) -> None:
            self.messages.append(msg)

        def _refresh_route_list(self) -> None:
            return

        def _refresh_install(self) -> None:
            return

        def _refresh_pickup(self) -> None:
            return

        def _refresh_audit(self) -> None:
            return

        def _refresh_workflow_strip(self) -> None:
            return

        def _refresh_field_alerts(self) -> None:
            return

        def _update_right(self, force_map: bool = False) -> None:
            _ = force_map

        def _push_state(self, fit: bool = False) -> None:
            _ = fit

        def _flush_install_form(self) -> None:
            return

        def _end_manual_grab(self, *, silent: bool = False, then=None) -> None:
            _ = silent
            if then:
                then()

        def _enter_pick_map_focus(self) -> None:
            return

        def _set_drive_mode(self, _on: bool) -> None:
            return

        def _apply_power_profile(self) -> None:
            return

        def _select_install_stop(self, idx: int) -> None:
            self.selected.append(idx)

    win = Win()
    win._on_map_clicked(33.82, -117.91)
    check(win._route_pick_uids == ["u1", "u2"], "on Route, a map click still adds the next stop")

    win._route_pick_uids = ["u1"]
    win._route_pick_sides = {"u1": "begin"}
    win._go_page(2)
    check(win.pages.currentIndex() == 2, "Install tab opens")
    check(win._route_pick_mode is False, "pick mode is off on Install")
    check(win._section_pick_active() is False, "map leaves pick mode")
    check(not win._route_pick_mode, "Drop pin guard sees pick mode off")
    check(any("paused" in m for m in win.messages), "operator is told the pick is paused")
    win._on_map_clicked(33.82, -117.91)
    check(win._route_pick_uids == ["u1"], "Install map click does not add a stop")
    win._on_stop_clicked("u2|end")
    check(win.selected == [1], "Install stop click selects that site")
    check(win._route_pick_uids == ["u1"], "Install stop click does not extend the order")
    saved_day2 = list(win._route_pick_suspended["by_map"]["Day 2"]["uids"])
    win._route_pick_by_map = {"Day 2": {"uids": ["changed"], "sides": {}}}

    win._gps_follow = True
    win._go_page(1)
    check(win._route_pick_mode is False, "GPS follow does not resume pick")
    check(win._route_pick_suspended is not None, "paused order kept during follow")
    win._stop_drive()
    check(win._route_pick_mode is True, "stopping follow on Route resumes pick")
    check(win._route_pick_uids == ["u1"], "resumed order is the paused order")
    check(win._route_pick_sides.get("u1") == "begin", "resumed side locks")
    check(win._route_pick_by_map["Day 2"]["uids"] == saved_day2, "other day's paused picks survive")
    check(win._route_pick_suspended is None, "pause cleared once pick is back")

    win._go_page(2)
    check(win._route_pick_mode is False, "leaving Route pauses again")
    win._begin_route_pick([{
        "uid": "new", "id": "9", "street": "New",
        "begin_lat": 33.9, "begin_lon": -117.9,
        "end_lat": 33.91, "end_lon": -117.9,
    }])
    check(win._route_pick_mode is True, "a new Build starts pick mode")
    check(win._route_pick_uids == [], "a new Build does not restore the paused order")
    check(win._route_pick_suspended is None, "a new Build clears the pause")
    check(win.pages.currentIndex() == 1, "a new Build opens Route")

    idle = Win()
    idle._route_pick_mode = False
    idle._route_pick_uids = []
    idle._go_page(2)
    check(idle._route_pick_suspended is None, "leaving Route with no pick does not invent a pause")
    check(idle._route_pick_mode is False, "Install stays out of pick mode")


def main() -> int:
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])  # noqa: F841
    test_gps_stale()
    test_gps_skips_ftdi()
    test_persistence_missing_key()
    test_export_serial()
    test_pickup_pending_advance()
    test_static_fixes()
    test_pick_pauses_on_install()
    print("PASS" if not fails else f"FAIL ({fails})")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
