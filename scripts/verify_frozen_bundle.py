"""Verify frozen PYZ/exe actually contains critical field UX code (not just fresh mtime)."""
from __future__ import annotations

import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DIST = os.path.join(ROOT, "dist", "TrafficDeployer")
HANDOFF_DIST = os.path.join(ROOT, "dist", "TrafficDeployer-AppUpdate", "TrafficDeployer")
PYZ_BUILD = os.path.join(ROOT, "build", "traffic_deployer", "PYZ-00.pyz")


def _resolve_paths() -> tuple[str, str]:
    """Return (bundle_dir, exe_path) — shipment handoff wins when present."""
    handoff = os.environ.get("TD_HANDOFF", "").strip()
    if handoff:
        root = handoff
    elif os.path.isfile(os.path.join(HANDOFF_DIST, "TrafficDeployer.exe")):
        root = HANDOFF_DIST
    else:
        root = os.environ.get("TD_VERIFY_ROOT", DEFAULT_DIST)
    exe = os.path.join(root, "TrafficDeployer.exe")
    return root, exe

MODULE_MARKERS: dict[str, tuple[str, ...]] = {
    "ui.route_pick_dialog": ("apply_requested", "Apply route"),
    "ui.threads": ("RouteApplyPickThread", "pick_sides", "start_ll"),
    "ui.controllers.route": (
        "_enter_pick_map_focus", "_begin_route_pick", "_route_pick_apply",
        "_merge_days_best_route",
    ),
    "ui.controllers.map_sync": (
        "_parse_stop_click", "_push_state", "_on_map_follow_toggled", "_map_follow",
        "_nearest_unpicked_stop", "_offer_merge_days",
    ),
    "ui.controllers.setup": ("_commit_home_start", "_ready_offline"),
    "ui.controllers.install": ("_commit_install", "_begin_manual_grab", "_clear_field_gps", "Tap Next"),
    "ui.controllers.counter": ("_counter_read_serial", "_counter_clear_configure"),
    "ui.pages.install_page": ("Grab GPS", "Clear GPS / pin", "INSTALL"),
    "ui.shell.field_mode": ("_sync_field_mode", "_internet_allowed"),
    "ui.web_page": ("tdstop.local", "tdmap.local", "tdnav.local"),
    "ui.shell.startup": ("_map_follow", "followToggled"),
    "bridge": ("followToggled", "onFollowToggled"),
    "core.routing": ("pick_cross_locked", "graph_covers_stops"),
    "core.setup_checklist": ("road_map_covers_job", "graph_uncovered"),
    "core.offline_gate": ("route_graph_uncovered",),
    "core.state": ("set_start_point",),
    "road_router": ("_normalize_graph_coords",),
}

# main.py is a thin mixin shell after P46 split — field UX lives in controllers/.
MAIN_ENTRY_MARKERS = (
    "MainWindow",
    "ShellStartupMixin",
    "InstallControllerMixin",
    "MapSyncControllerMixin",
    "RouteControllerMixin",
)


def _code_markers(code: types.CodeType) -> set[str]:
    found: set[str] = set()
    for const in code.co_consts:
        if isinstance(const, str):
            found.add(const)
        elif isinstance(const, types.CodeType):
            found |= _code_markers(const)
    found |= set(code.co_names)
    found |= set(code.co_varnames)
    return found


def _pyz_path() -> str | None:
    if os.path.isfile(PYZ_BUILD):
        return PYZ_BUILD
    return None


def _pyz_fresh_vs_exe(pyz: str, exe: str) -> bool:
    if not os.path.isfile(exe):
        return False
    return abs(os.path.getmtime(pyz) - os.path.getmtime(exe)) < 120.0


def _check_exe_main_markers(exe: str) -> list[str]:
    import marshal

    from PyInstaller.archive.readers import CArchiveReader

    fails: list[str] = []
    try:
        data = CArchiveReader(exe).extract("main")
        code = marshal.loads(data)
    except Exception as exc:  # noqa: BLE001
        return [f"exe main script extract failed: {exc}"]
    if not isinstance(code, types.CodeType):
        return ["exe main entry is not code object"]

    markers = _code_markers(code)
    for needle in MAIN_ENTRY_MARKERS:
        if any(needle in m for m in markers):
            print(f"  OK  exe main contains {needle!r}")
        else:
            fails.append(f"exe main missing marker {needle!r}")
    return fails


def _check_pyz_markers(pyz: str) -> list[str]:
    from PyInstaller.loader.pyimod01_archive import ZlibArchiveReader

    fails: list[str] = []
    arc = ZlibArchiveReader(pyz)
    for mod, needles in MODULE_MARKERS.items():
        try:
            code = arc.extract(mod)
        except KeyError:
            fails.append(f"PYZ missing module {mod}")
            continue
        if not isinstance(code, types.CodeType):
            fails.append(f"PYZ {mod} not a code object")
            continue
        markers = _code_markers(code)
        for needle in needles:
            if any(needle in m for m in markers):
                print(f"  OK  PYZ {mod} contains {needle!r}")
            else:
                fails.append(f"PYZ {mod} missing marker {needle!r}")
    return fails


def main() -> int:
    bundle_dir, exe = _resolve_paths()
    print(f"Frozen bundle check — {bundle_dir}\n")
    fails: list[str] = []
    if not os.path.isfile(exe):
        print(f"  FAIL  TrafficDeployer.exe missing — {exe}")
        return 1

    fails.extend(_check_exe_main_markers(exe))

    pyz = _pyz_path()
    if not pyz:
        fails.append("build/traffic_deployer/PYZ-00.pyz missing — rebuild portable first")
    else:
        if not _pyz_fresh_vs_exe(pyz, exe):
            fails.append("PYZ build artifact stale vs exe — rebuild portable")
        else:
            print(f"  OK  PYZ matches exe build ({pyz})")
        fails.extend(_check_pyz_markers(pyz))

    print()
    if fails:
        print(f"FROZEN BUNDLE FAIL ({len(fails)}) — do NOT hand off zip")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("FROZEN BUNDLE PASS — handoff build contains field UX fixes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
