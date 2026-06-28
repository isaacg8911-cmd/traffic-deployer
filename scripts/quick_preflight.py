"""Fast pre-launch check (<5s). Exit 1 only on critical map failures."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.field_ready import check_all


def main() -> int:
    r = check_all(ROOT, probe_gps=False, probe_counter=False)
    print(f"Field readiness: {r['score']}/100")
    for it in r["items"]:
        mark = "OK" if it["level"] == "ok" else it["level"].upper()
        line = f"  [{mark}] {it['label']}"
        if it.get("detail") and it["level"] != "ok":
            line += f" — {it['detail']}"
        print(line)
    if r["fail_count"]:
        print(f"\nCRITICAL: {r['fail_count']} issue(s) — fix before field.")
        return 1
    if r["warn_count"]:
        print(f"\nReady with {r['warn_count']} warning(s) — review Setup tab.")
    else:
        print("\nAll systems go.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
