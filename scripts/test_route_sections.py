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

    # Merged order reverses Day5 (101 then 100) and keeps Day6 (200 then 201).
    ordered = [win.state.stops[1], win.state.stops[2], win.state.stops[0], win.state.stops[3]]
    win._commit_merged_day_routes(
        ordered,
        {"polyline": [[34.0, -118.0], [34.2, -117.3]], "miles": 20.0, "graph": True},
        {
            "Day5": {
                "polyline": [[34.01, -118.01], [34.0, -118.0]],
                "miles": 8.0,
                "graph": True,
                "ids": ["101", "100"],
            },
            "Day6": {
                "polyline": [[34.2, -117.3], [34.21, -117.31]],
                "miles": 9.0,
                "graph": True,
                "ids": ["200", "201"],
            },
        },
    )
    win._set_route_section("Day5", persist=False)
    day5_ids = [s["id"] for s in win._stops_matching_day_filter()]
    if day5_ids == ["101", "100"] and abs(float(win.state.route.get("miles") or 0) - 8.0) < 0.01:
        ok("Day5 route matches the merged visit order")
    else:
        fail(
            "Day5 route matches the merged visit order",
            f"ids={day5_ids} miles={win.state.route.get('miles')}",
        )
    win._set_route_section("Day6", persist=False)
    if abs(float(win.state.route.get("miles") or 0) - 9.0) < 0.01:
        ok("Day6 route replaced, not the pre-merge line")
    else:
        fail("Day6 route replaced", f"miles={win.state.route.get('miles')}")
    win._set_route_section("All days", persist=False)
    if abs(float(win.state.route.get("miles") or 0) - 20.0) < 0.01:
        ok("Together still shows the merged route")
    else:
        fail("Together still shows the merged route", f"miles={win.state.route.get('miles')}")

    # A day the merge did not trace must not keep its old line, even under an alias key.
    win.state.active_files = ["Week 27 Day 1 Isaac", "Week 27 Day 2 Isaac"]
    win.state.routes_by_map = {
        "Day 1": {"polyline": [[1.0, 2.0]], "miles": 3.0, "graph": True},
        "Week 27 Day 2 Isaac": {"polyline": [[9.0, 8.0]], "miles": 4.5, "graph": True},
    }
    win.state.stops = [
        _stop("Week 27 Day 1 Isaac", "100", 34.0, -118.0),
        _stop("Week 27 Day 1 Isaac", "101", 34.01, -118.01),
        _stop("Week 27 Day 2 Isaac", "200", 34.2, -117.3),
        _stop("Week 27 Day 2 Isaac", "201", 34.21, -117.31),
    ]
    win._commit_merged_day_routes(
        list(win.state.stops),
        {"polyline": [[1, 2]], "miles": 11.0, "graph": False},
        {"Day 1": {"polyline": [[34.0, -118.0]], "miles": 1.5, "graph": False}},
    )
    win._set_route_section("Day 2", persist=False)
    stale = float(win.state.route.get("miles") or 0)
    alias_left = "Week 27 Day 2 Isaac" in win.state.routes_by_map
    if abs(stale) < 0.01 and not (win.state.route.get("polyline") or []) and not alias_left:
        ok("untraced day drops the pre-merge route")
    else:
        fail(
            "untraced day drops the pre-merge route",
            f"miles={stale} alias={alias_left} route={win.state.route}",
        )
    if abs(float((win.state.routes_by_map.get("Day 1") or {}).get("miles") or 0) - 1.5) < 0.01:
        ok("traced day keeps the new route")
    else:
        fail("traced day keeps the new route", str(win.state.routes_by_map.get("Day 1")))


def test_build_routes_by_section() -> None:
    print("\n[each day route from merged order]")
    from core import routing

    a = [_stop("Day5", "100", 34.0, -118.0), _stop("Day5", "101", 34.01, -118.01)]
    b = [_stop("Day6", "200", 34.2, -117.3), _stop("Day6", "201", 34.21, -117.31)]
    ordered = [a[1], b[0], a[0], b[1]]
    real = routing.build_route

    def fake(stops, home, data_dir, abort=None):
        _ = (home, data_dir, abort)
        ids = [s["id"] for s in stops]
        if ids == ["200", "201"]:
            raise RuntimeError("day trace failed")
        return {
            "polyline": [[s["lat"], s["lon"]] for s in stops],
            "miles": 8.0,
            "graph": False,
            "ids": ids,
        }

    routing.build_route = fake
    try:
        built = routing.build_routes_by_section(ordered, (34.0, -118.0), "")
    finally:
        routing.build_route = real
    day5 = built.get("Day5") or {}
    day6 = built.get("Day6") or {}
    if day5.get("ids") == ["101", "100"] and abs(float(day5.get("miles") or 0) - 8.0) < 0.01:
        ok("section route follows merged Day5 order")
    else:
        fail("section route follows merged Day5 order", str(day5))
    if not (day6.get("polyline") or []) and float(day6.get("miles") or 0) == 0.0:
        ok("failed day trace is empty, not the old route")
    else:
        fail("failed day trace is empty", str(day6))

    calls = {"n": 0}

    def counting(stops, home, data_dir, abort=None):
        _ = (stops, home, data_dir, abort)
        calls["n"] += 1
        return {"polyline": [[1, 2]], "miles": float(calls["n"]), "graph": False}

    routing.build_route = counting
    try:
        partial = routing.build_routes_by_section(
            ordered, (34.0, -118.0), "", abort=lambda: calls["n"] >= 1)
    finally:
        routing.build_route = real
    if list(partial) == ["Day5"] and calls["n"] == 1:
        ok("abort keeps only days finished before the stop")
    else:
        fail("abort keeps only days finished before the stop", f"{list(partial)} n={calls['n']}")

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from ui.threads import RouteOptimizeThread

    _ = QApplication.instance() or QApplication(sys.argv)
    thread = RouteOptimizeThread([], (34.0, -118.0), "", refresh_sections=True)
    if thread.refresh_sections and callable(thread.start):
        ok("merge worker can refresh each day without shadowing start")
    else:
        fail("merge worker refresh", f"flag={thread.refresh_sections} start={thread.start}")


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

    # A finished line used to eat the first site click: status changed, order did not.
    win._route_pick_uids = []
    win._route_pick_sides = {}
    win.state.routes_by_map["Day5"] = {
        "polyline": [[34.0, -118.0], [34.01, -118.01]],
        "miles": 3.0,
        "graph": True,
    }
    win.state.route = dict(win.state.routes_by_map["Day5"])
    if win._section_pick_active():
        fail("stored route should block pick-active before the click")
    else:
        ok("stored route looks applied before click")
    win._on_stop_clicked(f"{a[0]['uid']}|begin")
    cleared = not (win._ensure_routes_by_map().get("Day5") or {}).get("miles")
    if win._route_pick_uids == [a[0]["uid"]] and cleared:
        ok("first site click starts the order")
    else:
        fail(
            "first site click starts the order",
            f"uids={win._route_pick_uids} miles={win.state.routes_by_map.get('Day5')}",
        )

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


def _site(sid: str, sheet: str, lat: float, lon: float) -> dict:
    return {
        "begin_lat": lat, "begin_lon": lon,
        "end_lat": lat + 0.001, "end_lon": lon + 0.001,
        "lat": lat, "lon": lon,
        "street": sid,
        "excel_sheet": sheet,
    }


def test_excel_day_not_only_together() -> None:
    print("\n[Day 1 and Day 2 are separate; Together is both]")
    import tempfile
    from pathlib import Path

    from core import ingest, route_sections

    sec, src = route_sections.section_for_site(
        excel_sheet="Week 27 Day 2 Isaac",
        est_label="Map 1",
        est_index=0,
        est_count=2,
    )
    if sec == "Day 2" and src == "excel":
        ok("excel sheet names the day, not Map 1")
    else:
        fail("excel sheet names the day", f"{sec} {src}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        map1 = root / "Map 1.est"
        map2 = root / "Map 2.est"
        # Both files mention both ids — still one stop per site, day from Excel.
        map1.write_text("pins 4001 and 10001", encoding="latin-1")
        map2.write_text("pins 4001 and 10001", encoding="latin-1")
        sites = {
            "4001": _site("4001", "Week 27 Day 1 Isaac", 34.0, -118.0),
            "10001": _site("10001", "Week 27 Day 2 Isaac", 34.2, -117.3),
        }
        stops = ingest.match_est_files(
            [
                {"path": str(map1), "label": "Map 1"},
                {"path": str(map2), "label": "Map 2"},
            ],
            sites,
            (34.0, -118.0),
        )
    sheets = {s["id"]: s["sheet"] for s in stops}
    if sheets == {"4001": "Day 1", "10001": "Day 2"} and len(stops) == 2:
        ok("one stop per site, Excel day", str(sheets))
    else:
        fail("one stop per site, Excel day", str(sheets))
    labels = route_sections.section_labels(stops, ["Map 1", "Map 2"])
    if labels == ["Day 1", "Day 2"]:
        ok("filenames with no sites are not extra days", str(labels))
    else:
        fail("filenames with no sites are not extra days", str(labels))
    d1 = [s["id"] for s in route_sections.stops_for_section(stops, "Day 1")]
    d2 = [s["id"] for s in route_sections.stops_for_section(stops, "Week 27 Day 2 Isaac")]
    both = route_sections.stops_for_section(stops, "Together")
    if d1 == ["4001"] and d2 == ["10001"] and len(both) == 2:
        ok("Day 1, Day 2, and Together each return the right sites")
    else:
        fail("day filters", f"d1={d1} d2={d2} both={len(both)}")

    from ui.controllers.map_sync import MapSyncControllerMixin

    class Win(MapSyncControllerMixin):
        pass

    win = Win()
    win.state = type("S", (), {})()
    win.state.stops = [
        _stop("Week 27 Day 1 Isaac", "4001", 34.0, -118.0),
        _stop("Week 27 Day 2 Isaac", "10001", 34.2, -117.3),
    ]
    win.state.active_files = ["Map 1", "Map 2"]
    win.state.map_day_filter = "Day 1"
    shown = [s["id"] for s in win._stops_matching_day_filter()]
    win.state.map_day_filter = "Together"
    together = [s["id"] for s in win._stops_matching_day_filter()]
    if shown == ["4001"] and together == ["4001", "10001"]:
        ok("map filter: Day 1 alone, Together is both")
    else:
        fail("map filter", f"day1={shown} together={together}")
    if win._route_section_labels() == ["Day 1", "Day 2"]:
        ok("switcher labels are Day 1 and Day 2")
    else:
        fail("switcher labels", str(win._route_section_labels()))

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QWidget

    from ui.controllers.route import RouteControllerMixin

    class PickWin(MapSyncControllerMixin, RouteControllerMixin):
        def __init__(self) -> None:
            self._route_pick_mode = False
            self._route_pick_uids = []
            self._route_pick_sides = {}
            self._route_pick_by_map = {}
            self._route_pick_dialog = None
            self._manual_grab_mode = False
            self._map_preview_stops = []
            self._pick_layout_active = False
            self._map_js_ready = False
            self._gps_follow = False
            self._map_follow = False
            self._day_filter_prev = "All days"
            self.current_index = 0
            self.pickup_index = 0
            self.pages = type("P", (), {"currentIndex": lambda _s: 1})()
            self.chk_show_segments = type("C", (), {"isChecked": lambda _s: False})()
            self._day_btn_host = QWidget()
            self._day_btn_lay = QHBoxLayout(self._day_btn_host)
            self.combo_day = QComboBox()
            self.combo_day.currentTextChanged.connect(self._on_day_filter_changed)
            self.state = type("S", (), {})()
            self.state.stops = [
                _stop("Week 27 Day 1 Isaac", "4001", 34.0, -118.0),
                _stop("Week 27 Day 2 Isaac", "10001", 34.2, -117.3),
            ]
            self.state.active_files = ["Map 1", "Map 2"]
            self.state.map_day_filter = "All days"
            self.state.routes_by_map = {}
            self.state.route = {"polyline": [], "miles": 0.0, "graph": False}
            self.state.days_merged = False
            self.state.merged_route = None
            self.state.home = (34.0, -118.0)
            self.state.theme = "light"
            self.state.index_of = lambda uid: next(
                (i for i, s in enumerate(self.state.stops) if s.get("uid") == uid), -1)

        def _push_state(self, fit: bool = False) -> None:
            _ = fit

        def _refresh_route_list(self) -> None:
            return

        def _refresh_route_pick_ui(self, *, sync_dialog: bool = True) -> None:
            _ = sync_dialog

        def _go_page(self, _i: int) -> None:
            return

        def _enter_pick_map_focus(self) -> None:
            return

        def _exit_pick_map_focus(self) -> None:
            return

        def _end_manual_grab(self, *, silent: bool = True) -> None:
            _ = silent

        def _hide_route_pick_dialog(self) -> None:
            return

        def _leave_install_site(self) -> None:
            return

        def _installed_stops(self):
            return []

        def statusBar(self):
            return type("B", (), {"showMessage": lambda *_a, **_k: None})()

    _ = QApplication.instance() or QApplication(sys.argv)
    pick = PickWin()
    pick._refresh_day_filter()
    from PySide6.QtWidgets import QPushButton
    captions = [b.text() for b in pick._day_btn_host.findChildren(QPushButton)]
    if captions == ["Day 1", "Day 2", "Together"]:
        ok("buttons are Day 1, Day 2, Together", str(captions))
    else:
        fail("buttons are Day 1, Day 2, Together", str(captions))
    pick._select_day_button("Day 1")
    pick._begin_route_pick(list(pick.state.stops))
    if pick._route_pick_mode and pick._day_filter_value() == "Day 1" and pick._pick_pool_total() == 1:
        ok("Build route starts on Day 1, one day's sites")
    else:
        fail(
            "Build route starts on Day 1",
            f"mode={pick._route_pick_mode} day={pick._day_filter_value()} n={pick._pick_pool_total()}",
        )
    pick._on_stop_clicked(f"{pick.state.stops[0]['uid']}|begin")
    if pick._route_pick_uids == [pick.state.stops[0]["uid"]]:
        ok("Day 1 site click starts the order")
    else:
        fail("Day 1 site click starts the order", str(pick._route_pick_uids))
    pick._select_day_button("Day 2")
    day2 = [s["id"] for s in pick._stops_matching_day_filter()]
    if pick._day_filter_value() == "Day 2" and day2 == ["10001"] and pick._route_pick_mode:
        ok("Day 2 shows only its sites and stays clickable")
    else:
        fail(
            "Day 2 shows only its sites",
            f"day={pick._day_filter_value()} ids={day2} pick={pick._route_pick_mode}",
        )
    pick._on_stop_clicked(f"{pick.state.stops[1]['uid']}|end")
    if pick._route_pick_uids == [pick.state.stops[1]["uid"]]:
        ok("Day 2 site click starts that day's order")
    else:
        fail("Day 2 site click starts that day's order", str(pick._route_pick_uids))
    day2_uid = pick.state.stops[1]["uid"]
    pick._select_day_button("Together")
    both_ids = [s["id"] for s in pick._stops_matching_day_filter()]
    if pick._day_filter_value() == "All days" and both_ids == ["4001", "10001"]:
        ok("Together shows both days")
    else:
        fail("Together shows both days", f"day={pick._day_filter_value()} ids={both_ids}")
    if pick._route_pick_uids == [day2_uid] and pick._pick_apply_section() == "Day 2":
        ok("Together keeps Day 2 picks")
    else:
        fail(
            "Together keeps Day 2 picks",
            f"uids={pick._route_pick_uids} section={pick._pick_apply_section()}",
        )
    if pick._pick_pool_total() == 1:
        ok("Together pick pool stays the day being picked")
    else:
        fail("Together pick pool stays the day being picked", str(pick._pick_pool_total()))
    pick._pick_build_queue = ["Day 1", "Day 2"]
    pick._continue_pick_or_merge(pick._pick_apply_section())
    if pick._pick_build_queue == ["Day 1"]:
        ok("Apply from Together advances the queue")
    else:
        fail("Apply from Together advances the queue", str(pick._pick_build_queue))
    stashed = (pick._ensure_pick_by_map().get("Day 2") or {}).get("uids")
    if stashed == [day2_uid]:
        ok("Day 2 picks survive leaving Together")
    else:
        fail("Day 2 picks survive leaving Together", str(stashed))

    d1a = pick.state.stops[0]
    d2a = pick.state.stops[1]
    d1b = _stop("Week 27 Day 1 Isaac", "4002", 34.01, -118.01)
    d2b = _stop("Week 27 Day 2 Isaac", "10002", 34.21, -117.31)
    pick.state.stops = [d2b, d2a, d1b, d1a]
    pick.state.routes_by_map["Day 2"] = {"polyline": [[1, 2]], "miles": 4.0, "graph": True}
    pick._stops_from_uploads_merged = lambda: [d1a, d1b, d2a, d2b]
    pick._select_day_button("Day 1")
    pick._reoptimize()
    day2_ids = [
        s["id"] for s in pick.state.stops
        if route_sections.canonical_section(s.get("sheet")) == "Day 2"
    ]
    day1_ids = [
        s["id"] for s in pick.state.stops
        if route_sections.canonical_section(s.get("sheet")) == "Day 1"
    ]
    day2_route = (pick.state.routes_by_map.get("Day 2") or {}).get("miles")
    if day2_ids == ["10002", "10001"] and day1_ids == ["4001", "4002"] and day2_route == 4.0:
        ok("Pick order on Day 1 keeps Day 2 visit order")
    else:
        fail(
            "Pick order on Day 1 keeps Day 2 visit order",
            f"day1={day1_ids} day2={day2_ids} miles={day2_route}",
        )


def test_day_filter_drive_time() -> None:
    print("\n[day filter drive times use that day's legs]")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from ui.controllers.map_sync import MapSyncControllerMixin
    from ui.controllers.route import RouteControllerMixin

    class Win(MapSyncControllerMixin, RouteControllerMixin):
        pass

    _ = QApplication.instance() or QApplication(sys.argv)
    a = [_stop("Day5", "100", 34.0, -118.0), _stop("Day5", "101", 34.01, -118.01)]
    b = [_stop("Day6", "200", 34.2, -117.3), _stop("Day6", "201", 34.21, -117.31)]
    win = Win()
    win.state = type("S", (), {})()
    win.state.stops = a + b
    win.state.active_files = ["Day5", "Day6"]
    win.state.map_day_filter = "Day6"
    win.state.home = None
    win.state.routes_by_map = {}
    # Legs are Day6 only. Absolute index 2 is past this list.
    win.state.route = {
        "miles": 4.0,
        "graph": False,
        "est_version": 2,
        "job_drive_min": 9.0,
        "home_back_min": 12.0,
        "site_legs": [
            {
                "to_uid": b[0]["uid"],
                "drive_min": 0.0,
                "from_home_min": 15.0,
                "to_home_min": 0.0,
                "miles": 0.0,
            },
            {
                "to_uid": b[1]["uid"],
                "drive_min": 9.0,
                "from_home_min": 0.0,
                "to_home_min": 12.0,
                "miles": 4.0,
            },
        ],
    }
    first = win._stop_time_suffix(2, "--", leg_index=0)
    second = win._stop_time_suffix(3, "--", leg_index=1)
    if "from home 15 min" in first and "9 min drive" not in first:
        ok("Day6 first stop uses that day's from-home clock")
    else:
        fail("Day6 first stop uses that day's from-home clock", first)
    if "9 min drive" in second and "then 12 min home" in second:
        ok("Day6 second stop uses that day's drive and home clock")
    else:
        fail("Day6 second stop uses that day's drive and home clock", second)
    # The old absolute index read off the end of the day legs.
    stale = win._stop_time_suffix(2, "--")
    if "from home" not in stale and "9 min drive" not in stale:
        ok("absolute index is not a Day6 leg")
    else:
        fail("absolute index is not a Day6 leg", stale)


def main() -> int:
    print("ROUTE SECTIONS — two maps, two independent builds\n")
    test_core_helpers()
    test_days_merged_view()
    test_build_routes_by_section()
    test_day_filter_drive_time()
    test_pick_scoped_to_one_map()
    test_excel_day_not_only_together()
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
