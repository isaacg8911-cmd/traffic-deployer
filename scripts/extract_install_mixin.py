#!/usr/bin/env python3
"""One-shot P46 E1.3: move install flow from main.py to ui/controllers/install.py."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
START_LINE = 2147
END_LINE = 2636

HEADER = '''"""Install controller mixin - P46 E1.3 extract from main.py."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

import gps_reader
import road_router
from core import direction as direction_rules
from core import geo, install_checklist
from core.state import ca_now
from ui.paths import DATA_DIR, DIRECTIONS
from ui.threads import FieldStreetThread


class InstallControllerMixin:
'''

IMPORT_LINE = "from ui.controllers.install import InstallControllerMixin\n"


def main() -> int:
    lines = MAIN.read_text(encoding="utf-8").splitlines()
    body = lines[START_LINE - 1 : END_LINE]
    install_path = ROOT / "ui" / "controllers" / "install.py"
    install_path.write_text(HEADER + "\n".join(body) + "\n", encoding="utf-8")

    init_path = ROOT / "ui" / "controllers" / "__init__.py"
    init_text = init_path.read_text(encoding="utf-8")
    if "InstallControllerMixin" not in init_text:
        init_path.write_text(
            init_text.rstrip() + "\nfrom .install import InstallControllerMixin\n",
            encoding="utf-8",
        )

    remaining = lines[: START_LINE - 1] + lines[END_LINE:]
    text = "\n".join(remaining) + "\n"
    if IMPORT_LINE.strip() not in text:
        text = text.replace(
            "from ui.controllers.counter import CounterControllerMixin\n",
            "from ui.controllers.counter import CounterControllerMixin\n" + IMPORT_LINE,
        )
    text = text.replace(
        "class MainWindow(SetupControllerMixin, CounterControllerMixin, QMainWindow):",
        "class MainWindow(SetupControllerMixin, CounterControllerMixin, InstallControllerMixin, QMainWindow):",
    )
    MAIN.write_text(text, encoding="utf-8")
    moved = END_LINE - START_LINE + 1
    print(f"Moved {moved} lines to {install_path.relative_to(ROOT)}")
    print(f"main.py now {len(text.splitlines())} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
