"""Laptop power state — throttle map/GPS when on battery (Windows-first)."""
from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass

AC_ONLINE = 1
AC_OFFLINE = 0
AC_UNKNOWN = 255


@dataclass(frozen=True)
class PowerSnapshot:
    on_ac: bool | None  # True=plugged, False=battery, None=unknown
    battery_percent: int | None
    label: str


def read_power() -> PowerSnapshot:
    if sys.platform == "win32":
        return _read_windows()
    return PowerSnapshot(on_ac=None, battery_percent=None, label="power unknown")


def _read_windows() -> PowerSnapshot:
    class SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", ctypes.c_byte),
            ("BatteryFlag", ctypes.c_byte),
            ("BatteryLifePercent", ctypes.c_byte),
            ("SystemStatusFlag", ctypes.c_byte),
            ("BatteryLifeTime", ctypes.c_uint32),
            ("BatteryFullLifeTime", ctypes.c_uint32),
        ]

    status = SYSTEM_POWER_STATUS()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return PowerSnapshot(on_ac=None, battery_percent=None, label="power unknown")

    pct: int | None = None
    if status.BatteryLifePercent not in (0, 255):
        pct = int(status.BatteryLifePercent)

    ac = int(status.ACLineStatus)
    if ac == AC_ONLINE:
        label = "plugged in"
        if pct is not None:
            label += f" · {pct}%"
        return PowerSnapshot(on_ac=True, battery_percent=pct, label=label)
    if ac == AC_OFFLINE:
        label = "on battery"
        if pct is not None:
            label += f" · {pct}%"
        return PowerSnapshot(on_ac=False, battery_percent=pct, label=label)
    label = "power unknown"
    if pct is not None:
        label += f" · {pct}%"
    return PowerSnapshot(on_ac=None, battery_percent=pct, label=label)
