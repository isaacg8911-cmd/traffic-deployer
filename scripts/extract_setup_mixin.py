#!/usr/bin/env python3
"""One-shot P46 E1.1: move setup block from main.py to ui/controllers/setup.py."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
START_LINE = 1389
END_LINE = 2438

HEADER = '''"""Setup controller mixin — P46 E1.1 extract from main.py."""

from __future__ import annotations

import os
import time as _time

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QListWidgetItem,
    QMessageBox,
    QProgressDialog,
    QTableWidgetItem,
)

import gps_reader
import road_router
from core import auto_updater, connectivity, counter_inventory, crash_log, field_alerts, geo, ingest, setup_network
from core.field_ready import check_all
from core.offline_gate import evaluate as offline_gate_eval
from core.setup_checklist import evaluate as setup_checklist_eval
from core.setup_checklist import route_summary as build_route_summary
from core.state import RouteState
from ui.counter_ui import apply_counter_panel_connected, apply_volt_check, battery_cell_text
from ui.paths import APP_DIR, DATA_DIR, DEMO_CSV, DEMO_EST, LAUNCH_HINT
from ui.setup_wizard import SetupWizard
from ui.simple_mode import BUILD_LABEL, COMPACT_UI
from ui.threads import DownloadRoadsThread, GeocodeThread, MapSetupThread
from version import APP_VERSION


class SetupControllerMixin:
'''

IMPORT_LINE = "from ui.controllers.setup import SetupControllerMixin\n"


def main() -> int:
    lines = MAIN.read_text(encoding="utf-8").splitlines()
    body = lines[START_LINE - 1 : END_LINE]
    setup_path = ROOT / "ui" / "controllers" / "setup.py"
    setup_path.parent.mkdir(parents=True, exist_ok=True)
    setup_path.write_text(HEADER + "\n".join(body) + "\n", encoding="utf-8")
    (ROOT / "ui" / "controllers" / "__init__.py").write_text(
        "from .setup import SetupControllerMixin\n", encoding="utf-8"
    )

    remaining = lines[: START_LINE - 1] + lines[END_LINE:]
    text = "\n".join(remaining) + "\n"
    if IMPORT_LINE.strip() not in text:
        text = text.replace(
            "from ui.setup_wizard import SetupWizard\n",
            "from ui.setup_wizard import SetupWizard\n" + IMPORT_LINE,
        )
    text = text.replace(
        "class MainWindow(QMainWindow):",
        "class MainWindow(SetupControllerMixin, QMainWindow):",
    )
    MAIN.write_text(text, encoding="utf-8")
    moved = END_LINE - START_LINE + 1
    print(f"Moved {moved} lines to {setup_path.relative_to(ROOT)}")
    print(f"main.py now {len(text.splitlines())} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
