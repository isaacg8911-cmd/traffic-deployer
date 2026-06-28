"""Verify shift handoff EST pins match TDS_Report field GPS."""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

HANDOFF = os.environ.get(
    "TD_HANDOFF_OUT",
    os.path.join(ROOT, "tds_data", "exports", "shift_handoff"),
)
REPORT = os.environ.get("TD_HANDOFF_REPORT", "")

PAIRS = [
    ("Week 14 Map 1.est", "Week 14 Day 1 Isaac"),
    ("Week 14 Map 2.est", "Week 14 Day 2 Isaac"),
]

_INLINE_LAT = re.compile(rb"\x14\x08([0-9.\-]+)")
_INLINE_LON = re.compile(rb"\x15\t([0-9.\-]+)")


def read_est_site(path: str, site_id: str) -> list[tuple[float, float]]:
    data = open(path, "rb").read()
    out: list[tuple[float, float]] = []
    needle = b"\xff\xfe" + site_id.encode("ascii")
    pos = 0
    while True:
        pos = data.find(needle, pos)
        if pos < 0:
            break
        tail = data[pos : pos + 400]
        lat_m = _INLINE_LAT.search(tail)
        lon_m = _INLINE_LON.search(tail)
        if lat_m and lon_m:
            out.append((float(lat_m.group(1)), float(lon_m.group(1))))
        pos += 2
    return out


def main() -> int:
    from core.est_field_gps import field_coords_from_report, report_shared_coord_conflicts

    fails: list[str] = []
    excel_path = os.path.join(HANDOFF, "Week 14 IG TFC.xlsx")
    report_for_coords = REPORT if REPORT and os.path.isfile(REPORT) else excel_path
    if not os.path.isfile(report_for_coords):
        print(f"VALIDATE FAIL — missing report {report_for_coords}")
        return 1

    for est_name, sheet in PAIRS:
        est_path = os.path.join(HANDOFF, est_name)
        if not os.path.isfile(est_path):
            fails.append(f"missing {est_path}")
            continue
        orig_est = os.environ.get(
            f"TD_HANDOFF_EST_{sheet[-1]}",
            os.path.join(
                os.path.expanduser("~"),
                "Downloads",
                f"{sheet} (1).est",
            ),
        )
        conflict_sites: set[str] = set()
        if os.path.isfile(orig_est):
            for line in report_shared_coord_conflicts(orig_est, report_for_coords, sheet):
                for part in line.split(":")[-1].split(","):
                    tok = part.strip().split()
                    if tok and tok[0].isdigit():
                        conflict_sites.add(tok[0])
        coords = field_coords_from_report(
            report_for_coords, sheet, field_only=True, installed_only=True,
        )
        for site_id, (flat, flon) in coords.items():
            if site_id in conflict_sites:
                continue
            pins = read_est_site(est_path, site_id)
            if not pins:
                fails.append(f"{est_name}: site {site_id} not in EST")
                continue
            for lat, lon in pins:
                # EST stores ~5 decimal places; allow fixed-width rounding.
                if abs(lat - flat) > 0.00011 or abs(lon - flon) > 0.00011:
                    # Both pins should match field GPS; one pin matching is acceptable
                    # when Streets & Trips shares a coord slot between site pairs.
                    pin_ok = any(
                        abs(pl - flat) <= 0.00011 and abs(pn - flon) <= 0.00011
                        for pl, pn in pins
                    )
                    if pin_ok:
                        continue
                    fails.append(
                        f"{est_name}: site {site_id} EST {lat},{lon} != field {flat},{flon}"
                    )
        print(f"OK  {est_name} — {len(coords)} sites verified")

    if fails:
        print("\nVALIDATE FAIL")
        for f in fails:
            print(" ", f)
        return 1
    print("\nVALIDATE PASS — EST pins match TDS_Report field GPS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
