"""Field readiness on frozen portable layout (dist/TrafficDeployer)."""
from __future__ import annotations

import importlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist", "TrafficDeployer")
EXE = os.path.join(DIST, "TrafficDeployer.exe")


def main() -> int:
    if not os.path.isfile(EXE):
        print(f"FAIL: {EXE}")
        return 1

    sys.frozen = True  # type: ignore[attr-defined]
    sys.executable = EXE
    sys._MEIPASS = os.path.join(DIST, "_internal")  # type: ignore[attr-defined]

    for mod in list(sys.modules):
        if mod == "ui.paths" or mod.startswith("ui.paths."):
            del sys.modules[mod]
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    import ui.paths as paths

    paths = importlib.reload(paths)
    from core.field_ready import check_all

    r = check_all(paths.APP_DIR, probe_gps=True, probe_counter=True, stop_server_after=True)
    print(f"Portable field_ready: {r['score']}/100  fail={r['fail_count']} warn={r['warn_count']}")
    for it in r["items"]:
        mark = "OK" if it["ok"] else it["level"].upper()
        det = f" — {it['detail']}" if it.get("detail") and not it["ok"] else ""
        print(f"  [{mark}] {it['label']}{det}")

    if r["fail_count"]:
        print("\nPORTABLE FIELD READY FAIL")
        return 1
    if r["warn_count"]:
        print(f"\nPORTABLE FIELD READY PASS with {r['warn_count']} warning(s)")
    else:
        print("\nPORTABLE FIELD READY PASS — all green on handoff layout")
    return 0


if __name__ == "__main__":
    sys.exit(main())
