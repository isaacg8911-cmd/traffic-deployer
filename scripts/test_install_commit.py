"""INSTALL must save current site only — never auto-advance index."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    fails = 0

    class Win:
        state = type("S", (), {
            "stops": [
                {"uid": "a", "id": 1, "street": "", "installed": False, "skipped": False},
                {"uid": "b", "id": 2, "street": "", "installed": False, "skipped": False},
            ],
            "progress_install": lambda self: (0, 2),
            "save": lambda self: True,
        })()
        current_index = 0
        pages = type("P", (), {"currentIndex": lambda self: 2})()
        _undo_stack = []
        _export_nudge_shown = False
        _manual_grab_mode = False

        txt_street = type("T", (), {"text": lambda self: "Main St", "setText": lambda *a: None})()
        combo_dir = type("C", (), {"currentText": lambda self: "n"})()
        spin_lanes = type("S", (), {"value": lambda self: 2})()
        txt_serial = type("TS", (), {"text": lambda self: "123", "strip": lambda self: "123"})()
        txt_notes = type("N", (), {"toPlainText": lambda self: ""})()
        lbl_grab = type("L", (), {"setText": lambda *a: None})()
        lbl_street_warn = type("W", (), {"setText": lambda *a: None, "setVisible": lambda *a: None})()
        lbl_install_checklist = type("LC", (), {
            "setText": lambda *a: None,
            "setProperty": lambda *a: None,
            "style": lambda self: type("ST", (), {
                "unpolish": lambda *a: None, "polish": lambda *a: None,
            })(),
        })()
        bridge = type("B", (), {
            "clear_field_pin": lambda *a: None,
            "send_field_pin": lambda *a, **k: None,
        })()

        def _flush_install_form(self):
            pass

        def _sync_counter_fields(self, s):
            pass

        def _push_undo(self, *a, **k):
            pass

        def _persist_shift(self, quiet=True):
            pass

        def _counter_inventory_shift(self):
            pass

        def _update_live_shift_excel(self):
            pass

        def _push_state(self, fit=False):
            pass

        def _refresh_route_list(self):
            pass

        def _refresh_audit(self):
            pass

        def _refresh_field_alerts(self):
            pass

        def _maybe_export_nudge(self):
            pass

        def _refresh_install(self):
            pass

        def _refresh_install_progress_list(self):
            pass

        def _snapshot_stop(self, s):
            return dict(s)

        def _street_label(self, s):
            return str(s.get("street") or f"Site {s.get('id')}")

        def _visible_stop_indices(self):
            return [0, 1]

        def statusBar(self):
            return type("SB", (), {"showMessage": lambda *a: None})()

        def _warn(self, msg):
            pass

    from main import MainWindow

    w = Win()
    # Stub is not a MainWindow subclass — bind mixin body used by _commit_install.
    w._commit_install_body = lambda installed: MainWindow._commit_install_body(w, installed)
    w._current_uid = lambda: MainWindow._current_uid(w)
    before = w.current_index
    MainWindow._commit_install(w, True)
    if w.current_index != before:
        print(f"FAIL: INSTALL advanced index {before} -> {w.current_index}")
        fails += 1
    elif not w.state.stops[0].get("installed"):
        print("FAIL: INSTALL did not mark site installed")
        fails += 1
    elif w.state.stops[1].get("installed") or w.state.stops[1].get("skipped"):
        print("FAIL: INSTALL touched wrong site")
        fails += 1
    else:
        print("OK: INSTALL saves current site only, no auto-advance")

    from ui.controllers.shortcuts import ShortcutsControllerMixin
    import inspect

    src = inspect.getsource(ShortcutsControllerMixin._shortcut_install)
    if "_shortcut_blocked_by_form" not in src:
        print("FAIL: install shortcut missing form guard")
        fails += 1
    else:
        print("OK: install shortcut form guard wired")

    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
