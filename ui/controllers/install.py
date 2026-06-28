"""Install controller mixin - P46 E1.3 extract from main.py."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

import gps_reader
import road_router
from core import direction as direction_rules
from core import geo, install_checklist
from core.state import ca_now
from ui.paths import DATA_DIR, DIRECTIONS
from ui.threads import FieldStreetThread


class InstallControllerMixin:
    # ------------------------------------------------------- Install UI/flow
    def _refresh_install(self):
        done, total = self.state.progress_install()
        if not self.state.stops or self.current_index >= len(self.state.stops):
            self.lbl_install_title.setText("No stop selected.")
            self.lbl_install_prog.setText("")
            if hasattr(self, "lbl_cross_hint"):
                self.lbl_cross_hint.setText("")
            return
        s = self.state.stops[self.current_index]
        vis = self._visible_stop_indices()
        try:
            seq = vis.index(self.current_index) + 1
            seq_total = len(vis)
        except ValueError:
            seq = self.current_index + 1
            seq_total = total
        day = str(s.get("sheet") or "").strip()
        day_txt = f" · {day}" if day else ""
        self.lbl_install_title.setText(
            f"Stop {seq}/{seq_total} · Site {s['id']}{day_txt}")
        side = str(s.get("cross_side") or "").strip()
        cross_txt = ""
        if s.get("cross_lat") is not None:
            cross_txt = (
                f"Drive-to on line"
                f"{f' ({side})' if side else ''}")
        from ui.simple_mode import COMPACT_UI
        if COMPACT_UI:
            prog = f"{self._street_label(s)} · {done}/{total} done"
            if not s.get("cross_lat"):
                prog += " · build route for crossing"
            self.lbl_install_prog.setText(prog)
            if hasattr(self, "lbl_cross_hint"):
                self.lbl_cross_hint.setText("")
        else:
            self.lbl_cross_hint.setText(
                cross_txt or "Crossing not set — BUILD ROUTE after road map download.")
            self.lbl_install_prog.setText(
                f"{s.get('sheet', '')} · {self._street_label(s)} · {done}/{total} installed")
        raw = str(s.get("street", "")).strip()
        self.txt_street.setText(raw if raw and raw.lower() not in ("nan", "none", "nat") else "")
        raw_dir = str(s.get("direction") or "").strip().lower()
        if raw_dir not in DIRECTIONS:
            raw_dir = "n"
        self.combo_dir.blockSignals(True)
        self.combo_dir.setCurrentText(raw_dir)
        self.combo_dir.blockSignals(False)
        g_snap = self.gps.latest()
        hdg = g_snap.get("heading_display") or g_snap.get("heading_locked") or g_snap.get("heading")
        src = str(s.get("direction_source") or "")
        if (
            not s.get("installed")
            and src != "manual"
            and hdg is not None
            and g_snap.get("heading_mode") == "locked"
        ):
            hint = direction_rules.infer_from_heading(hdg)
            self.combo_dir.blockSignals(True)
            self.combo_dir.setCurrentText(hint["direction"])
            self.combo_dir.blockSignals(False)
            s["direction"] = hint["direction"]
            s["direction_source"] = "gps"
        if hasattr(self, "lbl_direction_hint"):
            self.lbl_direction_hint.setText(direction_rules.direction_hint_text(s))
        self.spin_lanes.setValue(int(s.get("lanes", 2)))
        self.txt_serial.setText(str(s.get("serial", "")))
        self.txt_notes.setPlainText(str(s.get("notes", "")))
        fl, fo = s.get("field_lat"), s.get("field_lon")
        if fl:
            src = str(s.get("field_coord_source") or "gps")
            prefix = "Manual GPS" if src == "manual" else "Field GPS"
            self.lbl_grab.setText(f"{prefix}: {fl:.5f}, {fo:.5f}")
        else:
            self.lbl_grab.setText("")
        warn = str(s.get("street_warning") or "").strip()
        if not warn and road_router.has_graph(DATA_DIR):
            try:
                from core import street_intel
                g = road_router.load_graph(DATA_DIR)
                cross = None
                if s.get("cross_lat") is not None:
                    cross = (float(s["cross_lat"]), float(s["cross_lon"]))
                r = street_intel.analyze_segment(
                    g,
                    (float(s["begin_lat"]), float(s["begin_lon"])),
                    (float(s["end_lat"]), float(s["end_lon"])),
                    cross,
                )
                warn = str(r.get("message") or "").strip()
                if warn:
                    s["street_warning"] = warn
            except Exception:
                pass
        self.lbl_street_warn.setText(warn)
        self.lbl_street_warn.setVisible(bool(warn))
        self._refresh_install_checklist()
        self._update_compass_labels(self.gps.latest())
        self._update_counter_labels()
        self._counter_show_memory()
        if self.state.stops and self.current_index < len(self.state.stops):
            s = self.state.stops[self.current_index]
            uid = s.get("uid")
            if uid != self._counter_serial_grab_uid and not str(s.get("serial", "")).strip():
                self._counter_serial_grab_uid = uid
                QTimer.singleShot(600, lambda: self._counter_read_serial(auto=True))

    def _on_install_dir_changed(self, *_):
        if self.state.stops and self.current_index < len(self.state.stops):
            s = self.state.stops[self.current_index]
            s["direction"] = self.combo_dir.currentText()
            s["direction_source"] = "manual"
            if hasattr(self, "lbl_direction_hint"):
                self.lbl_direction_hint.setText(direction_rules.direction_hint_text(s))
        self._schedule_autosave()
        self._update_counter_labels()

    def _refresh_install_checklist(self) -> None:
        if not hasattr(self, "lbl_install_checklist"):
            return
        if not self.state.stops or self.current_index >= len(self.state.stops):
            self.lbl_install_checklist.setText("")
            return
        s = self.state.stops[self.current_index]
        if hasattr(self, "txt_serial") and self.txt_serial.text().strip():
            sn = self.txt_serial.text().strip()
            s["serial"] = sn
            s["counter_serial"] = sn
        items = install_checklist.checklist_for_stop(s)
        self.lbl_install_checklist.setText(install_checklist.format_checklist_text(items))
        ready = install_checklist.all_ready(items)
        self.lbl_install_checklist.setProperty("allReady", "true" if ready else "false")
        st = self.lbl_install_checklist.style()
        st.unpolish(self.lbl_install_checklist)
        st.polish(self.lbl_install_checklist)

    def _set_dir_from_compass(self):
        g = self.gps.latest()
        hdg = g.get("heading_display") or g.get("heading_locked") or g.get("heading")
        if hdg is None:
            self._warn("No compass reading yet. Drive a short distance, then stop.")
            return
        hint = direction_rules.infer_from_heading(hdg)
        self.combo_dir.setCurrentText(hint["direction"])
        if self.state.stops and self.current_index < len(self.state.stops):
            s = self.state.stops[self.current_index]
            s["direction"] = hint["direction"]
            s["direction_source"] = "gps"
            if hasattr(self, "lbl_direction_hint"):
                self.lbl_direction_hint.setText(direction_rules.direction_hint_text(s))
        self._schedule_autosave()
        self._update_counter_labels()
        card = self._heading_cardinal(hdg)
        self.statusBar().showMessage(
            f"Direction {hint['direction']} from compass: {hdg:.0f}° ({card})", 5000)

    def _manual_grab_prompt(self) -> str:
        if not self.state.stops or self.current_index >= len(self.state.stops):
            return "Drop pin — click the map for this site"
        s = self.state.stops[self.current_index]
        return f"Drop pin — Site {s.get('id', '?')}: click the map (drag orange pin to adjust)"

    def _sync_manual_grab_btn(self) -> None:
        btn = getattr(self, "btn_manual_grab", None)
        if btn is None:
            return
        on = self._manual_grab_mode
        btn.setChecked(on)
        btn.setText("Cancel pin" if on else "Drop pin")

    def _end_manual_grab(self, *, silent: bool = False) -> None:
        if not self._manual_grab_mode:
            return
        self._pin_persist_timer.stop()
        self._flush_pin_persist()
        self._manual_grab_mode = False
        self._sync_manual_grab_btn()
        self.bridge.set_manual_grab(False)
        if self.state.stops and self.current_index < len(self.state.stops):
            s = self.state.stops[self.current_index]
            if s.get("field_geocode_pending") and s.get("field_lat") is not None:
                self._start_field_street_thread(
                    self.current_index,
                    float(s["field_lat"]),
                    float(s["field_lon"]),
                    prefer_online=self._internet_allowed(),
                )
        self._push_state()
        if not silent:
            self.statusBar().showMessage("Drop pin cancelled.", 4000)

    def _begin_manual_grab(self) -> None:
        if not self.state.stops or self.current_index >= len(self.state.stops):
            self._warn("No stop selected — build a route first.")
            return
        if self._route_pick_mode:
            self._warn("Finish route pick first, or clear pick mode.")
            return
        self._follow_before_manual_grab = bool(self._gps_follow)
        if self._gps_follow:
            self._gps_follow = False
            self.bridge.set_follow(False)
        self._manual_grab_mode = True
        self._sync_manual_grab_btn()
        s = self.state.stops[self.current_index]
        lat, lon = self.state.point(s)
        prompt = self._manual_grab_prompt()
        self.bridge.set_manual_grab(True, prompt)
        self.bridge.fly_to(lat, lon, 16)
        online = self._internet_allowed()
        hint = (
            "Drop pin — click the map. Orange pin saves GPS for this site (drag to adjust)."
            if online
            else "Drop pin — click the map. GPS saves now; street name updates when you're on Wi‑Fi."
        )
        self.statusBar().showMessage(hint, 10000)

    def _confirm_manual_grab_pin(self) -> None:
        if not self._manual_grab_mode:
            self.statusBar().showMessage("Turn on Drop pin first (M).", 5000)
            return

        def _after_confirm(raw) -> None:
            ok = raw is True or raw == "true"
            if not ok:
                self.statusBar().showMessage(
                    "Click the map first to drop an orange pin.", 6000)

        self.view.page().runJavaScript(
            "window.__tdConfirmDropPin ? window.__tdConfirmDropPin() : false",
            _after_confirm,
        )

    def _toggle_manual_grab(self) -> None:
        if self._manual_grab_mode:
            self._end_manual_grab()
        else:
            self._begin_manual_grab()

    def _manual_grab_at(self, lat: float, lon: float) -> None:
        if not self.state.stops or self.current_index >= len(self.state.stops):
            self._end_manual_grab(silent=True)
            return
        if not self._save_field_position(lat, lon, source="manual"):
            return
        s = self.state.stops[self.current_index]
        self.statusBar().showMessage(
            f"Site {s.get('id', '?')} GPS saved from map pin — drag pin to adjust.", 6000)

    def _retry_pending_field_geocode(self) -> None:
        """When Wi‑Fi returns, reverse-geocode streets for any manual/offline pin drops."""
        if not self._internet_allowed():
            return
        updated = 0
        for idx, s in enumerate(self.state.stops):
            if not s.get("field_geocode_pending"):
                continue
            lat, lon = s.get("field_lat"), s.get("field_lon")
            if lat is None or lon is None:
                s["field_geocode_pending"] = False
                continue
            online_street = geo.street_from_coords(float(lat), float(lon))
            if not online_street:
                continue
            s["field_geocode_pending"] = False
            s["street"] = online_street
            if idx == self.current_index and hasattr(self, "txt_street"):
                self.txt_street.setText(online_street)
            updated += 1
        if updated:
            self._persist_shift(quiet=True)
            self._push_state()
            self._refresh_install_checklist()
            if hasattr(self, "lbl_grab") and self.state.stops and self.current_index < len(self.state.stops):
                s = self.state.stops[self.current_index]
                fl, fo = s.get("field_lat"), s.get("field_lon")
                if fl is not None and fo is not None:
                    self.lbl_grab.setText(f"Manual GPS: {float(fl):.5f}, {float(fo):.5f}")
            self.statusBar().showMessage(
                f"Wi‑Fi on — updated street name for {updated} pinned site(s).", 8000)

    def _schedule_pin_persist(self) -> None:
        self._pin_persist_timer.start(450)

    def _flush_pin_persist(self) -> None:
        self._flush_install_form()
        self._persist_shift(quiet=True)

    def _start_field_street_thread(
        self,
        stop_idx: int,
        lat: float,
        lon: float,
        *,
        prefer_online: bool,
    ) -> None:
        thread = getattr(self, "_field_street_thread", None)
        if thread is not None and thread.isRunning():
            thread.requestInterruption()
            thread.wait(200)
        self._field_street_thread = FieldStreetThread(
            stop_idx, lat, lon, DATA_DIR, prefer_online=prefer_online,
        )
        self._field_street_thread.finished_result.connect(self._on_field_street_result)
        self._field_street_thread.start()

    def _on_field_street_result(
        self,
        stop_idx: int,
        lat: float,
        lon: float,
        street: str,
        src_tag: str,
        warning: str,
    ) -> None:
        self._field_street_thread = None
        if not self.state.stops or stop_idx >= len(self.state.stops):
            return
        s = self.state.stops[stop_idx]
        if s.get("field_lat") != lat or s.get("field_lon") != lon:
            return
        prefer_online = self._internet_allowed()
        if street:
            if stop_idx == self.current_index:
                self.txt_street.setText(street)
            s["field_geocode_pending"] = False
            hint = "online" if src_tag == "online" else "offline road map"
            self.statusBar().showMessage(f"Install GPS saved — street from {hint}.", 5000)
        else:
            excel_st = str(s.get("street", "")).strip()
            if excel_st and not excel_st.lower().startswith("site "):
                if stop_idx == self.current_index:
                    self.txt_street.setText(excel_st)
                s["field_geocode_pending"] = not prefer_online
                self.statusBar().showMessage("Install GPS saved — street from Excel.", 5000)
            else:
                s["field_geocode_pending"] = not prefer_online
                self.statusBar().showMessage(
                    "Install GPS saved. Type street or tap I'm online for geocode.", 6000)
        if warning:
            s["street_warning"] = warning
            if stop_idx == self.current_index:
                self.lbl_street_warn.setText(warning)
                self.lbl_street_warn.setVisible(True)
        self._persist_shift(quiet=True)
        if stop_idx == self.current_index:
            self._refresh_install_checklist()

    def _save_field_position(self, lat: float, lon: float, *, source: str = "gps") -> bool:
        """Persist install field_lat/lon; heavy street lookup stays off the click path."""
        if not self.state.stops or self.current_index >= len(self.state.stops):
            return False
        lat, lon = geo.normalize_ca_coords(float(lat), float(lon))
        if not geo.ca_coords_plausible(lat, lon):
            self._warn("That point is outside California — click a street on the map.")
            return False
        s = self.state.stops[self.current_index]
        s["field_lat"], s["field_lon"] = lat, lon
        s["field_coord_source"] = source
        label = "Manual GPS" if source == "manual" else "Field GPS"
        self.lbl_grab.setText(f"{label}: {lat:.5f}, {lon:.5f}")
        s["field_geocode_pending"] = True
        site_id = str(s.get("id", ""))
        uid = str(s.get("uid") or "")
        self.bridge.send_field_pin(uid, lat, lon, site_id, pending=(source == "manual"))
        self.statusBar().showMessage(
            f"Site {site_id} pin saved at {lat:.5f}, {lon:.5f}.", 4000)
        self._schedule_pin_persist()
        self._refresh_install_checklist()
        if source != "manual":
            self._start_field_street_thread(
                self.current_index, lat, lon, prefer_online=self._internet_allowed(),
            )
        return True

    def _finish_field_street_lookup(
        self, stop_idx: int, lat: float, lon: float, *, source: str = "gps",
    ) -> None:
        """Legacy entry — street lookup now runs in FieldStreetThread."""
        self._start_field_street_thread(
            stop_idx, lat, lon, prefer_online=self._internet_allowed(),
        )

    def _grab_gps_here(self):
        if not self.state.stops or self.current_index >= len(self.state.stops):
            self._warn("No stop selected — build a route first.")
            return
        g = self.gps.latest()
        fix = gps_reader.fix_from_snapshot(g)
        if fix is None:
            if hasattr(self, "lbl_grab"):
                self.lbl_grab.setText("No GPS fix")
            self._warn(gps_reader.no_fix_message(g))
            return
        lat, lon = fix
        sats = g.get("satellites", 0) if g.get("fix") else 0
        if self._save_field_position(lat, lon, source="gps") and hasattr(self, "lbl_grab"):
            fl, fo = lat, lon
            self.lbl_grab.setText(f"Field GPS: {fl:.5f}, {fo:.5f}  ({sats} sats)")

    def _commit_install(self, installed: bool):
        if not self.state.stops or self.current_index >= len(self.state.stops):
            return
        s = self.state.stops[self.current_index]
        self._flush_install_form()
        self._sync_counter_fields(s)
        notes = self.txt_notes.toPlainText()
        d, lanes, serial = geo.parse_dictation(notes, self.combo_dir.currentText(),
                                               self.spin_lanes.value(), self.txt_serial.text())
        if serial:
            s["serial"] = serial
            s["counter_serial"] = serial
        if installed and serial:
            dup = install_checklist.find_duplicate_serial(
                self.state.stops, s["uid"], serial)
            if dup:
                street = self._street_label(dup)
                if QMessageBox.question(
                    self,
                    "Duplicate counter serial",
                    f"Serial {serial} is already on Site {dup.get('id')} ({street}).\n\n"
                    "Install on this site anyway?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                ) != QMessageBox.Yes:
                    return
        unit_id = str(s.get("counter_unit_id") or "").strip()
        if installed and unit_id:
            dup_uid = install_checklist.find_duplicate_unit_id(
                self.state.stops, s["uid"], unit_id)
            if dup_uid:
                street = self._street_label(dup_uid)
                if QMessageBox.question(
                    self,
                    "Duplicate Unit ID",
                    f"Unit ID {unit_id} is already on Site {dup_uid.get('id')} ({street}).\n\n"
                    "Install anyway?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                ) != QMessageBox.Yes:
                    return
        self._push_undo(
            "install" if installed else "skip",
            s["uid"],
            self._snapshot_stop(s),
            site_id=s["id"],
            current_index=self.current_index,
        )
        date, exact = ca_now()
        s.update({"street": self.txt_street.text().strip(), "direction": d, "lanes": lanes,
                  "serial": s.get("serial", serial), "notes": notes,
                  "installed": installed, "skipped": not installed,
                  "date": date, "exact_time": exact})
        self._sync_counter_fields(s)
        self._persist_shift(quiet=True)
        self._counter_inventory_shift()
        self._push_state()
        self._refresh_route_list()
        self._refresh_audit()
        self._refresh_field_alerts()
        verb = "Installed" if installed else "Skipped"
        self.statusBar().showMessage(
            f"Site {s.get('id', '?')} {verb} — saved locally.", 8000)
        if installed:
            self._maybe_export_nudge()
        self._nav_install(1)

    def _nav_install(self, step: int):
        if not self.state.stops:
            return
        self._flush_install_form()
        self._persist_shift(quiet=True)
        vis = self._visible_stop_indices()
        if not vis:
            return
        try:
            pos = vis.index(self.current_index)
        except ValueError:
            pos = 0
        pos = max(0, min(len(vis) - 1, pos + step))
        self.current_index = vis[pos]
        self._end_manual_grab(silent=True)
        self._refresh_install()
        self._center_current()

    def _center_current(self):
        if self.state.stops and self.current_index < len(self.state.stops):
            lat, lon = self.state.point(self.state.stops[self.current_index])
            self.bridge.fly_to(lat, lon, 13)

