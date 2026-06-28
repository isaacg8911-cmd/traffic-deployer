"""Counter controller mixin — P46 E1.2 extract from main.py (PicoCount USB)."""

from __future__ import annotations

import os

from PySide6.QtCore import QTimer

from core import crash_log, picocount
from core.state import ca_now
from ui.counter_ui import apply_counter_status
from ui.paths import COUNTER_DOWNLOAD_DIR
from ui.threads import PicocountThread


class CounterControllerMixin:
    # ------------------------------------------------------- PicoCount counter
    def _counter_selected_port(self) -> str | None:
        if not hasattr(self, "combo_counter_port"):
            return None
        idx = self.combo_counter_port.currentIndex()
        if idx >= 0:
            data = self.combo_counter_port.itemData(idx)
            if data:
                return str(data)
        p = self.combo_counter_port.currentText().strip()
        if not p or p.startswith("("):
            return None
        return p.split(" ", 1)[0].strip()

    def _counter_list_ports(self) -> None:
        """List PicoCount COM ports only — GPS adapters stay out of the dropdown."""
        if not hasattr(self, "combo_counter_port"):
            return
        cur = self._counter_selected_port()
        self.combo_counter_port.clear()
        labeled = picocount.counter_ports_labeled()
        if not labeled:
            self.combo_counter_port.addItem("(none — plug PicoCount USB)")
        else:
            for device, label in labeled:
                self.combo_counter_port.addItem(label, device)
        if cur:
            for i in range(self.combo_counter_port.count()):
                if self.combo_counter_port.itemData(i) == cur:
                    self.combo_counter_port.setCurrentIndex(i)
                    break
        elif labeled:
            pref = picocount.preferred_counter_port([d for d, _ in labeled])
            if pref:
                for i in range(self.combo_counter_port.count()):
                    if self.combo_counter_port.itemData(i) == pref:
                        self.combo_counter_port.setCurrentIndex(i)
                        break

    def _counter_pause_gps(self) -> None:
        if self._gps_paused_for_counter:
            return
        self._gps_paused_for_counter = True
        self.gps.stop(join_timeout=3.5)

    def _counter_resume_gps(self) -> None:
        if not self._gps_paused_for_counter:
            return
        self._gps_paused_for_counter = False
        self.gps.start()

    def _counter_refresh_and_connect(self) -> None:
        crash_log.set_last_action("PicoCount refresh")
        self._counter_list_ports()
        if self._picocount_thread and self._picocount_thread.isRunning():
            return
        port = self._counter_selected_port()
        if not port:
            apply_counter_status(
                self.lbl_counter_status, "fail", "No PicoCount port — plug download USB cable.")
            return
        if picocount.is_gps_port(port):
            apply_counter_status(
                self.lbl_counter_status, "fail", f"{port} is GPS — select the PicoCount port.")
            return
        self._counter_set_busy("Refreshing counter… (GPS paused)")
        self._counter_pause_gps()
        QTimer.singleShot(1000, self._counter_connect_after_gps_pause)

    def _counter_connect_after_gps_pause(self) -> None:
        if self._picocount_thread and self._picocount_thread.isRunning():
            return
        port = self._counter_selected_port()

        def wrap(r):
            r["_op"] = "probe"
            self._on_picocount_done(r)

        thread = PicocountThread("probe", port=port)
        self._picocount_thread = thread
        thread.finished_result.connect(wrap)
        thread.start()

    def _planned_counter_unit_id(self) -> str:
        if not self.state.stops or self.current_index >= len(self.state.stops):
            return ""
        s = self.state.stops[self.current_index]
        g = self.gps.latest()
        hdg = g.get("heading_display") or g.get("heading_locked") or g.get("heading")
        return picocount.build_unit_id(
            s.get("id", ""),
            self.combo_dir.currentText() if hasattr(self, "combo_dir") else "n",
            heading_deg=hdg,
        )

    def _update_counter_labels(self) -> None:
        if not hasattr(self, "lbl_counter_unit"):
            return
        uid = self._planned_counter_unit_id()
        on_stop = ""
        if self.state.stops and self.current_index < len(self.state.stops):
            s = self.state.stops[self.current_index]
            on_stop = str(s.get("counter_unit_id") or "").strip()
        if on_stop:
            self.lbl_counter_unit.setText(f"Unit ID on counter: {on_stop}")
        elif uid:
            self.lbl_counter_unit.setText(f"Next Unit ID (Auto-name / Clear): {uid}")
        else:
            self.lbl_counter_unit.setText("")
        if self.state.stops and self.current_index < len(self.state.stops):
            s = self.state.stops[self.current_index]
            parts = []
            sn = str(s.get("counter_serial") or s.get("serial") or "").strip()
            if sn:
                parts.append(f"Serial {sn}")
            if s.get("counter_unit_id"):
                parts.append(f"Unit ID {s['counter_unit_id']}")
            if s.get("counter_download_path"):
                parts.append("Data downloaded")
            if parts and hasattr(self, "lbl_counter_download"):
                self.lbl_counter_download.setText(" · ".join(parts))

    def _counter_set_busy(self, msg: str) -> None:
        apply_counter_status(self.lbl_counter_status, "busy", msg)
        for w in (
            self.btn_counter_refresh,
            self.btn_counter_clear,
            getattr(self, "btn_counter_autoname", None),
            getattr(self, "btn_counter_download", None),
        ):
            if w is not None:
                w.setEnabled(False)

    def _counter_clear_busy(self) -> None:
        for w in (
            self.btn_counter_refresh,
            self.btn_counter_clear,
            getattr(self, "btn_counter_autoname", None),
            getattr(self, "btn_counter_download", None),
        ):
            if w is not None:
                w.setEnabled(True)
        if hasattr(self, "btn_counter_download"):
            self.btn_counter_download.setEnabled(self._counter_connected)
        self._update_counter_labels()

    def _counter_show_memory(self, res: dict | None = None) -> None:
        if not hasattr(self, "lbl_counter_data"):
            return
        if res is not None:
            if res.get("ok"):
                self._counter_memory_bytes = int(res.get("bytes") or 0)
            else:
                self._counter_memory_bytes = None
        b = self._counter_memory_bytes
        if b is None:
            self.lbl_counter_data.setText("")
            return
        if b <= 0:
            self.lbl_counter_data.setText("Counter data: 0 bytes — empty")
            self.lbl_counter_data.setProperty("counterEmpty", "true")
        else:
            self.lbl_counter_data.setText(f"Counter data: ~{b:,} bytes stored")
            self.lbl_counter_data.setProperty("counterEmpty", "false")
        st = self.lbl_counter_data.style()
        st.unpolish(self.lbl_counter_data)
        st.polish(self.lbl_counter_data)

    def _on_picocount_done(self, res: dict) -> None:
        self._picocount_thread = None
        op = res.pop("_op", "")
        resume_gps = True
        try:
            self._on_picocount_done_body(res, op, resume_gps_holder := {"v": True})
            resume_gps = resume_gps_holder["v"]
        except Exception as exc:  # noqa: BLE001
            path = crash_log.log_error(exc, context=f"picocount_{op or 'unknown'}")
            if hasattr(self, "lbl_counter_status"):
                apply_counter_status(
                    self.lbl_counter_status,
                    "fail",
                    f"Counter error — see {os.path.basename(path)} in tds_data/crashes/",
                )
            self._warn(
                f"PicoCount operation failed safely (app kept running).\n\n"
                f"Log saved:\n{path}")
        finally:
            if resume_gps:
                self._counter_resume_gps()
        self._counter_clear_busy()
        self._update_counter_labels()
        self._refresh_install_checklist()
        self._refresh_field_alerts()

    def _on_picocount_done_body(self, res: dict, op: str, resume_gps_holder: dict) -> None:
        if op == "probe":
            self._set_counter_connected_ui(bool(res.get("ok")))
            if res.get("ok"):
                self._counter_inventory_usb(res, event="probe")
                self._update_counter_volts(res)
                self._counter_show_memory(res)
                unit = str(res.get("unit_id") or "").strip()
                sn = str(res.get("serial_number") or "").strip()
                mem = res.get("label") or "connected"
                if sn and hasattr(self, "txt_serial"):
                    self.txt_serial.setText(sn)
                if sn and self.state.stops and self.current_index < len(self.state.stops):
                    s = self.state.stops[self.current_index]
                    s["counter_serial"] = sn
                    s["serial"] = sn
                    self._persist_shift(quiet=True)
                parts = [mem]
                if sn:
                    parts.append(f"Serial {sn}")
                if unit:
                    parts.append(f"Unit ID {unit}")
                volts = res.get("battery_volts")
                if volts is not None:
                    parts.append(f"Battery {volts:.2f} V")
                apply_counter_status(
                    self.lbl_counter_status,
                    "ok",
                    "Connected — " + " · ".join(parts),
                )
                self.statusBar().showMessage("PicoCount connected.", 6000)
                if (
                    self._counter_selected_port()
                    and not sn
                    and hasattr(self, "txt_serial")
                    and not self.txt_serial.text().strip()
                ):
                    resume_gps_holder["v"] = False
                    self._counter_read_serial(auto=True)
            else:
                self._update_counter_volts(None)
                self._counter_show_memory(None)
                apply_counter_status(
                    self.lbl_counter_status,
                    "fail",
                    res.get("error") or res.get("message", "Not connected"),
                )
        elif op == "serial":
            if res.get("ok"):
                self._counter_inventory_usb(res, event="serial")
                sn = str(res.get("serial_number", "")).strip()
                if sn and hasattr(self, "txt_serial"):
                    self.txt_serial.setText(sn)
                if self.state.stops and self.current_index < len(self.state.stops):
                    s = self.state.stops[self.current_index]
                    if sn:
                        s["counter_serial"] = sn
                        s["serial"] = sn
                    self._persist_shift(quiet=True)
                apply_counter_status(
                    self.lbl_counter_status,
                    "ok",
                    f"Serial {sn or '—'} · {res.get('model', '')} {res.get('firmware', '')}",
                )
                self.statusBar().showMessage("Counter serial read.", 5000)
            else:
                apply_counter_status(
                    self.lbl_counter_status,
                    "fail",
                    res.get("error", "Serial read failed"),
                )
        elif op == "clear_configure":
            if res.get("ok"):
                self._counter_inventory_usb({
                    "ok": True,
                    "serial_number": res.get("serial_number"),
                    "unit_id": res.get("unit_id"),
                    "battery_volts": res.get("battery_volts"),
                    "bytes": res.get("bytes_after"),
                    "label": res.get("memory_label") or "0 bytes — empty",
                    "model": res.get("model"),
                    "firmware": res.get("firmware"),
                }, event="clear")
                self._counter_memory_bytes = int(res.get("bytes_after") or 0)
                self._counter_show_memory()
                if self.state.stops and self.current_index < len(self.state.stops):
                    s = self.state.stops[self.current_index]
                    s["counter_unit_id"] = res.get("unit_id", "")
                    s["counter_serial"] = res.get("serial_number", s.get("counter_serial", ""))
                    if res.get("serial_number"):
                        s["serial"] = str(res["serial_number"])
                    s["counter_cleared_at"] = res.get("cleared_at") or ca_now()[1]
                    if res.get("serial_number") and hasattr(self, "txt_serial"):
                        self.txt_serial.setText(str(res["serial_number"]))
                    self._persist_shift(quiet=True)
                before = int(res.get("bytes_before") or 0)
                after = int(res.get("bytes_after") or 0)
                apply_counter_status(
                    self.lbl_counter_status,
                    "ok",
                    f"Cleared {before:,} → {after:,} bytes · Unit ID {res.get('unit_id', '')}",
                )
                self.statusBar().showMessage("Counter cleared and configured for this site.", 8000)
            else:
                apply_counter_status(
                    self.lbl_counter_status,
                    "fail",
                    res.get("error", "Clear/configure failed"),
                )
                self._warn(res.get("error", "Counter operation failed"))
        elif op == "rename":
            if res.get("ok"):
                self._counter_inventory_usb(res, event="rename")
                if self.state.stops and self.current_index < len(self.state.stops):
                    s = self.state.stops[self.current_index]
                    s["counter_unit_id"] = res.get("unit_id", "")
                    sn = str(res.get("serial_number") or "").strip()
                    if sn:
                        s["counter_serial"] = sn
                        s["serial"] = sn
                        if hasattr(self, "txt_serial"):
                            self.txt_serial.setText(sn)
                    self._persist_shift(quiet=True)
                apply_counter_status(
                    self.lbl_counter_status,
                    "ok",
                    f"Unit ID set to {res.get('unit_id', '')}",
                )
                self.statusBar().showMessage("Counter renamed for this site.", 6000)
            else:
                apply_counter_status(
                    self.lbl_counter_status,
                    "fail",
                    res.get("error", "Rename failed"),
                )
                self._warn(res.get("error", "Could not rename counter"))
        elif op == "download":
            if res.get("ok"):
                if self.state.stops and self.pickup_index < len(self._installed_stops()):
                    items = self._installed_stops()
                    s = items[min(self.pickup_index, len(items) - 1)]
                    s["counter_download_path"] = res.get("path", "")
                    self._persist_shift(quiet=True)
                    self._refresh_pickup()
                self._counter_inventory_shift()
                apply_counter_status(
                    self.lbl_counter_status,
                    "ok",
                    f"Downloaded {res.get('bytes', 0):,} bytes → {os.path.basename(res.get('path', ''))}",
                )
                self.statusBar().showMessage("Counter data saved locally.", 8000)
            else:
                apply_counter_status(
                    self.lbl_counter_status,
                    "fail",
                    res.get("error", "Download failed"),
                )
                self._warn(res.get("error", "Could not download counter data"))

    def _counter_read_serial(self, *, auto: bool = False) -> None:
        if auto and not hasattr(self, "txt_serial"):
            return
        if auto and self.txt_serial.text().strip():
            return
        if self._picocount_thread and self._picocount_thread.isRunning():
            return
        if not auto:
            self._counter_set_busy("Reading counter serial (slow)…")
        self._counter_pause_gps()

        def wrap(r):
            r["_op"] = "serial"
            self._on_picocount_done(r)

        thread = PicocountThread("serial", port=self._counter_selected_port())
        self._picocount_thread = thread
        thread.finished_result.connect(wrap)
        thread.start()

    def _counter_clear_configure(self) -> None:
        uid = self._planned_counter_unit_id()
        if not uid:
            self._warn("Select a stop first.")
            return
        if not self._counter_connected:
            self._warn("Connect counter first — tap Refresh.")
            return
        if self._picocount_thread and self._picocount_thread.isRunning():
            return
        crash_log.set_last_action(f"PicoCount clear {uid}")
        self._counter_set_busy(f"Clearing counter · {uid}… (GPS paused)")
        self._counter_pause_gps()
        QTimer.singleShot(1000, self._counter_clear_configure_after_pause)

    def _counter_clear_configure_after_pause(self) -> None:
        if self._picocount_thread and self._picocount_thread.isRunning():
            return
        uid = self._planned_counter_unit_id()
        if not uid:
            self._counter_resume_gps()
            self._counter_clear_busy()
            return

        def wrap(r):
            r["_op"] = "clear_configure"
            self._on_picocount_done(r)

        thread = PicocountThread(
            "clear_configure",
            port=self._counter_selected_port(),
            unit_id=uid,
        )
        self._picocount_thread = thread
        thread.finished_result.connect(wrap)
        thread.start()

    def _counter_autoname(self) -> None:
        uid = self._planned_counter_unit_id()
        if not uid:
            self._warn("Select a stop first.")
            return
        if not self._counter_connected:
            self._warn("Connect counter first — tap Refresh.")
            return
        if self._picocount_thread and self._picocount_thread.isRunning():
            return
        self._counter_set_busy(f"Naming counter · {uid}…")
        self._counter_pause_gps()

        def wrap(r):
            r["_op"] = "rename"
            self._on_picocount_done(r)

        thread = PicocountThread(
            "rename",
            port=self._counter_selected_port(),
            unit_id=uid,
        )
        self._picocount_thread = thread
        thread.finished_result.connect(wrap)
        thread.start()

    def _counter_download_pickup(self) -> None:
        items = self._installed_stops()
        if not items or self.pickup_index >= len(items):
            self._warn("Select an installed site on Pickup first.")
            return
        s = items[self.pickup_index]
        os.makedirs(COUNTER_DOWNLOAD_DIR, exist_ok=True)
        fname = f"site_{s.get('id', 'x')}_{s.get('counter_unit_id', 'data')}.pcbin"
        fname = "".join(c if c.isalnum() or c in "._-" else "_" for c in fname)
        dest = os.path.join(COUNTER_DOWNLOAD_DIR, self.state.profile, fname)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if self._picocount_thread and self._picocount_thread.isRunning():
            return
        self._counter_set_busy("Downloading counter data…")
        self._counter_pause_gps()
        meta = {
            "site_id": s.get("id"),
            "unit_id": s.get("counter_unit_id"),
            "street": s.get("street"),
            "counter_cleared_at": s.get("counter_cleared_at", ""),
            "study_start": s.get("counter_cleared_at", ""),
        }

        def wrap(r):
            r["_op"] = "download"
            self._on_picocount_done(r)

        thread = PicocountThread(
            "download",
            port=self._counter_selected_port(),
            dest_path=dest,
            meta=meta,
        )
        self._picocount_thread = thread
        thread.finished_result.connect(wrap)
        thread.start()

