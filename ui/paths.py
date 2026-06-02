"""App directory paths and shared UI constants."""
from __future__ import annotations

import os

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(APP_DIR, "web")
VENDOR_DIR = os.path.join(WEB_DIR, "vendor")
DATA_DIR = os.path.join(APP_DIR, "tds_data")
DEMO_DIR = os.path.join(APP_DIR, "demo_data")
DEMO_CSV = os.path.join(DEMO_DIR, "demo_sites.csv")
DEMO_EST = os.path.join(DEMO_DIR, "DemoDay.EST")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(VENDOR_DIR, exist_ok=True)

DIRECTIONS = ["n", "e", "s", "w"]

UNDO_FIELDS = (
    "installed", "skipped", "picked_up",
    "field_lat", "field_lon", "serial", "lanes", "direction", "notes",
    "date", "exact_time", "street", "street_warning",
)
