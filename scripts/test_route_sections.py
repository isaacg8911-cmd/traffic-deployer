"""Two .EST maps → two independent route sections (pick/apply/cycle)."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FAILURES: list[str] = []


def ok(name: str, detail: str = "") -> None:
    print(f"  OK  {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str = "") -> None:
    msg = f"{name}" + (f": {detail}" if detail else "")
    print(f"  FAIL {msg}")
    FAILURES.append(msg)


def _stop(sheet: str, sid: str, lat: float, lon: float) -> dict:
    from core.ingest import new_stop

    return new_stop(sid, sheet, {
        "street": f"{sheet} {sid}",
        "begin_lat": lat,
        "begin_lon": lon,
        "end_lat": lat + 0.001,
        "end_lon": lon + 0.001,
        "lat": lat,
        "lon": lon,
    })


def test_core_helpers() -> None:
    print("\n[core.route_sections]")
    from core import route_sections

    a = [_stop("Day5", "100", 34.0, -118.0), _stop("Day5", "101", 34.01, -118.01)]
    b = [_stop("Day6", "200", 34.2, -117.3), _stop("Day6", "201", 34.21, -117.31)]
    all_stops = a + b

    labels = route_sections.section_labels(all_stops, ["Day5", "Day6"])
    if labels == ["Day5", "Day6"]:
        ok("section labels", str(labels))
    else:
        fail("section labels", str(labels))

    if route_sections.multi_section(all_stops, ["Day5", "Day6"]):
        ok("multi_section")
    else:
        fail("multi_section")

    if route_sections.stops_for_section(all_stops, "Day6") == b:
        ok("stops_for_section Day6")
    else:
        fail("stops_for_section Day6")

    new_b = list(reversed(b))
    merged = route_sections.merge_section_order(all_stops, new_b)
    sheets = [s["sheet"] for s in merged]
    b_ids = [s["id"] for s in merged if s["sheet"] == "Day6"]
    a_ids = [s["id"] for s in merged if s["sheet"] == "Day5"]
    if a_ids == ["100", "101"] and b_ids == ["201", "200"] and sheets[:2] == ["Day5", "Day5"]:
        ok("merge_section_order keeps other map")
    else:
        fail("merge_section_order", f"ids a={a_ids} b={b_ids} sheets={sheets}")

    composed = route_sections.compose_section_routes(
        {
            "Day5": {"polyline": [[1.0, 2.0], [1.1, 2.1]], "miles": 3.0, "graph": True},
            "Day6": {"polyline": [[9.0, 8.0], [9.1, 8.1]], "miles": 4.5, "graph": True},
        },
        ["Day5", "Day6"],
    )
    if (
        abs(composed["miles"] - 7.5) < 0.01
        and len(composed.get("polylines") or []) == 2
        and composed.get("polyline") == []
    ):
        ok("compose_section_routes All days overlay")
    else:
        fail("compose_section_routes", str(composed))

    fresh = [
        _stop("Day5", "100", 34.0, -118.0),
        _stop("Day5", "101", 34.01, -118.01),
        _stop("Day6", "200", 34.2, -117.3),
        _stop("Day6", "201", 34.21, -117.31),
    ]
    old = a + list(reversed(b))
    preserved = route_sections.preserve_other_section_orders(
        old, fresh, rebuild_sheet="Day5")
    p6 = [s["id"] for s in preserved if s["sheet"] == "Day6"]
    if p6 == ["201", "200"]:
        ok("preserve_other_section_orders")
    else:
        fail("preserve_other_section_orders", str(p6))

    if route_sections.cycle_label(["Day5", "Day6"], "Day5", 1) == "Day6":
        ok("cycle Day5 -> Day6")
    else:
        fail("cycle")
    if route_sections.cycle_label(["Day5", "Day6"], "All days", 1) == "Day5":
        ok("cycle from All days")
    else:
        fail("cycle from All days")


def test_days_merged_view() -> None:
    print("\n[merge days = one best route]")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QStatusBar

    from ui.controllers.map_sync import MapSyncControllerMixin
    from ui.controllers.route import RouteControllerMixin
    from ui.map_helpers import display_route_for_map

    class Win(MapSyncControllerMixin, RouteControllerMixin):
        def __init__(self) -> None:
            self._route_pick_mode = False
            self._route_pick_uids = []
            self._route_pick_sides = {}
            self._route_pick_by_map = {}
            self._route_pick_dialog = None
            self._manual_grab_mode = False
            self._map_preview_stops = []
            self._map_js_ready = False
            self._gps_follow = False
            self._map_follow = False
            self._day_filter_prev = "All days"
            self.current_index = 0
            self.chk_show_segments = type("C", (), {"isChecked": lambda _s: False})()
            self.statusBar = lambda: self._status
            self._status = QStatusBar()
            a = [_stop("Day5", "100", 34.0, -118.0), _stop("Day5", "101", 34.01, -118.01)]
            b = [_stop("Day6", "200", 34.2, -117.3), _stop("Day6", "201", 34.21, -117.31)]
            self.state = type("S", (), {})()
            self.state.stops = a + b
            self.state.active_files = ["Day5", "Day6"]
            self.state.map_day_filter = "All days"
            self.state.days_merged = False
            self.state.merged_route = None
            self.state.routes_by_map = {
                "Day5": {"polyline": [[1.0, 2.0]], "miles": 3.0, "graph": True},
                "Day6": {"polyline": [[9.0, 8.0]], "miles": 4.5, "graph": True},
            }
            self.state.route = {"polyline": [], "miles": 0.0, "graph": False}
            self.state.home = (33.77, -117.94)

        def _persist_shift(self, *, quiet: bool = True):
            _ = quiet

    _ = QApplication.instance() or QApplication(sys.argv)
    win = Win()
    win._apply_section_route_to_state()
    composed = win._composed_all_days_route()
    if not win._days_merged_active() and len(composed.get("polylines") or []) == 2:
        ok("separate days overlay before merge")
    else:
        fail("separate days overlay", str(composed))

    merged = {
        "polyline": [[34.0, -118.0], [34.2, -117.3], [34.01, -118.01]],
        "miles": 12.4,
        "graph": True,
        "legs": [],
    }
    win.state.days_merged = True
    win.state.merged_route = merged
    win._apply_section_route_to_state()
    shown = win._display_route()
    if (
        win._days_merged_active()
        and abs(float(win.state.route.get("miles") or 0) - 12.4) < 0.01
        and abs(float(shown.get("miles") or 0) - 12.4) < 0.01
    ):
        ok("merged All days uses one best route")
    else:
        fail(
            "merged All days",
            f"mi={win.state.route.get('miles')} shown={shown.get('miles')}",
        )
    _ = display_route_for_map


def test_pick_scoped_to_one_map() -> None:
    print("\n[pick scoped to one map]")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QStatusBar

    from ui.controllers.map_sync import MapSyncControllerMixin
    from ui.controllers.route import RouteControllerMixin

    class Win(MapSyncControllerMixin, RouteControllerMixin):
        def __init__(self) -> None:
            self._route_pick_mode = False
            self._route_pick_uids: list[str] = []
            self._route_pick_sides: dict[str, str] = {}
            self._route_pick_by_map: dict[str, dict] = {}
            self._route_pick_dialog = None
            self._manual_grab_mode = False
            self._map_preview_stops: list[dict] = []
            self._pick_layout_active = False
            self._pick_splitter_saved = None
            self._map_js_ready = True
            self._gps_follow = False
            self._map_follow = False
            self.bridge = type("B", (), {"fly_to": lambda *_a, **_k: None})()
            self.pages = type("P", (), {"currentIndex": lambda _s: 1})()
            self.statusBar = lambda: self._status
            self._status = QStatusBar()

        def _push_state(self, fit: bool = False) -> None:
            _ = fit

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

        def _refresh_route_pick_ui(self, *, sync_dialog: bool = True) -> None:
            _ = sync_dialog

    a = [_stop("Day5", "100", 34.0, -118.0), _stop("Day5", "101", 34.01, -118.01)]
    b = [_stop("Day6", "200", 34.2, -117.3), _stop("Day6", "201", 34.21, -117.31)]
    all_stops = a + b

    app = QApplication.instance() or QApplication(sys.argv)
    win = Win()
    win.state = type("S", (), {})()
    win.state.stops = list(all_stops)
    win.state.home = (34.0, -118.0)
    win.state.route = {"polyline": [], "miles": 0.0, "graph": False}
    win.state.routes_by_map = {}
    win.state.map_day_filter = "All days"
    win.state.active_files = ["Day5", "Day6"]
    win.state.theme = "light"
    win.state.index_of = lambda uid, _stops=win.state.stops: next(
        (i for i, s in enumerate(_stops) if str(s.get("uid") or "") == str(uid)), -1)
    win.chk_show_segments = type("C", (), {"isChecked": lambda _s: False})()

    win._begin_route_pick(list(all_stops))
    if win._route_pick_mode and win._day_filter_value() == "Day5":
        ok("BUILD focuses first map")
    else:
        fail("BUILD focuses first map", win._day_filter_value())

    if win._pick_pool_total() == 2:
        ok("pick pool is Day5 only", str(win._pick_pool_total()))
    else:
        fail("pick pool is Day5 only", str(win._pick_pool_total()))

    win._route_pick_add(a[0]["uid"], side="begin")
    win._route_pick_add(b[0]["uid"], side="begin")
    if win._route_pick_uids == [a[0]["uid"]]:
        ok("other-map click rejected")
    else:
        fail("other-map click rejected", str(win._route_pick_uids))

    win._stash_route_section("Day5")
    win.state.routes_by_map["Day6"] = {
        "polyline": [[34.2, -117.3], [34.21, -117.31]],
        "miles": 4.2,
        "graph": True,
    }
    win._set_route_section("Day6", persist=False)
    if win._route_pick_uids == [] and float(win.state.route.get("miles") or 0) == 4.2:
        ok("cycle to Day6 keeps Day6 route, not Day5 picks")
    else:
        fail(
            "cycle to Day6",
            f"uids={win._route_pick_uids} mi={win.state.route.get('miles')}",
        )
    if not win._section_pick_active():
        ok("applied Day6 is view-only while Day5 still picking")
    else:
        fail("applied Day6 is view-only")

    day5_uids = (win._ensure_pick_by_map().get("Day5") or {}).get("uids")
    if day5_uids == [a[0]["uid"]]:
        ok("Day5 pick stash survived cycle")
    else:
        fail("Day5 pick stash", str(day5_uids))

    win._set_route_section("Day5", persist=False)
    if win._route_pick_uids == [a[0]["uid"]]:
        ok("cycle back restores Day5 picks")
    else:
        fail("cycle back", str(win._route_pick_uids))

    from core import route_sections
    applied_b = list(reversed(b))
    merged = route_sections.merge_section_order(list(all_stops), applied_b)
    win.state.stops = merged
    win.state.routes_by_map["Day6"] = {"polyline": [[1, 2]], "miles": 9.0, "graph": True}
    rebuilt_a = list(reversed(a))
    win.state.stops = route_sections.preserve_other_section_orders(
        win.state.stops, a + b, rebuild_sheet="Day5")
    win.state.stops = route_sections.merge_section_order(win.state.stops, rebuilt_a)
    b_ids = [s["id"] for s in win.state.stops if s["sheet"] == "Day6"]
    a_ids = [s["id"] for s in win.state.stops if s["sheet"] == "Day5"]
    if a_ids == ["101", "100"] and b_ids == ["201", "200"] and win.state.routes_by_map["Day6"]["miles"] == 9.0:
        ok("rebuild Day5 does not rewrite Day6 order/route")
    else:
        fail("rebuild isolation", f"a={a_ids} b={b_ids} routes={win.state.routes_by_map}")

    _ = app


def main() -> int:
    print("ROUTE SECTIONS — two maps, two independent builds\n")
    test_core_helpers()
    test_days_merged_view()
    test_pick_scoped_to_one_map()
    print()
    if FAILURES:
        print(f"FAIL ({len(FAILURES)})")
        for item in FAILURES:
            print(f"  - {item}")
        return 1
    print("ROUTE SECTIONS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
