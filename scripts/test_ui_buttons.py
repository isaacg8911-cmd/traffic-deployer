"""Offscreen check: field-panel buttons are not truncated at work-laptop width."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QPushButton


def _stub_window():
    from core.state import RouteState
    from ui.paths import DATA_DIR

    class W:
        state = RouteState(DATA_DIR)
        state.load()
        excel_paths = []
        est_paths = []
        gps = type("G", (), {"latest": lambda self: {}})()

        def _noop(self, *a, **k):
            return None

    w = W()
    for name in (
        "_warn", "_info", "_schedule_autosave", "_refresh_ports", "_switch_profile",
        "_save_profile_as", "_save_shift_now", "_reset_route", "_start_fresh_profile",
        "_refresh_field_ready", "_run_setup_network_test", "_origin_from_gps",
        "_save_default_home", "_load_default_home", "_origin_from_address",
        "_use_saved_home", "_origin_from_coords", "_pick_excel", "_pick_est",
        "_clear_files", "_download_basemap", "_download_roads", "_import_roads",
        "_build_route_from_uploads", "_toggle_drive",
        "_route_pick_clear", "_route_pick_apply", "_show_route_pick_dialog",
        "_start_pick_route_from_route_tab",
        "_offer_merge_days",
        "_recover_map", "_refresh_day_filter", "_grab_gps_here", "_toggle_manual_grab",
        "_confirm_manual_grab_pin", "_clear_field_gps", "_set_dir_from_compass", "_commit_install",
        "_nav_install", "_undo_last_action", "_center_current",
        "_counter_refresh_and_connect", "_counter_autoname", "_counter_clear_configure",
        "_counter_list_ports", "_counter_read_serial",
        "_on_install_dir_changed", "_refresh_install_checklist", "_push_state",
        "_on_pick_combo_chosen", "_nudge_stop", "_retrace_route_only", "_reoptimize",
        "_save_install_nav_links", "_save_pickup_nav_links", "_set_gps_port",
        "_run_smoke_test", "_show_setup_checklist", "_show_setup_wizard",
        "_route_item_clicked",
        "_install_progress_clicked",
        "_set_pick_side_mode",
        "_refresh_pickup",
        "_pickup_item_clicked",
        "_mark_pickup",
        "_nav_pickup",
        "_export_excel_quick",
    ):
        setattr(w, name, w._noop)
    return w


def _truncated_buttons(page, width: int) -> list[str]:
    page.resize(QSize(width, 800))
    page.show()
    QApplication.instance().processEvents()
    bad: list[str] = []
    for btn in page.findChildren(QPushButton):
        if not btn.isVisible() or not btn.text().strip():
            continue
        need = btn.sizeHint().width()
        have = btn.width()
        if need > have + 2:
            bad.append(f"{btn.text().strip()!r} need={need} have={have}")
    return bad


def main() -> int:
    from ui.pages.install_page import build_install_page
    from ui.pages.pickup_page import build_pickup_page
    from ui.pages.route_page import build_route_page
    from ui.pages.setup_page import build_setup_page

    app = QApplication.instance() or QApplication(sys.argv)
    w = _stub_window()
    fails: list[str] = []
    for name, builder, width in (
        ("install", build_install_page, 360),
        ("pickup", build_pickup_page, 360),
        ("route", build_route_page, 360),
        ("setup", build_setup_page, 380),
    ):
        bad = _truncated_buttons(builder(w), width)
        if bad:
            fails.append(f"{name}@{width}px: " + "; ".join(bad[:6]))
        else:
            print(f"  OK  {name} @{width}px — no truncated buttons")
        page = builder(w)
        for btn in page.findChildren(QPushButton):
            if btn.text().strip() == "Show more":
                btn.click()
                QApplication.instance().processEvents()
                break
        bad_more = _truncated_buttons(page, width)
        if bad_more:
            fails.append(f"{name} more @{width}px: " + "; ".join(bad_more[:6]))
        else:
            print(f"  OK  {name} more @{width}px — no truncated buttons")
    must_show = {
        "setup": "USB GPS",
        "route": "Follow GPS",
        "install": "INSTALL  (I)",
        "pickup": "SECURED",
    }
    pages = {
        "setup": build_setup_page(w),
        "route": build_route_page(w),
        "install": build_install_page(w),
        "pickup": build_pickup_page(w),
    }
    for name, label in must_show.items():
        texts = {
            btn.text().strip()
            for btn in pages[name].findChildren(QPushButton)
            if not btn.isHidden()
        }
        if label not in texts:
            fails.append(f"{name} missing visible primary {label!r}")
        else:
            print(f"  OK  {name} primary {label!r} visible")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        return 1
    print("UI BUTTONS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
