"""QApplication bootstrap — P46 extract from main.py."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from core import app_lifecycle, auto_updater, crash_log
from ui.paths import APP_DIR, DATA_DIR, IS_PORTABLE


def launch_app(argv: list[str] | None = None) -> None:
    """Start Traffic Deployer; never returns on success (calls sys.exit)."""
    from main import MainWindow

    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    QApplication.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings, True)
    crash_log.install_crash_logging()
    app_lifecycle.begin_session(DATA_DIR)
    if IS_PORTABLE:
        try:
            from version import APP_VERSION

            upd = auto_updater.maybe_apply_on_launch(APP_VERSION)
            if upd.relaunch:
                auto_updater.relaunch_and_exit(APP_DIR)
                return
        except Exception as exc:  # noqa: BLE001
            crash_log.log_error(exc, context="startup_auto_update")
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Traffic Deployer")
    try:
        win = MainWindow()
    except Exception as exc:  # noqa: BLE001
        path = crash_log.log_error(exc, context="main_window_init")
        QMessageBox.critical(
            None,
            "Traffic Deployer",
            f"Could not start the app window:\n\n{exc}\n\n"
            f"Details saved to:\n{path}",
        )
        sys.exit(1)
    if win._work_laptop:
        win.show()
        win.statusBar().showMessage(
            "Work-laptop mode — map throttled for 4 GB RAM. Plug in and use FOLLOW GPS on the road.",
            12_000,
        )
    else:
        win.showMaximized()
    sys.exit(app.exec())
