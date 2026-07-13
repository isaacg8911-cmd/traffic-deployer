"""Stage app-only update folder (exe + _internal + web). No map — work laptop keeps tds_data."""
from __future__ import annotations

import glob
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


def zip_basename(version: str) -> str:
    """Unique release name — never overwrite an older AppUpdate by accident."""
    return f"TrafficDeployer-AppUpdate-{version}.zip"


def zip_path_for(version: str) -> str:
    return os.path.join(ROOT, "dist", zip_basename(version))


def _copytree(src: str, dst: str) -> None:
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _clear_stale_zips(keep: str) -> None:
    """Remove unversioned + other versioned AppUpdate zips in dist/ (keep current)."""
    dist_dir = os.path.join(ROOT, "dist")
    keep_abs = os.path.normcase(os.path.abspath(keep))
    for pat in ("TrafficDeployer-AppUpdate.zip", "TrafficDeployer-AppUpdate-*.zip"):
        for path in glob.glob(os.path.join(dist_dir, pat)):
            if os.path.normcase(os.path.abspath(path)) == keep_abs:
                continue
            try:
                os.remove(path)
                print(f"  removed stale zip: {os.path.basename(path)}")
            except OSError:
                pass


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

    for name in (
        "OPEN_APP.bat",
        "APP_UPDATE.txt",
        "APPLY_UPDATE.bat",
        "FINISH_UPDATE.bat",
        "FORCE_UPDATE.bat",
        "WHERE_AM_I.bat",
        "select_app_update.ps1",
    ):
        src = os.path.join(ROOT, "packaging", name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(STAGE, name))

    # Bake LAN home URL so OPEN_APP can seed update_channel.json over Wi-Fi.
    lan_ip = os.environ.get("TD_RELEASES_HOST", "").strip()
    if not lan_ip:
        try:
            import socket

            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            lan_ip = s.getsockname()[0]
            s.close()
        except OSError:
            lan_ip = "192.168.1.30"
    port = os.environ.get("TD_RELEASES_PORT", "8765").strip() or "8765"
    home_url = f"http://{lan_ip}:{port}"
    with open(os.path.join(STAGE, "wifi_update_home.txt"), "w", encoding="ascii", newline="\n") as f:
        f.write(home_url + "\n")
    print(f"  OK  wifi_update_home.txt -> {home_url}")

    from version import APP_NAME, APP_TAGLINE, APP_VERSION

    try:
        from version import APP_BUILD_STAMP
    except ImportError:
        APP_BUILD_STAMP = ""

    stamp_line = f"Build stamp: {APP_BUILD_STAMP}\n" if APP_BUILD_STAMP else ""
    readme = (
        f"{APP_NAME.upper()} — APP UPDATE (no map)\n"
        f"Version {APP_VERSION}\n"
        f"{stamp_line}\n"
        f"{APP_TAGLINE}\n\n"
        "This folder updates an existing work-laptop install.\n"
        "Your offline map and shift data in tds_data\\ are NOT included.\n\n"
        f"Ship as: {zip_basename(APP_VERSION)}\n"
        "Steps: read APP_UPDATE.txt in this folder.\n"
        "Title bar must show this version after update — proof of progression.\n"
    )
    with open(os.path.join(STAGE, "READ_ME_FIRST.txt"), "w", encoding="utf-8") as f:
        f.write(readme)
    with open(os.path.join(STAGE, "VERSION.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(f"{APP_VERSION}\n")

    exe_mb = os.path.getsize(os.path.join(STAGE, "TrafficDeployer.exe")) / (1024 * 1024)
    total_mb = sum(
        os.path.getsize(os.path.join(r, f))
        for r, _, files in os.walk(STAGE)
        for f in files
    ) / (1024 * 1024)
    print(f"  OK  staged app update v{APP_VERSION} ({total_mb:.0f} MB total, exe {exe_mb:.1f} MB)")
    print(f"\nFOLDER: {STAGE}")

    out_zip = zip_path_for(APP_VERSION)
    _clear_stale_zips(out_zip)
    if os.path.isfile(out_zip):
        os.remove(out_zip)
    shutil.make_archive(out_zip[:-4], "zip", HANDOFF_ROOT, "TrafficDeployer")
    zip_mb = os.path.getsize(out_zip) / (1024 * 1024)
    print(f"\nZIP: {out_zip} ({zip_mb:.0f} MB)")
    print(f"  Copy that file to USB — name includes v{APP_VERSION} so releases do not collide.")

    py = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    print("\nApp update gate (mandatory — creator laptop trial)...")
    proc = subprocess.run([py, os.path.join(ROOT, "scripts", "pre_app_update_gate.py")], cwd=ROOT)
    if proc.returncode != 0:
        print("\nAPP UPDATE PACK FAIL — fix build and re-run BUILD_APP_UPDATE.bat")
        return proc.returncode

    print("\nAPP UPDATE PACK OK — copy versioned zip or folder to field laptop")
    print("Unzip over existing install — keep tds_data\\ (map + shift data)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
