"""Route controller mixin — P46 E1.5 extract from main.py."""

from __future__ import annotations

import time as _time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QListWidgetItem, QMessageBox, QProgressDialog

import road_router
from core import crash_log, ingest, routing, validate
from core import route_sections
from ui.paths import DATA_DIR
from ui.route_pick_dialog import RoutePickOrderDialog
from ui.setup_wizard import SetupWizard
from ui.simple_mode import BUILD_LABEL, SIMPLE_MODE
from ui.status_style import apply_active
from ui.threads import RouteApplyPickThread, RouteOptimizeThread, RouteRetraceThread


class RouteControllerMixin:
    @staticmethod
    def _h(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("role", "h")
        return lbl



    def _restore_build_button_if_idle(self) -> None:
        if not hasattr(self, "btn_build"):
            return
        rt = getattr(self, "_route_thread", None)
        if rt is not None and rt.isRunning():
            return
        self.btn_build.setEnabled(True)
        self.btn_build.setText(BUILD_LABEL)

    def _build_route_from_uploads(self):
        if not self.excel_paths or not self.est_paths:
            self._warn("Add at least one Excel/CSV and one .EST map first.")
            return
        self.statusBar().showMessage("BUILD ROUTE — reading Excel and .EST files…", 15000)
        if hasattr(self, "btn_build"):
            self.btn_build.setEnabled(False)
            self.btn_build.setText("BUILDING ROUTE…")
        try:
            sites = ingest.parse_excel_sites(self.excel_paths)
        except ingest.ExcelEngineMissing as exc:
            self._warn(str(exc))
            self._restore_build_button_if_idle()
            return
        except ingest.IngestFileReadError as exc:
            self._warn(str(exc))
            self._restore_build_button_if_idle()
            return
        except Exception as exc:  # noqa: BLE001
            self._warn(f"Could not read Excel/CSV: {exc}")
            self._restore_build_button_if_idle()
            return
        if not sites:
            self._warn("No site coordinates found in the Excel/CSV (need begin lat/lon columns).")
            self._restore_build_button_if_idle()
            return
        cfgs = self._est_configs()
        stops = ingest.match_est_files(cfgs, sites, self.state.home)
        if not stops:
            self._warn("0 sites matched. Check that site IDs appear in the .EST files.")
            self._restore_build_button_if_idle()
            return

        report = validate.validate_build(
            self.excel_paths, cfgs, sites, stops,
            home=tuple(self.state.home),
            default_home=self.state.default_home,
        )
        if not report["ok"]:
            self._warn("Cannot build route:\n\n" + "\n".join(report["errors"]))
            self._restore_build_button_if_idle()
            return
        if report["warnings"]:
            body = "; ".join(report["warnings"][:4])
            self.statusBar().showMessage(f"Build note: {body}", 12000)
            from core.state import RouteState
            factory = RouteState.is_factory_home(*self.state.home)
            # SIMPLE_MODE used to skip this dialog — status bar alone was missed on the truck.
            title = "Set starting point first" if factory else "Review before build"
            prompt = "\n".join(report["warnings"])
            if factory:
                prompt += (
                    "\n\nSet home on Setup (USB GPS, address search, or Save as my start), "
                    "then BUILD again.\n\nBuild anyway with the wrong origin?"
                )
            else:
                prompt += "\n\nBuild route anyway?"
            if QMessageBox.question(
                self, title, prompt,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            ) != QMessageBox.Yes:
                self._restore_build_button_if_idle()
                return

        self.state.active_files = route_sections.section_labels(stops)

        old_by_uid = {s["uid"]: s for s in self.state.stops}
        old_by_day = {
            (route_sections.canonical_section(s.get("sheet")), str(s.get("id") or "")): s
            for s in self.state.stops
        }

        def _prior(fresh: dict) -> dict | None:
            hit = old_by_uid.get(fresh.get("uid"))
            if hit is not None:
                return hit
            return old_by_day.get(
                (route_sections.canonical_section(fresh.get("sheet")), str(fresh.get("id") or ""))
            )

        matched = {id(p) for p in (_prior(f) for f in stops) if p is not None}
        orphans = [
            s for s in self.state.stops
            if id(s) not in matched and (
                s.get("installed") or s.get("skipped") or s.get("picked_up")
                or s.get("field_lat") is not None)
        ]
        if orphans:
            names = ", ".join(
                f"Site {s.get('id', '?')}" + (f" ({s.get('sheet')})" if s.get("sheet") else "")
                for s in orphans[:8])
            more = f" +{len(orphans) - 8} more" if len(orphans) > 8 else ""
            if QMessageBox.question(
                self, "Install data would be dropped",
                f"{len(orphans)} site(s) with install/pickup/GPS data are NOT in the "
                f"current Excel/.EST files:\n{names}{more}\n\n"
                "Building now removes them from this shift (and from the export).\n"
                "Tap No, then Export handoff first — or re-add their files.\n\n"
                "Build anyway and drop them?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            ) != QMessageBox.Yes:
                self._restore_build_button_if_idle()
                return
        merged = [ingest.merge_stop_progress(_prior(f), f) for f in stops]
        kept = sum(1 for f in merged if f["uid"] in old_by_uid
                   and (old_by_uid[f["uid"]].get("installed") or old_by_uid[f["uid"]].get("skipped")))
        if kept:
            self.statusBar().showMessage(
                f"Re-build: kept install/pickup data on {kept} site(s).", 6000)

        rebuild_sheet = None
        labels = route_sections.section_labels(merged, self.state.active_files)
        if route_sections.multi_section(merged, self.state.active_files):
            cur = route_sections.canonical_section(getattr(self.state, "map_day_filter", "") or "")
            if not route_sections.is_all_days(cur) and cur in labels:
                rebuild_sheet = cur
        self.state.stops = route_sections.preserve_other_section_orders(
            list(old_by_uid.values()), merged, rebuild_sheet=rebuild_sheet)
        keep = set(self.state.active_files)
        stored = getattr(self.state, "routes_by_map", None) or {}
        remapped: dict = {}
        for key, route in stored.items():
            canon = route_sections.canonical_section(key)
            if canon in keep and canon not in remapped:
                remapped[canon] = route
        self.state.routes_by_map = remapped
        if rebuild_sheet:
            self.state.routes_by_map.pop(rebuild_sheet, None)
        else:
            self.state.routes_by_map = {}
        self.state.days_merged = False
        self.state.merged_route = None
        self._map_preview_stops = []
        self.state.route = route_sections.empty_route()
        self._persist_shift(quiet=True)
        self.current_index = min(self.current_index, max(0, len(self.state.stops) - 1))
        self._update_right(force_map=True)
        self._route_pick_suspended = None
        self._go_page(1)
        self._refresh_day_filter()
        self._refresh_route_list()
        self._push_state(fit=True)
        # Stop order is always the operator's map clicks. No auto-order.
        two_maps = len(labels) >= 2 and rebuild_sheet is None
        self._offer_merge_after_build = two_maps
        self._pick_build_queue = []
        if rebuild_sheet:
            self._set_route_section(rebuild_sheet, persist=False)
            self._pick_build_queue = []
            self._offer_merge_after_build = False
        elif two_maps:
            self._pick_build_queue = list(labels)
            self._set_route_section(labels[0], persist=False)
        else:
            self._focus_route_section_for_pick()
        self._restore_build_button_if_idle()
        self._begin_route_pick(self.state.stops)

    def _start_pick_route_from_route_tab(self) -> None:
        """Manual pick order — same click-to-order path as Build."""
        stops = self._stops_from_uploads_merged() or list(self.state.stops)
        if not stops:
            self._warn("Load Excel + .EST on Setup first (or resume a saved shift).")
            return
        self._begin_route_pick(stops)

    def _start_auto_build_queue(
        self,
        jobs: list[tuple[str, list[dict]]],
        *,
        stay_all_days: bool = True,
    ) -> None:
        """Auto-optimize each map independently, then show All days together."""
        jobs = [(lab, list(stops)) for lab, stops in jobs if lab and stops]
        if not jobs:
            self._warn("No sites on this map to build.")
            self._restore_build_button_if_idle()
            return
        self._auto_build_queue = jobs
        self._auto_build_stay_all_days = stay_all_days
        self._run_next_auto_build()

    def _run_next_auto_build(self) -> None:
        queue = getattr(self, "_auto_build_queue", None) or []
        if not queue:
            return
        label, _ = queue[0]
        stops = route_sections.stops_for_section(self.state.stops, label)
        done_n = int(getattr(self, "_auto_build_done_n", 0) or 0)
        if done_n == 0:
            self._auto_build_queue_total = len(queue)
        self._optimize_and_route(
            stops or queue[0][1],
            section=label,
            queue_pos=done_n + 1,
            queue_total=int(getattr(self, "_auto_build_queue_total", len(queue)) or 1),
        )

    def _write_setup_install_html(self, *, mode: str = "both") -> list[str]:
        from core import maps_links

        labels = [
            lab for lab in self._route_section_labels()
            if not route_sections.is_all_days(lab)
        ]
        stored = self._ensure_routes_by_map()
        miles_by = {
            lab: float((stored.get(lab) or {}).get("miles") or 0) for lab in labels
        }
        try:
            return maps_links.write_install_html_bundle(
                list(self.state.stops),
                DATA_DIR,
                self.state.profile,
                labels=labels,
                miles_by_sheet=miles_by,
                mode=mode,
            )
        except Exception as exc:  # noqa: BLE001
            crash_log.log_error(exc, context="setup_install_html")
            self.statusBar().showMessage(f"HTML install list failed: {exc}", 8000)
            return []

    def _finish_auto_build_queue(self, last_section: str) -> None:
        self._auto_build_queue = []
        self._auto_build_done_n = 0
        stay_all = bool(getattr(self, "_auto_build_stay_all_days", True))
        self._refresh_day_filter()
        if stay_all and self._route_section_active():
            self._set_route_section(route_sections.DAY_FILTER_ALL, persist=False)
        elif last_section:
            self._set_route_section(last_section, persist=False)
        self._refresh_route_list()
        self._push_state(fit=True)
        if getattr(self, "_offer_merge_after_build", False) and self._route_section_active():
            self._offer_merge_after_build = False
            if self._offer_merge_days():
                return
        self._notify_install_html()

    def _notify_install_html(self) -> None:
        paths = self._write_setup_install_html(mode="both")
        if not paths:
            return
        names = "\n".join(paths)
        self._info(
            "HTML install lists saved (merged All days + each map separate):\n\n"
            f"{names}\n\nSend the file you need to your phone."
        )
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(paths[-1]))

    def _merge_days_best_route(self) -> None:
        """One new best driving order from every site on both maps."""
        stops = list(self.state.stops)
        if not route_sections.multi_section(stops, self.state.active_files):
            self._warn("Load two .EST maps before merging days.")
            return
        self._merge_build_pending = True
        self._set_route_section(route_sections.DAY_FILTER_ALL, persist=False)
        self._optimize_and_route(stops)

    def _commit_merged_day_routes(
        self,
        ordered: list[dict],
        route: dict,
        routes_by_section: dict,
    ) -> None:
        """Save the merged line and a fresh route for each day in that new order.

        Days missing from ``routes_by_section`` lose their pre-merge line so
        Day view cannot keep showing a route for the old visit order.
        """
        self.state.stops = list(ordered)
        self.state.days_merged = True
        self.state.merged_route = dict(route)
        self.state.route = dict(route)
        stored = self._ensure_routes_by_map()
        labels = route_sections.section_labels(
            self.state.stops, getattr(self.state, "active_files", None))
        fresh = {
            route_sections.canonical_section(key): value
            for key, value in (routes_by_section or {}).items()
            if isinstance(value, dict)
        }
        for key in list(stored):
            if route_sections.canonical_section(key) in labels:
                stored.pop(key, None)
        for label in labels:
            built = fresh.get(label)
            stored[label] = dict(built) if isinstance(built, dict) else route_sections.empty_route()

    @staticmethod
    def _street_label(s: dict) -> str:
        st = str(s.get("street", "")).strip()
        if not st or st.lower() in ("nan", "none", "nat"):
            return f"Site {s.get('id', '')}"
        return st

    def _stop_time_suffix(self, stop_index: int, mark: str, *, leg_index: int | None = None) -> str:
        """Drive + setup clock on a route-list row (open stops only).

        ``leg_index`` is the stop's place in the route on screen. A day filter's
        legs are 0..n-1 for that day, not the index in the full stop list.
        """
        try:
            from core import time_est
            section = self._section_stops_for_legs()
            time_est.ensure(
                self.state.route, section, getattr(self.state, "home", None))
            legs = self.state.route.get("site_legs") or []
            li = stop_index if leg_index is None else leg_index
            leg = legs[li] if 0 <= li < len(legs) else None
            pending = time_est.pending_stops(section)
            last_uid = pending[-1].get("uid") if pending else None
            if 0 <= li < len(section):
                uid = section[li].get("uid")
            elif 0 <= stop_index < len(self.state.stops):
                uid = self.state.stops[stop_index].get("uid")
            else:
                uid = None
            return time_est.stop_suffix(
                leg,
                first=li == 0,
                last=bool(last_uid) and uid == last_uid,
                remaining=mark == "--",
                home_back_min=float(self.state.route.get("home_back_min") or 0),
            )
        except Exception:
            return ""

    def _ensure_route_pick_dialog(self) -> RoutePickOrderDialog:
        if self._route_pick_dialog is None:
            dlg = RoutePickOrderDialog(self)
            dlg.order_changed.connect(self._route_pick_set_order)
            dlg.apply_requested.connect(self._route_pick_apply)
            self._route_pick_dialog = dlg
        return self._route_pick_dialog

    def _enter_pick_map_focus(self) -> None:
        """Give the map most of the window — pick is click-driven, not sidebar forms."""
        if not self._pick_layout_active:
            self._pick_splitter_saved = list(self._splitter.sizes())
            self._pick_layout_active = True
        total = max(800, sum(self._splitter.sizes()))
        self._splitter.setSizes([220, max(500, total - 220)])

    def _exit_pick_map_focus(self) -> None:
        if self._pick_layout_active and self._pick_splitter_saved:
            self._splitter.setSizes(self._pick_splitter_saved)
        self._pick_layout_active = False
        self._pick_splitter_saved = None

    def _show_route_pick_dialog(self) -> None:
        dlg = self._ensure_route_pick_dialog()
        if not dlg.isVisible():
            dlg.show()
        if self.isVisible():
            margin = 20
            # Left side — the map is on the right, and this window must not cover the dots.
            x = self.geometry().left() + margin
            y = self.geometry().top() + 72
            dlg.move(max(margin, x), max(margin, y))

    def _hide_route_pick_dialog(self) -> None:
        if self._route_pick_dialog is not None:
            self._route_pick_dialog.hide()

    def _suspend_route_pick(self) -> None:
        """Leave Route — stop pick clicks without throwing away the order."""
        if not getattr(self, "_route_pick_mode", False):
            return
        dlg = getattr(self, "_route_pick_dialog", None)
        by_map: dict[str, dict] = {}
        for key, val in (getattr(self, "_route_pick_by_map", None) or {}).items():
            if not isinstance(val, dict):
                continue
            by_map[str(key)] = {
                "uids": list(val.get("uids") or []),
                "sides": dict(val.get("sides") or {}),
            }
        self._route_pick_suspended = {
            "uids": list(self._route_pick_uids),
            "sides": dict(self._route_pick_sides),
            "section": str(getattr(self, "_route_pick_section", "") or ""),
            "by_map": by_map,
            "dialog_open": bool(dlg is not None and dlg.isVisible()),
        }
        self._route_pick_mode = False
        self._exit_pick_map_focus()
        self._hide_route_pick_dialog()
        n = len(self._route_pick_uids)
        chosen = f"{n} stop{'s' if n != 1 else ''} already chosen. " if n else ""
        self.statusBar().showMessage(
            f"Route pick paused. {chosen}Open Route to continue the same order.",
            8000,
        )

    def _resume_route_pick(self) -> None:
        """Back on Route — same unapplied order, pick clicks work again."""
        saved = getattr(self, "_route_pick_suspended", None)
        if not saved:
            return
        self._route_pick_suspended = None
        self._route_pick_mode = True
        self._route_pick_uids = list(saved.get("uids") or [])
        self._route_pick_sides = dict(saved.get("sides") or {})
        self._route_pick_section = str(saved.get("section") or "")
        self._route_pick_by_map = dict(saved.get("by_map") or {})
        if saved.get("dialog_open"):
            self._show_route_pick_dialog()
        self._refresh_route_pick_ui()
        n = len(self._route_pick_uids)
        self.statusBar().showMessage(
            f"Route pick is back — {n} stop{'s' if n != 1 else ''} already chosen.",
            6000,
        )

    def _route_pick_set_order(self, uids: list[str]) -> None:
        if not self._route_pick_mode:
            return
        by_uid = {s["uid"]: s for s in self.state.stops}
        prev = set(self._route_pick_uids)
        nxt = set(uids)
        for uid in prev - nxt:
            self._route_pick_sides.pop(uid, None)
            s = by_uid.get(uid)
            if s:
                s.pop("pick_cross_locked", None)
                for key in ("cross_lat", "cross_lon", "cross_side"):
                    s.pop(key, None)
        self._route_pick_uids = [u for u in uids if u in by_uid]
        self._refresh_route_pick_ui(sync_dialog=False)
        self._refresh_route_list()
        self._push_state()

    def _begin_route_pick(self, stops: list[dict]) -> None:
        self._route_pick_suspended = None
        self._end_manual_grab(silent=True)
        from core.map_display import enrich_segment_paths

        self.state.stops = list(stops)
        self._focus_route_section_for_pick()
        self._route_pick_mode = True
        self._route_pick_uids = []
        self._route_pick_sides = {}
        if self._day_filter_active():
            self._route_pick_section = route_sections.canonical_section(
                self._day_filter_value())
        # Drop a finished line on this map. Otherwise the first site click is
        # ignored ("route already applied") while the status line still changes.
        self._clear_visible_section_route_for_pick()
        if self.chk_show_segments.isChecked():
            enrich_segment_paths(self.state.stops, DATA_DIR)
        self._go_page(1)
        self._enter_pick_map_focus()
        self._refresh_route_pick_ui()
        self._refresh_route_list()
        self._push_state(fit=True)
        extra = ""
        queue = getattr(self, "_pick_build_queue", None) or []
        if len(queue) > 1:
            extra = f" After Apply, pick {queue[1]} next."
        elif self._route_section_active():
            extra = " Use Day 1, Day 2, or Together — each day keeps its own route."
        if any(str(s.get("day_source") or "") == "order" for s in self.state.stops):
            extra += " Day 1 is the first .EST file, Day 2 the second."
        self.statusBar().showMessage(
            f"Pick route on map — {self._pick_prompt_text()}. "
            f"Blue = begin, red = end.{extra}",
            14000)

    def _clear_visible_section_route_for_pick(self) -> None:
        """Forget this map's applied line so the next site click is stop 1."""
        section = self._pick_apply_section()
        if section:
            self._ensure_pick_by_map().pop(section, None)
            self._ensure_routes_by_map().pop(section, None)
        self.state.route = route_sections.empty_route()

    def _route_pick_click(self, uid: str, side: str | None, *, from_list: bool = False) -> None:
        """Map or list click during pick — always starts or extends the order.

        A stored route used to make ``_section_pick_active`` false, so the click
        only changed the status bar. That was a false update: no stop was added.
        """
        if not getattr(self, "_route_pick_mode", False):
            return
        uid = str(uid or "").strip()
        if not uid:
            return
        by_uid = {str(s.get("uid") or ""): s for s in self.state.stops}
        stop = by_uid.get(uid)
        if stop is None:
            self.statusBar().showMessage(
                "That site is not in this job — pick a blue or red dot on the map.",
                5000,
            )
            return
        pool = {str(s.get("uid") or "") for s in self._pick_pool_stops()}
        if uid not in pool:
            if self._route_pick_uids:
                sheet = stop.get("sheet") or "the other map"
                self.statusBar().showMessage(
                    f"That site is on {sheet} — finish this map, or Cycle Map.",
                    7000,
                )
                return
            sheet = str(stop.get("sheet") or "")
            if sheet and not route_sections.is_all_days(sheet):
                self._set_route_section(sheet, persist=False)
            self._clear_visible_section_route_for_pick()
        elif not self._section_pick_active():
            self._clear_visible_section_route_for_pick()
        if from_list or side not in ("begin", "end"):
            self._route_pick_add_from_list(uid)
        else:
            self._route_pick_add(uid, side=side)
        self._zoom_to_stop_click(stop, side if side in ("begin", "end") else None)

    def _refresh_route_pick_ui(self, *, sync_dialog: bool = True) -> None:
        if not hasattr(self, "lbl_pick_status"):
            return
        n = len(self._route_pick_uids)
        total = self._pick_pool_total()
        session = self._route_pick_mode
        on = self._section_pick_active()
        if hasattr(self, "sec_pick") and self.sec_pick is not None and SIMPLE_MODE:
            self.sec_pick.setVisible(on)
        self.btn_pick_apply.setEnabled(on and n > 0 and n >= total)
        self.btn_pick_clear.setEnabled(on and n > 0)
        if hasattr(self, "btn_pick_order_win"):
            self.btn_pick_order_win.setEnabled(on)
            self.btn_pick_order_win.setVisible(on)
        if hasattr(self, "pick_combo_row"):
            self.pick_combo_row.setVisible(not on)
        if hasattr(self, "pick_side_row"):
            self.pick_side_row.setVisible(on)
            self._sync_pick_side_buttons()
        if on:
            self._enter_pick_map_focus()
        elif self._pick_layout_active:
            self._exit_pick_map_focus()
        self._refresh_pick_site_combo()
        if not on:
            if session and self._route_section_active():
                day = self._day_filter_value()
                apply_active(
                    self.lbl_pick_status,
                    False,
                    f"{day} route is applied. Cycle Map to keep picking the other .EST.",
                )
            else:
                apply_active(
                    self.lbl_pick_status,
                    False,
                    "Route applied. Numbers on the map match drive order. "
                    f"Re-plan with {BUILD_LABEL} on Setup.",
                )
            if sync_dialog:
                self._hide_route_pick_dialog()
            return
        letters = self._pick_site_letters()
        if n >= total:
            pick_text = f"{self._section_pick_tag()}All {total} stops picked on the map. Tap Apply route."
        else:
            pick_text = (
                f"{self._pick_prompt_text()} — tap a blue (begin) or red (end) dot. "
                f"Order updates in the stop list.")
        apply_active(self.lbl_pick_status, True, pick_text)
        dlg = self._route_pick_dialog
        if sync_dialog and on and dlg is not None and dlg.isVisible():
            by_uid = {s["uid"]: s for s in self._pick_pool_stops()}
            dlg.sync_from_parent(
                uids=list(self._route_pick_uids),
                stops_by_uid=by_uid,
                letters=letters,
                street_label=self._street_label,
                total=total,
                prompt=self._pick_prompt_text(),
                pick_sides=dict(self._route_pick_sides),
            )

    def _refresh_pick_site_combo(self) -> None:
        if not hasattr(self, "combo_pick_site"):
            return
        n = len(self._route_pick_uids)
        total = self._pick_pool_total()
        on = self._section_pick_active()
        self.combo_pick_site.blockSignals(True)
        self.combo_pick_site.clear()
        if not on:
            self.combo_pick_site.setEnabled(False)
            self.lbl_pick_slot.setText("Stop:")
            self.combo_pick_site.addItem("(not picking)")
            self.combo_pick_site.blockSignals(False)
            return
        letters = self._pick_site_letters()
        picked = set(self._route_pick_uids)
        if n >= total:
            self.lbl_pick_slot.setText("Done:")
            self.combo_pick_site.setEnabled(False)
            self.combo_pick_site.addItem("All stops assigned")
            self.combo_pick_site.blockSignals(False)
            return
        self.lbl_pick_slot.setText(f"Stop {n + 1}:")
        self.combo_pick_site.setEnabled(True)
        self.combo_pick_site.addItem("— choose site —", None)
        for s in self._pick_pool_stops():
            if s["uid"] in picked:
                continue
            letter = letters.get(s["uid"], "?")
            label = f"[{letter}] Site {s['id']} — {self._street_label(s)}"
            self.combo_pick_site.addItem(label, s["uid"])
        self.combo_pick_site.setCurrentIndex(0)
        self.combo_pick_site.blockSignals(False)

    def _on_pick_combo_chosen(self, index: int) -> None:
        if not self._route_pick_mode or index <= 0:
            return
        uid = self.combo_pick_site.itemData(index)
        if uid:
            self._route_pick_add_from_list(str(uid))

    def _set_pick_side_mode(self, mode: str) -> None:
        """Begin / End — applies to the next left-list or combo pick.

        Map dots ignore this and use the end you tapped (blue = begin, red = end).
        """
        if mode not in ("begin", "end"):
            return
        self._pick_side_mode = mode
        self._sync_pick_side_buttons()
        labels = {
            "begin": "Begin (blue) — next list pick uses the begin end of the segment",
            "end": "End (red) — next list pick uses the end of the segment",
        }
        self.statusBar().showMessage(labels[mode], 6000)

    def _sync_pick_side_buttons(self) -> None:
        mode = getattr(self, "_pick_side_mode", "begin")
        if mode not in ("begin", "end"):
            mode = "begin"
            self._pick_side_mode = mode
        for attr, val in (
            ("btn_pick_side_begin", "begin"),
            ("btn_pick_side_end", "end"),
        ):
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.setChecked(mode == val)

    def _route_pick_add_from_list(self, uid: str) -> None:
        """Left list / combo — Begin or End only. Map clicks set the side themselves."""
        by_uid = {str(s.get("uid") or ""): s for s in self.state.stops}
        stop = by_uid.get(uid)
        if stop is None:
            return
        mode = getattr(self, "_pick_side_mode", "begin")
        if mode not in ("begin", "end"):
            mode = "begin"
        self._route_pick_add(uid, side=mode, lock_side=True)

    def _route_pick_add(
        self, uid: str, *, side: str | None = None, lock_side: bool | None = None,
    ) -> None:
        if not self._route_pick_mode:
            return
        uid = str(uid).strip()
        if not uid:
            return
        if uid in self._route_pick_uids:
            self.statusBar().showMessage("Already in your route — pick the next site.", 4000)
            return
        by_uid = {str(s.get("uid") or ""): s for s in self.state.stops}
        stop = by_uid.get(uid)
        if stop is None:
            self.statusBar().showMessage(
                "Unknown site — pick a blue or red dot on the map.", 5000)
            return
        pool_uids = {str(s.get("uid") or "") for s in self._pick_pool_stops()}
        if uid not in pool_uids:
            sheet = stop.get("sheet") or "the other map"
            self.statusBar().showMessage(
                f"That site is on {sheet} — cycle Map to pick that route.", 7000)
            return
        if stop and side in ("begin", "end"):
            if lock_side is None:
                lock_side = True
            self._apply_pick_side(stop, side, lock=bool(lock_side))
            if lock_side:
                self._route_pick_sides[uid] = side
            else:
                self._route_pick_sides.pop(uid, None)
        self._route_pick_uids.append(uid)
        n = len(self._route_pick_uids)
        total = self._pick_pool_total()
        self._refresh_route_pick_ui()
        self._refresh_route_list()
        self._push_state()
        side_note = ""
        if side in ("begin", "end"):
            side_note = f" ({side})"
        if n >= total:
            self.statusBar().showMessage(
                f"Stop {n}{side_note} added — all sites chosen. Tap Apply route.", 8000)
        else:
            self.statusBar().showMessage(
                f"Stop {n}{side_note} added — {self._pick_prompt_text()}.", 8000)

    def _route_pick_clear(self) -> None:
        if not self._route_pick_mode:
            return
        self._route_pick_uids = []
        self._route_pick_sides = {}
        for s in self._pick_pool_stops():
            s.pop("pick_cross_locked", None)
            for key in ("cross_lat", "cross_lon", "cross_side"):
                s.pop(key, None)
        self._refresh_route_pick_ui()
        self._refresh_route_list()
        self._push_state()
        self.statusBar().showMessage(
            f"Picks cleared — {self._pick_prompt_text()}.", 6000)

    def _sync_pick_order_from_dialog(self) -> None:
        """Adopt the order window's list order (source of truth for sequence).

        Guarantees a drag-reorder ("start from the top") is honored on Apply,
        independent of drop-signal timing. Only applies on a pure reorder (same
        set of stops) so it never clobbers an out-of-sync selection.
        """
        if self._route_pick_dialog is None:
            return
        dlg_order = self._route_pick_dialog.current_order()
        if dlg_order and set(dlg_order) == set(self._route_pick_uids):
            self._route_pick_uids = list(dlg_order)

    def _route_pick_apply(self) -> None:
        pool = self._pick_pool_stops()
        total = len(pool)
        self._sync_pick_order_from_dialog()
        if not self._route_pick_mode or not self._route_pick_uids:
            self._warn("Pick stop 1 on the map (blue or red dot) or from the dropdown.")
            return
        if len(self._route_pick_uids) < total:
            self._warn(
                f"Pick all {total} stops on this map before Apply "
                f"({len(self._route_pick_uids)} chosen so far).")
            return
        if self._route_thread is not None and self._route_thread.isRunning():
            self.statusBar().showMessage("Route build already running…", 4000)
            return
        if not road_router.has_graph(DATA_DIR):
            self.statusBar().showMessage(
                "No road map yet — applying your order as straight-line miles. "
                "Add a road map on Setup for real streets.", 9000)

        import time as _time

        dlg = QProgressDialog(
            "Applying your route order on real streets…",
            "Cancel", 0, 0, self)
        dlg.setWindowTitle("Apply route")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setMinimumWidth(420)
        t0 = _time.time()

        thread = RouteApplyPickThread(
            tuple(self.state.home),
            list(self._route_pick_uids),
            list(pool),
            DATA_DIR,
            dict(self._route_pick_sides),
        )
        self._route_thread = thread
        self.btn_pick_apply.setEnabled(False)
        if self._route_pick_dialog is not None:
            self._route_pick_dialog.btn_apply.setEnabled(False)

        def on_progress(msg: str):
            dlg.setLabelText(f"{msg}\n\nElapsed: {int(_time.time() - t0)}s")

        def _restore_apply_btn():
            if self._route_pick_mode:
                n = len(self._route_pick_uids)
                total_st = self._pick_pool_total()
                enabled = n > 0 and n >= total_st
                self.btn_pick_apply.setEnabled(enabled)
                if self._route_pick_dialog is not None:
                    self._route_pick_dialog.btn_apply.setEnabled(enabled)

        def done(res: dict):
            dlg.close()
            self._route_thread = None
            _restore_apply_btn()
            if not res.get("ok"):
                err = f"Apply route failed: {res.get('error', 'unknown')}"
                if self.state.offline_mode:
                    self._field_notice(err)
                else:
                    self._warn(err)
                if res.get("trace"):
                    print(res["trace"])
                return
            section = self._pick_apply_section()
            self.state.stops = route_sections.merge_section_order(
                self.state.stops, res["order"])
            self.state.route = res["route"]
            if section:
                self._ensure_routes_by_map()[section] = dict(res["route"])
                self._ensure_pick_by_map().pop(section, None)
            self._route_pick_suspended = None
            self._route_pick_mode = False
            self._route_pick_uids = []
            self._route_pick_sides = {}
            self._exit_pick_map_focus()
            self._hide_route_pick_dialog()
            self._persist_shift(quiet=True)
            self._refresh_route_list()
            self._refresh_route_pick_ui()
            self._refresh_route_summary_ui()
            self._refresh_field_ready()
            self._push_state(fit=True)
            miles = res["route"].get("miles", 0.0)
            route_res = res["route"]
            applied_n = len(res["order"])
            if route_res.get("graph_uncovered"):
                trace_note = "(straight-line — road map does not cover this job area)"
            elif route_res.get("graph"):
                trace_note = "(street-traced sites)"
            else:
                trace_note = "(straight-line — download road map on Setup)"
            other = ""
            if self._route_section_active():
                labels = self._route_section_labels()
                rest = [x for x in labels if x != section]
                if rest:
                    other = f" Cycle Map to {rest[0]} — that route is unchanged."
            self.statusBar().showMessage(
                f"Route applied: {applied_n} stops, {miles:.1f} mi {trace_note}.{other}",
                12000,
            )
            if route_res.get("graph_uncovered"):
                self.statusBar().showMessage(
                    f"Route applied: {applied_n} stops, {miles:.1f} mi "
                    "(straight-line — saved road map is for a different job). "
                    "Setup → Download roads with this job loaded, then Build again for real streets.",
                    14000)
                QMessageBox.warning(
                    self,
                    "Road map does not cover this job",
                    f"Applied {applied_n} stops ({miles:.1f} mi) as straight-line only.\n\n"
                    "The saved road_graph.graphml is for a different area — miles and "
                    "street order will be wrong until you fix it.\n\n"
                    "On Setup: Download road map while this Excel/.EST job is loaded, "
                    "then Apply / Build again for real streets.",
                )
            if hasattr(self, "btn_build"):
                self.btn_build.setEnabled(True)
                self.btn_build.setText(BUILD_LABEL)
            self._continue_pick_or_merge(section)

        def canceled():
            self._stop_worker(thread)
            dlg.close()
            self._route_thread = None
            _restore_apply_btn()
            self.statusBar().showMessage("Apply route cancelled.", 4000)

        dlg.canceled.connect(canceled)
        thread.progress_text.connect(on_progress)
        thread.finished_result.connect(done)
        thread.start()
        dlg.show()
        on_progress("Starting…")

    def _continue_pick_or_merge(self, just_applied: str) -> None:
        """After a manual Apply, pick the next day or offer merge."""
        queue = list(getattr(self, "_pick_build_queue", None) or [])
        if just_applied and just_applied in queue:
            queue = [lab for lab in queue if lab != just_applied]
            self._pick_build_queue = queue
        if queue:
            nxt = queue[0]
            self.statusBar().showMessage(
                f"{just_applied or 'Map'} saved. Now pick {nxt} on the map.", 12000)
            self._set_route_section(nxt, persist=False)
            QTimer.singleShot(0, lambda: self._begin_route_pick(self.state.stops))
            return
        if getattr(self, "_offer_merge_after_build", False) and self._route_section_active():
            self._offer_merge_after_build = False
            QTimer.singleShot(0, self._offer_merge_days)

    def _highlight_stop_uid(self) -> str | None:
        if self._manual_grab_mode and self.state.stops and self.current_index < len(self.state.stops):
            uid = str(self.state.stops[self.current_index].get("uid") or "")
            return uid or None
        nxt = self._next_leg_payload()
        return nxt["to_uid"] if nxt else None

    def _optimize_and_route(
        self,
        stops,
        *,
        section: str = "",
        queue_pos: int = 1,
        queue_total: int = 1,
    ):
        if self._route_thread is not None and self._route_thread.isRunning():
            self.statusBar().showMessage("Route build already running…", 4000)
            return
        rt = getattr(self, "_retrace_thread", None)
        if rt is not None and rt.isRunning():
            self.statusBar().showMessage("Wait — route re-trace still running…", 4000)
            return
        self._route_pick_suspended = None
        self._route_pick_mode = False
        self._route_pick_uids = []
        self._route_pick_sides = {}
        self._exit_pick_map_focus()
        self._hide_route_pick_dialog()
        if not road_router.has_graph(DATA_DIR):
            self.statusBar().showMessage(
                "No road map yet — building your route now as straight-line miles. "
                "Add a road map on Setup (Download roads / Import .graphml) for real streets.",
                9000)

        tag = f"{section} — " if section else ""
        queue_bit = f" ({queue_pos}/{queue_total})" if queue_total > 1 else ""
        dlg = QProgressDialog(
            f"Building {tag}route{queue_bit} — zone sweep from your start point...",
            "Cancel", 0, 0, self)
        dlg.setWindowTitle("Building route")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setMinimumWidth(420)

        import time as _time
        t0 = _time.time()
        etimer = QTimer(self)
        if hasattr(self, "btn_build"):
            self.btn_build.setEnabled(False)
            self.btn_build.setText("BUILDING ROUTE…")
        start = None
        if hasattr(self, "gps"):
            from gps_reader import fix_from_snapshot

            start = fix_from_snapshot(self.gps.latest())
        thread = RouteOptimizeThread(
            list(stops), tuple(self.state.home), DATA_DIR, start=start,
            refresh_sections=bool(getattr(self, "_merge_build_pending", False)),
        )
        self._route_thread = thread
        build_section = section
        queued = bool(getattr(self, "_auto_build_queue", None))

        def _restore_build_btn():
            if hasattr(self, "btn_build"):
                self.btn_build.setEnabled(True)
                self.btn_build.setText(BUILD_LABEL)

        def on_progress(msg: str):
            dlg.setLabelText(
                f"{tag}{msg}{queue_bit}\n\nElapsed: {int(_time.time() - t0)}s")

        def tick():
            pass  # progress_text from worker updates the label

        def done(res):
            etimer.stop()
            dlg.close()
            self._route_thread = None
            if not res.get("ok"):
                _restore_build_btn()
                self._auto_build_queue = []
                self._auto_build_done_n = 0
                self._merge_build_pending = False
                err = f"Routing failed: {res.get('error', 'unknown')}"
                if self.state.offline_mode:
                    self._field_notice(err)
                else:
                    self._warn(err)
                if res.get("trace"):
                    print(res["trace"])
                return
            ordered = res["order"]
            if getattr(self, "_merge_build_pending", False):
                self._merge_build_pending = False
                self._commit_merged_day_routes(
                    ordered, res["route"], res.get("routes_by_section") or {})
                self._set_route_section(route_sections.DAY_FILTER_ALL, persist=False)
            elif build_section and not route_sections.is_all_days(build_section):
                self.state.stops = route_sections.merge_section_order(
                    self.state.stops, ordered)
                self._ensure_routes_by_map()[build_section] = dict(res["route"])
                if self._day_filter_value() == build_section:
                    self.state.route = dict(res["route"])
            else:
                self.state.stops = ordered
                self.state.route = res["route"]
            self.current_index = min(self.current_index, max(0, len(self.state.stops) - 1))
            self._persist_shift(quiet=True)
            self._refresh_route_list()
            self._refresh_day_filter()
            self._update_right(force_map=True)
            self._push_state(fit=True)
            miles = res["route"].get("miles", 0.0)
            r = res["route"]
            uncovered = bool(r.get("graph_uncovered"))
            if r.get("graph"):
                kind = "traced on real streets"
                failed = int(r.get("failed_legs") or 0)
                if failed:
                    kind += f" ({failed} leg(s) need road map refresh)"
                if res.get("used_gps"):
                    kind += " · started from GPS"
                elif res.get("zoned"):
                    kind += " · zoned sweep"
            elif uncovered:
                kind = "straight-line — road map does not cover this job area"
            else:
                kind = "straight-line only — download road map on Setup"
            clock = ""
            try:
                from core import time_est
                clock = time_est.summary_clause(r)
            except Exception:
                clock = ""
            clock_bit = f" · {clock}" if clock else ""
            map_bit = f"{build_section} · " if build_section else ""
            self.statusBar().showMessage(
                f"{map_bit}Route ready: {len(ordered)} stops, {miles:.1f} mi{clock_bit} — {kind}",
                12000)
            last_in_queue = True
            queue = getattr(self, "_auto_build_queue", None) or []
            if queue and queue[0][0] == build_section:
                queue.pop(0)
                self._auto_build_done_n = int(getattr(self, "_auto_build_done_n", 0) or 0) + 1
            if queue:
                last_in_queue = False
                QTimer.singleShot(0, self._run_next_auto_build)
            elif queued or build_section:
                _restore_build_btn()
                self._finish_auto_build_queue(build_section)
            else:
                _restore_build_btn()
                if getattr(self.state, "days_merged", False):
                    self.statusBar().showMessage(
                        f"Merged route ready: {len(ordered)} stops, {miles:.1f} mi — {kind}",
                        12000)
                self._notify_install_html()
            if last_in_queue:
                if uncovered:
                    QMessageBox.warning(
                        self,
                        "Road map does not cover this job",
                        f"Route built: {len(ordered)} stops, {miles:.1f} mi "
                        "(straight-line only).\n\n"
                        "Saved road map is for a different job area. "
                        "Setup → Download roads with these Excel/.EST files loaded, "
                        "then Build again for real street miles.",
                    )
                elif not r.get("graph"):
                    self.statusBar().showMessage(
                        "Route built (straight-line miles). For real-street order and miles, "
                        "add a road map on Setup, then Build again.", 9000)
                self._refresh_field_ready()
                self._refresh_route_summary_ui()

        def canceled():
            etimer.stop()
            self._stop_worker(thread)
            dlg.close()
            self._route_thread = None
            self._auto_build_queue = []
            self._auto_build_done_n = 0
            self._merge_build_pending = False
            _restore_build_btn()

        etimer.timeout.connect(tick)
        dlg.canceled.connect(canceled)
        thread.progress_text.connect(on_progress)
        thread.finished_result.connect(done)
        thread.finished.connect(lambda: etimer.stop())
        thread.start()
        dlg.show()
        tick()

    def _show_setup_wizard(self):
        dlg = SetupWizard(self)
        dlg.exec()
        self._refresh_workflow_strip()
        self._refresh_field_ready()

    def _reoptimize(self):
        if not self.state.stops:
            return
        old = list(self.state.stops)
        fresh = self._stops_from_uploads_merged() or old
        rebuild = ""
        if self._route_section_active():
            if self._day_filter_active():
                rebuild = route_sections.canonical_section(self._day_filter_value())
            else:
                labels = self._route_section_labels()
                rebuild = labels[0] if labels else ""
        if rebuild:
            fresh = route_sections.preserve_other_section_orders(
                old, fresh, rebuild_sheet=rebuild)
        self._begin_route_pick(fresh)

    def _schedule_retrace(self, *, select_row: int | None = None) -> None:
        self._retrace_pending_row = select_row
        self._retrace_timer.start(350)

    def _run_retrace_debounced(self) -> None:
        row = self._retrace_pending_row
        self._retrace_pending_row = None
        self._retrace_route_async(select_row=row)

    def _retrace_route_only(self, *, select_row: int | None = None) -> None:
        if not self.state.stops:
            return
        self._schedule_retrace(select_row=select_row)

    def _retrace_route_async(self, *, select_row: int | None = None) -> None:
        if not self.state.stops:
            return
        rt = getattr(self, "_route_thread", None)
        if rt is not None and rt.isRunning():
            self.statusBar().showMessage("Route build already running…", 4000)
            return
        rtr = getattr(self, "_retrace_thread", None)
        if rtr is not None and rtr.isRunning():
            self._retrace_pending_row = select_row
            self._retrace_timer.start(350)
            return
        enrich = hasattr(self, "chk_show_segments") and self.chk_show_segments.isChecked()
        section_stops = self._section_stops_for_legs()
        thread = RouteRetraceThread(
            list(section_stops),
            tuple(self.state.home),
            DATA_DIR,
            enrich_segments=enrich,
        )
        self._retrace_thread = thread
        self.statusBar().showMessage("Re-tracing route on streets…", 0)
        started_section = self._day_filter_value() if self._day_filter_active() else ""
        started_order = [s.get("uid") for s in section_stops]

        def done(res: dict):
            if self._retrace_thread is thread:
                self._retrace_thread = None
            now_section = self._day_filter_value() if self._day_filter_active() else ""
            now_order = [s.get("uid") for s in self._section_stops_for_legs()]
            if (
                now_section != started_section or now_order != started_order
                or getattr(self, "_route_pick_mode", False) or not self.state.stops
            ):
                # Day / order / pick / clear changed while tracing — result is stale.
                self.statusBar().showMessage("Re-trace skipped (route changed meanwhile).", 4000)
                return
            if not res.get("ok"):
                err = res.get("error", "re-trace failed")
                if self.state.offline_mode:
                    self._field_notice(err)
                else:
                    self._warn(err)
                return
            self.state.route = res["route"]
            section = self._day_filter_value() if self._day_filter_active() else ""
            if section:
                self._ensure_routes_by_map()[section] = dict(res["route"])
            self._persist_shift(quiet=True)
            self._refresh_route_list()
            if select_row is not None:
                self.list_route.setCurrentRow(select_row)
            self._push_state()
            miles = self.state.route.get("miles", 0.0)
            self.statusBar().showMessage(
                f"Route re-traced — {miles:.1f} mi (order unchanged).", 6000)

        thread.finished_result.connect(done)
        # Hold a strong ref until the QThread fully exits (done() may clear the attr first).
        live = getattr(self, "_retrace_threads_live", None)
        if live is None:
            live = self._retrace_threads_live = set()
        live.add(thread)
        thread.finished.connect(lambda t=thread: live.discard(t))
        thread.start()

    def _stops_from_uploads_merged(self) -> list[dict] | None:
        """Fresh site list from current Excel/EST (keeps field progress), not saved route order."""
        if not self.excel_paths or not self.est_paths:
            return None
        try:
            sites = ingest.parse_excel_sites(self.excel_paths)
            cfgs = self._est_configs()
            stops = ingest.match_est_files(cfgs, sites, self.state.home)
            if not stops:
                return None
            old_by_uid = {s["uid"]: s for s in self.state.stops}
            return [ingest.merge_stop_progress(old_by_uid.get(f["uid"]), f) for f in stops]
        except ingest.ExcelEngineMissing as exc:
            self._warn(str(exc))
            return None
        except ingest.IngestFileReadError as exc:
            self._warn(str(exc))
            return None
        except Exception as exc:  # noqa: BLE001
            crash_log.log_error(exc, context="stops_from_uploads_merged")
            return None

    def _nudge_stop(self, delta: int):
        if not self.state.stops:
            return
        if getattr(self, "_route_pick_mode", False):
            # Pick-mode list rows are pick order + pool, not visible stops.
            self.statusBar().showMessage(
                "Picking — drag in the order window to move a stop.", 5000)
            return
        visible = self._visible_stop_indices()
        if not visible:
            return
        row = self.list_route.currentRow()
        if row < 0:
            try:
                row = visible.index(self.current_index)
            except ValueError:
                row = 0
        j_row = row + delta
        if j_row < 0 or j_row >= len(visible):
            return
        i, j = visible[row], visible[j_row]
        self._leave_install_site()
        stops = list(self.state.stops)
        stops[i], stops[j] = stops[j], stops[i]
        self.state.stops = stops
        self.current_index = j
        # Redraw now so a second quick tap reads the new row (not swap the pair back).
        self._refresh_route_list()
        self.list_route.setCurrentRow(j_row)
        self._retrace_route_only(select_row=j_row)

    def _reset_route(self):
        if QMessageBox.question(
            self, "Clear shift data",
            "Clear stops, route, and install/pickup progress?\n\n"
            "Your Excel/.EST file list stays — use \"Clear file lists\" on Setup "
            "or \"Start fresh…\" to wipe those too.\n\n"
            f"Profile: {self.state.profile}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self._apply_shift_clear(wipe_upload_paths=False)

    def _apply_shift_clear(self, *, wipe_upload_paths: bool) -> None:
        self._route_pick_suspended = None
        self._stop_drive()
        self._route_pick_mode = False
        self._route_pick_uids = []
        self._route_pick_sides = {}
        self._route_pick_by_map = {}
        if hasattr(self.state, "routes_by_map"):
            self.state.routes_by_map = {}
        self._exit_pick_map_focus()
        self._hide_route_pick_dialog()
        self._undo_stack.clear()
        self._refresh_undo_ui()
        self.state.clear_shift(wipe_upload_paths=wipe_upload_paths)
        if wipe_upload_paths:
            self.excel_paths = []
            self.est_paths = []
            self._refresh_file_lists()
        self._map_preview_stops = []
        self._map_preview_route = {"polyline": [], "miles": 0.0, "graph": False}
        self.current_index = self.pickup_index = 0
        self._refresh_day_filter()
        self._update_right()
        self._push_state(fit=True)
        self._refresh_route_list()
        self._refresh_workflow_strip()
        self._refresh_field_ready()
        self._refresh_map_preview()
        self.bridge.fly_to(self.state.home[0], self.state.home[1], 10)
        if wipe_upload_paths:
            self.statusBar().showMessage(
                "Profile cleared — empty map. Add files on Setup when ready.", 10000)
        else:
            self.statusBar().showMessage(
                "Shift cleared — map empty. Excel/.EST lists still on Setup.", 10000)

    # --------------------------------------------------------- Route list UI
    def _refresh_route_list(self):
        self.list_route.clear()
        letters = self._pick_site_letters() if self._section_pick_active() else {}
        day_tag = ""
        if self._day_filter_active():
            day_tag = f" · {self._day_filter_value()}"
        if self._section_pick_active():
            by_uid = {s["uid"]: s for s in self.state.stops}
            for i, uid in enumerate(self._route_pick_uids):
                s = by_uid.get(uid)
                if not s:
                    continue
                mark = "OK" if s.get("installed") else "SKIP" if s.get("skipped") else "--"
                sheet = f" · {s.get('sheet')}" if s.get("sheet") else ""
                item = QListWidgetItem(
                    f"→ {i + 1}. [{letters.get(uid, '?')}] Site {s['id']}{sheet} — "
                    f"{self._street_label(s)} [{mark}]")
                item.setData(Qt.ItemDataRole.UserRole, str(uid))
                self.list_route.addItem(item)
            picked_set = set(self._route_pick_uids)
            for s in self._pick_pool_stops():
                if s["uid"] in picked_set:
                    continue
                sheet = f" · {s.get('sheet')}" if s.get("sheet") else ""
                item = QListWidgetItem(
                    f"   [{letters.get(s['uid'], '?')}] Site {s['id']}{sheet} — "
                    f"{self._street_label(s)}")
                item.setData(Qt.ItemDataRole.UserRole, str(s["uid"]))
                self.list_route.addItem(item)
            return
        visible = self._visible_stop_indices()
        for seq, i in enumerate(visible, start=1):
            s = self.state.stops[i]
            mark = "OK" if s.get("installed") else "SKIP" if s.get("skipped") else "--"
            zone = s.get("route_zone")
            ztxt = f" Z{zone}" if zone else ""
            sheet = f" · {s.get('sheet')}" if s.get("sheet") and not self._day_filter_active() else ""
            self.list_route.addItem(
                f"[{mark}] {seq}.{ztxt} Site {s['id']}{sheet} — {self._street_label(s)}"
                f"{self._stop_time_suffix(i, mark, leg_index=seq - 1)}")
        miles = float(self.state.route.get("miles", 0.0) or 0)
        on_graph = bool(self.state.route.get("graph"))
        shown = len(visible)
        total = len(self.state.stops)
        if self.state.stops:
            kind_short = "Roads" if on_graph else "Segments"
            kind_long = (
                "Real roads + segment lines"
                if on_graph
                else "Segment lines — import road map for streets"
            )
        else:
            kind_short = "—"
            kind_long = "Build route on Setup"
        count_txt = f"{shown}/{total}" if shown != total else str(total)
        if hasattr(self, "lbl_stat_stops") and self.lbl_stat_stops is not None:
            self.lbl_stat_stops.setText(count_txt)
            self.lbl_stat_miles.setText(f"{miles:.1f}" if self.state.stops else "—")
            self.lbl_stat_kind.setText(kind_short)
        elif hasattr(self, "lbl_route_summary") and self.state.stops:
            self.lbl_route_summary.setText(
                f"{count_txt} stops{day_tag} · {miles:.1f} mi · {kind_short}")
        elif hasattr(self, "lbl_route_summary"):
            self.lbl_route_summary.setText("")
        self.lbl_route_stats.setText(
            f"{len(self.state.stops)} stops - {miles:.1f} mi - {kind_long}"
        )
        self._refresh_route_summary_ui()
        self._refresh_workflow_strip()
        self._refresh_field_strip_ui()
        self._refresh_field_alerts()
        self.btn_start.setText("STOP FOLLOW" if self._gps_follow else "FOLLOW GPS")
        self.btn_start.setObjectName("stop" if self._gps_follow else "go")
        self.btn_start.setStyleSheet("")  # re-evaluate object-name style
        self.btn_start.style().unpolish(self.btn_start)
        self.btn_start.style().polish(self.btn_start)

    def _route_item_clicked(self, item):
        # While picking a route, the left list mirrors the map dots. Clicking a
        # row must build the pick order — never jump to Install (P: field bug).
        if getattr(self, "_route_pick_mode", False):
            uid = item.data(Qt.ItemDataRole.UserRole)
            uid = str(uid) if uid else ""
            if not uid:
                self.statusBar().showMessage(
                    "Click a blue (begin) or red (end) dot on the map to start the order.",
                    5000,
                )
                return
            if uid in self._route_pick_uids:
                self._select_pick_in_dialog(uid)
            else:
                self._route_pick_click(uid, None, from_list=True)
            return
        row = self.list_route.row(item)
        visible = self._visible_stop_indices()
        idx = visible[row] if row < len(visible) else row
        if not (0 <= idx < len(self.state.stops)):
            return
        if self.pages.currentIndex() == 2:
            # Already on Install: flush form + end Drop pin before switching.
            self._select_install_stop(idx)
            return
        self.current_index = idx
        self._go_page(2)
        self._center_current()

    def _select_pick_in_dialog(self, uid: str) -> None:
        """Highlight an already-picked stop in the order window (no page change)."""
        dlg = self._route_pick_dialog
        if dlg is None:
            return
        for i in range(dlg.list.count()):
            it = dlg.list.item(i)
            if it and str(it.data(Qt.ItemDataRole.UserRole)) == uid:
                dlg.list.setCurrentRow(i)
                break
        self.statusBar().showMessage(
            "Already in your order — drag it in the order window to move it, "
            "or tap an orange dot to add the next stop.", 5000)

    # ----------------------------------------------------- Map follow (GPS)
    def _toggle_drive(self):
        if self._gps_follow:
            self._stop_drive()
        else:
            self._start_drive()

    def _start_drive(self):
        if not self.state.stops:
            self._warn("Build a route first.")
            return
        if self._route_section_active() and not self._day_filter_active():
            labels = self._route_section_labels()
            stored = self._ensure_routes_by_map()
            chosen = next(
                (lb for lb in labels if float((stored.get(lb) or {}).get("miles") or 0) > 0),
                labels[0] if labels else None,
            )
            if chosen:
                self._set_route_section(chosen)
                self._refresh_route_list()
        if not self._next_leg_payload():
            self._info("All stops are already done.")
            return
        if not road_router.has_graph(DATA_DIR):
            if self.state.offline_mode:
                self._field_notice(
                    "Straight-line legs — no local road map on this laptop.")
            else:
                self._warn(
                    "No offline road map for this area yet.\n\n"
                    "On WiFi: Setup → Download road map → BUILD ROUTE.")
        self._gps_follow = True
        self._map_follow = True
        self.nav = {"active": True}
        self.bridge.set_follow(True)
        self._set_drive_mode(True)
        self._apply_power_profile()
        self._update_right(force_map=True)
        self._push_state()
        self._refresh_route_list()
        self._go_page(1)
        nxt = self._next_leg_payload()
        if nxt:
            self.statusBar().showMessage(
                f"Following GPS — next Site {nxt.get('to_id', '?')} "
                f"({nxt['miles']:.1f} mi). Marker live — pan freely; tap Follow to recenter.",
                10000,
            )

    def _stop_drive(self):
        self._gps_follow = False
        self._map_follow = False
        self.nav = {"active": False}
        self._set_drive_mode(False)
        self.bridge.set_follow(False)
        self._apply_power_profile()
        self.btn_start.setText("FOLLOW GPS")
        self.btn_start.setObjectName("go")
        self.btn_start.style().unpolish(self.btn_start)
        self.btn_start.style().polish(self.btn_start)
        self._push_state()
        if (
            self.pages.currentIndex() == 1
            and getattr(self, "_route_pick_suspended", None)
        ):
            self._resume_route_pick()
            return
        self.statusBar().showMessage("GPS follow stopped.", 5000)
