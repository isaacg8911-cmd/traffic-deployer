"""Route-pick click stress — coder + user paths (headless, no GPS).

Proves:
  - Python: dot click (uid|begin/end), map click (nearest), combo, clear/re-pick
  - JS assets: enlarged pick-targets + nearestPickAt fallback wired
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FAILURES: list[str] = []


def ok(name: str, detail: str = "") -> None:
    print(f"  OK  {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str = "") -> None:
    msg = f"{name}" + (f": {detail}" if detail else "")
    print(f"  FAIL {msg}")
    FAILURES.append(msg)


def section(title: str) -> None:
    print(f"\n[{title}]")


def test_js_assets() -> None:
    section("JS pick click assets")
    appjs = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    for needle in (
        "pickTargets.push",
        "nearestPickAt",
        "pickHitPad",
        "showPickTargets",
        "lastState.map_mode === 'pick'",
    ):
        ok(needle) if needle in appjs else fail(f"missing {needle}")


def test_python_pick_flow() -> None:
    section("Python pick flow (user clicks)")
    from PySide6.QtWidgets import QApplication, QStatusBar

    from core import ingest
    from field_job_fixtures import resolve_field_job
    from ui.controllers.map_sync import MapSyncControllerMixin
    from ui.controllers.route import RouteControllerMixin

    class PickWin(MapSyncControllerMixin, RouteControllerMixin):
        def __init__(self) -> None:
            self._route_pick_mode = False
            self._route_pick_uids: list[str] = []
            self._route_pick_sides: dict[str, str] = {}
            self._route_pick_dialog = None
            self._manual_grab_mode = False
            self._map_preview_stops: list[dict] = []
            self._pick_layout_active = False
            self._pick_splitter_saved = None
            self._map_js_ready = True
            self._gps_follow = False
            self._map_follow = False
            self.pages = type("P", (), {"currentIndex": lambda _s: 1})()
            self.statusBar = lambda: self._status
            self._status = QStatusBar()
            self._push_calls = 0

        def _push_state(self, fit: bool = False) -> None:
            _ = fit
            self._push_calls += 1

        def _go_page(self, _i: int) -> None:
            return

        def _enter_pick_map_focus(self) -> None:
            return

        def _exit_pick_map_focus(self) -> None:
            return

        def _refresh_route_list(self) -> None:
            return

        def _show_route_pick_dialog(self) -> None:
            return

        def _hide_route_pick_dialog(self) -> None:
            return

        def _end_manual_grab(self, *, silent: bool = True) -> None:
            _ = silent

    job = resolve_field_job()
    sites = ingest.parse_excel_sites([job.xls])
    cfgs = [{"path": p, "label": label} for p, label in job.ests]
    stops = ingest.match_est_files(cfgs, sites, job.home)
    if len(stops) < 2:
        fail("need >=2 stops", str(len(stops)))
        return

    app = QApplication.instance() or QApplication(sys.argv)
    win = PickWin()
    win.state = type("S", (), {})()
    win.state.stops = list(stops)
    win.state.home = job.home
    win.state.route = {"polyline": [], "miles": 0.0, "graph": False}
    win.state.map_day_filter = "All days"
    win.state.theme = "light"
    win.state.active_files = []
    win.chk_show_segments = type("C", (), {"isChecked": lambda _s: False})()

    # User: Route tab -> Pick on map
    win._begin_route_pick(list(stops))
    ok("pick mode on") if win._route_pick_mode else fail("pick mode on")

    s0 = stops[0]
    uid0 = str(s0["uid"])
    bl, blo = float(s0["begin_lat"]), float(s0["begin_lon"])

    # User: clicks blue dot — exact payload from map JS
    win._on_stop_clicked(f"{uid0}|begin")
    ok("dot click adds stop 1") if len(win._route_pick_uids) == 1 else fail(
        "dot click adds stop 1", str(win._route_pick_uids))

    # User: clicks same dot again — should not duplicate
    win._on_stop_clicked(f"{uid0}|begin")
    ok("repeat click ignored") if len(win._route_pick_uids) == 1 else fail(
        "repeat click ignored", str(len(win._route_pick_uids)))

    # User: near-miss map click on next site (~40 m off)
    s1 = stops[1]
    uid1 = str(s1["uid"])
    near_lat = float(s1["end_lat"]) + 0.00035
    near_lon = float(s1["end_lon"])
    win._on_map_clicked(near_lat, near_lon)
    ok("near-miss map click adds stop 2") if win._route_pick_uids[-1] == uid1 else fail(
        "near-miss map click", f"got {win._route_pick_uids}")

    # User: empty map click far from sites
    win._on_map_clicked(0.0, 0.0)
    ok("far click feedback") if "near that click" in win._status.currentMessage().lower() else fail(
        "far click feedback", win._status.currentMessage())

    # Coder: clear and re-pick via combo path
    win._route_pick_clear()
    ok("clear picks") if not win._route_pick_uids else fail("clear picks")

    win._on_stop_clicked(f"{uid0}|end")
    ok("end dot pick") if win._route_pick_sides.get(uid0) == "end" else fail(
        "end dot pick", str(win._route_pick_sides))

    # Bogus uid — user feedback
    win._on_stop_clicked("not-a-real-uid|begin")
    ok("bogus uid message") if "not in this job" in win._status.currentMessage().lower() else fail(
        "bogus uid message", win._status.currentMessage())

    _ = app


def test_drag_reorder_commit() -> None:
    """Drag a picked stop to the top — the applied order must follow (start-from-top)."""
    section("Drag reorder -> start from the top")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from core import ingest
    from core.map_display import apply_manual_order
    from field_job_fixtures import resolve_field_job
    from ui.paths import DATA_DIR
    from ui.route_pick_dialog import RoutePickOrderDialog

    job = resolve_field_job()
    sites = ingest.parse_excel_sites([job.xls])
    cfgs = [{"path": p, "label": label} for p, label in job.ests]
    stops = ingest.match_est_files(cfgs, sites, job.home)
    if len(stops) < 3:
        fail("need >=3 stops for reorder", str(len(stops)))
        return

    app = QApplication.instance() or QApplication(sys.argv)
    uids = [str(s["uid"]) for s in stops]
    by_uid = {str(s["uid"]): s for s in stops}

    parent_order: list[str] = list(uids)

    def on_order(new_uids: list[str]) -> None:
        parent_order[:] = list(new_uids)

    dlg = RoutePickOrderDialog()
    dlg.order_changed.connect(on_order)
    dlg.sync_from_parent(
        uids=list(uids),
        stops_by_uid=by_uid,
        letters={u: chr(65 + i) for i, u in enumerate(uids)},
        street_label=lambda s: str(s.get("street", "")),
        total=len(uids),
        prompt="",
        pick_sides={},
    )

    last = dlg.list.count() - 1
    moved_uid = dlg.list.item(last).data(Qt.ItemDataRole.UserRole)

    # Simulate the *visible* result of a drag: source removed, item re-inserted
    # at the top. QListWidget InternalMove does this without emitting rowsMoved,
    # so at this point the parent order is still stale (this is the reported bug).
    it = dlg.list.takeItem(last)
    dlg.list.insertItem(0, it)
    if parent_order[0] == moved_uid:
        fail("precondition: rowsMoved should not have fired on manual take/insert")
        return
    ok("stale before drop commit (reproduces bug)")

    # dropEvent schedules dlg.list.dropped; fire it as the deferred timer would.
    dlg.list.dropped.emit()
    app.processEvents()

    if parent_order[0] == moved_uid:
        ok("drop commit moved stop to the top", f"first={parent_order[0]}")
    else:
        fail("drop commit did not update order", f"first={parent_order[0]} want={moved_uid}")
        return

    # And the applied route must actually start at that stop.
    picked = [by_uid[u] for u in parent_order]
    res = apply_manual_order(tuple(job.home), picked, DATA_DIR)
    applied = [str(s["uid"]) for s in res["order"]]
    if applied and applied[0] == moved_uid:
        ok("applied route starts at chosen top stop", f"miles={res['route'].get('miles', 0):.1f}")
    else:
        fail("applied route wrong start", str(applied[:3]))

    # Belt-and-suspenders: even if the drop-commit signal is NEVER delivered,
    # Apply must adopt the list order. Simulate a totally missed signal.
    class _AppWin:
        def __init__(self, dialog, uids):
            self._route_pick_dialog = dialog
            self._route_pick_uids = list(uids)

    from ui.controllers.route import RouteControllerMixin as _RC

    # reorder list again (move NEW bottom to top) with NO signal at all
    stale = [str(dlg.list.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(dlg.list.count())]
    last2 = dlg.list.count() - 1
    top_uid = str(dlg.list.item(last2).data(Qt.ItemDataRole.UserRole))
    it2 = dlg.list.takeItem(last2)
    dlg.list.insertItem(0, it2)
    app_win = _AppWin(dlg, stale)  # parent still holds pre-drag order
    _RC._sync_pick_order_from_dialog(app_win)
    if app_win._route_pick_uids and app_win._route_pick_uids[0] == top_uid:
        ok("apply adopts list order even if drop signal missed")
    else:
        fail("apply did not adopt list order", str(app_win._route_pick_uids[:3]))

    _ = app


def main() -> int:
    print("ROUTE PICK CLICK STRESS\n")
    test_js_assets()
    test_python_pick_flow()
    test_drag_reorder_commit()
    print("\n" + "=" * 50)
    if FAILURES:
        for f in FAILURES:
            print(f"  - {f}")
        print("ROUTE PICK CLICK STRESS FAIL")
        return 1
    print("ROUTE PICK CLICK STRESS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
