"""Gate before copying TrafficDeployer-WorkLaptop.zip to USB / work laptop."""
from __future__ import annotations

import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP_PATH = os.path.join(ROOT, "dist", "TrafficDeployer-WorkLaptop.zip")
PREFIX = "TrafficDeployer/"
MIN_MAP_MB = 100

REQUIRED = (
    f"{PREFIX}TrafficDeployer.exe",
    f"{PREFIX}OPEN_APP.bat",
    f"{PREFIX}READ_ME_FIRST.txt",
    f"{PREFIX}WORK_LAPTOP_FRESH_INSTALL.txt",
    f"{PREFIX}web/index.html",
    f"{PREFIX}_internal/web/index.html",
    f"{PREFIX}tds_data/california.pmtiles",
    f"{PREFIX}_internal/web/vendor/maplibre-gl.js",
    f"{PREFIX}_internal/web/app.js",
)

RECOMMENDED = (
    f"{PREFIX}tds_data/road_graph.graphml",
    f"{PREFIX}_internal/web/vendor/fonts/Noto Sans Regular/0-255.pbf",
    f"{PREFIX}WORK_LAPTOP.md",
    f"{PREFIX}FIX_USB.bat",
    f"{PREFIX}fix_usb_ports.ps1",
    f"{PREFIX}USB_FIX_README.txt",
    f"{PREFIX}_internal/demo_data/demo_sites.csv",
)


def _norm(name: str) -> str:
    return name.replace("\\", "/")


def main() -> int:
    fails: list[str] = []
    warns: list[str] = []

    if not os.path.isfile(ZIP_PATH):
        print(f"  FAIL  missing zip — run BUILD_WORK_LAPTOP.bat on home Wi-Fi")
        print(f"        {ZIP_PATH}")
        return 1

    mb = os.path.getsize(ZIP_PATH) / (1024 * 1024)
    print(f"  OK    zip ({mb:.0f} MB)")

    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from version import APP_VERSION

    with zipfile.ZipFile(ZIP_PATH, "r") as zf:
        names = {_norm(n) for n in zf.namelist()}
        readme_name = f"{PREFIX}READ_ME_FIRST.txt"
        if readme_name in names:
            text = zf.read(readme_name).decode("utf-8", errors="replace")
            if APP_VERSION not in text:
                fails.append("READ_ME_FIRST missing version")
                print(f"  FAIL  READ_ME_FIRST.txt — expected v{APP_VERSION}")
            elif "Version ?" in text:
                fails.append("READ_ME_FIRST version placeholder")
                print("  FAIL  READ_ME_FIRST.txt still has Version ? — rebuild zip")
            else:
                print(f"  OK    READ_ME_FIRST.txt (v{APP_VERSION})")
        for path in REQUIRED:
            if path not in names:
                fails.append(path)
                print(f"  FAIL  {path}")
            else:
                print(f"  OK    {os.path.basename(path) or path}")

        for path in RECOMMENDED:
            if path not in names:
                warns.append(path)
                print(f"  WARN  {path} — routing may need Wi-Fi import at work")
            else:
                print(f"  OK    {os.path.basename(path)}")

        map_name = f"{PREFIX}tds_data/california.pmtiles"
        if map_name in names:
            info = zf.getinfo(map_name)
            map_mb = info.file_size / (1024 * 1024)
            if map_mb < MIN_MAP_MB:
                fails.append(f"basemap too small ({map_mb:.0f} MB)")
                print(f"  FAIL  california.pmtiles only {map_mb:.0f} MB — re-run START.bat, rebuild zip")
            else:
                print(f"  OK    california.pmtiles ({map_mb:.0f} MB)")

    dist = os.path.join(ROOT, "dist", "TrafficDeployer")
    exe = os.path.join(dist, "TrafficDeployer.exe")
    if os.path.isfile(exe):
        try:
            if ROOT not in sys.path:
                sys.path.insert(0, ROOT)
            import road_router

            data = os.path.join(dist, "tds_data")
            if road_router.graph_file_exists(data):
                g = road_router.load_graph(data)
                n = len(g.nodes) if g else 0
                if n > 0:
                    print(f"  OK    road graph loads ({n:,} nodes)")
                else:
                    warns.append("road graph empty")
                    print("  WARN  road_graph.graphml present but empty — rebuild route at home")
            else:
                warns.append("no road graph on disk")
        except Exception as exc:
            warns.append(str(exc))
            print(f"  WARN  could not load road graph from dist: {exc}")
    else:
        warns.append("dist folder missing — zip-only check")

    print()
    if fails:
        print(f"WORK LAPTOP VERIFY FAIL ({len(fails)}) — do not copy to work laptop yet")
        return 1
    if warns:
        print(f"WORK LAPTOP VERIFY PASS with {len(warns)} warning(s) — review before field")
        return 0
    print("WORK LAPTOP VERIFY PASS — safe to copy zip to work laptop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
