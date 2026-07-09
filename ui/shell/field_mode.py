"""Offline/online field mode alignment — P46 extract from main.py."""

from __future__ import annotations

import os

from PySide6.QtWidgets import QMessageBox

from core import crash_log, offline_policy


class FieldModeMixin:
    def _internet_allowed(self) -> bool:
        """Online features (address search, road download) only before Ready for Offline."""
        return not self.state.offline_mode

    def _sync_field_mode(self) -> None:
        """Keep geo/connectivity aligned with offline_mode (no public internet on road)."""
        offline_policy.set_field_mode(bool(self.state.offline_mode))

    def _field_status_short(self, msg: str, *, ms: int = 12000) -> None:
        """Status bar line for field mode — first line only, trimmed."""
        line = str(msg).replace("\n", " — ").strip()[:240]
        self.statusBar().showMessage(line, ms)

    def _warn(self, msg):
        """Blocking dialog at home; status bar + tds_data/crashes/ notice on the road."""
        if getattr(self, "state", None) and self.state.offline_mode:
            path = crash_log.log_field_notice(str(msg), context="warn")
            short = str(msg).replace("\n", " — ").strip()[:200]
            tail = f" — logged {os.path.basename(path)}" if path else ""
            self.statusBar().showMessage(short + tail, 12000)
            return
        QMessageBox.warning(self, "Traffic Deployer", msg)

    def _info(self, msg):
        if getattr(self, "state", None) and self.state.offline_mode:
            crash_log.log_field_notice(str(msg), context="info")
            self._field_status_short(msg, ms=8000)
            return
        QMessageBox.information(self, "Traffic Deployer", msg)
