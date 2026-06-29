"""Pack dist/TrafficDeployer for work laptop + zip. Run after build_exe.ps1."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DIST = os.path.join(ROOT, "dist", "TrafficDeployer")
SRC_DATA = os.path.join(ROOT, "tds_data")
ZIP_PATH = os.path.join(ROOT, "dist", "TrafficDeployer-WorkLaptop.zip")
MIN_MAP_MB = 100


def _copytree(src: str, dst: str) -> None:
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def main() -> int:
    if not os.path.isfile(os.path.join(DIST, "TrafficDeployer.exe")):
        print(f"FAIL: run build_exe.ps1 first — {DIST}")
        return 1

    internal_web = os.path.join(DIST, "_internal", "web")
    beside_web = os.path.join(DIST, "web")
    if not os.path.isfile(os.path.join(internal_web, "index.html")):
        print("FAIL: _internal/web/index.html missing after PyInstaller build")
        return 1
    _copytree(internal_web, beside_web)
    print("  OK  web/ beside exe")

    dest_data = os.path.join(DIST, "tds_data")
    if os.path.isdir(dest_data):
        shutil.rmtree(dest_data)
    os.makedirs(dest_data, exist_ok=True)

    warns: list[str] = []
    map_src = os.path.join(SRC_DATA, "california.pmtiles")
    if os.path.isfile(map_src):
        mb = os.path.getsize(map_src) / (1024 * 1024)
        if mb < MIN_MAP_MB:
            warns.append(f"california.pmtiles too small ({mb:.0f} MB)")
        else:
            shutil.copy2(map_src, os.path.join(dest_data, "california.pmtiles"))
            print(f"  OK  map ({mb:.0f} MB)")
    else:
        warns.append("No california.pmtiles on home PC")

    graph_src = os.path.join(SRC_DATA, "road_graph.graphml")
    if os.path.isfile(graph_src):
        shutil.copy2(graph_src, os.path.join(dest_data, "road_graph.graphml"))
        print("  OK  road graph")
    else:
        warns.append("No road_graph.graphml")

    font_src = os.path.join(ROOT, "web", "vendor", "fonts")
    if os.path.isdir(font_src):
        font_dest = os.path.join(dest_data, "vendor", "fonts")
        os.makedirs(font_dest, exist_ok=True)
        _copytree(font_src, font_dest)
        print("  OK  label fonts in tds_data")

    for name in ("WORK_LAPTOP.md",):
        src = os.path.join(ROOT, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(DIST, name))

    for name in ("OPEN_APP.bat", "WORK_LAPTOP_FRESH_INSTALL.txt", "FIX_USB.bat", "fix_usb_ports.ps1", "USB_FIX_README.txt"):
        src = os.path.join(ROOT, "packaging", name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(DIST, name))

    from version import APP_NAME, APP_TAGLINE, APP_VERSION

    readme = (
        f"{APP_NAME.upper()} — WORK LAPTOP\n"
        f"Version {APP_VERSION}\n\n"
        f"{APP_TAGLINE}\n\n"
        "GETTING STARTED\n"
        "  1. Unzip TrafficDeployer-WorkLaptop.zip (e.g. C:\\TrafficDeployer)\n"
        "  2. Open the TrafficDeployer folder inside the unzip location\n"
        "  3. Double-click OPEN_APP.bat  (NOT START.bat — developers only)\n\n"
        "USB port / COM issues (GPS or PicoCount):\n"
        "  Double-click FIX_USB.bat as Administrator — see USB_FIX_README.txt\n\n"
        "Fresh install steps: WORK_LAPTOP_FRESH_INSTALL.txt\n"
        "Full handover guide: WORK_LAPTOP.md\n"
    )
    with open(os.path.join(DIST, "READ_ME_FIRST.txt"), "w", encoding="utf-8") as f:
        f.write(readme)

    if not os.path.isfile(os.path.join(beside_web, "index.html")):
        print("FAIL: web/index.html missing beside exe after pack")
        return 1

    if os.path.isfile(ZIP_PATH):
        os.remove(ZIP_PATH)
    shutil.make_archive(ZIP_PATH[:-4], "zip", os.path.dirname(DIST), "TrafficDeployer")
    print(f"\nZIP: {ZIP_PATH}")

    py = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    print("\nPre-ship gate (mandatory)...")
    proc = subprocess.run([py, os.path.join(ROOT, "scripts", "pre_ship_gate.py")], cwd=ROOT)
    if proc.returncode != 0:
        return proc.returncode

    for w in warns:
        print(f"WARN: {w}")
    if warns:
        return 2
    print("\nPACK OK — copy zip to work laptop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
