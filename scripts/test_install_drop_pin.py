"""User-path desk test: INSTALL without checklist block + drop-pin GPS + Wi-Fi geocode."""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  OK  {name}")
    else:
        msg = f"{name}" + (f": {detail}" if detail else "")
        print(f"  FAIL {msg}")
        FAILURES.append(msg)


def main() -> int:
    print(f"Install + drop-pin user path — {ROOT}\n")

    from core import install_checklist
    from core.state import RouteState, ca_now
    from main import MainWindow

    check("install never blocked", install_checklist.install_block_reason({}) is None)
    items = install_checklist.checklist_for_stop({})
    check("checklist advisory", all(it.get("optional") for it in items))

    td, _ = ca_now()
    d = tempfile.mkdtemp()
    st = RouteState(d, profile="DROP_PIN_TEST")
    st.stops = [{
        "uid": "u1", "id": "99001", "street": "Site 99001",
        "begin_lat": 33.77, "begin_lon": -117.94,
        "end_lat": 33.771, "end_lon": -117.941,
        "lat": 33.7705, "lon": -117.9405,
        "direction": "n", "lanes": 2,
        "date": td,
    }]
    st.home = (33.7715, -117.9431)
    st.save()

    class Win:
        state = st
        current_index = 0
        txt_street = type("T", (), {"text": lambda self: "", "setText": lambda self, v: None})()
        txt_notes = type("N", (), {"toPlainText": lambda self: "", "setPlainText": lambda self, v: None})()
        combo_dir = type("C", (), {"currentText": lambda self: "n"})()
        spin_lanes = type("S", (), {"value": lambda self: 2})()
        txt_serial = type("X", (), {"text": lambda self: ""})()
        lbl_grab = type("L", (), {"setText": lambda self, v: setattr(self, "v", v), "v": ""})()
        lbl_street_warn = type("W", (), {
            "setText": lambda self, v: None, "setVisible": lambda self, v: None,
        })()
        pages = type("P", (), {"currentIndex": lambda self: 2})()
        _undo_stack: list = []

        def _internet_allowed(self):
            return False

        def _flush_install_form(self):
            pass

        def _sync_counter_fields(self, s):
            pass

        def _persist_shift(self, quiet=True):
            self.state.save()

        def _push_state(self):
            pass

        def _refresh_install_checklist(self):
            pass

        def _push_undo(self, *a, **k):
            self._undo_stack.append((a, k))

        def _counter_inventory_shift(self):
            pass

        def _refresh_route_list(self):
            pass

        def _refresh_audit(self):
            pass

        def _refresh_field_alerts(self):
            pass

        def _maybe_export_nudge(self):
            pass

        def _nav_install(self, step):
            pass

        def _schedule_pin_persist(self):
            pass

        def _flush_pin_persist(self):
            pass

        bridge = type("B", (), {"send_field_pin": lambda *a, **k: None})()

        def statusBar(self):
            return type("SB", (), {"showMessage": lambda self, *a: None})()

        def _field_notice(self, msg, *, status_ms=10000):
            pass

        def _snapshot_stop(self, s):
            return dict(s)

        def _street_label(self, s):
            return str(s.get("street", ""))

    w = Win()

    # Drop pin on map (offline field) — no counter clear, no USB GPS.
    ok_save = MainWindow._save_field_position(w, 33.7706, -117.9406, source="manual")
    s = st.stops[0]
    check("drop pin saves coords", ok_save and s.get("field_lat") == 33.7706)
    check("pending geocode offline", bool(s.get("field_geocode_pending")))

    # INSTALL without serial or counter clear must succeed.
    before_installed = s.get("installed")
    MainWindow._commit_install(w, True)
    check("install without serial/clear", s.get("installed") is True)
    check("install kept field gps", s.get("field_lat") == 33.7706)
    s["installed"] = before_installed

    # Wi-Fi geocode retry updates all pending stops, not just current.
    st.stops.append({
        "uid": "u2", "id": "99002", "street": "",
        "field_lat": 34.05, "field_lon": -118.25,
        "field_geocode_pending": True,
        "begin_lat": 34.05, "begin_lon": -118.25,
        "end_lat": 34.051, "end_lon": -118.251,
        "lat": 34.0505, "lon": -118.2505,
        "direction": "e", "lanes": 2, "date": td,
    })

    class OnlineWin(Win):
        _geocoded = 0

        def _internet_allowed(self):
            return True

        def _push_state(self):
            OnlineWin._geocoded += 1

    ow = OnlineWin()
    ow.current_index = 0

    from unittest.mock import patch

    with patch("ui.controllers.install.geo.street_from_coords", side_effect=lambda lat, lon: f"Street@{lat:.2f}"):
        MainWindow._retry_pending_field_geocode(ow)

    check("geocode both stops", not st.stops[0].get("field_geocode_pending"))
    check("geocode second stop", st.stops[1].get("street", "").startswith("Street@"))
    check("push_state after geocode", OnlineWin._geocoded >= 1)

    if FAILURES:
        print(f"\nFAILED ({len(FAILURES)})")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK  install + drop-pin user path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
