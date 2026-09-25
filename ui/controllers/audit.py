"""Audit/export controller mixin — P46 E1.5 extract from main.py."""

from __future__ import annotations

import os

from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem

from core import export, handoff
from core.shift_summary import summarize as shift_summarize
from ui.paths import DATA_DIR


class AuditControllerMixin:
    # ---------------------------------------------------------- Audit/export
    def _refresh_audit(self):
        summ = shift_summarize(self.state.stops, self.state.route)
        if hasattr(self, "lbl_shift_summary"):
            self.lbl_shift_summary.setText(summ["text"])
        rep = export.audit(self.state.stops)
        if not self.state.stops:
            audit_txt = "No data yet."
        elif rep["missing"]:
            audit_txt = "ACTION NEEDED:\n- " + "\n- ".join(rep["missing"])
        else:
            audit_txt = f"All {rep['count']} completed sites have full data. Ready to export."
        self.lbl_audit.setText(audit_txt)
        self._refresh_audit_sheet()
        self._refresh_export_hint()
        self._refresh_field_alerts()

    def _refresh_audit_sheet(self) -> None:
        tbl = getattr(self, "table_audit_sheet", None)
        if tbl is None:
            return
        stops = self.state.stops or []
        tbl.setRowCount(len(stops))
        for i, s in enumerate(stops):
            lat = s.get("field_lat") or s.get("lat")
            lon = s.get("field_lon") or s.get("lon")
            gps = ""
            if lat is not None and lon is not None:
                gps = f"{float(lat):.5f}, {float(lon):.5f}"
            cells = (
                str(i + 1),
                str(s.get("id", "")),
                str(s.get("street", "") or ""),
                str(s.get("serial", "") or ""),
                str(s.get("direction", "") or ""),
                str(s.get("lanes", "") or ""),
                "x" if s.get("installed") else "",
                "x" if s.get("skipped") else "",
                "x" if s.get("picked_up") else "",
                gps,
            )
            for j, text in enumerate(cells):
                tbl.setItem(i, j, QTableWidgetItem(text))

    def _refresh_export_hint(self):
        if not hasattr(self, "lbl_export_hint"):
            return
        ig = getattr(self.state, "ig_tfc_path", "") or ""
        folder = handoff.handoff_dir(DATA_DIR)
        prefix = handoff.handoff_prefix(ig_tfc_path=ig, est_paths=self.est_paths)
        names = handoff.handoff_filenames(prefix, max(len(self.est_paths), 2))
        lines = [names["excel"]]
        for i in range(1, max(len(self.est_paths), 2) + 1):
            key = f"map{i}"
            if key in names:
                lines.append(names[key])
        self.lbl_export_hint.setText(
            f"Shift handoff folder:\n{folder}\n\n"
            + "\n".join(f"  • {n}" for n in lines))

    def _export_paths(self) -> tuple[str, str]:
        ig = getattr(self.state, "ig_tfc_path", "") or ""
        return ig, DATA_DIR

    def _update_live_shift_excel(self) -> None:
        """Keep tds_data/shift_live.xlsx in sync after GPS grab or INSTALL (newest wins per site)."""
        if not self.state.stops:
            return
        try:
            ig, data_dir = self._export_paths()
            data, _err = export.to_excel_result(
                self.state.stops, ig_tfc_path=ig, data_dir=data_dir)
            if not data:
                return
            path = os.path.join(data_dir, "shift_live.xlsx")
            with open(path, "wb") as f:
                f.write(data)
        except PermissionError:
            self.statusBar().showMessage(
                "shift_live.xlsx is open in Excel — close it so it keeps updating.", 8000)
        except Exception:
            pass

    def _export_shift_handoff(self, *, pick_folder: bool = False) -> None:
        ig, data_dir = self._export_paths()
        rep = export.audit(self.state.stops)
        if not rep["count"]:
            self._warn("Nothing to export yet (no installed/skipped sites).")
            return
        if not rep["ok"]:
            if QMessageBox.question(
                self, "Audit gaps",
                "Some completed sites are missing data:\n\n"
                + "\n".join(rep["missing"][:12])
                + ("\n…" if len(rep["missing"]) > 12 else "")
                + "\n\nExport anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            ) != QMessageBox.Yes:
                return
        out_dir = handoff.handoff_dir(data_dir)
        if pick_folder:
            picked = QFileDialog.getExistingDirectory(
                self, "Shift handoff folder", out_dir)
            if not picked:
                return
            out_dir = picked
        result = handoff.export_shift_handoff(
            self.state.stops,
            self.est_paths,
            data_dir=data_dir,
            ig_tfc_path=ig,
            out_dir=out_dir,
        )
        self._refresh_export_hint()
        if not result["ok"]:
            self._warn("Handoff failed:\n\n" + "\n".join(result["errors"]))
            return
        files = result.get("files") or {}
        msg = f"Shift handoff saved:\n\n{result['folder']}\n\n"
        for key in ("excel", "map1", "map2", "readme"):
            path = files.get(key)
            if path:
                msg += f"  • {os.path.basename(path)}\n"
        msg += "\nZip Excel + .est for the office. Do not include .html or .kml.\n"
        warns = result.get("warnings") or []
        if warns:
            msg += "\nNotes:\n" + "\n".join(f"  • {w}" for w in warns[:8])
            if len(warns) > 8:
                msg += f"\n  • …and {len(warns) - 8} more"
        self._info(msg.strip())

    def _export_shift_handoff_quick(self) -> None:
        self._export_shift_handoff(pick_folder=False)

    def _export_excel(self):
        self._export_shift_handoff(pick_folder=True)

    def _export_excel_quick(self):
        self._export_shift_handoff_quick()

    def _export_csv(self):
        text = export.to_csv_text(self.state.stops)
        if not text.strip() or text.count("\n") <= 1:
            self._warn("Nothing to export yet (no installed/skipped sites).")
            return
        default = export.default_report_path(DATA_DIR, self.state.profile, "csv")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save report", default, "CSV (*.csv)")
        if path:
            with open(path, "w", newline="", encoding="utf-8") as f:
                f.write(text)
            self._info(f"CSV report saved.\n\n{path}")

    def _export_csv_quick(self):
        text = export.to_csv_text(self.state.stops)
        if not text.strip() or text.count("\n") <= 1:
            self._warn("Nothing to export yet (no installed/skipped sites).")
            return
        path = export.default_report_path(DATA_DIR, self.state.profile, "csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write(text)
        self._refresh_export_hint()
        self._info(f"CSV saved to default folder:\n\n{path}")
