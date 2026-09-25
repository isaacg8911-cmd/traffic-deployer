"""Window close + simple dialogs — P46 extract from main.py."""

from __future__ import annotations

from core import app_lifecycle, crash_log
from ui.paths import DATA_DIR

_EXIT_WORKERS = (
    "_picocount_thread", "_route_thread", "_retrace_thread",
    "_dl_thread", "_geocode_thread", "_field_street_thread",
)


class ShellLifecycleMixin:
    def _shutdown_for_exit(self) -> bool:
        """Stop workers, save the shift, release GPS/counter. True only if the save landed.

        Shared by closeEvent and the in-app updater (which exits the process next).
        """
        saved = False
        try:
            self._hide_route_pick_dialog()
            for attr in _EXIT_WORKERS:
                self._stop_worker(getattr(self, attr, None))
            for t in list(getattr(self, "_field_street_threads", None) or ()):
                self._stop_worker(t, 1500)
            if self.pages.currentIndex() == 2:
                self._flush_install_form()
            saved = bool(self._persist_shift(quiet=True))
        except Exception as exc:  # noqa: BLE001
            crash_log.log_error(exc, context="shutdown_save")
        if not saved:
            return False
        try:
            self._counter_resume_gps()
            self.gps.stop()
        except Exception as exc:  # noqa: BLE001
            crash_log.log_error(exc, context="shutdown_release")
        return True

    def closeEvent(self, event):
        if not self._shutdown_for_exit():
            try:
                self._counter_resume_gps()
                self.gps.stop()
            except Exception:
                pass
        try:
            app_lifecycle.end_session_clean(DATA_DIR)
        except Exception:
            pass
        super().closeEvent(event)
