"""Verify frozen PYZ/exe actually contains critical field UX code (not just fresh mtime)."""
from __future__ import annotations

import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist", "TrafficDeployer")
EXE = os.path.join(DIST, "TrafficDeployer.exe")
PYZ_BUILD = os.path.join(ROOT, "build", "traffic_deployer", "PYZ-00.pyz")

MODULE_MARKERS: dict[str, tuple[str, ...]] = {
    "ui.route_pick_dialog": ("apply_requested", "Apply route"),
    "ui.threads": ("RouteApplyPickThread", "pick_sides"),
    "ui.controllers.route": ("_enter_pick_map_focus", "_begin_route_pick", "_route_pick_apply"),
    "ui.controllers.map_sync": ("_parse_stop_click", "_push_state"),
    "ui.controllers.setup": ("_commit_home_start", "_ready_offline"),
    "ui.controllers.install": ("_commit_install", "_begin_manual_grab"),
    "ui.shell.field_mode": ("_sync_field_mode", "_internet_allowed"),
    "core.routing": ("pick_cross_locked",),
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
    return found


def _pyz_path() -> str | None:
    if os.path.isfile(PYZ_BUILD):
        return PYZ_BUILD
    return None


def _pyz_fresh_vs_exe(pyz: str) -> bool:
    if not os.path.isfile(EXE):
        return False
    return abs(os.path.getmtime(pyz) - os.path.getmtime(EXE)) < 120.0


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
    fails: list[str] = []
    if not os.path.isfile(EXE):
        print("  FAIL  TrafficDeployer.exe missing — run BUILD_WORK_LAPTOP.bat")
        return 1

    fails.extend(_check_exe_main_markers(EXE))

    pyz = _pyz_path()
    if not pyz:
        fails.append("build/traffic_deployer/PYZ-00.pyz missing — rebuild portable first")
    else:
        if not _pyz_fresh_vs_exe(pyz):
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
