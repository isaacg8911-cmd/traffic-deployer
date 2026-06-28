"""Traffic Deployer - desktop app (PySide6).

A Streets-&-Trips-style window: native side panels + an embedded offline
California map. Keeps every existing tool (USB GPS, .EST/Excel ingest, encrypted
save) and routes on the real road network (origin → stops → origin).

Run:  python main.py     (START.bat does the venv + launch for you)
"""
from __future__ import annotations

from core.hardware_profile import apply_webengine_env

# Stabilize Qt WebEngine on Windows GPUs that drop the D3D context ("context lost
# during MakeCurrent"). MapLibre NEEDS WebGL — route GL through SwiftShader.
# Low-RAM work laptops get tighter Chromium cache + JS heap (see hardware_profile).
# Must be set before any QtWebEngine import.
apply_webengine_env()

from PySide6.QtWidgets import QMainWindow

from ui.controllers.audit import AuditControllerMixin
from ui.controllers.counter import CounterControllerMixin
from ui.controllers.install import InstallControllerMixin
from ui.controllers.map_sync import MapSyncControllerMixin
from ui.controllers.pickup import PickupControllerMixin
from ui.controllers.route import RouteControllerMixin
from ui.controllers.setup import SetupControllerMixin
from ui.controllers.shortcuts import ShortcutsControllerMixin
from ui.shell.field_mode import FieldModeMixin
from ui.shell.lifecycle import ShellLifecycleMixin
from ui.shell.main_layout import ShellLayoutMixin
from ui.shell.power_profile import PowerProfileMixin
from ui.shell.startup import ShellStartupMixin
from ui.shell.topbar import ShellTopbarMixin
from ui.shell.topbar_theme import ShellThemeMixin
from version import APP_NAME, APP_VERSION


class MainWindow(
    ShellStartupMixin,
    ShellLayoutMixin,
    ShellLifecycleMixin,
    PowerProfileMixin,
    FieldModeMixin,
    ShellTopbarMixin,
    ShellThemeMixin,
    SetupControllerMixin,
    CounterControllerMixin,
    InstallControllerMixin,
    MapSyncControllerMixin,
    RouteControllerMixin,
    PickupControllerMixin,
    ShortcutsControllerMixin,
    AuditControllerMixin,
    QMainWindow,
):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self._init_window_startup()


def main():
    from ui.app_entry import launch_app

    launch_app()


if __name__ == "__main__":
    main()
