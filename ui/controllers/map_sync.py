"""Map sync controller mixin - P46 E1.4 extract from main.py."""

from __future__ import annotations

from PySide6.QtCore import QTimer

from core import crash_log, geo, ingest
from core import route_sections
from ui.map_helpers import (
    coords_moved,
    display_route_for_map,
    dist_m,
    heading_cardinal,
    shift_has_field_progress,
    should_push_gps_bridge,
)
from ui.paths import DATA_DIR
from ui.page_indices import NAV_PAGE_COUNT
from ui.simple_mode import FIELD_NAV_INDICES, FIELD_SHELL, SIMPLE_MODE
from version import APP_VERSION

DAY_FILTER_ALL = "All days"
SITE_CLICK_ZOOM = 15


class MapSyncControllerMixin:
    # ------------------------------------------------------ map / state push
    def _on_page_load_finished(self, ok: bool):
        if not ok:
            return
        self._map_ready_polls = 0
        self._poll_map_ready()

    def _poll_map_ready(self):
        def cb(ready):
            if ready:
                if not self._map_js_ready:
                    self._map_js_ready = True
                    self._on_map_ready()
            elif self._map_ready_polls < 150:
                self._map_ready_polls += 1
                QTimer.singleShot(200, self._poll_map_ready)
        self.view.page().runJavaScript("!!window.__mapLoaded", cb)

    def _on_map_ready(self):
        self._hide_map_load_overlay()
        self.bridge.set_follow(bool(self._map_follow))
        if self.state.stops:
            self._apply_map_startup_view()

    def _on_map_follow_toggled(self, on: bool) -> None:
        """Map HUD Follow Me — camera recenter only; drive mode stays on (D7)."""
        self._map_follow = bool(on)
        if on:
            self._last_gps_bridge = None
            g = self.gps.latest()
            if g.get("fix") and g.get("lat") is not None:
                hdg = g.get("heading_display") or g.get("heading_locked") or g.get("heading")
                self.bridge.send_gps({
                    "lat": g["lat"], "lon": g["lon"], "heading": hdg,
                    "heading_mode": g.get("heading_mode"), "speed_mps": g.get("speed_mps"),
                })
            self.statusBar().showMessage(
                "Map following GPS — pan freely; tap Follow Me to recenter.", 8000)
        elif self._gps_follow:
            self.statusBar().showMessage(
                "Map pan unlocked — GPS marker still live. Tap Follow Me to recenter.", 6000)
        else:
            self.statusBar().showMessage("Map follow off.", 4000)
        self._apply_power_profile(force=True)

    def _shift_has_field_progress(self) -> bool:
        return shift_has_field_progress(self.state.stops)

    def _map_focus_coords(self) -> tuple[float, float] | None:
        """Most recent install/skip/pickup field point, else current stop."""
        last: tuple[float, float] | None = None
        for s in self.state.stops:
            if not (s.get("installed") or s.get("skipped") or s.get("picked_up")):
                continue
            if s.get("field_lat") is not None and s.get("field_lon") is not None:
                last = (float(s["field_lat"]), float(s["field_lon"]))
            else:
                anchor = self._stop_anchor_coords(s)
                if anchor:
                    last = anchor
        if last:
            return last
        if self.state.stops and self.current_index < len(self.state.stops):
            lat, lon = self.state.point(self.state.stops[self.current_index])
            return float(lat), float(lon)
        items = self._installed_stops()
        if items:
            s = items[min(self.pickup_index, len(items) - 1)]
            if s.get("field_lat") is not None and s.get("field_lon") is not None:
                return float(s["field_lat"]), float(s["field_lon"])
            anchor = self._stop_anchor_coords(s)
            if anchor:
                return anchor
        return None

    def _apply_map_startup_view(self) -> None:
        """Fit all sites on fresh route; after field work, zoom to last action."""
        if not self.state.stops:
            return
        self.bridge.refresh_view()
        if self._shift_has_field_progress():
            self._push_state(fit=False)
            coords = self._map_focus_coords()
            if coords:
                lat, lon = coords
                QTimer.singleShot(350, lambda: self.bridge.fly_to(lat, lon, 14))
        else:
            self._push_state(fit=True)

    def _refresh_map_view(self):
        """Resize the WebEngine canvas (it starts at 0px while hidden) and redraw."""
        self.bridge.refresh_view()
        self._push_state(fit=True)

    def _display_route(self) -> dict:
        if self._route_section_active() and not self._day_filter_active():
            return display_route_for_map(route_sections.empty_route())
        return display_route_for_map(self.state.route)

    def _section_stops_for_legs(self) -> list[dict]:
        if self._day_filter_active():
            return self._stops_matching_day_filter()
        return list(self.state.stops)

    def _ensure_site_legs(self) -> None:
        stops = self._section_stops_for_legs()
        if not stops:
            return
        if self.state.route.get("site_legs"):
            return
        from core.routing import build_site_legs
        self.state.route["site_legs"] = build_site_legs(
            stops, tuple(self.state.home), DATA_DIR)

    def _first_pending_index(self) -> int | None:
        vis = self._visible_stop_indices()
        for i in vis:
            s = self.state.stops[i]
            if not s.get("installed") and not s.get("skipped"):
                return i
        return None

    def _next_leg_payload(self) -> dict | None:
        if not self.state.stops:
            return None
        route = self.state.route or {}
        if not route.get("site_legs") and float(route.get("miles") or 0) <= 0:
            return None
        self._ensure_site_legs()
        idx = self._first_pending_index()
        if idx is None:
            return None
        vis = self._visible_stop_indices()
        try:
            local = vis.index(idx)
        except ValueError:
            return None
        legs = route.get("site_legs") or []
        if local >= len(legs):
            return None
        leg = legs[local]
        poly = leg.get("polyline") or []
        if len(poly) < 2:
            return None
        target = self.state.stops[idx]
        from core.routing import _stop_pt, sanitize_leg_polyline

        dest = _stop_pt(target)
        if not geo.ca_coords_plausible(*self.state.home) or not geo.ca_coords_plausible(*dest):
            return None
        clean = sanitize_leg_polyline(poly, tuple(self.state.home), dest)
        if not clean or len(clean) < 2:
            return None
        return {
            "polyline": clean,
            "to_uid": target["uid"],
            "to_id": target.get("id"),
            "miles": float(leg.get("miles") or 0.0),
            "index": idx,
        }

    def _follow_banner_text(self) -> str:
        if not self._gps_follow:
            return ""
        nxt = self._next_leg_payload()
        if not nxt:
            return "All stops done."
        gi = nxt["index"]
        target = self.state.stops[gi]
        return (
            f"Next: Site {nxt.get('to_id', '?')} — {nxt['miles']:.1f} mi  "
            f"({self._street_label(target)})")

    def _update_follow_banner(self) -> None:
        text = self._follow_banner_text()
        if hasattr(self, "lbl_drive_next"):
            if self._gps_follow and text:
                self.lbl_drive_next.setText(text)
                self.lbl_drive_next.show()
            else:
                self.lbl_drive_next.hide()
        if not hasattr(self, "lbl_drive_banner"):
            return
        if not self._gps_follow:
            self.lbl_drive_banner.hide()
            return
        if not text:
            self.lbl_drive_banner.hide()
            return
        self.lbl_drive_banner.setText(text)
        self.lbl_drive_banner.show()

    def _set_drive_mode(self, on: bool) -> None:
        if hasattr(self, "btn_drive_arrived"):
            self.btn_drive_arrived.setVisible(on)
            self.btn_drive_end.setVisible(on)
        if on:
            self._splitter_sizes_saved = self._splitter.sizes()
            total = max(800, sum(self._splitter_sizes_saved))
            self._splitter.setSizes([0, total])
            for box in getattr(self, "_route_fold_boxes", []):
                if box is not None:
                    box.hide()
            for i in range(NAV_PAGE_COUNT):
                btn = getattr(self, f"_navbtn_{i}", None)
                if btn is not None:
                    btn.setEnabled(i in (1, 2))
            self._update_follow_banner()
            self.brand_sub.setText("Following GPS — next site on map")
        else:
            if self._splitter_sizes_saved:
                self._splitter.setSizes(self._splitter_sizes_saved)
            for box in getattr(self, "_route_fold_boxes", []):
                if box is not None:
                    box.show()
            self._apply_field_nav_shell()
            for i in range(NAV_PAGE_COUNT):
                btn = getattr(self, f"_navbtn_{i}", None)
                if btn is not None:
                    if FIELD_SHELL and self.state.offline_mode:
                        btn.setEnabled(i in FIELD_NAV_INDICES)
                    else:
                        btn.setEnabled(True)
            self.lbl_drive_banner.hide()
            self.brand_sub.setText(
                f"v{APP_VERSION}  ·  field mode" if self.state.offline_mode
                else f"v{APP_VERSION}  ·  home setup · Wi‑Fi tools on")
        self._sync_gps_timer()
        self._sync_map_health_interval()

    def _drive_arrived_install(self) -> None:
        if not self._gps_follow:
            return
        self._go_page(2)
        self._center_current()

    def _route_section_labels(self) -> list[str]:
        return route_sections.section_labels(
            self.state.stops, getattr(self.state, "active_files", None))

    def _route_section_active(self) -> bool:
        return route_sections.multi_section(
            self.state.stops, getattr(self.state, "active_files", None))

    def _ensure_routes_by_map(self) -> dict[str, dict]:
        stored = getattr(self.state, "routes_by_map", None)
        if not isinstance(stored, dict):
            stored = {}
            self.state.routes_by_map = stored
        return stored

    def _ensure_pick_by_map(self) -> dict[str, dict]:
        saved = getattr(self, "_route_pick_by_map", None)
        if not isinstance(saved, dict):
            saved = {}
            self._route_pick_by_map = saved
        return saved

    def _stash_route_section(self, label: str) -> None:
        if route_sections.is_all_days(label):
            return
        stash = self._ensure_pick_by_map()
        stash[label] = {
            "uids": list(getattr(self, "_route_pick_uids", []) or []),
            "sides": dict(getattr(self, "_route_pick_sides", {}) or {}),
        }
        if self._route_pick_mode:
            return
        route = getattr(self.state, "route", None)
        if isinstance(route, dict) and (
            route.get("polyline") or float(route.get("miles") or 0) > 0
        ):
            self._ensure_routes_by_map()[label] = dict(route)

    def _restore_route_section(self, label: str) -> None:
        saved = self._ensure_pick_by_map().get(label) or {}
        if self._route_pick_mode:
            self._route_pick_uids = list(saved.get("uids") or [])
            self._route_pick_sides = dict(saved.get("sides") or {})
        self._apply_section_route_to_state()

    def _apply_section_route_to_state(self) -> None:
        day = self._day_filter_value()
        if route_sections.is_all_days(day):
            if self._route_section_active():
                self.state.route = route_sections.empty_route()
            return
        stored = self._ensure_routes_by_map().get(day)
        if stored:
            self.state.route = dict(stored)
        elif self._route_pick_mode:
            self.state.route = route_sections.empty_route()

    def _set_route_section(self, label: str, *, persist: bool = True) -> None:
        prev = getattr(self, "_day_filter_prev", None)
        if prev and prev != label:
            self._stash_route_section(prev)
        self.state.map_day_filter = label
        if hasattr(self, "combo_day"):
            idx = self.combo_day.findText(label)
            if idx >= 0 and self.combo_day.currentIndex() != idx:
                self.combo_day.blockSignals(True)
                self.combo_day.setCurrentIndex(idx)
                self.combo_day.blockSignals(False)
        self._day_filter_prev = label
        self._restore_route_section(label)
        if persist:
            try:
                self.state.save()
            except Exception:
                pass

    def _focus_route_section_for_pick(self) -> None:
        labels = self._route_section_labels()
        if len(labels) < 2 or self._day_filter_active():
            return
        self._set_route_section(labels[0], persist=False)

    def _cycle_route_section(self, delta: int = 1) -> None:
        labels = self._route_section_labels()
        nxt = route_sections.cycle_label(labels, self._day_filter_value(), delta)
        if not nxt:
            return
        self._set_route_section(nxt)
        vis = self._visible_stop_indices()
        if vis and self.current_index not in vis:
            self.current_index = vis[0]
        self._refresh_route_list()
        if self._route_pick_mode:
            self._refresh_route_pick_ui()
        if self.pages.currentIndex() == 2:
            self._refresh_install()
        elif self.pages.currentIndex() == 3:
            self._refresh_pickup()
        self._push_state(fit=True)
        n = labels.index(nxt) + 1 if nxt in labels else 1
        self.statusBar().showMessage(
            f"Map {n}/{len(labels)} — {nxt}. Route for this map only.", 8000)

    def _cycle_map_prev(self) -> None:
        self._cycle_route_section(-1)

    def _cycle_map_next(self) -> None:
        self._cycle_route_section(1)

    def _on_day_filter_changed(self):
        label = self.combo_day.currentText() if hasattr(self, "combo_day") else (
            self.state.map_day_filter or DAY_FILTER_ALL)
        self._set_route_section(label)
        vis = self._visible_stop_indices()
        if vis and self.current_index not in vis:
            self.current_index = vis[0]
        items = self._installed_stops()
        if items and self.pickup_index >= len(items):
            self.pickup_index = max(0, len(items) - 1)
        self._refresh_route_list()
        if self._route_pick_mode:
            self._refresh_route_pick_ui()
        if self.pages.currentIndex() == 2:
            self._refresh_install()
        elif self.pages.currentIndex() == 3:
            self._refresh_pickup()
        self._push_state(fit=True)

    def _day_filter_value(self) -> str:
        if hasattr(self, "combo_day") and self.combo_day.count():
            return self.combo_day.currentText() or DAY_FILTER_ALL
        return getattr(self.state, "map_day_filter", None) or DAY_FILTER_ALL

    def _day_filter_active(self) -> bool:
        return not route_sections.is_all_days(self._day_filter_value())

    def _pick_pool_stops(self) -> list[dict]:
        if not self.state.stops:
            return []
        if self._day_filter_active():
            return self._stops_matching_day_filter()
        if self._route_section_active():
            labels = self._route_section_labels()
            return route_sections.stops_for_section(self.state.stops, labels[0])
        return list(self.state.stops)

    def _pick_pool_total(self) -> int:
        return len(self._pick_pool_stops())

    def _section_pick_active(self) -> bool:
        """True when the visible map is the one being picked (not just viewed)."""
        if not getattr(self, "_route_pick_mode", False):
            return False
        if not self._route_section_active() or not self._day_filter_active():
            return True
        if self._route_pick_uids:
            return True
        day = self._day_filter_value()
        stored = self._ensure_routes_by_map().get(day) or {}
        if stored.get("polyline") or float(stored.get("miles") or 0) > 0:
            return False
        return True

    def _visible_stop_indices(self) -> list[int]:
        if not self.state.stops:
            return []
        day = self._day_filter_value()
        if route_sections.is_all_days(day):
            return list(range(len(self.state.stops)))
        return [i for i, s in enumerate(self.state.stops) if s.get("sheet") == day]

    def _stops_matching_day_filter(self, stops: list[dict] | None = None) -> list[dict]:
        base = stops if stops is not None else self.state.stops
        if not base:
            return []
        day = self._day_filter_value()
        if route_sections.is_all_days(day):
            return list(base)
        return [s for s in base if s.get("sheet") == day]

    def _refresh_day_filter(self):
        if not hasattr(self, "combo_day"):
            return
        cur = self.state.map_day_filter or self.combo_day.currentText()
        if cur == "All maps":
            cur = DAY_FILTER_ALL
        self.combo_day.blockSignals(True)
        self.combo_day.clear()
        self.combo_day.addItem(DAY_FILTER_ALL)
        for label in self._route_section_labels():
            if label and self.combo_day.findText(label) < 0:
                self.combo_day.addItem(label)
        idx = self.combo_day.findText(cur)
        self.combo_day.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_day.blockSignals(False)
        self.state.map_day_filter = self.combo_day.currentText()
        self._day_filter_prev = self.state.map_day_filter
        show = self.combo_day.count() > 2
        if hasattr(self, "_day_filter_wrap"):
            self._day_filter_wrap.setVisible(show)
        if hasattr(self, "lbl_day_filter"):
            self.lbl_day_filter.setText("Map" if show else "Sites")
        for attr in ("btn_map_prev", "btn_map_next"):
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.setVisible(show)

    def _stops_for_map(self) -> list[dict]:
        base = self.state.stops or getattr(self, "_map_preview_stops", []) or []
        filtered = self._stops_matching_day_filter(base)
        if self._section_pick_active():
            return [dict(s) for s in filtered]
        return self._stops_with_seq(filtered)

    @staticmethod
    def _site_letter(index: int) -> str:
        """A, B, … Z, AA — stable label per site during map pick."""
        n = index
        letters = ""
        while True:
            letters = chr(ord("A") + (n % 26)) + letters
            n = n // 26 - 1
            if n < 0:
                break
        return letters

    def _pick_site_letters(self) -> dict[str, str]:
        return {
            s["uid"]: self._site_letter(i)
            for i, s in enumerate(self._pick_pool_stops())
            if s.get("uid")
        }

    def _section_pick_tag(self) -> str:
        if not self._route_section_active() or not self._day_filter_active():
            return ""
        labels = self._route_section_labels()
        day = self._day_filter_value()
        n = labels.index(day) + 1 if day in labels else 1
        return f"Map {n}/{len(labels)} {day} — "

    def _pick_prompt_text(self) -> str:
        n = len(self._route_pick_uids)
        total = self._pick_pool_total()
        tag = self._section_pick_tag()
        if n >= total:
            return f"{tag}All {total} sites chosen — tap Apply route"
        return f"{tag}Click stop {n + 1} of {total} on the map"

    def _pick_waiting_hint(self) -> str:
        n = len(self._route_pick_uids)
        total = self._pick_pool_total()
        if n >= total:
            return "ready for Apply"
        return "waiting for your click — blue begin or red end"

    @staticmethod
    def _parse_stop_click(raw: str) -> tuple[str, str | None]:
        if "|" in raw:
            uid, side = raw.split("|", 1)
            if side in ("begin", "end"):
                return uid, side
        return raw, None

    def _stop_by_uid(self, uid: str) -> tuple[int, dict] | tuple[None, None]:
        idx = self.state.index_of(uid)
        if idx >= 0:
            return idx, self.state.stops[idx]
        preview = getattr(self, "_map_preview_stops", []) or []
        for i, s in enumerate(preview):
            if str(s.get("uid") or "") == uid:
                d = dict(s)
                d.setdefault("seq", i + 1)
                return i, d
        return None, None

    def _stop_click_status(self, stop: dict, idx: int, side: str | None) -> str:
        seq = stop.get("seq") or (idx + 1)
        site_id = stop.get("id", "?")
        street = str(stop.get("street", "") or "").strip()
        if street.lower() in ("nan", "none", "nat", ""):
            street = self._street_label(stop)
        msg = f"Stop {seq} · Excel site {site_id}"
        if street:
            msg += f" — {street}"
        if side in ("begin", "end"):
            msg += f" ({'Begin' if side == 'begin' else 'End'} point)"
        return msg

    @staticmethod
    def _apply_pick_side(stop: dict, side: str, *, lock: bool = True) -> None:
        if side == "begin":
            stop["cross_lat"] = stop["begin_lat"]
            stop["cross_lon"] = stop["begin_lon"]
        else:
            stop["cross_lat"] = stop["end_lat"]
            stop["cross_lon"] = stop["end_lon"]
        stop["cross_side"] = side
        if lock:
            stop["pick_cross_locked"] = True
        else:
            stop.pop("pick_cross_locked", None)

    def _ask_route_build_mode(self) -> str | None:
        """Pick-first workflow — BUILD ROUTE always opens manual pick (D2)."""
        return "pick"

    @staticmethod
    def _stops_with_seq(stops: list[dict]) -> list[dict]:
        """Route visit order → map labels 1, 2, 3…"""
        out = []
        for i, s in enumerate(stops):
            d = dict(s)
            d["seq"] = i + 1
            out.append(d)
        return out

    def _refresh_map_preview(self):
        """Show every site begin/end line as soon as Excel + .EST are loaded (before BUILD ROUTE)."""
        if self.state.stops:
            self._map_preview_stops = []
            self._map_preview_route = {"polyline": [], "miles": 0.0, "graph": False}
            return
        if not self.excel_paths or not self.est_paths:
            self._map_preview_stops = []
            self._map_preview_route = {"polyline": [], "miles": 0.0, "graph": False}
            self._update_right()
            if self._map_js_ready:
                self._push_state()
            return
        try:
            from core import routing
            sites = ingest.parse_excel_sites(self.excel_paths)
            raw = ingest.match_est_files(self._est_configs(), sites, self.state.home)
            self._map_preview_stops = routing.assign_crossings_for_display(
                raw, self.state.home, DATA_DIR)
            self._map_preview_route = {"polyline": [], "miles": 0.0, "graph": False}
        except ingest.ExcelEngineMissing as exc:
            crash_log.log_field_notice(str(exc), context="map_preview_ingest")
            self._map_preview_stops = []
            self._map_preview_route = {"polyline": [], "miles": 0.0, "graph": False}
        except ingest.IngestFileReadError as exc:
            crash_log.log_field_notice(str(exc), context="map_preview_ingest")
            self._map_preview_stops = []
            self._map_preview_route = {"polyline": [], "miles": 0.0, "graph": False}
        except Exception as exc:  # noqa: BLE001
            crash_log.log_error(exc, context="map_preview")
            self._map_preview_stops = []
            self._map_preview_route = {"polyline": [], "miles": 0.0, "graph": False}
        self._update_right(force_map=bool(self._map_preview_stops))
        if self._map_js_ready:
            self._push_state(fit=bool(self._map_preview_stops))

    def _warn_missing_upload_paths(self):
        saved_e = len(getattr(self.state, "excel_paths", []) or [])
        saved_m = len(getattr(self.state, "est_paths", []) or [])
        have_e, have_m = len(self.excel_paths), len(self.est_paths)
        if saved_e > have_e or saved_m > have_m:
            self.statusBar().showMessage(
                "Saved file list is incomplete — some Excel/EST paths moved. "
                "Re-add files on Setup.", 15000)

    def _route_for_map(self, *, preview: bool) -> dict:
        if preview:
            return getattr(self, "_map_preview_route", None) or {"polyline": [], "graph": False}
        return self._display_route()

    def _push_state(self, fit: bool = False):
        crash_log.set_last_action("map push")
        try:
            self._push_state_body(fit)
        except Exception as exc:  # noqa: BLE001
            crash_log.log_error(exc, context="push_state")

    def _push_state_body(self, fit: bool = False):
        following = bool(self._gps_follow or self._map_follow)
        preview = bool(self._map_preview_stops) and not self.state.stops
        picking = bool(self._section_pick_active())
        manual_grab = bool(self._manual_grab_mode)
        nxt = None if manual_grab else self._next_leg_payload()
        if manual_grab:
            mode = "manual_grab"
        elif picking:
            mode = "pick"
        elif following:
            mode = "drive"
        elif preview:
            mode = "preview"
        else:
            mode = "plan"
        hi = self._highlight_stop_uid()
        on_setup = self.pages.currentIndex() == 0
        st = {
            "theme": self.state.theme,
            "home": list(self.state.home),
            "stops": self._stops_for_map(),
            "route": self._route_for_map(preview=preview),
            "next_leg": nxt,
            "fit": fit,
            "driving": following,
            "map_mode": mode,
            "highlight_uid": hi,
            "drive_target_uid": hi if nxt else None,
            "pick_order": list(self._route_pick_uids) if picking else [],
            "pick_prompt": self._manual_grab_prompt() if manual_grab else (
                self._pick_prompt_text() if picking else ""),
            "pick_waiting": self._pick_waiting_hint() if picking else "",
            "pick_letters": self._pick_site_letters() if picking else {},
            "show_segments": False,
            "show_badges": not picking,
            "show_guide": False,
            # Lean map stripped streets/sites and broke field GPS follow — keep full map offline.
            "lean_drive": False,
            "current_uid": (
                self.state.stops[self.current_index]["uid"]
                if self.state.stops and self.current_index < len(self.state.stops)
                and self.pages.currentIndex() == 2
                else None
            ),
            "on_install": self.pages.currentIndex() == 2,
            "drive_banner": self._follow_banner_text() if following else "",
        }
        self.bridge.send_state(st)
        shown = self._stops_matching_day_filter() if self._day_filter_active() else self.state.stops
        miles = self.state.route.get("miles", 0.0)
        drive = (miles / 30.0) * 60 if miles else 0
        tag = f"{self._day_filter_value()} · " if self._day_filter_active() else ""
        self.status_route.setText(
            f"{tag}Stops: {len(shown)}   Route: {miles:.1f} mi   ~{drive:.0f} min")
        if nxt and not following:
            self.status_route.setText(
                f"Next: Site {nxt.get('to_id', '?')} — {nxt['miles']:.1f} mi"
                f"   ({len(shown)} stops this map)")

    @staticmethod
    def _stop_click_coords(stop: dict, side: str | None = None) -> tuple[float, float] | None:
        if side == "begin":
            bl, blo = stop.get("begin_lat"), stop.get("begin_lon")
            if bl is not None and blo is not None:
                return float(bl), float(blo)
        elif side == "end":
            el, elo = stop.get("end_lat"), stop.get("end_lon")
            if el is not None and elo is not None:
                return float(el), float(elo)
        anchor = MapSyncControllerMixin._stop_anchor_coords(stop)
        if anchor:
            return anchor
        bl, blo = stop.get("begin_lat"), stop.get("begin_lon")
        if bl is not None and blo is not None:
            return float(bl), float(blo)
        return None

    def _zoom_to_stop_click(self, stop: dict, side: str | None = None) -> None:
        """D5: recenter map on a tapped site at street-level zoom."""
        if not getattr(self, "_map_js_ready", False):
            return
        coords = self._stop_click_coords(stop, side)
        if coords:
            lat, lon = coords
            self.bridge.fly_to(lat, lon, SITE_CLICK_ZOOM)

    @staticmethod
    def _stop_anchor_coords(s: dict) -> tuple[float, float] | None:
        clat, clon = s.get("cross_lat"), s.get("cross_lon")
        if clat is not None and clon is not None:
            return float(clat), float(clon)
        lat, lon = s.get("lat"), s.get("lon")
        if lat is not None and lon is not None:
            return float(lat), float(lon)
        return None

    def _nearest_unpicked_stop(
        self, lat: float, lon: float, *, max_m: float = 750.0,
    ) -> tuple[str | None, str | None]:
        from road_router import _haversine_m

        picked = set(self._route_pick_uids)
        best_uid: str | None = None
        best_side: str | None = None
        best_d = max_m
        for s in self._pick_pool_stops():
            uid = str(s.get("uid") or "")
            if not uid or uid in picked:
                continue
            candidates: list[tuple[tuple[float, float], str | None]] = []
            bl, blo = s.get("begin_lat"), s.get("begin_lon")
            if bl is not None and blo is not None:
                candidates.append(((float(bl), float(blo)), "begin"))
            el, elo = s.get("end_lat"), s.get("end_lon")
            if el is not None and elo is not None:
                candidates.append(((float(el), float(elo)), "end"))
            for pt, side in candidates:
                d = _haversine_m(lat, lon, pt[0], pt[1])
                if d < best_d:
                    best_d = d
                    best_uid = uid
                    best_side = side
        return best_uid, best_side

    def _on_map_clicked(self, lat: float, lon: float) -> None:
        if self._manual_grab_mode:
            self._manual_grab_at(lat, lon)
            return
        if not self._section_pick_active():
            return
        uid, side = self._nearest_unpicked_stop(lat, lon)
        if uid:
            idx = self.state.index_of(uid)
            stop = self.state.stops[idx] if idx >= 0 else None
            self._route_pick_add(uid, side=side)
            if stop is not None:
                self._zoom_to_stop_click(stop, side)
            return
        self.statusBar().showMessage(
            "No site near that click — tap the blue or red dot (or lettered orange ring).",
            5000,
        )

    def _on_stop_clicked(self, uid: str):
        if self._manual_grab_mode:
            return
        if uid.startswith("install|"):
            real_uid = uid.split("|", 1)[1]
            idx = self.state.index_of(real_uid)
            if idx >= 0:
                stop = self.state.stops[idx]
                site_id = stop.get("id", "?")
                flat, flon = stop.get("field_lat"), stop.get("field_lon")
                src = str(stop.get("field_coord_source") or "gps")
                src_txt = "manual pin" if src == "manual" else "GPS grab"
                if flat is not None and flon is not None:
                    self.statusBar().showMessage(
                        f"Site {site_id} — {src_txt} at {float(flat):.6f}, {float(flon):.6f}",
                        10000,
                    )
                else:
                    self.statusBar().showMessage(f"Site {site_id} — install GPS pin", 8000)
                if self.pages.currentIndex() == 2:
                    self._select_install_stop(idx)
            return
        uid, side = self._parse_stop_click(str(uid).strip())
        if self._section_pick_active():
            by_uid = {str(s.get("uid") or ""): s for s in self.state.stops}
            if uid not in by_uid:
                self.statusBar().showMessage(
                    "That site is not in this job — pick a blue or red dot on the map.",
                    5000,
                )
                return
            pool = {str(s.get("uid") or "") for s in self._pick_pool_stops()}
            if uid not in pool:
                sheet = by_uid[uid].get("sheet") or "the other map"
                self.statusBar().showMessage(
                    f"That site is on {sheet} — cycle Map to pick that route.",
                    7000,
                )
                return
            self._route_pick_add(uid, side=side)
            self._zoom_to_stop_click(by_uid[uid], side)
            return
        idx, stop = self._stop_by_uid(uid)
        if stop is None:
            return
        self.statusBar().showMessage(self._stop_click_status(stop, idx, side), 10000)
        self._zoom_to_stop_click(stop, side)
        if self.pages.currentIndex() == 2:
            if idx < len(self.state.stops):
                self._select_install_stop(idx)
            return
        # Setup / Route / other tabs: show Excel site # only — stay on current tab.

    def _should_push_gps_bridge(
        self, lat: float, lon: float, heading: float | None,
    ) -> bool:
        import time as _time

        return should_push_gps_bridge(
            lat, lon, heading,
            last=self._last_gps_bridge,
            last_t=self._last_gps_bridge_t,
            now=_time.time(),
            heartbeat_s=self._gps_push_heartbeat_s,
            min_m=self._gps_push_min_m,
        )

    # ------------------------------------------------------------ GPS tick
    def _tick_gps(self):
        try:
            self._tick_gps_body()
        except Exception as exc:  # noqa: BLE001
            crash_log.log_error(exc, context="gps_tick")

    def _tick_gps_body(self):
        g = self.gps.latest()
        if g.get("fix") and g.get("lat") is not None:
            lat, lon = g["lat"], g["lon"]
            hdg = g.get("heading_display") or g.get("heading_locked") or g.get("heading")
            if self._should_push_gps_bridge(lat, lon, hdg):
                import time as _time
                self.bridge.send_gps({
                    "lat": lat, "lon": lon, "heading": hdg,
                    "heading_mode": g.get("heading_mode"), "speed_mps": g.get("speed_mps"),
                })
                self._last_gps_bridge = (lat, lon, hdg)
                self._last_gps_bridge_t = _time.time()
            self._update_compass_labels(g)
            self.status_gps.setText(f"GPS: FIX  {g.get('satellites', 0)} sats   {lat:.5f}, {lon:.5f}")
            if self._gps_follow or self._map_follow:
                self._update_follow_banner()
            if hasattr(self, "lbl_field_score") and not hasattr(self, "_gps_ready_refreshed"):
                self._gps_ready_refreshed = True
                self._refresh_field_ready()
            self._maybe_refresh_field_strip()
        elif g.get("connected"):
            self.status_gps.setText(f"GPS: searching... {g.get('satellites', 0)} sats (need clear sky)")
            self._maybe_refresh_field_strip()
        else:
            self.status_gps.setText("GPS: not detected (check USB receiver)")
            self._maybe_refresh_field_strip()

    @staticmethod
    def _moved(a, b, min_m: float = 4.0) -> bool:
        return coords_moved(a, b, min_m=min_m)

    @staticmethod
    def _heading_cardinal(deg: float | None) -> str:
        return heading_cardinal(deg)

    def _update_compass_labels(self, g: dict):
        hdg = g.get("heading_display") or g.get("heading_locked") or g.get("heading")
        mode = g.get("heading_mode") or "none"
        from ui.simple_mode import COMPACT_UI
        if hdg is None:
            txt = "No heading — drive briefly, then stop."
            sub = ""
        else:
            card = self._heading_cardinal(hdg)
            txt = f"{hdg:.0f}° ({card})"
            if COMPACT_UI:
                sub = ""
            elif mode == "locked":
                sub = "Stopped — locked heading (use for install direction)"
            elif mode == "moving":
                sub = "Moving — live GPS course"
            else:
                sub = "Slow/stop — averaging recent heading"
        if hasattr(self, "lbl_compass"):
            self.lbl_compass.setText(txt)
        if hasattr(self, "lbl_compass_sub") and self.lbl_compass_sub.parent():
            self.lbl_compass_sub.setText(sub)

    @staticmethod
    def _dist_m(lat1, lon1, lat2, lon2) -> float:
        return dist_m(lat1, lon1, lat2, lon2)
