"""One-time, online setup: download the offline California basemap + map JS libs.

Run ONCE at home/work on wifi:

    python setup_maps.py

It will:
  1. Download the browser JS libraries (MapLibre + PMTiles + leave qwebchannel.js
     to the app) into web/vendor/  -> so the map renders with no internet later.
  2. Download the pmtiles CLI (if not already present).
  3. Extract a whole-California street basemap from the latest Protomaps build into
     tds_data/california.pmtiles  (vector street outlines, ~hundreds of MB).

After this finishes you can run the app fully offline. Re-run only to refresh maps.
"""
from __future__ import annotations

import os
import platform
import stat
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone

import requests

APP_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(APP_DIR, "web")
VENDOR_DIR = os.path.join(WEB_DIR, "vendor")
DATA_DIR = os.path.join(APP_DIR, "tds_data")

# California bounding box: min_lon, min_lat, max_lon, max_lat
CA_BBOX = "-124.48,32.53,-114.13,42.01"
CA_MAXZOOM = 16  # building footprints + house numbers; each extra zoom ~doubles download size

VENDOR_FILES = {
    "maplibre-gl.js": "https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.js",
    "maplibre-gl.css": "https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.css",
    "pmtiles.js": "https://unpkg.com/pmtiles@3/dist/pmtiles.js",
}

# Offline street labels (OSM names in tiles need local glyph PBFs).
FONT_STACK = "Noto Sans Regular"
FONT_BASE_URL = (
    "https://raw.githubusercontent.com/protomaps/basemaps-assets/main/fonts/"
    "Noto%20Sans%20Regular"
)
FONT_RANGES = (
    "0-255", "256-511", "512-767", "768-1023", "1024-1279", "1280-1535",
    "1536-1791", "1792-2047",
)


def _download(url: str, dest: str):
    print(f"  - {os.path.basename(dest)} ...", flush=True)
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(r.content)


def fetch_vendor():
    print("[1/4] Downloading map libraries -> web/vendor/")
    for name, url in VENDOR_FILES.items():
        _download(url, os.path.join(VENDOR_DIR, name))


def fetch_fonts():
    """Local Noto Sans glyphs so OSM street names render fully offline."""
    font_dir = os.path.join(VENDOR_DIR, "fonts", FONT_STACK)
    os.makedirs(font_dir, exist_ok=True)
    print(f"[2/4] Downloading label fonts -> web/vendor/fonts/{FONT_STACK}/")
    for rng in FONT_RANGES:
        dest = os.path.join(font_dir, f"{rng}.pbf")
        if os.path.isfile(dest) and os.path.getsize(dest) > 100:
            print(f"  - {rng}.pbf (exists)")
            continue
        _download(f"{FONT_BASE_URL}/{rng}.pbf", dest)


def _pmtiles_binary() -> str:
    """Return path to a usable pmtiles CLI, downloading it if needed."""
    exe = "pmtiles.exe" if os.name == "nt" else "pmtiles"
    local = os.path.join(APP_DIR, exe)
    if os.path.exists(local):
        return local
    # Resolve latest go-pmtiles release asset for this OS/arch.
    print("[3/4] Downloading pmtiles CLI ...")
    rel = requests.get("https://api.github.com/repos/protomaps/go-pmtiles/releases/latest",
                       timeout=30).json()
    sysname = platform.system()  # Windows / Linux / Darwin
    machine = platform.machine().lower()
    arch = "x86_64" if machine in ("amd64", "x86_64") else ("arm64" if "arm" in machine or "aarch" in machine else machine)
    asset = None
    for a in rel.get("assets", []):
        n = a["name"]
        if sysname in n and arch in n and n.endswith(".zip"):
            asset = a
            break
    if not asset:
        raise RuntimeError(f"No pmtiles CLI asset for {sysname}/{arch}. Download manually from "
                           "https://github.com/protomaps/go-pmtiles/releases and place pmtiles(.exe) here.")
    zpath = os.path.join(APP_DIR, "_pmtiles_dl.zip")
    _download(asset["browser_download_url"], zpath)
    with zipfile.ZipFile(zpath) as zf:
        for member in zf.namelist():
            if member.endswith(exe) or member == exe:
                with zf.open(member) as src, open(local, "wb") as dst:
                    dst.write(src.read())
                break
    os.remove(zpath)
    if not os.path.exists(local):
        raise RuntimeError("pmtiles CLI not found inside the downloaded archive.")
    if os.name != "nt":
        os.chmod(local, os.stat(local).st_mode | stat.S_IEXEC)
    return local


def _latest_build_date() -> str:
    """Find a recent Protomaps daily build that exists (walk back up to 14 days)."""
    today = datetime.now(timezone.utc).date()
    for back in range(0, 15):
        d = (today - timedelta(days=back)).strftime("%Y%m%d")
        url = f"https://build.protomaps.com/{d}.pmtiles"
        try:
            r = requests.head(url, timeout=15, allow_redirects=True)
            if r.status_code == 200:
                return d
        except Exception:
            continue
    raise RuntimeError("Could not find a recent Protomaps build. Check your internet connection.")


def fetch_basemap():
    os.makedirs(DATA_DIR, exist_ok=True)
    out = os.path.join(DATA_DIR, "california.pmtiles")
    pmtiles = _pmtiles_binary()
    date = _latest_build_date()
    src = f"https://build.protomaps.com/{date}.pmtiles"
    print(f"[4/4] Extracting California basemap from build {date}")
    print(f"      bbox={CA_BBOX} maxzoom={CA_MAXZOOM}  (this can take several minutes)")
    cmd = [pmtiles, "extract", src, out, f"--bbox={CA_BBOX}", f"--maxzoom={CA_MAXZOOM}"]
    subprocess.run(cmd, check=True)
    size_mb = os.path.getsize(out) / (1024 * 1024)
    print(f"      Done -> {out}  ({size_mb:.0f} MB)")


def main():
    print("Traffic Deployer - one-time map setup (needs internet)\n")
    try:
        fetch_vendor()
        fetch_fonts()
        fetch_basemap()
    except Exception as exc:  # noqa: BLE001
        print(f"\nSETUP FAILED: {exc}")
        sys.exit(1)
    print("\nAll set. You can now run the app fully offline (START.bat / python main.py).")


if __name__ == "__main__":
    main()
