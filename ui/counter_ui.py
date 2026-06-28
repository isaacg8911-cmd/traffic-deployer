"""PicoCount panel status styling (enterprise feedback chips)."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QWidget

from core.counter_inventory import format_battery, volt_check_message, volt_level

STATUS_PROP = "statusLevel"
PANEL_CONNECTED_PROP = "counterConnected"


def apply_counter_status(label: QLabel, level: str, text: str) -> None:
    """level: idle | ok | warn | fail | busy"""
    label.setText(text)
    label.setProperty(STATUS_PROP, level)
    style = label.style()
    style.unpolish(label)
    style.polish(label)


def apply_counter_panel_connected(panel: QWidget | None, connected: bool) -> None:
    """Green border on the PicoCount section when USB is live."""
    if panel is None:
        return
    panel.setProperty(PANEL_CONNECTED_PROP, "true" if connected else "false")
    style = panel.style()
    style.unpolish(panel)
    style.polish(panel)


def apply_volt_check(label: QLabel, volts: float | None, *, serial: str = "") -> None:
    """TrafficViewer-style battery volt checker chip."""
    level = volt_level(volts) if volts is not None else "unknown"
    ui_level = level if level in ("ok", "warn", "fail") else "idle"
    label.setText(volt_check_message(volts, serial=serial))
    label.setProperty(STATUS_PROP, ui_level)
    style = label.style()
    style.unpolish(label)
    style.polish(label)


def battery_cell_text(volts: float | None) -> str:
    return format_battery(volts)

