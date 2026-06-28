"""Detect low-RAM field laptops (e.g. Intel N200 / 4 GB) and tune runtime."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

# 4 GB machines often report ~3.6 GB usable / ~3.9 GB total.
WORK_LAPTOP_RAM_GB_MAX = 5.5


@dataclass(frozen=True)
class HardwareProfile:
    work_laptop: bool
    ram_gb: float | None
    reason: str


def _env_work_laptop() -> bool | None:
    raw = os.environ.get("TDS_WORK_LAPTOP", "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return None


def _total_ram_gb() -> float | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return stat.ullTotalPhys / (1024 ** 3)
    except Exception:
        pass
    return None


def detect_hardware() -> HardwareProfile:
    env = _env_work_laptop()
    ram = _total_ram_gb()
    if env is True:
        return HardwareProfile(True, ram, "TDS_WORK_LAPTOP=1")
    if env is False:
        return HardwareProfile(False, ram, "TDS_WORK_LAPTOP=0")
    if ram is not None and ram <= WORK_LAPTOP_RAM_GB_MAX:
        return HardwareProfile(True, ram, f"RAM {ram:.1f} GB")
    return HardwareProfile(False, ram, "default")


def is_work_laptop() -> bool:
    return detect_hardware().work_laptop


_BASE_CHROMIUM = (
    "--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader "
    "--ignore-gpu-blocklist --disable-background-timer-throttling"
)

_WORK_LAPTOP_CHROMIUM = (
    " --disable-dev-shm-usage"
    " --js-flags=--max-old-space-size=384"
    " --disk-cache-size=33554432"
    " --media-cache-size=16777216"
    " --renderer-process-limit=2"
)


def chromium_flags() -> str:
    flags = _BASE_CHROMIUM
    if is_work_laptop():
        flags += _WORK_LAPTOP_CHROMIUM
    return flags


def apply_webengine_env() -> None:
    """Must run before any QtWebEngine import."""
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = chromium_flags()


def default_window_size() -> tuple[int, int]:
    if is_work_laptop():
        return 1152, 720
    return 1320, 860


def web_http_cache_bytes() -> int:
    return 32 * 1024 * 1024 if is_work_laptop() else 64 * 1024 * 1024
