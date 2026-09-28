"""Week 28 step 4 only: copy TFC site GPS onto the matching EST map.

Map choice follows which sites are on the file (Map 1 is Day 1, Map 2 is
Day 2 for this week). Does not restamp counts or rename photos.

Backs up EST files to _week28_backup/ on first run.
"""
from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import re

from core.est_field_gps import (  # noqa: E402
    _fmt_lat,
    _fmt_lon,
    find_paired_inline_coords,
)
from core.est_viewer import pushpins_from_est  # noqa: E402
from week27_est_gps import patch_map  # noqa: E402
from week28_common import BACKUP_NAME, FOLDER, TFC_NAME, load_tfc  # noqa: E402


def stored_is_best_fit(est: Path, site: str, lat: float, lon: float) -> bool:
    """True when every pin for this site holds the closest fixed-width TFC text."""
    data = est.read_bytes()
    needle = b"\xff\xfe" + site.encode("ascii")
    pos = 0
    found = False
    while True:
        pos = data.find(needle, pos)
        if pos < 0:
            break
        after = pos + len(needle)
        if after < len(data) and 48 <= data[after] <= 57:
            pos += 2
            continue
        tail = data[pos : pos + 400]
        pair = find_paired_inline_coords(tail)
        if not pair:
            pos += 2
            continue
        la0, la1, lo0, lo1 = pair
        if tail[la0:la1] != _fmt_lat(lat, la1 - la0) or tail[lo0:lo1] != _fmt_lon(lon, lo1 - lo0):
            return False
        found = True
        pos += 2
    return found


def main() -> int:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else FOLDER
    tfc = folder / TFC_NAME
    if not folder.is_dir() or not tfc.is_file():
        print(f"missing folder or TFC under {folder}", file=sys.stderr)
        return 1

    ests = sorted(folder.glob("*.est"))
    if len(ests) < 1:
        print("no EST files", file=sys.stderr)
        return 1

    info = load_tfc(tfc)
    backup = folder / BACKUP_NAME
    backup.mkdir(exist_ok=True)
    lines: list[str] = []
    errors: list[str] = []

    print("STEP 4 — EST GPS only")
    print(f"Folder: {folder}")
    print(f"TFC Day 1 GPS: {len(info['gps1'])}  Day 2 GPS: {len(info['gps2'])}")
    lines.append("STEP 4 — EST GPS only")
    lines.append(f"TFC Day 1 GPS: {len(info['gps1'])}  Day 2 GPS: {len(info['gps2'])}")

    pin_sets: dict[Path, set[str]] = {}
    for est in ests:
        pin_sets[est] = {p["site"] for p in pushpins_from_est(est)}
        print(f"  {est.name}: {len(pin_sets[est])} sites")

    def place(label: str, gps: dict[str, tuple[float, float]]) -> None:
        for est in ests:
            subset = {s: gps[s] for s in gps if s in pin_sets[est]}
            if not subset:
                continue
            print(f"{label} -> {est.name}: {len(subset)} sites")
            lines.append(f"{label} -> {est.name}: {len(subset)} sites")
            raw_errors = patch_map(est, backup, subset, lines)
            for err in raw_errors:
                m = re.search(r"site (\d+) ([0-9.]+)m from TFC", err)
                if m and stored_is_best_fit(est, m.group(1), subset[m.group(1)][0], subset[m.group(1)][1]):
                    note = (
                        f"  note {est.name} site {m.group(1)} is {m.group(2)}m off; "
                        "EST digit width cannot store the TFC longitude any closer"
                    )
                    print(note)
                    lines.append(note)
                    continue
                errors.append(err)
        placed = set()
        for sites in pin_sets.values():
            placed |= set(gps) & sites
        for sid in sorted(set(gps) - placed, key=lambda s: (len(s), s)):
            errors.append(f"{label} site {sid} has TFC GPS but is on no EST")

    place("Day 1", info["gps1"])
    place("Day 2", info["gps2"])

    for msg in lines:
        if msg.startswith("STEP") or msg.startswith("TFC") or msg.startswith("Day"):
            continue
        print(msg)

    report = folder / "WEEK28_STEP4_EST_GPS.txt"
    body = lines + [""] + [f"ERROR {e}" for e in errors]
    report.write_text("\n".join(body) + "\n", encoding="utf-8")
    print(f"Report: {report}")
    if errors:
        for e in errors:
            print(f"  ERROR {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
