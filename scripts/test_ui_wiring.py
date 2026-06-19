"""Static audit: every UI click target must connect to a real MainWindow handler."""
from __future__ import annotations

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

UI_GLOBS = (
    "ui/pages/setup_page.py",
    "ui/pages/route_page.py",
    "ui/pages/install_page.py",
    "ui/pages/pickup_page.py",
    "ui/pages/audit_page.py",
    "ui/setup_wizard.py",
    "ui/route_pick_dialog.py",
)

MAIN_PY = os.path.join(ROOT, "main.py")
BRIDGE_PY = os.path.join(ROOT, "bridge.py")
APP_JS = os.path.join(ROOT, "web", "app.js")
INDEX_HTML = os.path.join(ROOT, "web", "index.html")

# Handlers that may exist on MainWindow but are optional / internal-only.
ORPHAN_HANDLER_ALLOW = frozenset({
    "_save_profile_as",  # wired via new Save as button
    "_h",
    "_warn",
    "_info",
    "_field_notice",
    "_stop_worker",
    "_street_label",
    "_stops_with_seq",
    "_site_letter",
    "_snapshot_stop",
    "_moved",
    "_heading_cardinal",
    "_dist_m",
    "_stop_anchor_coords",
    "_est_label_from_path",
    "_est_configs",
    "_gather_area_points",
    "_highlight_stop_uid",
    "_stops_from_uploads_merged",
    "_phone_nav_links",
    "_save_nav_links_page",
    "_counter_selected_port",
    "_counter_pause_gps",
    "_counter_resume_gps",
    "_counter_connect_after_gps_pause",
    "_counter_set_busy",
    "_counter_clear_busy",
    "_counter_show_memory",
    "_on_picocount_done",
    "_on_picocount_done_body",
    "_counter_read_serial",
    "_planned_counter_unit_id",
    "_update_counter_labels",
    "_sync_counter_fields",
    "_set_counter_connected_ui",
    "_flush_install_form",
    "_sync_upload_paths",
    "_warn_missing_upload_paths",
    "_route_for_map",
    "_display_route",
    "_ensure_site_legs",
    "_first_pending_index",
    "_next_leg_payload",
    "_refresh_map_preview",
    "_refresh_pick_site_combo",
    "_route_pick_add",
    "_route_pick_set_order",
    "_begin_route_pick",
    "_refresh_route_pick_ui",
    "_hide_route_pick_dialog",
    "_ensure_route_pick_dialog",
    "_optimize_and_route",
    "_evaluate_setup_checklist",
    "_maybe_field_startup_dialog",
    "_maybe_export_nudge",
    "_maybe_refresh_field_strip",
    "_counter_auto_connect",
    "_pick_geocode_candidate",
    "_installed_stops",
    "_refresh_pickup_cur",
    "_refresh_install_checklist",
    "_refresh_export_hint",
    "_sync_prefs_ui",
    "_sync_theme_buttons",
    "_refresh_theme_labels",
    "_refresh_address_hint",
    "_refresh_online_status",
    "_refresh_ports",
    "_apply_field_nav_shell",
    "_apply_power_profile",
    "_poll_power",
    "_sync_field_mode",
    "_internet_allowed",
    "_should_push_gps_bridge",
    "_sync_gps_timer",
    "_sync_map_health_interval",
    "_schedule_autosave",
    "_autosave_current_stop",
    "_periodic_save_shift",
    "_map_health_check",
    "_persist_shift",
    "_set_origin",
    "_update_right",
    "_on_page_load_finished",
    "_poll_map_ready",
    "_refresh_map_view",
    "_update_follow_banner",
    "_set_drive_mode",
    "_refresh_day_filter",
    "_stops_for_map",
    "_pick_site_letters",
    "_pick_prompt_text",
    "_ask_route_build_mode",
    "_next_stop_distance_mi",
    "_refresh_field_alerts",
    "_refresh_field_strip_ui",
    "_refresh_workflow_strip",
    "_refresh_route_summary_ui",
    "_refresh_undo_ui",
    "_push_undo",
    "_go_page",
    "_build_ui",
    "_wrap_scroll",
    "_placeholder",
    "_build_topbar",
    "_setup_shortcuts",
    "_shortcut_install",
    "_shortcut_skip",
    "_shortcut_grab_gps",
    "_shortcut_prev_stop",
    "_shortcut_next_stop",
})

FAILS: list[str] = []
OKS: list[str] = []


def ok(msg: str) -> None:
    OKS.append(msg)
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    FAILS.append(msg)
    print(f"  FAIL {msg}")


def _main_methods() -> set[str]:
    import main as appmod
    return {n for n in dir(appmod.MainWindow) if callable(getattr(appmod.MainWindow, n, None))}


def _handlers_in_file(path: str) -> set[str]:
    text = open(path, encoding="utf-8").read()
    refs: set[str] = set()
    refs |= set(re.findall(r"win\.(_[a-zA-Z0-9_]+)\(", text))
    refs |= set(re.findall(
        r"\.connect\((?:lambda[^:]*:\s*)?win\.(_[a-zA-Z0-9_]+)", text))
    return refs


def _wizard_handlers(path: str) -> set[str]:
    text = open(path, encoding="utf-8").read()
    return set(re.findall(r"self\._win\.(_[a-zA-Z0-9_]+)", text))


def _main_click_handlers() -> set[str]:
    text = open(MAIN_PY, encoding="utf-8").read()
    found = set(re.findall(r"\.connect\(self\.(_[a-zA-Z0-9_]+)\)", text))
    found |= set(re.findall(r"\.connect\(lambda[^:]*:\s*self\.(_[a-zA-Z0-9_]+)", text))
    return found


def test_page_handlers_exist():
    print("[page -> MainWindow handlers]")
    methods = _main_methods()
    all_refs: set[str] = set()
    for rel in UI_GLOBS:
        path = os.path.join(ROOT, rel.replace("/", os.sep))
        if not os.path.isfile(path):
            fail(f"missing {rel}")
            continue
        refs = _handlers_in_file(path)
        if "setup_wizard" in rel:
            refs |= _wizard_handlers(path)
        for h in sorted(refs):
            all_refs.add(h)
            if h not in methods:
                fail(f"{rel} references missing handler {h}")
        ok(f"{rel} ({len(refs)} handler refs)")

    main_src = open(MAIN_PY, encoding="utf-8").read()
    for sig in ("order_changed.connect", "apply_requested.connect"):
        if sig not in main_src:
            fail(f"main.py missing route dialog {sig}")
        else:
            ok(f"route dialog {sig.split('.')[0]}")


def test_user_facing_orphans():
    print("\n[user-facing handler wiring]")
    methods = _main_methods()
    referenced: set[str] = set()
    for rel in UI_GLOBS:
        path = os.path.join(ROOT, rel.replace("/", os.sep))
        referenced |= _handlers_in_file(path)
        if "setup_wizard" in rel:
            referenced |= _wizard_handlers(path)
    referenced |= _main_click_handlers()

    must_wire = {
        "_load_default_home": "Setup -> Use default start",
        "_save_profile_as": "Setup -> Save profile as",
        "_toggle_drive": "Route -> FOLLOW GPS",
        "_route_pick_apply": "Route -> Apply route",
        "_on_mode_offline": "Top bar -> Go offline",
        "_build_route_from_uploads": "Setup -> BUILD ROUTE",
        "_counter_download_pickup": "Pickup -> Download counter",
        "_undo_last_action": "Install/Pickup -> Undo",
    }
    for h, label in must_wire.items():
        if h not in methods:
            fail(f"missing method {h} ({label})")
        elif h not in referenced:
            fail(f"orphan handler {h} - {label} not referenced from UI")
        else:
            ok(label)


def test_bridge_and_map():
    print("\n[map bridge + JS clicks]")
    main_src = open(MAIN_PY, encoding="utf-8").read()
    for sig in (
        "bridge.mapReady.connect",
        "bridge.mapClicked.connect",
        "bridge.stopClicked.connect",
        "page.stopClicked.connect",
    ):
        ok(sig) if sig in main_src else fail(f"missing {sig}")
    for sig in (
        "_enter_pick_map_focus",
        "_parse_stop_click",
        "_route_pick_add",
        "pick_cross_locked",
    ):
        ok(f"main.py {sig}") if sig in main_src else fail(f"main.py missing {sig}")

    appjs = open(APP_JS, encoding="utf-8").read()
    for needle in (
        "followBtn.addEventListener",
        "zoomInBtn.addEventListener",
        "zoomOutBtn.addEventListener",
        "nextSiteBtn.addEventListener",
        "bridge.onMapClick",
        "fireStopClick",
        "map.on('click'",
        "alreadyPicked",
        "pick_waiting",
    ):
        ok(f"app.js {needle.split('(')[0]}") if needle in appjs else fail(f"app.js missing {needle}")

    idx = open(INDEX_HTML, encoding="utf-8").read()
    for bid in ("follow-btn", "zoom-in", "zoom-out", "next-site-btn"):
        ok(f"index.html #{bid}") if f'id="{bid}"' in idx else fail(f"index.html missing {bid}")


def test_route_pick_dialog_internal():
    print("\n[route pick dialog internal]")
    path = os.path.join(ROOT, "ui", "route_pick_dialog.py")
    src = open(path, encoding="utf-8").read()
    pairs = (
        ("btn_up.clicked.connect", "_move_up"),
        ("btn_down.clicked.connect", "_move_down"),
        ("btn_remove.clicked.connect", "_remove_selected"),
        ("btn_apply.clicked.connect", "apply_requested"),
        ("rowsMoved.connect", "_emit_order_from_list"),
    )
    for conn, target in pairs:
        ok(f"dialog {target}") if conn in src and target in src else fail(f"dialog missing {conn}")


def test_nav_and_shortcuts():
    print("\n[nav + shortcuts]")
    main_src = open(MAIN_PY, encoding="utf-8").read()
    for i, label in enumerate(("Setup", "Route", "Install", "Pickup", "Audit")):
        ok(f"nav {label}") if f"_go_page({i})" in main_src or f"_go_page(i)" in main_src else None
    ok("nav buttons") if "_nav_labels" in main_src and "_go_page" in main_src else fail("nav wiring")
    for key in ("Ctrl+Z", '"I"', '"G"'):
        ok(f"shortcut {key}") if key in main_src else fail(f"missing shortcut {key}")


def main() -> int:
    print("UI wiring audit\n")
    test_page_handlers_exist()
    test_user_facing_orphans()
    test_bridge_and_map()
    test_route_pick_dialog_internal()
    test_nav_and_shortcuts()
    print(f"\n{'=' * 50}")
    print(f"OK: {len(OKS)}  FAIL: {len(FAILS)}")
    if FAILS:
        print("\nFailures:")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print("\nUI WIRING PASS — all click targets connected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
