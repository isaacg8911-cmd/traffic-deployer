#!/usr/bin/env python3
"""One-shot P46 E1.4: move map/GPS sync from main.py to ui/controllers/map_sync.py."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
START_LINE = 777
END_LINE = 1386

HEADER = '''"""Map sync controller mixin - P46 E1.4 extract from main.py."""

from __future__ import annotations

import math

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from core import crash_log, geo, ingest
from ui.paths import DATA_DIR
from ui.simple_mode import FIELD_NAV_INDICES, FIELD_SHELL
from version import APP_VERSION

DAY_FILTER_ALL = "All days"


class MapSyncControllerMixin:
'''

IMPORT_LINE = "from ui.controllers.map_sync import MapSyncControllerMixin\n"


def main() -> int:
    lines = MAIN.read_text(encoding="utf-8").splitlines()
    body = lines[START_LINE - 1 : END_LINE]
    body_text = "\n".join(body).replace(
        "return MainWindow._dist_m(a[0], a[1], b[0], b[1]) >= min_m",
        "return MapSyncControllerMixin._dist_m(a[0], a[1], b[0], b[1]) >= min_m",
    )
    map_sync_path = ROOT / "ui" / "controllers" / "map_sync.py"
    map_sync_path.write_text(HEADER + body_text + "\n", encoding="utf-8")

    init_path = ROOT / "ui" / "controllers" / "__init__.py"
    init_text = init_path.read_text(encoding="utf-8")
    if "MapSyncControllerMixin" not in init_text:
        init_path.write_text(
            init_text.rstrip() + "\nfrom .map_sync import MapSyncControllerMixin\n",
            encoding="utf-8",
        )

    remaining = lines[: START_LINE - 1] + lines[END_LINE:]
    text = "\n".join(remaining) + "\n"
    if IMPORT_LINE.strip() not in text:
        text = text.replace(
            "from ui.controllers.install import InstallControllerMixin\n",
            "from ui.controllers.install import InstallControllerMixin\n" + IMPORT_LINE,
        )
    text = text.replace(
        "class MainWindow(SetupControllerMixin, CounterControllerMixin, InstallControllerMixin, QMainWindow):",
        "class MainWindow(SetupControllerMixin, CounterControllerMixin, InstallControllerMixin, MapSyncControllerMixin, QMainWindow):",
    )
    MAIN.write_text(text, encoding="utf-8")
    moved = END_LINE - START_LINE + 1
    print(f"Moved {moved} lines to {map_sync_path.relative_to(ROOT)}")
    print(f"main.py now {len(text.splitlines())} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
