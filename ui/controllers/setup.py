"""Setup controller mixin — P46 E1.1 extract from main.py."""

from __future__ import annotations

import os
import time as _time

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QListWidgetItem,
    QMessageBox,
    QProgressDialog,
    QTableWidgetItem,
)

import gps_reader
import road_router
from core import auto_updater, connectivity, counter_inventory, crash_log, field_alerts, geo, ingest, setup_network
from core.field_ready import check_all
from core.offline_gate import evaluate as offline_gate_eval
from core.setup_checklist import evaluate as setup_checklist_eval
from core.setup_checklist import route_summary as build_route_summary
from core.state import RouteState
from ui.counter_ui import apply_counter_panel_connected, apply_volt_check, battery_cell_text
from ui.paths import APP_DIR, DATA_DIR, DEMO_CSV, DEMO_EST, LAUNCH_HINT
from ui.setup_wizard import SetupWizard
from ui.simple_mode import BUILD_LABEL, COMPACT_UI
from ui.threads import DownloadRoadsThread, GeocodeThread, MapSetupThread
from version import APP_VERSION


class SetupControllerMixin:
    # --------------------------------------------------------- Setup actions
    def _save_shift_now(self):
        if self.pages.currentIndex() == 2:
            self._flush_install_form()
        self._persist_shift(f"Saved profile '{self.state.profile}'.", quiet=False)

    def _save_profile_as(self):
        name = self.txt_profile.text().strip().upper() or "DEFAULT"
        if name == self.state.profile:
            self._save_shift_now()
            return
        path = os.path.join(DATA_DIR, f"tds_backup_{name}.json")
        if os.path.isfile(path):
            if QMessageBox.question(
                self, "Overwrite profile",
                f"Profile '{name}' already exists.\n\nOverwrite with your current shift?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            ) != QMessageBox.Yes:
                return
        if self.pages.currentIndex() == 2:
            self._flush_install_form()
        self._persist_shift(quiet=True)
        data = self.state.to_dict()
        data["profile"] = name
        import persistence as _persist
        if not _persist.save_state(data, path, DATA_DIR):
            self._warn("Could not write profile file.")
            return
        self._switch_profile(name, from_save_as=True)

    def _switch_profile(self, name: str | None = None, *, from_save_as: bool = False):
        if self.pages.currentIndex() == 2:
            self._flush_install_form()
        outgoing = self.state.profile
        self._persist_shift(quiet=True)
        name = (name or self.txt_profile.text().strip().upper() or "DEFAULT")
        self.txt_profile.setText(name)
        self._gps_follow = False
        self.nav = {"active": False}
        self._undo_stack.clear()
        self._export_nudge_shown = False
        self.state = RouteState(DATA_DIR, profile=name)
        self.state.load()
        self._sync_field_mode()
        if self.state.default_home:
            self.state.apply_default_home()
        self.excel_paths = [p for p in self.state.excel_paths if os.path.isfile(p)]
        self.est_paths = [p for p in self.state.est_paths if os.path.isfile(p)]
        self.state.excel_paths = list(self.excel_paths)
        self.state.est_paths = list(self.est_paths)
        self.current_index = min(self.state.current_index, max(0, len(self.state.stops) - 1))
        self.pickup_index = min(self.state.pickup_index, max(0, len(self._installed_stops()) - 1))
        self.spin_lat.setValue(self.state.home[0])
        self.spin_lon.setValue(self.state.home[1])
        self._refresh_origin_label()
        self._refresh_workflow_strip()
        self._refresh_offline_ui()
        self._refresh_file_lists()
        self._refresh_day_filter()
        self._warn_missing_upload_paths()
        self._update_right(force_map=bool(self.state.stops))
        if self.state.stops:
            self._refresh_route_list()
            if self.pages.currentIndex() == 2:
                self._refresh_install()
        self._push_state(fit=bool(self.state.stops))
        self._sync_prefs_ui()
        self._refresh_undo_ui()
        self._refresh_field_ready()
        msg = f"Profile '{name}' loaded."
        if from_save_as:
            msg = f"Saved and switched to profile '{name}'."
        elif outgoing != name:
            msg = f"Switched {outgoing} → {name}."
        self._info(msg)

    def _refresh_origin_label(self):
        dh = ""
        if self.state.default_home:
            dh = f"\nDefault saved: {self.state.default_home[0]:.5f}, {self.state.default_home[1]:.5f}"
        self.lbl_origin.setText(f"Origin: {self.state.home[0]:.5f}, {self.state.home[1]:.5f}{dh}")

    def _save_default_home(self):
        lat, lon = geo.normalize_ca_coords(self.spin_lat.value(), self.spin_lon.value())
        label = self.txt_address.text().strip() or f"{lat:.5f}, {lon:.5f}"
        self._commit_home_start(lat, lon, label, note=f"Default start saved:\n{label[:120]}")

    def _load_default_home(self):
        if not self.state.default_home:
            self._warn(
                "No saved start yet.\n\n"
                "Type your address and tap Search, then pick a match.")
            return
        self.state.apply_default_home()
        lat, lon = self.state.home
        label = self.state.saved_home_label or f"{lat:.5f}, {lon:.5f}"
        self._apply_home_ui(lat, lon, f"Loaded saved start:\n{label[:120]}")
        self.statusBar().showMessage(f"Start point loaded — {label[:60]}", 8000)

    def _evaluate_setup_checklist(self) -> dict:
        r = getattr(self, "_field_report", None)
        if r is None:
            r = check_all(APP_DIR, probe_gps=False, stop_server_after=False)
        return setup_checklist_eval(
            home=tuple(self.state.home),
            default_home=self.state.default_home,
            excel_paths=self.excel_paths,
            est_paths=self.est_paths,
            has_graph=road_router.has_graph(DATA_DIR),
            route_miles=float(self.state.route.get("miles", 0) or 0),
            field_report=r,
        )

    def _show_setup_checklist(self):
        ck = self._evaluate_setup_checklist()
        lines = []
        for it in ck["items"]:
            sym = "✓" if it["ok"] else "✗"
            extra = ""
            if it.get("detail"):
                extra = f" — {it['detail']}"
            lines.append(f"{sym} {it['label']}{extra}")
        title = "Ready to leave" if ck["ok"] else "Setup incomplete"
        QMessageBox.information(self, title, "\n".join(lines))

    def _run_setup_network_test(self):
        if self.state.offline_mode:
            self._field_notice("Tap I'm online in the top bar to test home Wi‑Fi.")
            return
        self.statusBar().showMessage("Testing home Wi‑Fi…", 3000)
        rows = setup_network.run_checks(data_dir=DATA_DIR, app_dir=APP_DIR)
        lines = []
        fails = 0
        for row in rows:
            sym = "OK" if row["ok"] else "FAIL"
            if not row["ok"]:
                fails += 1
            lines.append(f"[{sym}] {row['label']}: {row['detail']}")
        QMessageBox.information(
            self, "Home Wi‑Fi test",
            "\n".join(lines) + ("\n\nAll checks passed." if fails == 0 else f"\n\n{fails} issue(s) — fix before leaving."),
        )

    def _use_saved_home(self):
        if not self.state.saved_home_coords:
            self._warn(
                "No saved home yet.\n\n"
                "Type your address and tap Search, then pick a match — or use Save as my start.")
            return
        lat, lon = self.state.saved_home_coords
        label = self.state.saved_home_label or f"{lat:.5f}, {lon:.5f}"
        self._commit_home_start(lat, lon, label, note=f"Restored home:\n{label[:120]}")

    def _recover_map(self):
        self.bridge.refresh_view()
        self._push_state(fit=bool(self.state.stops))
        self.statusBar().showMessage("Map refreshed.", 5000)

    def _refresh_route_summary_ui(self):
        if not hasattr(self, "lbl_route_summary"):
            return
        if not self.state.stops:
            self.lbl_route_summary.setText("")
            return
        summ = build_route_summary(self.state.stops, self.state.route)
        from ui.simple_mode import COMPACT_UI
        if COMPACT_UI:
            miles = float(self.state.route.get("miles", 0.0) or 0)
            on_graph = bool(self.state.route.get("graph"))
            kind = "roads" if on_graph else "segments"
            self.lbl_route_summary.setText(
                f"{len(self.state.stops)} stops · {miles:.1f} mi · {kind} · {summ['text']}")
        else:
            self.lbl_route_summary.setText(summ["text"])

    def _next_stop_distance_mi(self) -> str:
        if not self.state.stops:
            return ""
        remaining = [
            self.state.stops[i] for i in self._visible_stop_indices()
            if not self.state.stops[i].get("installed")
            and not self.state.stops[i].get("skipped")
        ]
        if not remaining:
            return " · all stops done"
        target = remaining[0]
        g = self.gps.latest() if hasattr(self, "gps") else {}
        if g.get("fix") and g.get("lat") is not None:
            d = self._dist_m(g["lat"], g["lon"], *self.state.point(target)) / 1609.34
            return f" · next Site {target.get('id', '?')} {d:.1f} mi"
        tlat, tlon = self.state.point(target)
        d = self._dist_m(self.state.home[0], self.state.home[1], tlat, tlon) / 1609.34
        return f" · next Site {target.get('id', '?')} ~{d:.1f} mi from start"

    def _maybe_refresh_field_strip(self) -> None:
        """Throttle status strip updates while driving (GPS ticks ~7 Hz)."""
        import time as _time
        if self._gps_follow:
            now = _time.time()
            if now - self._strip_tick < self._strip_throttle_s:
                return
            self._strip_tick = now
        self._refresh_field_strip_ui()

    def _refresh_field_alerts(self) -> None:
        text = field_alerts.pickup_reminder_text(self.state.stops)
        for attr in ("lbl_pickup_reminder", "lbl_download_reminder"):
            lbl = getattr(self, attr, None)
            if lbl is None:
                continue
            if text:
                lbl.setText(text)
                lbl.show()
            else:
                lbl.setText("")
                lbl.hide()

    def _counter_auto_connect(self) -> None:
        """One-shot connect when opening Install — skips if already live."""
        if self.pages.currentIndex() != 2:
            return
        if self._counter_connected:
            return
        if self._picocount_thread and self._picocount_thread.isRunning():
            return
        if not self._counter_selected_port():
            return
        self._counter_refresh_and_connect()

    def _maybe_export_nudge(self) -> None:
        if self._export_nudge_shown or not field_alerts.shift_closed(self.state.stops):
            return
        self._export_nudge_shown = True
        total = len(self.state.stops)
        dl = field_alerts.pending_download_count(self.state.stops)
        body = f"All {total} stops are installed or skipped."
        if dl:
            body += f"\n\n{dl} counter download(s) still pending — use Pickup tab."
        body += "\n\nExport shift handoff now?\n(IG TFC Excel + Map 1 & 2 .est)"
        box = QMessageBox(self)
        box.setWindowTitle("Shift complete")
        box.setText(body)
        btn_go = box.addButton("Export handoff", QMessageBox.AcceptRole)
        box.addButton("Later", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() == btn_go:
            self._export_shift_handoff_quick()
            self._go_page(4)

    def _refresh_field_strip_ui(self):
        if not hasattr(self, "lbl_field_strip"):
            return
        gps = self.gps.latest() if hasattr(self, "gps") else {}
        if gps.get("fix"):
            gps_txt = f"GPS fix · {gps.get('satellites', 0)} sats"
        elif gps.get("connected"):
            gps_txt = "GPS searching…"
        else:
            gps_txt = "GPS not detected"
        next_txt = self._next_stop_distance_mi() if self.state.stops else ""
        self.lbl_field_strip.setText(f"{gps_txt}{next_txt}")
        if hasattr(self, "btn_saved_home"):
            has = bool(self.state.saved_home_coords)
            self.btn_saved_home.setEnabled(has)
            if has:
                short = self.state.saved_home_label[:50]
                if len(self.state.saved_home_label) > 50:
                    short += "…"
                self.btn_saved_home.setText(f"Use last address ({short})")
            else:
                self.btn_saved_home.setText("Use last address")
        if hasattr(self, "btn_use_default"):
            self.btn_use_default.setEnabled(bool(self.state.default_home))

    def _ready_offline(self):
        if self.state.offline_mode:
            self._info("Already in field (offline) mode. All data saves locally on the road.")
            return
        ck = self._evaluate_setup_checklist()
        if not ck["ok"]:
            body = "\n".join(f"• {b}" for b in ck["blockers"])
            self._warn(
                f"Cannot go offline yet:\n\n{body}\n\n"
                "Open Setup → Setup checklist for the full list.")
            return
        r = getattr(self, "_field_report", None) or check_all(APP_DIR, probe_gps=False, stop_server_after=False)
        gate = offline_gate_eval(
            r,
            has_stops=bool(self.state.stops),
            route_miles=float(self.state.route.get("miles", 0) or 0),
            graph_loaded=road_router.has_graph(DATA_DIR),
        )
        if gate["blockers"]:
            body = "\n".join(f"• {b}" for b in gate["blockers"])
            self._warn(f"Cannot go offline yet:\n\n{body}\n\nFix items on Setup → Field Readiness.")
            return
        if gate["warns"]:
            body = "\n".join(f"• {w}" for w in gate["warns"])
            if QMessageBox.question(
                self, "Ready for offline?",
                f"Warnings:\n\n{body}\n\nContinue to offline mode anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            ) != QMessageBox.Yes:
                return
        self.state.offline_mode = True
        self.state.save()
        self._sync_field_mode()
        self._refresh_offline_ui()
        self._apply_field_nav_shell()
        self._sync_map_health_interval()
        if self.pages.currentIndex() == 0:
            self._go_page(1)
        self._refresh_workflow_strip()
        self._push_state(fit=bool(self.state.stops))
        self.statusBar().showMessage(
            "Field mode — on the road the app uses only local data (no internet).", 12000)
        self._info(
            "Ready for the road (offline mode).\n\n"
            "On site:\n"
            "• GPS, map, driving, installs, export — all local\n"
            "• No address search or road downloads (saves data)\n\n"
            "Back home on Wi‑Fi:\n"
            "• Tap I'm online in the top bar to set up the next day"
        )

    def _on_mode_online(self):
        if not self.state.offline_mode:
            self.statusBar().showMessage("Already online — home setup (Wi‑Fi tools enabled).", 5000)
            self._refresh_mode_bar()
            return
        self._resume_online()

    def _on_mode_offline(self):
        if self.state.offline_mode:
            self.statusBar().showMessage("Already offline — field mode (local data only).", 5000)
            self._refresh_mode_bar()
            return
        self._ready_offline()

    def _resume_online(self):
        if QMessageBox.question(
            self, "Back to home setup (online)",
            "Use Wi‑Fi at home again?\n\n"
            "• Address search and road map download work\n"
            "• Import road map from file still works anytime\n\n"
            "Your route and install progress stay saved.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self.state.offline_mode = False
        self.state.save()
        self._sync_field_mode()
        self._refresh_offline_ui()
        self._apply_field_nav_shell()
        self._sync_map_health_interval()
        self._refresh_address_hint()
        self._refresh_workflow_strip()
        self._refresh_online_status()
        self._push_state(fit=bool(self.state.stops))
        self.statusBar().showMessage(
            "Home setup (online) — use Wi‑Fi for address, road map, and BUILD.", 10000)
        QTimer.singleShot(800, lambda: self._maybe_auto_update(force=True))

    def _maybe_auto_update(self, *, force: bool = False) -> None:
        """Home Wi‑Fi: check manifest and apply portable update when configured."""
        if self.state.offline_mode or not self._internet_allowed():
            return
        self.statusBar().showMessage("Checking for app updates…", 4000)
        try:
            result = auto_updater.check_and_apply(
                APP_VERSION,
                field_mode=False,
                force_check=force,
            )
        except Exception as exc:  # noqa: BLE001
            crash_log.log_error(exc, context="auto_update")
            return
        if result.relaunch:
            self._info(result.message)
            auto_updater.relaunch_and_exit(APP_DIR)
            return
        if result.update_available and not result.applied:
            msg = f"Update v{result.latest} listed"
            if result.error:
                msg += f" — {result.error}"
            elif not IS_PORTABLE:
                msg += " — run BUILD_APP_UPDATE on home PC for work laptop"
            self.statusBar().showMessage(msg[:200], 12000)
            return
        if result.checked and result.message:
            self.statusBar().showMessage(result.message[:200], 6000)

    def _refresh_mode_bar(self):
        """Top bar: one place for online/offline mode (no duplicate status strings)."""
        if not hasattr(self, "btn_mode_online"):
            return
        on = self.state.offline_mode
        self.lbl_mode_pill.setText("OFFLINE" if on else "ONLINE")
        self.lbl_mode_pill.setProperty("mode", "offline" if on else "online")
        self.lbl_mode_pill.style().unpolish(self.lbl_mode_pill)
        self.lbl_mode_pill.style().polish(self.lbl_mode_pill)
        self.btn_mode_online.setChecked(not on)
        self.btn_mode_offline.setChecked(on)
        sub = "field mode · local only" if on else "home setup · Wi‑Fi tools on"
        if hasattr(self, "brand_sub"):
            self.brand_sub.setText(f"v{APP_VERSION}  ·  {sub}")

    def _refresh_offline_ui(self):
        self._sync_field_mode()
        on = self.state.offline_mode
        self._refresh_mode_bar()
        if on:
            self.lbl_offline.setText(
                "On the road — field mode. GPS, map, route, and installs use only local data.")
            self.lbl_offline.setStyleSheet("color:#138a3e;font-weight:700;")
        else:
            self.lbl_offline.setText(
                "At home: search address, download road map, BUILD ROUTE, then Go offline before you leave.")
            self.lbl_offline.setStyleSheet("color:#475569;font-size:12px;")
        allow = self._internet_allowed()
        self.txt_address.setEnabled(allow)
        if hasattr(self, "btn_address"):
            self.btn_address.setEnabled(allow)
        if hasattr(self, "btn_download_roads"):
            self.btn_download_roads.setEnabled(allow)
        if hasattr(self, "btn_import_roads"):
            self.btn_import_roads.setEnabled(True)
        self._refresh_address_hint()
        self._refresh_field_strip_ui()
        self._apply_field_nav_shell()
        self._sync_map_health_interval()

    def _refresh_online_status(self):
        """Geocode reachability hint when online (does not overwrite route status bar)."""
        if not self._internet_allowed():
            return
        self._retry_pending_field_geocode()
        reachable = connectivity.geocode_hosts_reachable()
        if reachable is False and hasattr(self, "lbl_address_hint"):
            self.lbl_address_hint.setText(
                "Wi‑Fi connected but geocoding sites look blocked — try hotspot, "
                "or use USB GPS / lat·lon.")
            self.lbl_address_hint.setStyleSheet("color:#b45309;font-weight:700;font-size:12px;")

    def _refresh_address_hint(self):
        if not hasattr(self, "lbl_address_hint"):
            return
        if self.state.offline_mode:
            self.lbl_address_hint.setText(
                "Field mode — address search off on the road. USB GPS or coordinates; "
                "tap I'm online when back home.")
            self.lbl_address_hint.setStyleSheet("color:#b45309;font-weight:700;font-size:12px;")
            return
        if not geo.geocode_available():
            self.lbl_address_hint.setText(
                f"Address search unavailable — {LAUNCH_HINT} (needs requests package).")
            self.lbl_address_hint.setStyleSheet("color:#b91c1c;font-weight:700;font-size:12px;")
            return
        self.lbl_address_hint.setText(
            "At home: type address + Search (5–20 sec). Internet used until you tap Go offline.")
        self.lbl_address_hint.setStyleSheet("")
        self._refresh_online_status()

    def _field_notice(self, msg: str, *, status_ms: int = 10000):
        """On the road: status bar only — no blocking dialogs for non-critical issues."""
        self.statusBar().showMessage(msg, status_ms)

    def _schedule_autosave(self):
        if not self.state.stops or self.current_index >= len(self.state.stops):
            return
        self._autosave_timer.start(800)

    def _flush_install_form(self):
        if not self.state.stops or self.current_index >= len(self.state.stops):
            return
        s = self.state.stops[self.current_index]
        s["street"] = self.txt_street.text().strip()
        s["direction"] = self.combo_dir.currentText()
        s["lanes"] = int(self.spin_lanes.value())
        s["serial"] = self.txt_serial.text().strip()
        s["notes"] = self.txt_notes.toPlainText()
        self._sync_counter_fields(s)

    def _sync_counter_fields(self, s: dict) -> None:
        """Keep stop + Excel export aligned with PicoCount serial and Unit ID."""
        sn = self.txt_serial.text().strip() if hasattr(self, "txt_serial") else ""
        if not sn:
            sn = str(s.get("counter_serial") or "").strip()
        if sn:
            s["counter_serial"] = sn
            s["serial"] = sn

    def _set_counter_connected_ui(self, connected: bool) -> None:
        self._counter_connected = connected
        apply_counter_panel_connected(getattr(self, "counter_panel", None), connected)
        if hasattr(self, "lbl_counter_connected"):
            if connected:
                self.lbl_counter_connected.show()
            else:
                self.lbl_counter_connected.hide()
        if not connected and hasattr(self, "lbl_counter_volts"):
            self.lbl_counter_volts.hide()

    def _refresh_counter_inventory(self) -> None:
        if not hasattr(self, "table_counter_inventory"):
            return
        if self.pages.currentIndex() != 0:
            return
        rows = counter_inventory.build_rows(self.state.stops)
        summary = counter_inventory.inventory_summary(self.state.stops)
        tbl = self.table_counter_inventory
        tbl.setRowCount(len(rows))
        for i, row in enumerate(rows):
            mem = row.get("memory_label") or ""
            if not mem and row.get("memory_bytes"):
                mem = f"~{int(row['memory_bytes']):,} bytes"
            vals = [
                row.get("serial_number") or "—",
                battery_cell_text(row.get("battery_volts")),
                row.get("unit_id") or "—",
                row.get("shift_status") or "In stock",
                mem or "—",
                row.get("last_seen_at") or row.get("shift_updated_at") or "—",
            ]
            for j, text in enumerate(vals):
                tbl.setItem(i, j, QTableWidgetItem(str(text)))
        parts = [f"{summary['total']} unit(s) tracked"]
        if summary["deployed"]:
            parts.append(f"{summary['deployed']} deployed")
        if summary["needs_download"]:
            parts.append(f"{summary['needs_download']} need download")
        if summary["low_battery"]:
            parts.append(f"{summary['low_battery']} low battery")
        self.lbl_inventory_summary.setText(" · ".join(parts))

    def _counter_inventory_usb(self, res: dict, *, event: str = "usb") -> None:
        rec = counter_inventory.record_usb(res, event=event)
        if not rec:
            return
        counter_inventory.sync_from_shift(self.state.stops)
        if self.pages.currentIndex() == 0 and hasattr(self, "lbl_inventory_live"):
            apply_volt_check(
                self.lbl_inventory_live,
                rec.get("battery_volts"),
                serial=str(rec.get("serial_number") or ""),
            )
            self._refresh_counter_inventory()

    def _counter_inventory_shift(self) -> None:
        counter_inventory.sync_from_shift(self.state.stops)
        if self.pages.currentIndex() == 0:
            self._refresh_counter_inventory()

    def _update_counter_volts(self, res: dict | None) -> None:
        if not hasattr(self, "lbl_counter_volts"):
            return
        if not res or not res.get("ok"):
            self.lbl_counter_volts.hide()
            return
        sn = str(res.get("serial_number") or "").strip()
        apply_volt_check(
            self.lbl_counter_volts,
            res.get("battery_volts"),
            serial=sn,
        )
        self.lbl_counter_volts.show()

    def _persist_shift(self, note: str = "", quiet: bool = False):
        self.state.current_index = self.current_index
        self.state.pickup_index = self.pickup_index
        if hasattr(self, "combo_day"):
            self.state.map_day_filter = self.combo_day.currentText()
        self.state.excel_paths = list(self.excel_paths)
        self.state.est_paths = list(self.est_paths)
        if self.state.save():
            if note and not quiet:
                self.statusBar().showMessage(note, 3000)
            elif not quiet:
                self.statusBar().showMessage("Shift saved on this laptop.", 2500)

    def _periodic_save_shift(self):
        try:
            if self.pages.currentIndex() == 2:
                self._flush_install_form()
            self._persist_shift(quiet=True)
        except Exception as exc:  # noqa: BLE001
            crash_log.log_error(exc, context="periodic_save")

    def _map_health_check(self):
        try:
            self._map_health_check_body()
        except Exception as exc:  # noqa: BLE001
            crash_log.log_error(exc, context="map_health")

    def _map_health_check_body(self):
        if self.right_stack.currentIndex() != 1 or not self.state.stops:
            return

        def cb(healthy):
            try:
                if healthy:
                    return
                self.bridge.refresh_view()
                self._push_state(fit=False)
                self.statusBar().showMessage("Map refreshed (recovered blank canvas).", 5000)
            except Exception:
                pass

        n = len(self._stops_for_map())
        self.view.page().runJavaScript(
            f"!!window.__mapLoaded && window.__dbg.lastStops >= {n} && window.__dbg.applied > 0",
            cb)

    def _autosave_current_stop(self):
        if not self.state.stops or self.current_index >= len(self.state.stops):
            return
        self._flush_install_form()
        self._persist_shift("Saved locally.", quiet=False)

    def _apply_home_ui(self, lat: float, lon: float, note: str = "") -> None:
        lat, lon = geo.normalize_ca_coords(lat, lon)
        self.spin_lat.setValue(lat)
        self.spin_lon.setValue(lon)
        self._refresh_origin_label()
        self._refresh_workflow_strip()
        self._refresh_field_strip_ui()
        self._refresh_field_ready()
        self.bridge.fly_to(lat, lon, 13)
        self._push_state()
        if note:
            self._info(note)

    def _commit_home_start(self, lat: float, lon: float, label: str, *, note: str = "") -> bool:
        lat, lon = geo.normalize_ca_coords(lat, lon)
        if RouteState.is_factory_home(lat, lon):
            self._warn(
                "Those coordinates are still the factory demo location.\n\n"
                "Type your address and tap Search, use USB GPS, or enter your real lat/lon.")
            return False
        ok = self.state.set_start_point(lat, lon, label)
        if not ok:
            self._warn(
                "Could not write home to disk.\n\n"
                f"Check that {DATA_DIR} is writable (not read-only or full).")
            return False
        self.state.home = (lat, lon)
        msg = note or f"Home saved:\n{(label or f'{lat:.5f}, {lon:.5f}')[:120]}"
        self.statusBar().showMessage(
            f"Start point saved — {label[:60] if label else f'{lat:.5f}, {lon:.5f}'}",
            12000,
        )
        self._apply_home_ui(lat, lon, msg)
        return True

    def _set_origin(self, lat, lon, note=""):
        lat, lon = geo.normalize_ca_coords(lat, lon)
        self.state.home = (float(lat), float(lon))
        if not self.state.save():
            self._warn(
                "Could not save start point to disk.\n\n"
                f"Check that {DATA_DIR} is writable.")
        self._apply_home_ui(lat, lon, note)

    def _refresh_ports(self):
        self.combo_port.clear()
        self.combo_port.addItem("Auto-detect", None)
        for p in gps_reader.describe_ports():
            self.combo_port.addItem(f"{p['device']} - {p['description']}", p["device"])

    def _set_gps_port(self):
        dev = self.combo_port.currentData()
        try:
            self.gps.stop()
        except Exception:
            pass
        self.gps = gps_reader.GPSStream(preferred_port=dev)
        self.gps.start()
        self.statusBar().showMessage(f"GPS port set to {dev or 'Auto-detect'}", 4000)

    def _origin_from_gps(self):
        g = self.gps.latest()
        fix = gps_reader.fix_from_snapshot(g)
        if fix is not None:
            label = f"USB GPS {fix[0]:.5f}, {fix[1]:.5f}"
            self._commit_home_start(fix[0], fix[1], label, note="Origin set from USB GPS.")
            return
        self._warn(gps_reader.no_fix_message(g))

    def _origin_from_address(self):
        if not self._internet_allowed():
            self._field_notice(
                "Field mode — address search is off. Use GPS or coordinates; "
                "Tap I'm online at home for address search.")
            return
        if not geo.geocode_available():
            self._warn(
                "Address search needs the 'requests' library.\n\n"
                f"Launch with {LAUNCH_HINT} so dependencies are active.")
            return
        addr = self.txt_address.text().strip()
        if not addr:
            self.statusBar().showMessage("Type an address first.", 3000)
            return
        if getattr(self, "_geocode_thread", None) and self._geocode_thread.isRunning():
            self.statusBar().showMessage("Address search already running…", 3000)
            return

        dlg = QProgressDialog("Searching address online…\n\nThis can take 5–20 seconds.", None, 0, 0, self)
        dlg.setWindowTitle("Address search")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setMinimumWidth(380)
        self.btn_address.setEnabled(False)
        self.txt_address.setEnabled(False)

        thread = GeocodeThread(addr, limit=6)
        self._geocode_thread = thread

        def _restore_addr_ui():
            dlg.close()
            allow = self._internet_allowed()
            self.btn_address.setEnabled(allow)
            self.txt_address.setEnabled(allow)
            self._geocode_thread = None

        def done(cands: list, err: str):
            _restore_addr_ui()
            if err == "missing_requests":
                self._warn(f"Address search unavailable — {LAUNCH_HINT}.")
                return
            if err:
                self._warn(f"Address search failed:\n\n{err}")
                return
            if not cands:
                self._warn(
                    "Address not found.\n\n"
                    "Try:\n"
                    "• Full street + city + CA zip\n"
                    "  (e.g. 123 Main St, Garden Grove, CA 92840)\n"
                    "• Phone hotspot if work Wi‑Fi blocks geocoding sites\n"
                    "• Read USB GPS, or enter lat/lon → Save coordinates\n\n"
                    "Run: scripts\\diagnose_network.py (now includes address hosts)"
                )
                return
            self._pick_geocode_candidate(cands)

        thread.finished_result.connect(done)
        thread.start()
        dlg.show()

    def _pick_geocode_candidate(self, cands: list[dict]):
        from PySide6.QtWidgets import QInputDialog

        if len(cands) == 1:
            c = cands[0]
            self._commit_home_start(
                c["lat"], c["lon"], c["label"],
                note=f"Home saved:\n{c['label'][:120]}")
            return
        labels = [c["label"][:120] for c in cands]
        pick, ok = QInputDialog.getItem(
            self, "Pick your address", "Several matches — choose one:", labels, 0, False)
        if not ok or not pick:
            self.statusBar().showMessage("Address search cancelled.", 4000)
            return
        idx = labels.index(pick)
        c = cands[idx]
        self._commit_home_start(
            c["lat"], c["lon"], c["label"],
            note=f"Home saved:\n{c['label'][:120]}")

    def _origin_from_coords(self):
        lat, lon = self.spin_lat.value(), self.spin_lon.value()
        label = self.txt_address.text().strip() or f"{lat:.5f}, {lon:.5f}"
        if self._commit_home_start(lat, lon, label):
            self._refresh_map_preview()

    def _sync_upload_paths(self):
        self.state.excel_paths = list(self.excel_paths)
        self.state.est_paths = list(self.est_paths)
        self.state.save()

    @staticmethod
    def _stop_worker(thread: QThread | None, wait_ms: int = 4000):
        if thread is None or not thread.isRunning():
            return
        thread.requestInterruption()
        if thread.wait(wait_ms):
            return
        # Never QThread.terminate() — it corrupts serial/USB state on Windows.
        crash_log.log_error(
            RuntimeError(
                f"background worker still running after {wait_ms}ms "
                f"({type(thread).__name__})"),
            context="stop_worker_timeout",
        )

    def _pick_excel(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add Excel/CSV", "",
                                                "Spreadsheets (*.xlsx *.xls *.csv);;All files (*)")
        for p in paths:
            if p not in self.excel_paths:
                self.excel_paths.append(p)
        self._refresh_file_lists()
        self._sync_upload_paths()
        self._refresh_map_preview()

    def _pick_est(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add .EST maps", "",
                                                "EST maps (*.est *.EST);;All files (*)")
        for p in paths:
            if p not in self.est_paths:
                self.est_paths.append(p)
        self._refresh_file_lists()
        self._sync_upload_paths()
        self._refresh_map_preview()

    def _clear_files(self):
        if QMessageBox.question(
            self, "Clear file lists",
            "Remove Excel and .EST paths from this profile only?\n\n"
            "Your route, installs, and pickup progress are NOT cleared.\n"
            "Use \"Clear shift data…\" in Profile to wipe sites on the map.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self.excel_paths = []
        self.est_paths = []
        self._refresh_file_lists()
        self._sync_upload_paths()
        self._refresh_map_preview()
        self.statusBar().showMessage("File lists cleared — shift data unchanged.", 5000)

    def _start_fresh_profile(self):
        if QMessageBox.question(
            self, "Start fresh",
            "Clear everything for this profile?\n\n"
            "• Sites, route, install/pickup progress\n"
            "• Excel and .EST file lists\n\n"
            "Saved home/start point and offline map files stay.\n\n"
            f"Profile: {self.state.profile}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self._apply_shift_clear(wipe_upload_paths=True)
        self._go_page(0)

    def _load_demo_files(self):
        if not os.path.isfile(DEMO_CSV) or not os.path.isfile(DEMO_EST):
            self._warn("Demo files missing from demo_data/ folder.")
            return
        added = False
        if DEMO_CSV not in self.excel_paths:
            self.excel_paths.append(DEMO_CSV)
            added = True
        if DEMO_EST not in self.est_paths:
            self.est_paths.append(DEMO_EST)
            added = True
        self._refresh_file_lists()
        self._sync_upload_paths()
        self._refresh_map_preview()
        msg = "Demo files loaded (5 sites)." if added else "Demo files already in the list."
        self.statusBar().showMessage(
            f"{msg} Blue/red dots = begin/end of each line. BUILD ROUTE when ready.", 8000)

    @staticmethod
    def _est_label_from_path(path: str) -> str:
        """Use upload filename (no extension) so Day# matches the file."""
        return os.path.splitext(os.path.basename(path))[0]

    def _refresh_file_lists(self):
        self.list_excel.clear()
        self.list_excel.addItems([os.path.basename(p) for p in self.excel_paths])
        self.list_est.clear()
        for p in self.est_paths:
            item = QListWidgetItem(self._est_label_from_path(p))
            item.setToolTip(p)
            self.list_est.addItem(item)
        self._refresh_workflow_strip()

    def _est_configs(self) -> list[dict]:
        return [{"path": p, "label": self._est_label_from_path(p)} for p in self.est_paths]

    def _gather_area_points(self):
        """All segment endpoints + home so the road download bbox covers every street line."""
        pts = [list(self.state.home)]
        if self.state.stops:
            for s in self.state.stops:
                pts.append([s["begin_lat"], s["begin_lon"]])
                pts.append([s["end_lat"], s["end_lon"]])
            return pts
        try:
            sites = ingest.parse_excel_sites(self.excel_paths)
        except ingest.ExcelEngineMissing as exc:
            self._warn(str(exc))
            return pts
        stops = ingest.match_est_files(self._est_configs(), sites, self.state.home)
        for s in stops:
            pts.append([s["begin_lat"], s["begin_lon"]])
            pts.append([s["end_lat"], s["end_lon"]])
        return pts

    def _download_basemap(self):
        from core.map_setup import basemap_ok

        if not self._internet_allowed():
            self.statusBar().showMessage(
                "Go online (top bar) to download the California map.", 8000)
            return
        if basemap_ok(DATA_DIR):
            self.statusBar().showMessage("California map already installed.", 6000)
            return
        dlg = QProgressDialog(
            "Downloading California map (~10-20 min on Wi-Fi)...",
            "Cancel", 0, 0, self)
        dlg.setWindowTitle("California map")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setMinimumWidth(420)
        thread = MapSetupThread()
        self._map_setup_thread = thread

        def done(res: dict):
            dlg.close()
            if res.get("ok"):
                self._refresh_field_ready()
                self._push_state(fit=True)
                self.statusBar().showMessage("California map ready.", 8000)
            else:
                self.statusBar().showMessage(
                    f"Map download failed: {res.get('error', 'unknown')}", 12000)

        thread.finished_result.connect(done)
        thread.start()
        dlg.show()

    def _download_roads(self):
        if not self._internet_allowed():
            self._warn(
                "Field (offline) mode — download needs Wi‑Fi at home.\n\n"
                "Use Import road map if you copied road_graph.graphml, or "
                "Tap I'm online on home Wi‑Fi.")
            return
        if not road_router.HAS_ROUTING:
            self.statusBar().showMessage(
                "Road download skipped — import road_graph.graphml or keep going without it.",
                8000)
            return
        if road_router.has_graph(DATA_DIR):
            if QMessageBox.question(
                self, "Road map",
                "A road map is already saved for this area.\n\nRe-download from the internet anyway?",
            ) != QMessageBox.Yes:
                self.statusBar().showMessage("Using existing local road map.", 5000)
                return
        pts = self._gather_area_points()
        if len(pts) < 2:
            self._warn("Add your Excel + .EST files first so I know the area.")
            return
        try:
            _w, _s, _e, _n, span_mi = road_router.bbox_for_points(pts)
        except ValueError as exc:
            self._warn(str(exc))
            return
        net_err = road_router.probe_roads_internet()
        if net_err:
            self.statusBar().showMessage(
                "Road servers look blocked — trying download anyway (use hotspot if this fails)...",
                12000,
            )

        dlg = QProgressDialog("Downloading road map (needs internet)...", "Cancel", 0, 0, self)
        dlg.setWindowTitle("Downloading")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setMinimumWidth(400)

        import time as _time
        t0 = _time.time()
        etimer = QTimer(self)

        thread = DownloadRoadsThread(pts, DATA_DIR)
        self._dl_thread = thread

        def tick():
            dlg.setLabelText(
                f"Downloading road map from OpenStreetMap...\n\n"
                f"Elapsed: {int(_time.time() - t0)}s  (~{span_mi:.0f} mi work area)\n\n"
                f"Usually 30-90 seconds on home Wi-Fi.\n"
                f"If this passes 3 minutes, work firewall may be blocking it — Cancel, "
                f"then copy tds_data\\road_graph.graphml from home.")

        def done(res):
            etimer.stop()
            dlg.close()
            self._dl_thread = None
            if res.get("ok"):
                named = res.get("named_edges", 0)
                self._info(
                    f"Road map ready: {res['nodes']} intersections (~{res['radius_mi']} mi span).\n"
                    f"Street names on {named} road segments (for driving directions).\n"
                    f"Now press {BUILD_LABEL}.")
                self.statusBar().showMessage(
                    "Road map downloaded — build your route next.", 8000)
                self._refresh_field_ready()
            else:
                err = res.get("error", "unknown")
                self._warn(
                    f"Road map download failed:\n\n{err}\n\n"
                    "On work Wi‑Fi: use phone hotspot and try again, OR\n"
                    "copy tds_data\\road_graph.graphml from your home PC and tap\n"
                    "Import road map from file.\n\n"
                    "Cmd download:\n"
                    "  .venv\\Scripts\\python.exe scripts\\download_road_map.py --demo"
                )

        def canceled():
            etimer.stop()
            self._stop_worker(thread)
            dlg.close()
            self._dl_thread = None

        etimer.timeout.connect(tick)
        etimer.start(1000)
        dlg.canceled.connect(canceled)
        thread.finished_result.connect(done)
        thread.start()
        dlg.show()
        tick()

    def _import_roads(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import road map",
            DATA_DIR,
            "Road graph (*.graphml);;All files (*)",
        )
        if not path:
            return
        try:
            info = road_router.import_graph(path, DATA_DIR)
        except Exception as exc:  # noqa: BLE001
            self._warn(f"Could not import road map:\n\n{exc}")
            return
        nodes = info.get("nodes", 0)
        if nodes:
            self._info(
                f"Road map imported: {nodes:,} intersections.\n"
                f"Now press {BUILD_LABEL}.")
        elif road_router.has_graph(DATA_DIR):
            g = road_router.load_graph(DATA_DIR)
            n = len(g.nodes) if g else 0
            self._info(f"Road map imported and loaded ({n:,} nodes).\nNow press {BUILD_LABEL}.")
        else:
            mb = info.get("size_mb", "?")
            self._warn(
                f"File copied ({mb} MB) but graph did not load.\n\n"
                f"{LAUNCH_HINT} or re-copy road_graph.graphml from home PC."
            )
            return
        self.statusBar().showMessage("Road map imported from file.", 8000)
        self._refresh_field_ready()
