"""App directory paths and shared UI constants."""
from __future__ import annotations

import os
import sys


def _resolve_app_dir() -> str:
    """Writable folder: repo root in dev; folder containing TrafficDeployer.exe when frozen."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_web_dir(app_dir: str) -> str:
    """Bundled map UI — PyInstaller puts web/ under _MEIPASS (_internal), not beside exe."""
    candidates: list[str] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(os.path.join(meipass, "web"))
        candidates.append(os.path.join(app_dir, "_internal", "web"))
    candidates.append(os.path.join(app_dir, "web"))
    for path in candidates:
        if os.path.isfile(os.path.join(path, "index.html")):
            return path
    for path in candidates:
        if os.path.isdir(path):
            return path
    return candidates[-1]


def _resolve_demo_dir(app_dir: str, web_dir: str) -> str:
    candidates: list[str] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(os.path.join(meipass, "demo_data"))
        candidates.append(os.path.join(app_dir, "_internal", "demo_data"))
    candidates.append(os.path.join(app_dir, "demo_data"))
    for path in candidates:
        if os.path.isdir(path):
            return path
    return os.path.join(os.path.dirname(web_dir), "demo_data")


APP_DIR = _resolve_app_dir()
IS_PORTABLE = getattr(sys, "frozen", False)
LAUNCH_HINT = "Double-click OPEN_APP.bat" if IS_PORTABLE else "Run START.bat"
WEB_DIR = _resolve_web_dir(APP_DIR)
DEMO_DIR = _resolve_demo_dir(APP_DIR, WEB_DIR)

DATA_DIR = os.path.join(APP_DIR, "tds_data")
COUNTER_DOWNLOAD_DIR = os.path.join(DATA_DIR, "counter_downloads")
CRASH_DIR = os.path.join(DATA_DIR, "crashes")
# Portable: vendor downloads/fonts go beside tds_data (bundle may be read-only).
VENDOR_DIR = (
    os.path.join(DATA_DIR, "vendor")
    if IS_PORTABLE
    else os.path.join(WEB_DIR, "vendor")
)
DEMO_CSV = os.path.join(DEMO_DIR, "demo_sites.csv")
DEMO_EST = os.path.join(DEMO_DIR, "DemoDay.EST")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(COUNTER_DOWNLOAD_DIR, exist_ok=True)
os.makedirs(CRASH_DIR, exist_ok=True)
os.makedirs(VENDOR_DIR, exist_ok=True)

DIRECTIONS = ["n", "e", "s", "w"]

UNDO_FIELDS = (
    "installed", "skipped", "picked_up",
    "field_lat", "field_lon", "serial", "lanes", "direction", "notes",
    "date", "exact_time", "street", "street_warning", "install_photo_path",
)


def web_assets_ok() -> tuple[bool, str]:
    """Portable gate: index.html must resolve under WEB_DIR."""
    index = os.path.join(WEB_DIR, "index.html")
    if os.path.isfile(index):
        return True, WEB_DIR
    return False, (
        f"Map UI missing (looked in {WEB_DIR}). "
        "Re-extract the full zip — _internal folder must sit beside TrafficDeployer.exe."
    )
