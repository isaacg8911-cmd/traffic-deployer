"""Worst-case portable path scenarios (no _MEIPASS, partial extract, HTTP map)."""
from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist", "TrafficDeployer")
ZIP_PATH = os.path.join(ROOT, "dist", "TrafficDeployer-WorkLaptop.zip")
EXE = os.path.join(DIST, "TrafficDeployer.exe")
INTERNAL = os.path.join(DIST, "_internal")
WEB_BESIDE = os.path.join(DIST, "web")

ASSETS = (
    "index.html",
    "app.js",
    "style.js",
    "vendor/maplibre-gl.js",
    "vendor/fonts/Noto Sans Regular/0-255.pbf",
)


def _purge_modules() -> None:
    for mod in list(sys.modules):
        if mod == "ui.paths" or mod.startswith("ui.paths.") or mod in (
            "local_server", "core.field_ready", "core.setup_network",
        ):
            del sys.modules[mod]


def _frozen_env(*, meipass: str | None) -> None:
    sys.frozen = True  # type: ignore[attr-defined]
    sys.executable = EXE
    if meipass is None and hasattr(sys, "_MEIPASS"):
        delattr(sys, "_MEIPASS")
    elif meipass is not None:
        sys._MEIPASS = meipass  # type: ignore[attr-defined]


def _load_paths():
    _purge_modules()
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    import ui.paths as paths
    return importlib.reload(paths)


def _http_ok(web_dir: str, data_dir: str) -> tuple[bool, list[str]]:
    import local_server

    local_server.stop()
    port = local_server.start(web_dir, data_dir)
    errs: list[str] = []
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=5) as r:
            body = r.read(8000).decode("utf-8", errors="replace")
        if "Traffic Deployer Map" not in body:
            errs.append("index.html body wrong")
        for rel in ASSETS:
            url = f"http://127.0.0.1:{port}/" + quote(rel, safe="/")
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    if r.status != 200:
                        errs.append(f"HTTP {r.status} {rel}")
            except Exception as exc:
                errs.append(f"{rel}: {exc}")
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/data/california.pmtiles", timeout=5
        ) as r:
            if r.status not in (200, 206):
                errs.append(f"pmtiles HTTP {r.status}")
    except Exception as exc:
        errs.append(f"server: {exc}")
    finally:
        local_server.stop()
    return len(errs) == 0, errs


def _scenario(label: str, *, meipass: str | None) -> list[str]:
    fails: list[str] = []
    print(f"\n  scenario: {label}")
    _frozen_env(meipass=meipass)
    paths = _load_paths()
    ok, msg = paths.web_assets_ok()
    if not ok:
        fails.append(f"{label}: {msg}")
        print(f"    FAIL web_assets_ok — {msg}")
        return fails
    print(f"    OK WEB_DIR={paths.WEB_DIR}")
    for rel in ASSETS:
        if not os.path.isfile(os.path.join(paths.WEB_DIR, rel.replace("/", os.sep))):
            fails.append(f"{label}: missing {rel}")
            print(f"    FAIL missing {rel}")
    http_ok, http_errs = _http_ok(paths.WEB_DIR, paths.DATA_DIR)
    if not http_ok:
        fails.extend(f"{label}: {e}" for e in http_errs)
        for e in http_errs:
            print(f"    FAIL HTTP {e}")
    else:
        print("    OK HTTP map assets + pmtiles")
    from core.field_ready import check_all

    r = check_all(paths.APP_DIR, probe_gps=False, probe_counter=False, stop_server_after=True)
    for it in r["items"]:
        if it["id"] in ("server", "web_index.html", "web_app.js", "web_style.js", "maplibre", "fonts"):
            if not it["ok"]:
                fails.append(f"{label}: {it['label']}")
                print(f"    FAIL {it['label']}: {it.get('detail', '')}")
    if not fails:
        print(f"    OK field_ready score {r['score']}")
    return fails


def _zip_extract_scenario() -> list[str]:
    fails: list[str] = []
    if not os.path.isfile(ZIP_PATH):
        print("\n  scenario: zip-extract — SKIP (no zip yet)")
        return fails
    print("\n  scenario: zip-extract to temp")
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(ZIP_PATH, "r") as zf:
            zf.extractall(tmp)
        extracted = os.path.join(tmp, "TrafficDeployer")
        if not os.path.isfile(os.path.join(extracted, "TrafficDeployer.exe")):
            fails.append("zip-extract: missing exe")
            return fails
        for rel in (
            "_internal/web/index.html",
            "web/index.html",
            "tds_data/california.pmtiles",
            "OPEN_APP.bat",
        ):
            p = os.path.join(extracted, *rel.split("/"))
            if not os.path.isfile(p):
                fails.append(f"zip-extract: missing {rel}")
                print(f"    FAIL missing {rel}")
            else:
                print(f"    OK {rel}")
        # Simulate frozen from extracted tree
        sys.frozen = True  # type: ignore[attr-defined]
        sys.executable = os.path.join(extracted, "TrafficDeployer.exe")
        sys._MEIPASS = os.path.join(extracted, "_internal")  # type: ignore[attr-defined]
        _purge_modules()
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        import ui.paths as paths

        paths = importlib.reload(paths)
        # paths module uses frozen flag but APP_DIR from executable in extracted dir
        # Override by re-importing after setting executable - reload should pick it up
        ok, msg = paths.web_assets_ok()
        if not ok:
            fails.append(f"zip-extract: {msg}")
            print(f"    FAIL {msg}")
        else:
            print(f"    OK WEB_DIR from extract")
    return fails


def main() -> int:
    if not os.path.isfile(EXE):
        print(f"FAIL: build portable first — {EXE}")
        return 1

    all_fails: list[str] = []

    if not os.path.isfile(os.path.join(INTERNAL, "web", "index.html")):
        all_fails.append("dist missing _internal/web/index.html")
    if not os.path.isfile(os.path.join(WEB_BESIDE, "index.html")):
        all_fails.append("dist missing web/index.html beside exe — run build_work_laptop_zip")

    all_fails.extend(_scenario("frozen+_MEIPASS", meipass=INTERNAL))
    all_fails.extend(_scenario("frozen NO _MEIPASS", meipass=None))
    all_fails.extend(_zip_extract_scenario())

    print()
    if all_fails:
        print(f"PORTABLE SCENARIOS FAIL ({len(all_fails)})")
        for f in all_fails[:12]:
            print(f"  - {f}")
        return 1
    print("PORTABLE SCENARIOS PASS — all frozen + zip paths OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
