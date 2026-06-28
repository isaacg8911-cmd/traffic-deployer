"""Route controller mixin — P46 E1.5 extract from main.py."""

from __future__ import annotations

import time as _time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QMessageBox, QProgressDialog

import road_router
from core import ingest, routing, validate
from ui.paths import DATA_DIR
from ui.route_pick_dialog import RoutePickOrderDialog
from ui.setup_wizard import SetupWizard
from ui.simple_mode import BUILD_LABEL, SIMPLE_MODE
from ui.threads import RouteApplyPickThread, RouteOptimizeThread


class RouteControllerMixin:
    @staticmethod
    def _h(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("role", "h")
        return lbl



    def _build_route_from_uploads(self):
        if not self.excel_paths or not self.est_paths:
            self._warn("Add at least one Excel/CSV and one .EST map first.")
            return
        try:
            sites = ingest.parse_excel_sites(self.excel_paths)
        except ingest.ExcelEngineMissing as exc:
            self._warn(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._warn(f"Could not read Excel/CSV: {exc}")
            return
        if not sites:
            self._warn("No site coordinates found in the Excel/CSV (need begin lat/lon columns).")
            return
        cfgs = self._est_configs()
        stops = ingest.match_est_files(cfgs, sites, self.state.home)
        if not stops:
            self._warn("0 sites matched. Check that site IDs appear in the .EST files.")
            return

        report = validate.validate_build(
            self.excel_paths, cfgs, sites, stops,
            home=tuple(self.state.home),
            default_home=self.state.default_home,
        )
        if not report["ok"]:
            self._warn("Cannot build route:\n\n" + "\n".join(report["errors"]))
            return
        if report["warnings"]:
            body = "\n".join(report["warnings"])
            if QMessageBox.question(
                self, "Review before build",
                f"{body}\n\nBuild route anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            ) != QMessageBox.Yes:
                return

        self.state.active_files = [c["label"] for c in cfgs]

        old_by_uid = {s["uid"]: s for s in self.state.stops}
        merged = [ingest.merge_stop_progress(old_by_uid.get(f["uid"]), f) for f in stops]
        kept = sum(1 for f in merged if f["uid"] in old_by_uid
                   and (old_by_uid[f["uid"]].get("installed") or old_by_uid[f["uid"]].get("skipped")))
        if kept:
            self.statusBar().showMessage(
                f"Re-build: kept install/pickup data on {kept} site(s).", 6000)

        self.state.stops = merged
        self._map_preview_stops = []
        self.state.route = {"polyline": [], "miles": 0.0, "graph": False}
        self._persist_shift(quiet=True)
        self.current_index = min(self.current_index, max(0, len(self.state.stops) - 1))
        self._update_right(force_map=True)
        self._go_page(1)
        self._refresh_route_list()
        self._refresh_day_filter()
        self._push_state(fit=True)
        mode = self._ask_route_build_mode()
        if mode == "pick":
            self._begin_route_pick(merged)
        elif mode == "optimize":
            self._optimize_and_route(merged)
        else:
            self.statusBar().showMessage("Route build cancelled.", 4000)

    @staticmethod
    def _street_label(s: dict) -> str:
        st = str(s.get("street", "")).strip()
        if not st or st.lower() in ("nan", "none", "nat"):
            return f"Site {s.get('id', '')}"
        return st

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
        dlg.raise_()
        dlg.activateWindow()
        if self.isVisible():
            margin = 20
            x = self.geometry().right() - dlg.width() - margin
            y = self.geometry().top() + 72
            dlg.move(max(margin, x), max(margin, y))

    def _hide_route_pick_dialog(self) -> None:
        if self._route_pick_dialog is not None:
            self._route_pick_dialog.hide()

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
        self._end_manual_grab(silent=True)
        from core.map_display import enrich_segment_paths

        self._route_pick_mode = True
        self._route_pick_uids = []
        self._route_pick_sides = {}
        self.state.stops = list(stops)
        self.state.route = {"polyline": [], "miles": 0.0, "graph": False}
        if self.chk_show_segments.isChecked():
            enrich_segment_paths(self.state.stops, DATA_DIR)
        self._go_page(1)
        self._enter_pick_map_focus()
        self._refresh_route_pick_ui()
        self._show_route_pick_dialog()
        self._refresh_route_list()
        self._push_state(fit=True)
        self.statusBar().showMessage(
            f"Pick route on map — {self._pick_prompt_text()}. "
            "Blue = begin, red = end. Order list is on the right.",
            12000)

    def _refresh_route_pick_ui(self, *, sync_dialog: bool = True) -> None:
        if not hasattr(self, "lbl_pick_status"):
            return
        n = len(self._route_pick_uids)
        total = len(self.state.stops)
        on = self._route_pick_mode
        if hasattr(self, "sec_pick") and self.sec_pick is not None and SIMPLE_MODE:
            self.sec_pick.setVisible(on)
        self.btn_pick_apply.setEnabled(on and n > 0 and n >= total)
        if hasattr(self, "btn_pick_auto"):
            self.btn_pick_auto.setEnabled(False)
            self.btn_pick_auto.hide()
        self.btn_pick_clear.setEnabled(on and n > 0)
        if hasattr(self, "btn_pick_order_win"):
            self.btn_pick_order_win.setEnabled(on)
            self.btn_pick_order_win.setVisible(not on)
        if hasattr(self, "pick_combo_row"):
            self.pick_combo_row.setVisible(not on)
        if on:
            self._enter_pick_map_focus()
        elif self._pick_layout_active:
            self._exit_pick_map_focus()
        self._refresh_pick_site_combo()
        if not on:
            self.lbl_pick_status.setStyleSheet("")
            self.lbl_pick_status.setText(
                "Route applied. Numbers on the map match drive order. "
                f"Re-plan with {BUILD_LABEL} on Setup.")
            if sync_dialog:
                self._hide_route_pick_dialog()
            return
        letters = self._pick_site_letters()
        self.lbl_pick_status.setStyleSheet(
            "font-size:14px;font-weight:700;color:#0d47a1;padding:8px 0;")
        if n >= total:
            self.lbl_pick_status.setText(
                f"All {total} stops picked on the map. Tap Apply route.")
        else:
            self.lbl_pick_status.setText(
                f"{self._pick_prompt_text()} — blue begin or red end. "
                f"Order updates in the popup.")
        if sync_dialog and on and self._route_pick_dialog is not None:
            by_uid = {s["uid"]: s for s in self.state.stops}
            self._route_pick_dialog.sync_from_parent(
                uids=list(self._route_pick_uids),
                stops_by_uid=by_uid,
                letters=letters,
                street_label=self._street_label,
                total=total,
                prompt=self._pick_prompt_text(),
                pick_sides=dict(self._route_pick_sides),
            )
            self._show_route_pick_dialog()

    def _refresh_pick_site_combo(self) -> None:
        if not hasattr(self, "combo_pick_site"):
            return
        n = len(self._route_pick_uids)
        total = len(self.state.stops)
        on = self._route_pick_mode
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
        for s in self.state.stops:
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
            self._route_pick_add(str(uid))

    def _route_pick_add(self, uid: str, *, side: str | None = None) -> None:
        if not self._route_pick_mode:
            return
        if uid in self._route_pick_uids:
            self.statusBar().showMessage("Already in your route — pick the next site.", 4000)
            return
        by_uid = {s["uid"]: s for s in self.state.stops}
        stop = by_uid.get(uid)
        if stop and side in ("begin", "end"):
            self._route_pick_sides[uid] = side
            self._apply_pick_side(stop, side)
        self._route_pick_uids.append(uid)
        n = len(self._route_pick_uids)
        total = len(self.state.stops)
        self._refresh_route_pick_ui()
        self._refresh_route_list()
        self._push_state()
        side_note = ""
        if side in ("begin", "end"):
            side_note = f" ({side} end)"
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
        for s in self.state.stops:
            s.pop("pick_cross_locked", None)
            for key in ("cross_lat", "cross_lon", "cross_side"):
                s.pop(key, None)
        self._refresh_route_pick_ui()
        self._refresh_route_list()
        self._push_state()
        self.statusBar().showMessage(
            f"Picks cleared — {self._pick_prompt_text()}.", 6000)

    def _route_pick_auto_finish(self) -> None:
        if not self._route_pick_mode or not self.state.stops:
            return
        from core.map_display import auto_finish_order

        by_uid = {s["uid"]: s for s in self.state.stops}
        picked = [by_uid[u] for u in self._route_pick_uids if u in by_uid]
        remaining = [s for s in self.state.stops if s["uid"] not in self._route_pick_uids]
        ordered = auto_finish_order(tuple(self.state.home), picked, remaining, DATA_DIR)
        self._route_pick_uids = [s["uid"] for s in ordered]
        self._refresh_route_pick_ui()
        self._refresh_route_list()
        self._push_state()
        self.statusBar().showMessage(
            f"Auto-finished — {len(self._route_pick_uids)} stops in order. Tap Apply route.", 8000)

    def _route_pick_apply(self) -> None:
        total = len(self.state.stops)
        if not self._route_pick_mode or not self._route_pick_uids:
            self._warn("Pick stop 1 on the map (blue or red dot) or from the dropdown.")
            return
        if len(self._route_pick_uids) < total:
            self._warn(
                f"Pick all {total} stops before Apply "
                f"({len(self._route_pick_uids)} chosen so far).")
            return
        if self._route_thread is not None and self._route_thread.isRunning():
            self.statusBar().showMessage("Route build already running…", 4000)
            return
        if not road_router.has_graph(DATA_DIR):
            msg = (
                "Download the road map first (Setup tab → Download road map).\n\n"
                "That is required for accurate routes that follow real streets.")
            if self.state.offline_mode:
                self._field_notice(
                    "No local road map — import road_graph.graphml at home, or resume online mode.")
            else:
                self._warn(msg)
            return

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
            list(self.state.stops),
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
                total_st = len(self.state.stops)
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
            self.state.stops = res["order"]
            self.state.route = res["route"]
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
            self.statusBar().showMessage(
                f"Route applied: {len(self.state.stops)} stops, {miles:.1f} mi "
                "(street-traced sites).",
                10000,
            )
            if hasattr(self, "btn_build"):
                self.btn_build.setEnabled(True)
                self.btn_build.setText(BUILD_LABEL)

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

    def _highlight_stop_uid(self) -> str | None:
        if self._manual_grab_mode and self.state.stops and self.current_index < len(self.state.stops):
            uid = str(self.state.stops[self.current_index].get("uid") or "")
            return uid or None
        nxt = self._next_leg_payload()
        return nxt["to_uid"] if nxt else None

    def _optimize_and_route(self, stops):
        self._route_pick_mode = False
        self._route_pick_uids = []
        self._route_pick_sides = {}
        self._exit_pick_map_focus()
        self._hide_route_pick_dialog()
        if not road_router.has_graph(DATA_DIR):
            msg = (
                "Download the road map first (Setup tab → Download road map).\n\n"
                "That is required for accurate routes that follow real streets and "
                "cross each site line efficiently.")
            if self.state.offline_mode:
                self._field_notice(
                    "No local road map — import road_graph.graphml at home, or resume online mode.")
            else:
                self._warn(msg)
            return

        dlg = QProgressDialog(
            "Optimizing route on real streets\n(crossing each site line in best order)...",
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
        thread = RouteOptimizeThread(list(stops), tuple(self.state.home), DATA_DIR)
        self._route_thread = thread

        def _restore_build_btn():
            if hasattr(self, "btn_build"):
                self.btn_build.setEnabled(True)
                self.btn_build.setText(BUILD_LABEL)

        def on_progress(msg: str):
            dlg.setLabelText(f"{msg}\n\nElapsed: {int(_time.time() - t0)}s")

        def tick():
            pass  # progress_text from worker updates the label

        def done(res):
            etimer.stop()
            dlg.close()
            self._route_thread = None
            _restore_build_btn()
            if not res.get("ok"):
                err = f"Routing failed: {res.get('error', 'unknown')}"
                if self.state.offline_mode:
                    self._field_notice(err)
                else:
                    self._warn(err)
                if res.get("trace"):
                    print(res["trace"])
                return
            self.state.stops = res["order"]
            self.state.route = res["route"]
            self.current_index = min(self.current_index, max(0, len(self.state.stops) - 1))
            self._persist_shift(quiet=True)
            self._refresh_route_list()
            self._refresh_day_filter()
            self._update_right(force_map=True)
            self._push_state(fit=True)
            miles = res["route"].get("miles", 0.0)
            r = res["route"]
            if r.get("graph"):
                kind = "traced on real streets"
                failed = int(r.get("failed_legs") or 0)
                if failed:
                    kind += f" ({failed} leg(s) need road map refresh)"
            else:
                kind = "straight-line only — download road map on Setup"
            self.statusBar().showMessage(
                f"Route ready: {len(res['order'])} stops, {miles:.1f} mi — {kind}", 12000)
            if not r.get("graph"):
                self._warn(
                    "Route line is straight (chord) because no road graph is loaded.\n\n"
                    "Setup → Download road map (or import road_graph.graphml), then BUILD again.")
            self._refresh_field_ready()
            self._refresh_route_summary_ui()

        def canceled():
            etimer.stop()
            self._stop_worker(thread)
            dlg.close()
            self._route_thread = None
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
        mode = self._ask_route_build_mode()
        if mode is None:
            return
        stops = self._stops_from_uploads_merged() or list(self.state.stops)
        if mode == "pick":
            self._begin_route_pick(stops)
        else:
            self._route_pick_mode = False
            self._route_pick_uids = []
            self._route_pick_sides = {}
            self._exit_pick_map_focus()
            self._hide_route_pick_dialog()
            self._optimize_and_route(stops)

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
        except Exception:
            return None

    def _nudge_stop(self, delta: int):
        if not self.state.stops:
            return
        idx = self.list_route.currentRow()
        if idx < 0:
            idx = self.current_index
        j = idx + delta
        if j < 0 or j >= len(self.state.stops):
            return
        stops = list(self.state.stops)
        stops[idx], stops[j] = stops[j], stops[idx]
        self.state.stops = stops
        self.current_index = j
        self._retrace_route_only(select_row=j)

    def _retrace_route_only(self, *, select_row: int | None = None):
        if not self.state.stops:
            return
        from core import routing
        res = routing.retrace_only(
            list(self.state.stops), tuple(self.state.home), DATA_DIR)
        from core.map_display import enrich_segment_paths

        self.state.route = res["route"]
        if self.chk_show_segments.isChecked():
            enrich_segment_paths(self.state.stops, DATA_DIR)
        self._persist_shift(quiet=True)
        self._refresh_route_list()
        if select_row is not None:
            self.list_route.setCurrentRow(select_row)
        self._push_state()
        self.statusBar().showMessage(
            f"Route re-traced — {self.state.route.get('miles', 0):.1f} mi (order unchanged).",
            6000,
        )

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
        self._stop_drive()
        self._route_pick_mode = False
        self._route_pick_uids = []
        self._route_pick_sides = {}
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
        letters = self._pick_site_letters() if self._route_pick_mode else {}
        day_tag = ""
        if self._day_filter_active():
            day_tag = f" · {self._day_filter_value()}"
        if self._route_pick_mode:
            by_uid = {s["uid"]: s for s in self.state.stops}
            for i, uid in enumerate(self._route_pick_uids):
                s = by_uid.get(uid)
                if not s:
                    continue
                mark = "OK" if s.get("installed") else "SKIP" if s.get("skipped") else "--"
                sheet = f" · {s.get('sheet')}" if s.get("sheet") else ""
                self.list_route.addItem(
                    f"→ {i + 1}. [{letters.get(uid, '?')}] Site {s['id']}{sheet} — "
                    f"{self._street_label(s)} [{mark}]")
            picked_set = set(self._route_pick_uids)
            for s in self.state.stops:
                if s["uid"] in picked_set:
                    continue
                sheet = f" · {s.get('sheet')}" if s.get("sheet") else ""
                self.list_route.addItem(
                    f"   [{letters.get(s['uid'], '?')}] Site {s['id']}{sheet} — "
                    f"{self._street_label(s)}")
            return
        visible = self._visible_stop_indices()
        for seq, i in enumerate(visible, start=1):
            s = self.state.stops[i]
            mark = "OK" if s.get("installed") else "SKIP" if s.get("skipped") else "--"
            zone = s.get("route_zone")
            ztxt = f" Z{zone}" if zone else ""
            sheet = f" · {s.get('sheet')}" if s.get("sheet") and not self._day_filter_active() else ""
            self.list_route.addItem(
                f"[{mark}] {seq}.{ztxt} Site {s['id']}{sheet} — {self._street_label(s)}")
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
        row = self.list_route.row(item)
        visible = self._visible_stop_indices()
        if row < len(visible):
            self.current_index = visible[row]
        else:
            self.current_index = row
        self._go_page(2)
        self._center_current()

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
                f"({nxt['miles']:.1f} mi). Map pans with you.",
                10000,
            )

    def _stop_drive(self):
        self._gps_follow = False
        self.nav = {"active": False}
        self._set_drive_mode(False)
        self.bridge.set_follow(False)
        self._apply_power_profile()
        self.btn_start.setText("FOLLOW GPS")
        self.btn_start.setObjectName("go")
        self.btn_start.style().unpolish(self.btn_start)
        self.btn_start.style().polish(self.btn_start)
        self._push_state()
        self.statusBar().showMessage("GPS follow stopped.", 5000)
