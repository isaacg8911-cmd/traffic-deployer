"""Check for Traffic Deployer updates (online, home Wi‑Fi).

  .venv\\Scripts\\python.exe scripts\\check_updates.py

Configure: tds_data/update_channel.json  (see update_channel.json.example)
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import update_check
from version import APP_VERSION


def main() -> int:
    info = update_check.check_for_update(APP_VERSION)
    print(f"Traffic Deployer {info.current}")
    if info.error:
        print(f"  {info.error}")
        return 0
    print(f"  Latest: {info.latest}")
    if info.update_available:
        print("  UPDATE AVAILABLE")
        if info.notes:
            print(f"  Notes: {info.notes}")
        if info.download_url:
            print(f"  Download: {info.download_url}")
        return 2
    print("  Up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
