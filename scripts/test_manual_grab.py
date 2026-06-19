"""Manual Grab — map click saves field coords; offline pending geocode flag."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import geo


def main() -> int:
    fails = 0

    class Win:
        state = type("S", (), {"stops": [{"uid": "u1", "id": 1, "street": ""}], "save": lambda self: None})()
        current_index = 0
        txt_street = type("T", (), {"setText": lambda self, v: setattr(self, "v", v), "v": ""})()
        lbl_grab = type("L", (), {"setText": lambda self, v: None})()
        lbl_street_warn = type("W", (), {
            "setText": lambda self, v: None, "setVisible": lambda self, v: None,
        })()

        def _internet_allowed(self):
            return False

        def _flush_install_form(self):
            pass

        def _persist_shift(self, quiet=True):
            pass

        def _push_state(self):
            pass

        def _refresh_install_checklist(self):
            pass

        def statusBar(self):
            return type("B", (), {"showMessage": lambda self, *a: None})()

    from main import MainWindow

    w = Win()
    ok = MainWindow._save_field_position(w, 33.77, -117.94, source="manual")
    s = w.state.stops[0]
    if not ok or s.get("field_lat") != 33.77 or s.get("field_coord_source") != "manual":
        print("FAIL: _save_field_position manual")
        fails += 1
    elif not s.get("field_geocode_pending"):
        print("FAIL: offline manual grab should set field_geocode_pending")
        fails += 1
    else:
        print("OK: manual grab saves coords + pending geocode when offline")

    lat, lon = 34.0, -118.0
    if not geo.ca_coords_plausible(*geo.normalize_ca_coords(lat, lon)):
        print("FAIL: ca_coords_plausible")
        fails += 1
    else:
        print("OK: CA coord normalize")

    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
