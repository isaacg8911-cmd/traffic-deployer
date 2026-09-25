"""Window close + simple dialogs — P46 extract from main.py."""

from __future__ import annotations

from core import app_lifecycle
from ui.paths import DATA_DIR


class ShellLifecycleMixin:
    def closeEvent(self, event):
        try:
            self._hide_route_pick_dialog()
            for attr in ("_picocount_thread", "_route_thread", "_retrace_thread", "_dl_thread", "_geocode_thread", "_field_street_thread"):
                self._stop_worker(getattr(self, attr, None))
            for t in list(getattr(self, "_field_street_threads", None) or ()):
                self._stop_worker(t, 1500)
            if self.pages.currentIndex() == 2:
                self._flush_install_form()
            self._persist_shift(quiet=True)
            self._counter_resume_gps()
            self.gps.stop()
        except Exception:
            pass
        try:
            app_lifecycle.end_session_clean(DATA_DIR)
        except Exception:
            pass
        super().closeEvent(event)
