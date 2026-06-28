"""Home start point must persist across save/load (address + default)."""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    from core.state import DEFAULT_HOME, RouteState

    d = tempfile.mkdtemp()
    st = RouteState(d, profile="HOMETEST")
    lat, lon = 33.81234, -117.92345
    label = "123 Main St, Garden Grove, CA"
    ok = st.set_start_point(lat, lon, label)
    if not ok:
        print("FAIL set_start_point returned False")
        return 1
    st2 = RouteState(d, profile="HOMETEST")
    if not st2.load():
        print("FAIL load after save")
        return 1
    checks = [
        ("home", st2.home, (lat, lon)),
        ("default_home", st2.default_home, (lat, lon)),
        ("saved_home_coords", st2.saved_home_coords, (lat, lon)),
        ("saved_home_label", st2.saved_home_label, label),
    ]
    for name, got, want in checks:
        if got != want:
            print(f"FAIL {name}: got {got!r} want {want!r}")
            return 1
        print(f"  OK  {name}")
    if RouteState.is_factory_home(*st2.home):
        print("FAIL home still factory after save")
        return 1
    if RouteState.is_factory_home(*DEFAULT_HOME):
        pass
    print("HOME SAVE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
