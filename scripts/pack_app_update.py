"""Stage app-only update folder (exe + _internal + web). No map — work laptop keeps tds_data."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DIST = os.path.join(ROOT, "dist", "TrafficDeployer")
HANDOFF_ROOT = os.path.join(ROOT, "dist", "TrafficDeployer-AppUpdate")
STAGE = os.path.join(HANDOFF_ROOT, "TrafficDeployer")
ZIP_PATH = os.path.join(ROOT, "dist", "TrafficDeployer-AppUpdate.zip")


def _copytree(src: str, dst: str) -> None:
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def main() -> int:
    exe = os.path.join(DIST, "TrafficDeployer.exe")
    internal = os.path.join(DIST, "_internal")
    if not os.path.isfile(exe):
        print(f"FAIL: run build_exe.ps1 first — {exe}")
        return 1
    if not os.path.isdir(internal):
        print(f"FAIL: _internal missing after PyInstaller build — {internal}")
        return 1

    internal_web = os.path.join(internal, "web")
    if not os.path.isfile(os.path.join(internal_web, "index.html")):
        print("FAIL: _internal/web/index.html missing after PyInstaller build")
        return 1

    if os.path.isdir(HANDOFF_ROOT):
        shutil.rmtree(HANDOFF_ROOT)
    os.makedirs(STAGE, exist_ok=True)

    shutil.copy2(exe, os.path.join(STAGE, "TrafficDeployer.exe"))
    _copytree(internal, os.path.join(STAGE, "_internal"))
    _copytree(internal_web, os.path.join(STAGE, "web"))

    for name in ("OPEN_APP.bat", "APP_UPDATE.txt"):
        src = os.path.join(ROOT, "packaging", name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(STAGE, name))

    from version import APP_NAME, APP_TAGLINE, APP_VERSION

    readme = (
        f"{APP_NAME.upper()} — APP UPDATE (no map)\n"
        f"Version {APP_VERSION}\n\n"
        f"{APP_TAGLINE}\n\n"
        "This folder updates an existing work-laptop install.\n"
        "Your offline map and shift data in tds_data\\ are NOT included.\n\n"
        "Steps: read APP_UPDATE.txt in this folder.\n"
    )
    with open(os.path.join(STAGE, "READ_ME_FIRST.txt"), "w", encoding="utf-8") as f:
        f.write(readme)

    exe_mb = os.path.getsize(os.path.join(STAGE, "TrafficDeployer.exe")) / (1024 * 1024)
    total_mb = sum(
        os.path.getsize(os.path.join(r, f))
        for r, _, files in os.walk(STAGE)
        for f in files
    ) / (1024 * 1024)
    print(f"  OK  staged app update ({total_mb:.0f} MB total, exe {exe_mb:.1f} MB)")
    print(f"\nFOLDER: {STAGE}")

    py = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    print("\nApp update gate (mandatory — creator laptop trial)...")
    proc = subprocess.run([py, os.path.join(ROOT, "scripts", "pre_app_update_gate.py")], cwd=ROOT)
    if proc.returncode != 0:
        print("\nAPP UPDATE PACK FAIL — fix build and re-run BUILD_APP_UPDATE.bat")
        return proc.returncode

    if os.path.isfile(ZIP_PATH):
        os.remove(ZIP_PATH)
    shutil.make_archive(ZIP_PATH[:-4], "zip", HANDOFF_ROOT, "TrafficDeployer")
    zip_mb = os.path.getsize(ZIP_PATH) / (1024 * 1024)
    print(f"\nZIP: {ZIP_PATH} ({zip_mb:.0f} MB)")

    print("\nAPP UPDATE PACK OK — copy zip or folder to field laptop")
    print("Unzip over existing install — keep tds_data\\ (map + shift data)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
