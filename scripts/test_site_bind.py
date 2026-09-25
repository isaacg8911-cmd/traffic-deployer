"""GPS grab / Drop pin must bind to the chosen site — never the previous one.

Field bug: skip Install, tap next site, Grab GPS -> saved on previous site.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import site_window  # noqa: E402

# Two sites ~1.1 km apart on a N-S street (Anaheim-ish).
A = {"uid": "a", "id": 101, "begin_lat": 33.8300, "begin_lon": -117.9100,
     "end_lat": 33.8320, "end_lon": -117.9100, "street": "A St"}
B = {"uid": "b", "id": 102, "begin_lat": 33.8400, "begin_lon": -117.9100,
     "end_lat": 33.8420, "end_lon": -117.9100, "street": "B St"}
AT_A = (33.8310, -117.9101)
AT_B = (33.8410, -117.9101)

fails = 0


def check(cond: bool, label: str) -> None:
    global fails
    print(("  OK  " if cond else "  FAIL ") + label)
    if not cond:
        fails += 1


def test_site_window() -> None:
    print("[core.site_window]")
    stops = [dict(A), dict(B)]
    check(site_window.check(stops, 0, *AT_A)["ok"], "point on site A segment is inside A")
    r = site_window.check(stops, 0, *AT_B)
    check(not r["ok"] and r["reason"] == "other_site" and r["nearest_idx"] == 1,
          "point at site B while A selected -> other_site (B)")
    r = site_window.check(stops, 0, 33.90, -117.91)
    check(not r["ok"] and r["reason"] == "far", "point 7 km away -> far")
    check(site_window.check([{"uid": "x", "id": 1}], 0, *AT_A)["ok"],
          "site without coords never blocks")


def _make_win(answer_yes: bool = True):
    from PySide6.QtWidgets import QMessageBox
    from ui.controllers import install as install_mod
    from ui.controllers.install import InstallControllerMixin

    install_mod.QMessageBox.question = staticmethod(
        lambda *a, **k: QMessageBox.Yes if answer_yes else QMessageBox.No)

    class _Lbl:
        def __init__(self):
            self.v = ""

        def setText(self, v):
            self.v = v

        def setVisible(self, *_):
            pass

    class _Page:
        def __init__(self):
            self.pending = []

        def runJavaScript(self, js, cb=None):
            if cb is not None:
                self.pending.append(cb)

    class _Bridge:
        def __getattr__(self, _name):
            return lambda *a, **k: None

    class _Timer:
        def stop(self):
            pass

        def start(self, *_):
            pass

    class Win(InstallControllerMixin):
        def __init__(self):
            self.state = type("S", (), {})()
            self.state.stops = [dict(A), dict(B)]
            self.current_index = 0
            self._manual_grab_mode = False
            self._pin_flush_busy = False
            self._route_pick_mode = False
            self._gps_follow = False
            self._pin_persist_timer = _Timer()
            self.lbl_grab = _Lbl()
            self.bridge = _Bridge()
            self._page = _Page()
            self.view = type("V", (), {"page": lambda _s: self._page})()
            self.flushed_into = []
            self.status = ""
            self.gps_fix = None

        def _flush_install_form(self):
            self.flushed_into.append(self.current_index)

        def _persist_shift(self, quiet=True): pass
        def _refresh_install(self): pass
        def _refresh_install_checklist(self): pass
        def _refresh_install_progress_list(self): pass
        def _push_state(self, fit=False): pass
        def _center_current(self): pass
        def _internet_allowed(self): return False
        def _start_field_street_thread(self, *a, **k): pass
        def _warn(self, msg): self.status = msg

        def statusBar(self):
            win = self
            return type("SB", (), {"showMessage": lambda _s, m, *a: setattr(win, "status", m)})()

    import core.geo as geo_mod
    geo_mod.snap_field_gps = lambda lat, lon, _d: (lat, lon, False)
    return Win()


def test_switch_while_drop_pin() -> None:
    print("[Drop pin on A -> tap site B]")
    w = _make_win()
    w._manual_grab_mode = True
    w._select_install_stop(1)
    check(w.current_index == 1, "index moves to B immediately (no async wait)")
    check(w.flushed_into[:1] == [0], "form flushed into A before switching")
    check(not w._manual_grab_mode, "Drop pin mode off — map taps no longer save")
    # Grab before the JS pin read returns -> blocked, not saved to A.
    w._grab_gps_here()
    check(w.state.stops[0].get("field_lat") is None and w.state.stops[1].get("field_lat") is None,
          "Grab GPS during pin flush saves nothing")
    # JS returns A's dragged pin late -> lands on A only.
    cb = w._page.pending.pop(0)
    cb({"lat": AT_A[0], "lon": AT_A[1], "uid": "a"})
    check(w.state.stops[0].get("field_lat") == AT_A[0], "late pin read saved to A (its own site)")
    check(w.state.stops[1].get("field_lat") is None, "B untouched by A's pin")
    check(w.lbl_grab.v == "", "B's GPS label not overwritten with A's pin")


def test_foreign_pin_rejected() -> None:
    print("[pin owned by A never saves to B]")
    w = _make_win()
    w.current_index = 1
    ok = w._apply_manual_pin_coords({"lat": AT_A[0], "lon": AT_A[1], "uid": "a"}, uid="b")
    check(not ok and w.state.stops[1].get("field_lat") is None, "A pin rejected for B")


def test_grab_outside_window() -> None:
    print("[Grab GPS at site A while B selected]")
    w = _make_win(answer_yes=False)
    w.current_index = 1
    ok = w._save_field_position(*AT_A, source="gps")
    check(not ok and w.state.stops[1].get("field_lat") is None,
          "user says No -> not saved to B")
    w2 = _make_win(answer_yes=True)
    w2.current_index = 1
    check(w2._save_field_position(*AT_A, source="gps"), "user says Yes -> saved")
    w3 = _make_win(answer_yes=False)
    w3.current_index = 1
    check(w3._save_field_position(*AT_B, source="gps"), "grab at B for B -> no prompt, saved")


def test_route_list_click_on_install() -> None:
    print("[left route list click while on Install]")
    import inspect
    from ui.controllers.route import RouteControllerMixin
    src = inspect.getsource(RouteControllerMixin._route_item_clicked)
    check("_select_install_stop" in src, "route list click routes through _select_install_stop")


def test_js_pin_owner() -> None:
    print("[web/app.js pin ownership]")
    with open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8") as f:
        js = f.read()
    check("fieldPinMarker._tdUid !== (state.current_uid || '')" in js,
          "foreign-site pin cleared on site change")
    check("uid: fieldPinMarker._tdUid || ''" in js, "confirm returns pin uid")


def main() -> int:
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])  # noqa: F841
    test_site_window()
    test_switch_while_drop_pin()
    test_foreign_pin_rejected()
    test_grab_outside_window()
    test_route_list_click_on_install()
    test_js_pin_owner()
    print("PASS" if not fails else f"FAIL ({fails})")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
