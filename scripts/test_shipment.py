"""Prove the AppUpdate folder/zip we ship — not dev .venv source.

Default target: dist/TrafficDeployer-AppUpdate/TrafficDeployer (same layout as the zip).
Override: TD_HANDOFF=C:\\path\\to\\TrafficDeployer

Desk .venv smoke = source code. This script = what the work laptop receives.
GPS + PicoCount USB still require the physical laptop.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

HANDOFF = os.path.join(ROOT, "dist", "TrafficDeployer-AppUpdate", "TrafficDeployer")
BUILD_EXE = os.path.join(ROOT, "dist", "TrafficDeployer", "TrafficDeployer.exe")
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")

FAILURES: list[str] = []


def _resolve_zip_path() -> str:
    """Prefer versioned zip (TrafficDeployer-AppUpdate-1.0.12.zip)."""
    from version import APP_VERSION

    versioned = os.path.join(ROOT, "dist", f"TrafficDeployer-AppUpdate-{APP_VERSION}.zip")
    if os.path.isfile(versioned):
        return versioned
    legacy = os.path.join(ROOT, "dist", "TrafficDeployer-AppUpdate.zip")
    return legacy


ZIP_PATH = _resolve_zip_path()


def ok(name: str, detail: str = "") -> None:
    print(f"  OK  {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str = "") -> None:
    msg = name + (f": {detail}" if detail else "")
    print(f"  FAIL {msg}")
    FAILURES.append(msg)


def section(title: str) -> None:
    print(f"\n[{title}]")


def _handoff_root() -> str:
    env = os.environ.get("TD_HANDOFF", "").strip()
    if env:
        return env
    return HANDOFF


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_layout(handoff: str) -> None:
    section("1. Shipment layout (AppUpdate folder)")
    exe = os.path.join(handoff, "TrafficDeployer.exe")
    for rel in (
        "TrafficDeployer.exe",
        "_internal",
        "web/index.html",
        "web/app.js",
        "web/style.js",
        "_internal/web/index.html",
        "OPEN_APP.bat",
        "APP_UPDATE.txt",
        "READ_ME_FIRST.txt",
    ):
        path = os.path.join(handoff, rel)
        ok(rel) if os.path.exists(path) else fail(f"missing {rel}", path)

    if os.path.isfile(exe):
        mb = os.path.getsize(exe) / (1024 * 1024)
        ok("exe size", f"{mb:.1f} MB")

    try:
        from version import APP_VERSION

        with open(os.path.join(handoff, "READ_ME_FIRST.txt"), encoding="utf-8") as f:
            body = f.read()
        ok("readme version", APP_VERSION) if APP_VERSION in body else fail(
            "readme version", f"expected {APP_VERSION}")
    except Exception as exc:  # noqa: BLE001
        fail("readme version", str(exc))


def check_zip_matches_folder(handoff: str) -> None:
    section("2. Zip matches folder")
    zip_path = _resolve_zip_path()
    if not os.path.isfile(zip_path):
        fail("zip exists", zip_path)
        return
    ok("zip on disk", f"{os.path.basename(zip_path)} ({os.path.getsize(zip_path) / (1024**2):.0f} MB)")
    try:
        from version import APP_VERSION

        if APP_VERSION not in os.path.basename(zip_path):
            fail("zip versioned name", f"expected TrafficDeployer-AppUpdate-{APP_VERSION}.zip")
        else:
            ok("zip versioned name", os.path.basename(zip_path))
    except Exception as exc:  # noqa: BLE001
        fail("zip versioned name", str(exc))
    folder_exe = os.path.join(handoff, "TrafficDeployer.exe")
    if not os.path.isfile(folder_exe):
        return
    tmp = tempfile.mkdtemp(prefix="tds_zip_")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp)
        zip_exe = os.path.join(tmp, "TrafficDeployer", "TrafficDeployer.exe")
        if not os.path.isfile(zip_exe):
            fail("zip layout", "TrafficDeployer/TrafficDeployer.exe missing inside zip")
            return
        fh, zh = _sha256(folder_exe), _sha256(zip_exe)
        ok("zip exe hash matches folder") if fh == zh else fail(
            "zip exe hash", "folder and zip differ — re-run BUILD_APP_UPDATE.bat")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_fresh_vs_build(handoff: str) -> None:
    section("3. Handoff fresh vs PyInstaller build")
    handoff_exe = os.path.join(handoff, "TrafficDeployer.exe")
    if not os.path.isfile(BUILD_EXE):
        fail("build exe", BUILD_EXE)
        return
    if not os.path.isfile(handoff_exe):
        return
    if os.path.getmtime(handoff_exe) < os.path.getmtime(BUILD_EXE) - 1.0:
        fail("handoff stale", "AppUpdate folder older than dist/TrafficDeployer — rebuild")
    else:
        bh, hh = _sha256(BUILD_EXE), _sha256(handoff_exe)
        ok("handoff exe matches build") if bh == hh else fail(
            "handoff exe hash", "differs from dist/TrafficDeployer — re-run pack")


def run_subgate(script: str, env: dict | None = None) -> None:
    if not os.path.isfile(PY):
        fail(f"{script}", ".venv missing")
        return
    proc = subprocess.run(
        [PY, os.path.join(ROOT, "scripts", script)],
        cwd=ROOT,
        env={**os.environ, **(env or {})},
    )
    ok(script) if proc.returncode == 0 else fail(script, f"exit {proc.returncode}")


def check_web_shipped(handoff: str) -> None:
    section("4. Shipped web map (beside exe)")
    app_js = os.path.join(handoff, "web", "app.js")
    if not os.path.isfile(app_js):
        fail("web/app.js")
        return
    body = open(app_js, encoding="utf-8").read()
    needles = (
        "fireMapClick",
        "alreadyPicked",
        "pushGps",
        "highlight_uid",
        "onFollowToggled",
        "fromPython",
        "siteDotLabel",
        "s.id",
    )
    for needle in needles:
        ok(f"app.js {needle}") if needle in body else fail(f"app.js missing {needle}")
    idx = os.path.join(handoff, "web", "index.html")
    src_idx = os.path.join(ROOT, "web", "index.html")
    if os.path.isfile(idx) and os.path.isfile(src_idx):
        ib = open(idx, encoding="utf-8").read()
        src_ib = open(src_idx, encoding="utf-8").read()
        src_m = re.search(r"app\.js\?v=(\d+)", src_ib)
        hand_m = re.search(r"app\.js\?v=(\d+)", ib)
        if not src_m:
            fail("index.html cache bust", "source web/index.html missing app.js?v=")
        elif not hand_m:
            fail("index.html cache bust", "handoff web/index.html missing app.js?v=")
        elif hand_m.group(0) != src_m.group(0):
            fail(
                "index.html cache bust",
                f"expected {src_m.group(0)} — rebuild handoff",
            )
        else:
            ok("index.html app.js cache bust", src_m.group(0))
    style = os.path.join(handoff, "web", "style.js")
    if os.path.isfile(style):
        sb = open(style, encoding="utf-8").read()
        ok("style.js lean labels") if "text-optional" in sb else fail("style.js lean labels")


def main() -> int:
    handoff = _handoff_root()
    print("SHIPMENT TEST — AppUpdate package (what we zip to the laptop)")
    print(f"Target: {handoff}\n")

    if not os.path.isdir(handoff):
        fail("handoff folder", handoff)
        print("\nSHIPMENT FAIL — run BUILD_APP_UPDATE.bat first")
        return 1

    check_layout(handoff)
    check_zip_matches_folder(handoff)
    check_fresh_vs_build(handoff)
    check_web_shipped(handoff)

    section("5. Install UX (shipped web + frozen markers)")
    app_js = os.path.join(handoff, "web", "app.js")
    if os.path.isfile(app_js):
        body = open(app_js, encoding="utf-8").read()
        ok("shipped follow offline hook") if "onFollowToggled" in body else fail(
            "follow offline", "onFollowToggled missing in handoff web/app.js")
        ok("shipped site id on dots") if "s.id" in body and "siteDotLabel" in body else fail(
            "site dots", "site id labels missing in handoff web/app.js")

    section("6. Frozen exe / PYZ markers (shipped code)")
    run_subgate("verify_frozen_bundle.py", {"TD_HANDOFF": handoff})

    section("7. Full field cycle (shipped exe)")
    run_subgate("test_shipment_workflow.py", {"TD_HANDOFF": handoff})

    section("8. Routing graph string coords (field laptop path)")
    run_subgate("test_string_graph_coords.py")

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"SHIPMENT FAIL ({len(FAILURES)}) — do NOT copy zip to laptop")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("SHIPMENT PASS — AppUpdate folder + zip proven")
    print("Still test on truck: GPS, PicoCount USB, map load (OPEN_APP.bat)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
