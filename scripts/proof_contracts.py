"""Shared assertions for user-path proof scripts."""
from __future__ import annotations

from typing import Any


def split_mainwindow_contract(win: Any) -> dict:
    """Fail fast if a proof is accidentally pointed at a stale monolith."""
    from ui.controllers.install import InstallControllerMixin
    from ui.controllers.map_sync import MapSyncControllerMixin
    from ui.controllers.pickup import PickupControllerMixin
    from ui.controllers.route import RouteControllerMixin
    from ui.controllers.setup import SetupControllerMixin
    from ui.shell.field_mode import FieldModeMixin
    from ui.shell.lifecycle import ShellLifecycleMixin
    from ui.shell.main_layout import ShellLayoutMixin
    from ui.shell.startup import ShellStartupMixin

    expected_mixins = (
        ShellStartupMixin,
        ShellLayoutMixin,
        ShellLifecycleMixin,
        FieldModeMixin,
        SetupControllerMixin,
        InstallControllerMixin,
        MapSyncControllerMixin,
        RouteControllerMixin,
        PickupControllerMixin,
    )
    missing = [cls.__name__ for cls in expected_mixins if not isinstance(win, cls)]
    method_modules = {
        "_sync_field_mode": "ui.shell.field_mode",
        "_refresh_install": "ui.controllers.install",
        "_begin_manual_grab": "ui.controllers.install",
        "_commit_install": "ui.controllers.install",
        "_push_state": "ui.controllers.map_sync",
    }
    actual_methods = {
        name: getattr(getattr(win, name), "__func__", getattr(win, name)).__module__
        for name in method_modules
    }
    wrong_methods = {
        name: {"expected": expected, "actual": actual_methods.get(name)}
        for name, expected in method_modules.items()
        if actual_methods.get(name) != expected
    }
    if missing or wrong_methods:
        raise AssertionError(
            f"proof not exercising split MainWindow contract: "
            f"missing={missing} wrong_methods={wrong_methods}"
        )
    return {
        "main_window_class": type(win).__name__,
        "mixins": [cls.__name__ for cls in expected_mixins],
        "methods": actual_methods,
    }
