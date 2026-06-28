"""One-time California basemap setup — works from portable exe on Wi-Fi."""
from __future__ import annotations

import os


def basemap_path(data_dir: str) -> str:
    return os.path.join(data_dir, "california.pmtiles")


def basemap_ok(data_dir: str, *, min_mb: float = 100.0) -> bool:
    path = basemap_path(data_dir)
    if not os.path.isfile(path):
        return False
    return os.path.getsize(path) / (1024 * 1024) >= min_mb


def run_map_setup(app_dir: str, web_dir: str, data_dir: str, vendor_dir: str) -> None:
    """Download map JS/fonts + California pmtiles into data_dir (needs internet)."""
    import setup_maps as sm

    sm.APP_DIR = app_dir
    sm.WEB_DIR = web_dir
    sm.DATA_DIR = data_dir
    sm.VENDOR_DIR = vendor_dir
    os.makedirs(vendor_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)
    sm.fetch_vendor()
    sm.fetch_fonts()
    sm.fetch_basemap()
