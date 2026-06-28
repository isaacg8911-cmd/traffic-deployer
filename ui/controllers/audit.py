"""Audit/export controller mixin — P46 E1.5 extract from main.py."""

from __future__ import annotations

import os

from PySide6.QtWidgets import QFileDialog, QMessageBox

from core import export, handoff, volume_report
from core.shift_summary import summarize as shift_summarize
from ui.paths import COUNTER_DOWNLOAD_DIR, DATA_DIR


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
        self._refresh_export_hint()
        self._refresh_field_alerts()

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

    def _export_volume_csv_pickup(self) -> None:
        items = self._installed_stops()
        if not items or self.pickup_index >= len(items):
            self._warn("Select an installed site on Pickup first.")
            return
        s = items[self.pickup_index]
        dl = str(s.get("counter_download_path") or "").strip()
        if not dl or not os.path.isfile(dl):
            self._warn(
                "No counter download for this site.\n\n"
                "Tap Download counter data first (or pick a .pcbin / .tvp file).")
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Open counter study file",
                COUNTER_DOWNLOAD_DIR,
                "Counter study (*.pcbin *.tvp);;All (*.*)",
            )
            if not path:
                return
            dl = path
        unit = str(s.get("counter_unit_id") or os.path.splitext(os.path.basename(dl))[0])
        default = volume_report.default_export_path(DATA_DIR, unit)
        dest, _ = QFileDialog.getSaveFileName(
            self, "Save volume CSV", default, "CSV (*.csv)")
        if not dest:
            return
        res = volume_report.write_volume_csv(dl, dest, stop=s)
        if not res.get("ok"):
            self._warn(res.get("error", "Volume report failed."))
            return
        s["counter_volume_csv"] = res.get("path", dest)
        self._persist_shift(quiet=True)
        dirs = res.get("directions", ("", ""))
        self._info(
            f"Volume by Lane CSV saved.\n\n{res.get('path')}\n\n"
            f"{res.get('vehicle_count', 0)} vehicles · {dirs[0]} / {dirs[1]}")

    def _export_volume_csv_all(self) -> None:
        results = volume_report.volume_reports_for_stops(self.state.stops, DATA_DIR)
        if not results:
            self._warn(
                "No counter downloads on this route.\n\n"
                "Pickup tab → Download counter data for each site first.")
            return
        ok = [r for r in results if r.get("ok")]
        fail = [r for r in results if not r.get("ok")]
        for r in ok:
            for s in self.state.stops:
                if s.get("id") == r.get("site_id"):
                    s["counter_volume_csv"] = r.get("path", "")
                    break
        if ok:
            self._persist_shift(quiet=True)
        lines = [f"Volume CSVs → tds_data/exports/volume/"]
        for r in ok:
            lines.append(
                f"  Site {r.get('site_id')}: {os.path.basename(r.get('path', ''))} "
                f"({r.get('vehicle_count', 0)} vehicles)")
        for r in fail:
            lines.append(f"  Site {r.get('site_id')}: FAILED — {r.get('error')}")
        if fail and not ok:
            self._warn("\n".join(lines))
        else:
            self._info("\n".join(lines))

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
