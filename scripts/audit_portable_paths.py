"""Simulate portable (frozen) paths + HTTP map server — gate before work-laptop zip ships."""
from __future__ import annotations

import importlib
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist", "TrafficDeployer")
EXE = os.path.join(DIST, "TrafficDeployer.exe")
INTERNAL = os.path.join(DIST, "_internal")


def _simulate_frozen() -> None:
    sys.frozen = True  # type: ignore[attr-defined]
    sys.executable = EXE
    sys._MEIPASS = INTERNAL  # type: ignore[attr-defined]


def main() -> int:
    fails: list[str] = []

    if not os.path.isfile(EXE):
        print(f"  FAIL  missing {EXE}")
        return 1

    index_internal = os.path.join(INTERNAL, "web", "index.html")
    if not os.path.isfile(index_internal):
        fails.append("_internal/web/index.html")
        print(f"  FAIL  {index_internal}")
    else:
        print(f"  OK    bundled web/index.html")

    for mod in ("ui.paths", "local_server", "core.field_ready"):
        if mod in sys.modules:
            del sys.modules[mod]

    _simulate_frozen()
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    import ui.paths as paths

    importlib.reload(paths)
    ok, msg = paths.web_assets_ok()
    if ok:
        print(f"  OK    WEB_DIR resolves -> {paths.WEB_DIR}")
    else:
        fails.append("WEB_DIR")
        print(f"  FAIL  {msg}")

    # Must NOT point at exe-adjacent web/ when only _internal has files
    bad = os.path.join(DIST, "web", "index.html")
    if not os.path.isfile(bad) and paths.WEB_DIR == os.path.join(DIST, "web"):
        fails.append("WEB_DIR fallback wrong")
        print("  FAIL  WEB_DIR fell back to missing TrafficDeployer/web")

    import local_server

    local_server.stop()
    port = local_server.start(paths.WEB_DIR, paths.DATA_DIR)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=5) as r:
            body = r.read(8000).decode("utf-8", errors="replace")
        if "Traffic Deployer Map" in body:
            print("  OK    HTTP /index.html (map UI)")
        else:
            fails.append("index body")
            print("  FAIL  /index.html 404 or wrong content")
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/vendor/maplibre-gl.js", timeout=5) as r:
            r.read(200)
        print("  OK    HTTP /vendor/maplibre-gl.js")
    except Exception as exc:
        fails.append(f"http:{exc}")
        print(f"  FAIL  map HTTP: {exc}")
    finally:
        local_server.stop()

    from core.field_ready import check_all

    r = check_all(paths.APP_DIR, probe_gps=False, probe_counter=False, stop_server_after=True)
    web_fails = [i for i in r["items"] if i["id"].startswith("web_") and not i["ok"]]
    if web_fails:
        fails.append("field_ready web")
        for i in web_fails:
            print(f"  FAIL  {i['label']}")
    else:
        print("  OK    field_ready map UI checks")

    srv = next((i for i in r["items"] if i["id"] == "server"), None)
    if not srv or not srv["ok"]:
        fails.append("field_ready server")
        print(f"  FAIL  local map server — {srv.get('detail') if srv else 'missing'}")
    else:
        print("  OK    field_ready map server")

    print()
    if fails:
        print(f"PORTABLE PATH AUDIT FAIL ({len(fails)}) — do not ship zip")
        return 1
    print("PORTABLE PATH AUDIT PASS — frozen layout + map HTTP OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
