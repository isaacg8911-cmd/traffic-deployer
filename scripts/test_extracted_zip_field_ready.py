"""Field readiness from a fresh zip extract — closest to work-laptop install."""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP_PATH = os.path.join(ROOT, "dist", "TrafficDeployer-WorkLaptop.zip")


def main() -> int:
    if not os.path.isfile(ZIP_PATH):
        print(f"FAIL: missing zip — {ZIP_PATH}")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(ZIP_PATH, "r") as zf:
            zf.extractall(tmp)
        extracted = os.path.join(tmp, "TrafficDeployer")
        exe = os.path.join(extracted, "TrafficDeployer.exe")
        if not os.path.isfile(exe):
            print("FAIL: extracted exe missing")
            return 1

        sys.frozen = True  # type: ignore[attr-defined]
        sys.executable = exe
        sys._MEIPASS = os.path.join(extracted, "_internal")  # type: ignore[attr-defined]

        for mod in list(sys.modules):
            if mod == "ui.paths" or mod.startswith("ui.paths."):
                del sys.modules[mod]
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)

        import ui.paths as paths

        paths = importlib.reload(paths)
        from core.field_ready import check_all

        r = check_all(paths.APP_DIR, probe_gps=True, probe_counter=True, stop_server_after=True)
        print(f"Extracted zip field_ready: {r['score']}/100  fail={r['fail_count']}  warn={r['warn_count']}")
        for it in r["items"]:
            mark = "OK" if it["ok"] else it["level"].upper()
            det = f" — {it['detail']}" if it.get("detail") and not it["ok"] else ""
            print(f"  [{mark}] {it['label']}{det}")

    if r["fail_count"]:
        print("\nEXTRACTED ZIP FIELD READY FAIL")
        return 1
    print("\nEXTRACTED ZIP FIELD READY PASS — fresh unzip + hardware OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
