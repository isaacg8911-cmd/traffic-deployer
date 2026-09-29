"""Regression checks for the 2026-09-25 bug sweep (GPS, persistence, pickup, export)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

fails = 0


def check(cond: bool, label: str) -> None:
    global fails
    print(("  OK  " if cond else "  FAIL ") + label)
    if not cond:
        fails += 1


def test_gps_stale() -> None:
    print("[gps fix expiry]")
    import time
    import gps_reader

    s = gps_reader.GPSStream()
    if s._lock is None:
        print("  skip (pyserial missing)")
        return
    s._update(fix=True, lat=33.8, lon=-117.9, connected=True)
    s._last_fix_t = time.monotonic()
    check(s.latest()["fix"] is True, "fresh fix reported")
    s._last_fix_t = time.monotonic() - (gps_reader.FIX_STALE_S + 1)
    g = s.latest()
    check(g["fix"] is False and g.get("stale"), "fix older than FIX_STALE_S reported as no fix")
    check(gps_reader.fix_from_snapshot(g) is None, "Grab GPS refuses stale fix")

    class RMC:
        status, latitude, longitude = "V", 33.8, -117.9

    class GGA0:
        gps_qual, latitude, longitude = 0, 33.8, -117.9

    class GGA1:
        gps_qual, latitude, longitude = 1, 33.8, -117.9

    check(gps_reader._valid_fix(RMC()) is None and gps_reader._reports_no_fix(RMC()), "RMC V = no fix")
    check(gps_reader._valid_fix(GGA0()) is None, "GGA quality 0 = no fix")
    check(gps_reader._valid_fix(GGA1()) == (33.8, -117.9), "GGA quality 1 = fix")


def test_gps_skips_ftdi() -> None:
    print("[gps scan never probes counter FTDI port]")
    import gps_reader

    blobs = {"COM3": "usb serial port ftdi vid_0403", "COM4": "some other serial"}
    orig = (gps_reader.list_serial_ports, gps_reader._port_blob)
    gps_reader.list_serial_ports = lambda: list(blobs)
    gps_reader._port_blob = lambda p: blobs.get(p, "")
    try:
        check(gps_reader.candidate_gps_ports() == ["COM4"], "FTDI excluded from fallback scan")
    finally:
        gps_reader.list_serial_ports, gps_reader._port_blob = orig


def test_persistence_missing_key() -> None:
    print("[persistence: missing .tds_key must not wipe shift]")
    import persistence

    if not persistence.HAS_CRYPTO:
        print("  skip (cryptography missing)")
        return
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "tds_backup_T.json")
        persistence.save_state({"stops": [{"uid": "a", "installed": True}]}, p, d)
        os.remove(os.path.join(d, ".tds_key"))
        back = persistence.load_state(p, d)
        check(back == {}, "unreadable state loads empty (no crash)")
        check(not os.path.exists(os.path.join(d, ".tds_key")), "load did NOT invent a new key")
        kept = [f for f in os.listdir(d) if ".unreadable-" in f]
        check(bool(kept), "encrypted shift copied aside before any overwrite")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_export_serial() -> None:
    print("[export serial stays exact]")
    import pandas as pd
    from core import export

    for raw, want in (("0457", "0457"), ("22976.0", 22976.0), ("22976", 22976.0), ("AB12", "AB12")):
        df = pd.DataFrame({"Site": ["1"], "Serial": [None]}, dtype=object)
        export._merge_stop_into_ig_row(df, 0, {"id": "1", "serial": raw})
        got = df.at[0, "Serial"]
        check(got == want, f"serial {raw!r} -> {got!r}")


def test_pickup_pending_advance() -> None:
    print("[Mark picked up with 'Not picked up only' on]")
    from ui.controllers.pickup import PickupControllerMixin

    class Chk:
        def isChecked(self):
            return True

    class W(PickupControllerMixin):
        def __init__(self):
            self.state = type("S", (), {})()
            self.state.stops = [
                {"uid": u, "id": i, "installed": True} for i, u in enumerate("abc", start=1)]
            self.pickup_index = 0
            self.chk_pickup_pending = Chk()

        def _stops_matching_day_filter(self, items=None):
            return self.state.stops if items is None else items

        def _push_undo(self, *a, **k): pass
        def _snapshot_stop(self, s): return dict(s)
        def _persist_shift(self, quiet=True): pass
        def _counter_inventory_shift(self): pass
        def _refresh_pickup(self): pass
        def _push_state(self): pass
        def _refresh_audit(self): pass

    w = W()
    w._mark_pickup()
    items = w._installed_stops()
    check(items[w.pickup_index]["uid"] == "b", "next pending site is B (not skipped to C)")
    w._mark_pickup()
    items = w._installed_stops()
    check(items and items[w.pickup_index]["uid"] == "c", "then C")


def test_static_fixes() -> None:
    print("[static wiring]")
    import inspect
    import road_router
    from ui.controllers.install import InstallControllerMixin
    from ui.controllers.shortcuts import ShortcutsControllerMixin

    src = inspect.getsource(road_router)
    check("            maneuvers.extend(leg.get(\"maneuvers\")" not in src,
          "nav_plan appends each leg's maneuvers once")
    src = inspect.getsource(InstallControllerMixin._start_field_street_thread)
    check("_field_street_threads" in src and "finished.connect" in src,
          "street lookup threads kept alive until finished")
    src = inspect.getsource(ShortcutsControllerMixin._undo_last_action)
    check("self.current_index = idx" in src, "undo opens the undone site by uid")
    src = inspect.getsource(InstallControllerMixin._commit_install_body)
    check("already" in src and "exact_time" in src, "re-save keeps original install time")


def test_pick_pauses_on_install() -> None:
    """RTE-5: Install must not keep route-pick clicks. Route restores the order."""
    print("[RTE-5 pick pauses when leaving Route]")
    from ui.controllers.map_sync import MapSyncControllerMixin
    from ui.controllers.route import RouteControllerMixin
    from ui.page_indices import NAV_PAGE_COUNT
    from ui.shell.topbar import ShellTopbarMixin

    class Pages:
        def __init__(self) -> None:
            self.i = 1

        def currentIndex(self) -> int:
            return self.i

        def setCurrentIndex(self, i: int) -> None:
            self.i = i

    class Btn:
        def setChecked(self, _on: bool) -> None:
            return

        def setText(self, text: str) -> None:
            self.text = text

        def setObjectName(self, _name: str) -> None:
            return

        def style(self):
            return self

        def unpolish(self, _w) -> None:
            return

        def polish(self, _w) -> None:
            return

    class Win(ShellTopbarMixin, RouteControllerMixin, MapSyncControllerMixin):
        def __init__(self) -> None:
            self.pages = Pages()
            self._route_pick_mode = True
            self._route_pick_uids = ["u1"]
            self._route_pick_sides = {"u1": "begin"}
            self._route_pick_section = "Day 1"
            self._route_pick_by_map = {"Day 2": {"uids": ["u9"], "sides": {"u9": "end"}}}
            self._route_pick_suspended = None
            self._route_pick_dialog = None
            self._manual_grab_mode = False
            self._map_js_ready = False
            self._map_preview_stops = []
            self._pick_layout_active = False
            self._pick_splitter_saved = None
            self._gps_follow = False
            self._pick_side_mode = "begin"
            self.messages: list[str] = []
            self.selected: list[int] = []
            self.chk_show_segments = type("C", (), {"isChecked": lambda _s: False})()
            stops = [
                {
                    "uid": "u1", "id": "1", "street": "First",
                    "begin_lat": 33.80, "begin_lon": -117.90,
                    "end_lat": 33.81, "end_lon": -117.90,
                },
                {
                    "uid": "u2", "id": "2", "street": "Second",
                    "begin_lat": 33.82, "begin_lon": -117.91,
                    "end_lat": 33.83, "end_lon": -117.91,
                },
            ]
            self.state = type("S", (), {
                "offline_mode": False,
                "stops": stops,
                "home": (33.7, -117.8),
                "route": {"polyline": [], "miles": 0.0, "graph": False},
                "map_day_filter": "All days",
                "active_files": [],
                "routes_by_map": {},
            })()
            self.state.index_of = lambda uid, rows=stops: next(
                (i for i, s in enumerate(rows) if s["uid"] == uid), -1)
            for j in range(NAV_PAGE_COUNT):
                setattr(self, f"_navbtn_{j}", Btn())
            self.btn_start = Btn()
            self.bridge = type("B", (), {"set_follow": lambda *_a, **_k: None})()

        def statusBar(self):
            return self

        def showMessage(self, msg: str, _ms: int = 0) -> None:
            self.messages.append(msg)

        def _refresh_route_list(self) -> None:
            return

        def _refresh_install(self) -> None:
            return

        def _refresh_pickup(self) -> None:
            return

        def _refresh_audit(self) -> None:
            return

        def _refresh_workflow_strip(self) -> None:
            return

        def _refresh_field_alerts(self) -> None:
            return

        def _update_right(self, force_map: bool = False) -> None:
            _ = force_map

        def _push_state(self, fit: bool = False) -> None:
            _ = fit

        def _flush_install_form(self) -> None:
            return

        def _end_manual_grab(self, *, silent: bool = False, then=None) -> None:
            _ = silent
            if then:
                then()

        def _enter_pick_map_focus(self) -> None:
            return

        def _set_drive_mode(self, _on: bool) -> None:
            return

        def _apply_power_profile(self) -> None:
            return

        def _select_install_stop(self, idx: int) -> None:
            self.selected.append(idx)

    win = Win()
    win._on_map_clicked(33.82, -117.91)
    check(win._route_pick_uids == ["u1", "u2"], "on Route, a map click still adds the next stop")

    win._route_pick_uids = ["u1"]
    win._route_pick_sides = {"u1": "begin"}
    win._go_page(2)
    check(win.pages.currentIndex() == 2, "Install tab opens")
    check(win._route_pick_mode is False, "pick mode is off on Install")
    check(win._section_pick_active() is False, "map leaves pick mode")
    check(not win._route_pick_mode, "Drop pin guard sees pick mode off")
    check(any("paused" in m for m in win.messages), "operator is told the pick is paused")
    win._on_map_clicked(33.82, -117.91)
    check(win._route_pick_uids == ["u1"], "Install map click does not add a stop")
    win._on_stop_clicked("u2|end")
    check(win.selected == [1], "Install stop click selects that site")
    check(win._route_pick_uids == ["u1"], "Install stop click does not extend the order")
    saved_day2 = list(win._route_pick_suspended["by_map"]["Day 2"]["uids"])
    win._route_pick_by_map = {"Day 2": {"uids": ["changed"], "sides": {}}}

    win._gps_follow = True
    win._go_page(1)
    check(win._route_pick_mode is False, "GPS follow does not resume pick")
    check(win._route_pick_suspended is not None, "paused order kept during follow")
    win._stop_drive()
    check(win._route_pick_mode is True, "stopping follow on Route resumes pick")
    check(win._route_pick_uids == ["u1"], "resumed order is the paused order")
    check(win._route_pick_sides.get("u1") == "begin", "resumed side locks")
    check(win._route_pick_by_map["Day 2"]["uids"] == saved_day2, "other day's paused picks survive")
    check(win._route_pick_suspended is None, "pause cleared once pick is back")

    win._go_page(2)
    check(win._route_pick_mode is False, "leaving Route pauses again")
    win._begin_route_pick([{
        "uid": "new", "id": "9", "street": "New",
        "begin_lat": 33.9, "begin_lon": -117.9,
        "end_lat": 33.91, "end_lon": -117.9,
    }])
    check(win._route_pick_mode is True, "a new Build starts pick mode")
    check(win._route_pick_uids == [], "a new Build does not restore the paused order")
    check(win._route_pick_suspended is None, "a new Build clears the pause")
    check(win.pages.currentIndex() == 1, "a new Build opens Route")

    idle = Win()
    idle._route_pick_mode = False
    idle._route_pick_uids = []
    idle._go_page(2)
    check(idle._route_pick_suspended is None, "leaving Route with no pick does not invent a pause")
    check(idle._route_pick_mode is False, "Install stays out of pick mode")


def test_est_id_not_coordinate() -> None:
    """IMP-1: coordinate digits are not a site id. Real pins and demo tokens are."""
    print("[IMP-1 site id is not a coordinate fragment]")
    import tempfile

    from core import ingest

    def pin(sid: str) -> dict:
        return {
            "begin_lat": 33.7, "begin_lon": -117.9,
            "end_lat": 33.8, "end_lon": -117.8,
            "lat": 33.75, "lon": -117.85,
            "street": f"Site {sid}",
        }

    sites = {
        sid: pin(sid)
        for sid in ("117", "33", "5057", "1001", "50570", "771", "101")
    }
    body = "coords -117.5057 33.77150\n\xff\xfe1001\x00\xff\xfe50570\x00"
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "map.est")
        with open(path, "w", encoding="latin-1", newline="\n") as f:
            f.write(body)
        stops = ingest.match_est_files(
            [{"path": path, "label": "Day 1"}], sites, (33.7, -117.9))
        ids = {s["id"] for s in stops}
        check(ids == {"1001", "50570"}, "pins match; coordinate fragments do not: " + str(sorted(ids)))

        xbody = "\xff\xfe5057x\x00-117.101\n"
        xpath = os.path.join(tmp, "table.est")
        with open(xpath, "w", encoding="latin-1", newline="\n") as f:
            f.write(xbody)
        stops = ingest.match_est_files(
            [{"path": xpath, "label": "Day 1"}], sites, (33.7, -117.9))
        ids = {s["id"] for s in stops}
        check(ids == {"5057"}, "coord-table pin 5057x is site 5057, not 117 or 101: " + str(sorted(ids)))

    demo_stops = ingest.match_est_files(
        [{"path": os.path.join(ROOT, "demo_data", "DemoDay.EST"), "label": "DemoDay"}],
        ingest.parse_excel_sites([os.path.join(ROOT, "demo_data", "demo_sites.csv")]),
        (33.77, -117.94),
    )
    demo_ids = {s["id"] for s in demo_stops}
    check(demo_ids == {"101", "102", "103", "104", "105"}, "demo text map still matches its site tokens")


def test_duplicate_site_id() -> None:
    """IMP-2: import and export keep the first copy of a duplicate site id."""
    print("[IMP-2 duplicate site id keeps the first copy]")
    import pandas as pd

    from core import export, ingest

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "sites.csv")
        with open(path, "w", encoding="latin-1", newline="\n") as f:
            f.write(
                "Site,Begin Lat,Begin Lon,Street\n"
                "1001,33.77,-117.94,First St\n"
                "1001,33.78,-117.95,Second St\n"
            )
        sites = ingest.parse_excel_sites([path])
        check(sites["1001"]["street"] == "First St", "import keeps the first row")

        xls = os.path.join(tmp, "sites.xlsx")
        pd.DataFrame([
            ["1001", 33.77, -117.94, "First St"],
            ["1001", 33.78, -117.95, "Second St"],
        ], columns=["Site", "Begin Lat", "Begin Lon", "Street"]).to_excel(xls, index=False)
        sites = ingest.parse_excel_sites([xls])
        check(sites["1001"]["street"] == "First St", "excel import keeps the first row")

    same = export._stops_by_id([
        {"id": "1001", "serial": "111", "installed": True},
        {"id": "1001", "serial": "222", "installed": True},
    ])
    check(same["1001"]["serial"] == "111", "export keeps the first copy when both are installed")
    better = export._stops_by_id([
        {"id": "1001", "serial": "", "installed": False},
        {"id": "1001", "serial": "222", "installed": True, "field_lat": 33.7, "field_lon": -117.9},
    ])
    check(better["1001"]["serial"] == "222", "a later copy wins only when it has more field work")


def test_title_row_above_headers() -> None:
    """IMP-3: a title row above the column names still finds the sites."""
    print("[IMP-3 title row above headers]")
    import pandas as pd

    from core import ingest

    with tempfile.TemporaryDirectory() as tmp:
        csv_path = os.path.join(tmp, "titled.csv")
        with open(csv_path, "w", encoding="latin-1", newline="\n") as f:
            f.write(
                "Week 17 site list\n"
                "Site,Begin Lat,Begin Lon,Street\n"
                "1001,33.77,-117.94,Harbor Blvd\n"
            )
        sites = ingest.parse_excel_sites([csv_path])
        check("1001" in sites and sites["1001"]["street"] == "Harbor Blvd",
              "csv title row still imports the site")

        xls = os.path.join(tmp, "titled.xlsx")
        pd.DataFrame([
            ["Week 17 site list", None, None, None],
            ["Site", "Begin Lat", "Begin Lon", "Street"],
            [1001, 33.77, -117.94, "Harbor Blvd"],
        ]).to_excel(xls, index=False, header=False)
        sites = ingest.parse_excel_sites([xls])
        check("1001" in sites and sites["1001"]["street"] == "Harbor Blvd",
              "excel title row still imports the site")

        plain = os.path.join(tmp, "plain.xlsx")
        pd.DataFrame(
            [{"Site": 1002, "Begin Lat": 33.78, "Begin Lon": -117.93, "Street": "Oak Ave"}]
        ).to_excel(plain, index=False)
        sites = ingest.parse_excel_sites([plain])
        check(sites.get("1002", {}).get("street") == "Oak Ave", "a normal header row still imports")


def test_tile_edge_roads() -> None:
    """MAP-1: tiled downloads overlap, and each tile keeps crossing roads."""
    print("[MAP-1 roads that cross a tile edge]")
    import road_router

    west, south, east, north = -118.0, 33.0, -117.2, 34.6
    boxes = road_router.tile_boxes(
        west, south, east, north, max_tile_mi=30.0, overlap_m=400.0)
    check(len(boxes) >= 4, f"large area splits into tiles ({len(boxes)})")
    bands: dict[float, list] = {}
    for box in boxes:
        mid = round((box[1] + box[3]) / 2.0, 2)
        bands.setdefault(mid, []).append(box)
    keys = sorted(bands)
    check(len(keys) >= 2, "more than one row of tiles")
    lower = bands[keys[0]][0]
    upper = bands[keys[1]][0]
    check(lower[3] > upper[1], "neighbor rows overlap across the cut")
    seam = (max(lower[1], upper[1]) + min(lower[3], upper[3])) / 2.0
    check(lower[1] < seam < lower[3] and upper[1] < seam < upper[3],
          "a point on the shared edge is inside both tiles")

    if not road_router.HAS_OSMNX:
        print("  skip truncate_by_edge (osmnx missing)")
        return
    seen: dict = {}
    orig = road_router.ox.graph_from_bbox

    def _fake(*_a, **kwargs):
        seen["kwargs"] = kwargs
        return object()

    road_router.ox.graph_from_bbox = _fake
    try:
        road_router._fetch_bbox_graph(west, south, east, north)
    finally:
        road_router.ox.graph_from_bbox = orig
    check(seen.get("kwargs", {}).get("truncate_by_edge") is True,
          "each tile keeps roads that cross its edge")


def test_online_street_lookup() -> None:
    """ONL-1: going online must not geocode on the UI thread or replace a typed street."""
    print("[ONL-1 online street lookup]")
    from core import geo
    from ui.controllers.install import InstallControllerMixin, take_online_street

    check(take_online_street({"street_user_edited": True}, "Oak") is False, "typed street is kept")
    check(take_online_street({"street": "Site 5"}, "Oak") is True, "an untouched street can be filled")
    check(take_online_street({"street": "Site 5"}, "") is False, "an empty lookup fills nothing")

    class Win(InstallControllerMixin):
        def __init__(self) -> None:
            self.state = type("S", (), {})()
            self.state.stops = [
                {
                    "id": "5", "field_lat": 33.7, "field_lon": -117.9,
                    "field_geocode_pending": True, "street": "Site 5",
                },
                {
                    "id": "6", "field_lat": 33.71, "field_lon": -117.8,
                    "field_geocode_pending": True, "street": "Oak Ave",
                    "street_user_edited": True,
                },
            ]
            self.started: list[int] = []

        def _internet_allowed(self) -> bool:
            return True

        def _start_field_street_thread(self, idx, lat, lon, *, prefer_online) -> None:
            self.started.append(idx)

    def _boom(*_a, **_k):
        raise AssertionError("street lookup ran on the caller")

    orig = geo.street_from_coords
    geo.street_from_coords = _boom
    try:
        win = Win()
        win._retry_pending_field_geocode()
        win._retry_pending_field_geocode()
    finally:
        geo.street_from_coords = orig
    check(win.started == [0], "only the untyped site is queued, and only once")
    check(win.state.stops[1]["street"] == "Oak Ave", "typed street unchanged")
    check(win.state.stops[1]["field_geocode_pending"] is False, "typed street is not looked up again")


def test_local_server_streams() -> None:
    """PERF-1: file responses are chunked and still return the right bytes."""
    print("[PERF-1 local server streams files]")
    import inspect
    import urllib.request

    import local_server

    src = inspect.getsource(local_server._Handler._write_slice)
    check("while remaining" in src and "_CHUNK" in src, "responses are written in chunks")
    local_server.stop()
    folder = tempfile.mkdtemp()
    try:
        web = os.path.join(folder, "web")
        os.makedirs(web)
        payload = b"abcdefghij" * 5000
        with open(os.path.join(web, "blob.bin"), "wb") as f:
            f.write(payload)
        port = local_server.start(web, folder)
        url = f"http://127.0.0.1:{port}/blob.bin"
        with urllib.request.urlopen(url, timeout=5) as resp:
            check(resp.read() == payload, "full response matches the file")
        req = urllib.request.Request(url, headers={"Range": "bytes=10-19"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            check(getattr(resp, "status", 200) == 206, "range request is 206")
            check(resp.read() == payload[10:20], "range bytes match")
    finally:
        local_server.stop()
        shutil.rmtree(folder, ignore_errors=True)


def _pair_reference(hits, pair_max_s, study_start):
    """The old O(n²) pairing, kept here so the linear pass must match it."""
    from datetime import timedelta

    ab = sorted(hits, key=lambda x: x["seconds"])
    used: set[int] = set()
    events = []

    def _match(first_ch: str, second_ch: str, key: str) -> None:
        for i, a in enumerate(ab):
            if a["channel"] != first_ch or i in used:
                continue
            best_j = None
            best_dt = None
            for j, b in enumerate(ab):
                if j in used or b["channel"] != second_ch:
                    continue
                dt = b["seconds"] - a["seconds"]
                if dt <= 0 or dt > pair_max_s:
                    continue
                if best_dt is None or dt < best_dt:
                    best_dt = dt
                    best_j = j
            if best_j is not None:
                used.add(i)
                used.add(best_j)
                events.append({
                    "datetime": study_start + timedelta(seconds=a["seconds"]),
                    "direction_key": key,
                })

    _match("A", "B", "ab")
    _match("B", "A", "ba")
    events.sort(key=lambda e: e["datetime"])
    return events


def test_hit_pairing_linear() -> None:
    """PERF-2: pairing matches the old results, and stream scan does not re-read a study."""
    print("[PERF-2 hit pairing and stream scan]")
    from datetime import datetime

    from core import picocount_hits

    start = datetime(2026, 6, 1, 8, 0, 0)
    hits = []
    t = 0.0
    for i in range(40):
        hits.append({"channel": "A" if i % 3 else "B", "seconds": t})
        t += 0.03 if i % 5 else 0.2
    debounced = picocount_hits.debounce_hits(hits)
    got = picocount_hits.pair_vehicles(hits, study_start=start)
    want = _pair_reference(debounced, picocount_hits.DEFAULT_PAIR_MAX_S, start)
    check(
        [(e["direction_key"], e["datetime"]) for e in got]
        == [(e["direction_key"], e["datetime"]) for e in want],
        f"linear pairing matches ({len(got)} events)",
    )

    def _encode(n: int) -> bytes:
        out = bytearray()
        for i in range(n):
            ticks = i * 32768
            out.append((12 << 4) | (1 if i % 2 == 0 else 2))
            out += int(ticks).to_bytes(4, "little")
        return bytes(out)

    data = b"\x00" * 30 + _encode(4000) + b"\xff" * 20
    calls = {"n": 0}
    orig = picocount_hits.decompress_hits

    def _wrapped(buf, start_at=0):
        calls["n"] += 1
        return orig(buf, start_at)

    picocount_hits.decompress_hits = _wrapped
    try:
        off, found = picocount_hits.find_best_stream(data)
    finally:
        picocount_hits.decompress_hits = orig
    check(len(found) == 4000 and off == 30, f"hour-long stream found at {off} ({len(found)} hits)")
    check(calls["n"] < 80, f"scan jumped the study ({calls['n']} parses, not one per byte)")

    from core.volume_report import _hours_by_day

    morning = datetime(2026, 6, 1, 8, 0, 0)
    next_day = datetime(2026, 6, 2, 9, 0, 0)
    grouped = _hours_by_day({next_day: {"total": 1}, morning: {"total": 2}})
    check(
        grouped[morning.date()] == [morning] and grouped[next_day.date()] == [next_day],
        "volume hours are grouped by day once",
    )


def main() -> int:
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])  # noqa: F841
    test_gps_stale()
    test_gps_skips_ftdi()
    test_persistence_missing_key()
    test_export_serial()
    test_pickup_pending_advance()
    test_static_fixes()
    test_pick_pauses_on_install()
    test_est_id_not_coordinate()
    test_duplicate_site_id()
    test_title_row_above_headers()
    test_tile_edge_roads()
    test_online_street_lookup()
    test_local_server_streams()
    test_hit_pairing_linear()
    print("PASS" if not fails else f"FAIL ({fails})")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
