"""PicoCount panel status styling (enterprise feedback chips)."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel

STATUS_PROP = "statusLevel"


def apply_counter_status(label: QLabel, level: str, text: str) -> None:
    """level: idle | ok | warn | fail | busy"""
    label.setText(text)
    label.setProperty(STATUS_PROP, level)
    style = label.style()
    style.unpolish(label)
    style.polish(label)
