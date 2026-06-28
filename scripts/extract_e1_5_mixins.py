#!/usr/bin/env python3
"""P46 E1.5: shell topbar + route/pickup/audit/shortcuts controllers from main.py."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

# Extract bottom-to-top so line numbers stay valid.
BLOCKS = [
    (
        1920,
        1963,
        ROOT / "ui" / "shell" / "topbar_theme.py",
        '''"""Shell theme helpers — P46 E1.5 tail from main.py."""

from __future__ import annotations

from ui_themes import normalize_theme, qt_stylesheet


class ShellThemeMixin:
''',
        "ShellThemeMixin",
        "from ui.shell.topbar_theme import ShellThemeMixin\n",
    ),
    (
        1738,
        1918,
        ROOT / "ui" / "controllers" / "audit.py",
        '''"""Audit/export controller mixin — P46 E1.5 extract from main.py."""

from __future__ import annotations

import os

from PySide6.QtWidgets import QFileDialog, QMessageBox

from core import export, handoff, volume_report
from core.shift_summary import summarize as shift_summarize
from ui.paths import COUNTER_DOWNLOAD_DIR, DATA_DIR


class AuditControllerMixin:
''',
        "AuditControllerMixin",
        "from ui.controllers.audit import AuditControllerMixin\n",
    ),
    (
        1604,
        1736,
        ROOT / "ui" / "controllers" / "shortcuts.py",
        '''"""Undo, keyboard shortcuts, and phone nav links — P46 E1.5."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import QFileDialog

from core import maps_links
from ui.paths import DATA_DIR, UNDO_FIELDS


class ShortcutsControllerMixin:
''',
        "ShortcutsControllerMixin",
        "from ui.controllers.shortcuts import ShortcutsControllerMixin\n",
    ),
    (
        1533,
        1602,
        ROOT / "ui" / "controllers" / "pickup.py",
        '''"""Pickup controller mixin — P46 E1.5 extract from main.py."""

from __future__ import annotations


class PickupControllerMixin:
''',
        "PickupControllerMixin",
        "from ui.controllers.pickup import PickupControllerMixin\n",
    ),
    (
        768,
        1531,
        ROOT / "ui" / "controllers" / "route.py",
        '''"""Route controller mixin — P46 E1.5 extract from main.py."""

from __future__ import annotations

import time as _time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QMessageBox, QProgressDialog

import ingest
import road_router
from core import routing, validate
from ui.paths import DATA_DIR
from ui.route_pick_dialog import RoutePickOrderDialog
from ui.setup_wizard import SetupWizard
from ui.simple_mode import BUILD_LABEL, SIMPLE_MODE
from ui.threads import RouteApplyPickThread, RouteOptimizeThread


class RouteControllerMixin:
''',
        "RouteControllerMixin",
        "from ui.controllers.route import RouteControllerMixin\n",
    ),
    (
        508,
        764,
        ROOT / "ui" / "shell" / "topbar.py",
        '''"""Shell topbar + page navigation — P46 E1.5 extract from main.py."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import road_router
from core import counter_inventory
from core.field_ready import check_all
from ui import workflow as setup_workflow
from ui.paths import APP_DIR, DATA_DIR, IS_PORTABLE
from ui.simple_mode import COMPACT_UI, FIELD_NAV_INDICES, FIELD_SHELL, HIDE_PANEL_THEMES, SIMPLE_MODE
from ui.threads import SmokeTestThread
from version import APP_NAME, APP_VERSION, APP_TAGLINE


class ShellTopbarMixin:
''',
        "ShellTopbarMixin",
        "from ui.shell.topbar import ShellTopbarMixin\n",
    ),
]

OLD_CLASS = (
    "class MainWindow(SetupControllerMixin, CounterControllerMixin, "
    "InstallControllerMixin, MapSyncControllerMixin, QMainWindow):"
)
NEW_CLASS = (
    "class MainWindow(ShellTopbarMixin, ShellThemeMixin, SetupControllerMixin, "
    "CounterControllerMixin, InstallControllerMixin, MapSyncControllerMixin, "
    "RouteControllerMixin, PickupControllerMixin, ShortcutsControllerMixin, "
    "AuditControllerMixin, QMainWindow):"
)


def main() -> int:
    lines = MAIN.read_text(encoding="utf-8").splitlines()
    moved_total = 0
    new_imports: list[str] = []

    for start, end, path, header, _class_name, import_line in BLOCKS:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = lines[start - 1 : end]
        path.write_text(header + "\n".join(body) + "\n", encoding="utf-8")
        moved_total += end - start + 1
        if import_line.strip() not in new_imports:
            new_imports.append(import_line)
        print(f"Wrote {end - start + 1} lines -> {path.relative_to(ROOT)}")

    remaining: list[str] = []
    skip_ranges = [(s, e) for s, e, *_ in BLOCKS]

    def in_skip(line_no: int) -> bool:
        return any(s <= line_no <= e for s, e in skip_ranges)

    for i, line in enumerate(lines, start=1):
        if not in_skip(i):
            remaining.append(line)

    text = "\n".join(remaining) + "\n"
    for imp in reversed(new_imports):
        if imp.strip() not in text:
            anchor = "from ui.controllers.map_sync import MapSyncControllerMixin\n"
            text = text.replace(anchor, anchor + imp)
    text = text.replace(OLD_CLASS, NEW_CLASS)

  # _info/_warn used across mixins — keep on MainWindow shell tail
    if "    def _info(self, msg):" not in text:
        dialog_helpers = '''
    def _info(self, msg):
        QMessageBox.information(self, "Traffic Deployer", msg)

    def _warn(self, msg):
        QMessageBox.warning(self, "Traffic Deployer", msg)
'''
        text = text.replace(
            "    def closeEvent(self, event):",
            dialog_helpers + "\n    def closeEvent(self, event):",
        )

    MAIN.write_text(text, encoding="utf-8")

    init = ROOT / "ui" / "controllers" / "__init__.py"
    init_text = init.read_text(encoding="utf-8")
    for _, _, _, _, class_name, import_line in BLOCKS:
        if "controllers" not in str(import_line):
            continue
        if class_name not in init_text:
            init_text = init_text.rstrip() + "\n" + import_line
    init.write_text(init_text, encoding="utf-8")

    shell_init = ROOT / "ui" / "shell" / "__init__.py"
    shell_init.write_text(
        "from .topbar import ShellTopbarMixin\nfrom .topbar_theme import ShellThemeMixin\n",
        encoding="utf-8",
    )

    print(f"Moved {moved_total} lines total; main.py now {len(text.splitlines())} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
