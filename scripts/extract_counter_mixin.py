#!/usr/bin/env python3
"""One-shot P46 E1.2: move PicoCount block from main.py to ui/controllers/counter.py."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
START_LINE = 2148
END_LINE = 2620

HEADER = '''"""Counter controller mixin — P46 E1.2 extract from main.py (PicoCount USB)."""

from __future__ import annotations

import os

from PySide6.QtCore import QTimer

from core import crash_log, picocount
from core.state import ca_now
from ui.counter_ui import apply_counter_status
from ui.paths import COUNTER_DOWNLOAD_DIR
from ui.threads import PicocountThread


class CounterControllerMixin:
'''

IMPORT_LINE = "from ui.controllers.counter import CounterControllerMixin\n"


def main() -> int:
    lines = MAIN.read_text(encoding="utf-8").splitlines()
    body = lines[START_LINE - 1 : END_LINE]
    counter_path = ROOT / "ui" / "controllers" / "counter.py"
    counter_path.write_text(HEADER + "\n".join(body) + "\n", encoding="utf-8")

    init_path = ROOT / "ui" / "controllers" / "__init__.py"
    init_text = init_path.read_text(encoding="utf-8")
    if "CounterControllerMixin" not in init_text:
        init_path.write_text(
            init_text.rstrip() + "\nfrom .counter import CounterControllerMixin\n",
            encoding="utf-8",
        )

    remaining = lines[: START_LINE - 1] + lines[END_LINE:]
    text = "\n".join(remaining) + "\n"
    if IMPORT_LINE.strip() not in text:
        text = text.replace(
            "from ui.controllers.setup import SetupControllerMixin\n",
            "from ui.controllers.setup import SetupControllerMixin\n" + IMPORT_LINE,
        )
    text = text.replace(
        "class MainWindow(SetupControllerMixin, QMainWindow):",
        "class MainWindow(SetupControllerMixin, CounterControllerMixin, QMainWindow):",
    )
    MAIN.write_text(text, encoding="utf-8")
    moved = END_LINE - START_LINE + 1
    print(f"Moved {moved} lines to {counter_path.relative_to(ROOT)}")
    print(f"main.py now {len(text.splitlines())} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
