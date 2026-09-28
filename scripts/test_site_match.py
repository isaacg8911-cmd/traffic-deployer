"""Grab GPS must link the fix to the site you are standing on.

Proves the matcher: nearest unfinished segment, ask when ambiguous or fuzzy,
refuse when far, and do not steal a neighbor after the close site is already done.
The phone copy in mobile_web/static/local.js is checked against the same cases.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from mobile_web.site_match import match_site  # noqa: E402

LAT = 33.80
LON = -117.90
M_PER_DEG = 111_320.0


def north(meters: float, lat: float = LAT, lon: float = LON) -> tuple[float, float]:
    return lat + meters / M_PER_DEG, lon


def site(uid: str, lat: float, lon: float, **flags) -> dict:
    stop = {
        "uid": uid,
        "id": uid,
        "street": flags.pop("street", uid),
        "begin_lat": lat,
        "begin_lon": lon,
        "end_lat": flags.pop("end_lat", lat),
        "end_lon": flags.pop("end_lon", lon),
        "lat": lat,
        "lon": lon,
        "installed": False,
        "skipped": False,
    }
    stop.update(flags)
    return stop


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'OK ' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        raise SystemExit(1)


def cases() -> list[dict]:
    a = site("A", *north(0))
    far = site("FAR", *north(500))
    mid_lat, mid_lon = north(120)
    confirm = site("C", mid_lat, mid_lon)
    b_lat, b_lon = north(25)
    close_b = site("B", b_lat, b_lon)
    # Long count: ~185 m east-west. Standing at the middle must still bind.
    end_lon = LON + 0.002
    tube = site("TUBE", LAT, LON, end_lat=LAT, end_lon=end_lon)
    tube_mid_lon = (LON + end_lon) / 2
    done = site("DONE", *north(0), installed=True)
    pending_far = site("NEXT", *north(400))
    pending_near = site("SIDE", *north(20))
    skipped = site("SKIP", *north(0), skipped=True)
    # field_lat is a previous truck fix and must not move the match.
    decoy = site("MAP", *north(0))
    decoy["field_lat"], decoy["field_lon"] = north(5000)
    parked = site("PARKED", *north(5000))
    parked["field_lat"], parked["field_lon"] = north(0)
    return [
        {
            "name": "bind_close",
            "stops": [a, far],
            "at": north(20),
            "accuracy": 8,
            "status": "bind",
            "uid": "A",
        },
        {
            "name": "none_when_far",
            "stops": [a],
            "at": north(500),
            "accuracy": 8,
            "status": "none",
            "uid": None,
        },
        {
            "name": "choose_when_only_nearby",
            "stops": [confirm],
            "at": [LAT, LON],
            "accuracy": 8,
            "status": "choose",
            "reason": "confirm",
        },
        {
            "name": "choose_when_ambiguous",
            "stops": [a, close_b],
            "at": north(12),
            "accuracy": 8,
            "status": "choose",
            "reason": "ambiguous",
        },
        {
            "name": "choose_when_fuzzy",
            "stops": [a],
            "at": north(15),
            "accuracy": 90,
            "status": "choose",
            "reason": "fuzzy",
        },
        {
            "name": "bind_middle_of_segment",
            "stops": [tube],
            "at": [LAT, tube_mid_lon],
            "accuracy": 5,
            "status": "bind",
            "uid": "TUBE",
            "max_m": 15,
        },
        {
            "name": "ignore_old_field_gps",
            "stops": [decoy],
            "at": north(10),
            "accuracy": 5,
            "status": "bind",
            "uid": "MAP",
        },
        {
            "name": "do_not_follow_field_gps_off_the_pin",
            "stops": [parked],
            "at": north(10),
            "accuracy": 5,
            "status": "none",
            "uid": None,
        },
        {
            "name": "done_site_blocks_neighbor",
            "stops": [done, pending_far],
            "at": north(5),
            "accuracy": 5,
            "status": "done",
            "uid": "DONE",
        },
        {
            "name": "done_site_asks_before_neighbor",
            "stops": [done, pending_near],
            "at": north(8),
            "accuracy": 5,
            "status": "choose",
            "reason": "already_near",
        },
        {
            "name": "skipped_counts_as_done",
            "stops": [skipped, pending_far],
            "at": north(5),
            "accuracy": 5,
            "status": "done",
            "uid": "SKIP",
        },
        {
            "name": "empty",
            "stops": [],
            "at": north(0),
            "accuracy": 5,
            "status": "none",
            "reason": "empty",
        },
        {
            "name": "skip_stop_with_no_coords",
            "stops": [{"uid": "X", "id": "X", "installed": False, "skipped": False}],
            "at": north(0),
            "accuracy": 5,
            "status": "none",
            "reason": "empty",
        },
    ]


def run_python() -> list[dict]:
    out = []
    for case in cases():
        lat, lon = case["at"]
        result = match_site(case["stops"], lat, lon, case["accuracy"])
        out.append({"name": case["name"], "result": result})
        ok = result["status"] == case["status"]
        if case.get("uid") is not None or "uid" in case and case["status"] in ("bind", "done"):
            ok = ok and result.get("uid") == case.get("uid")
        if case.get("reason"):
            ok = ok and result.get("reason") == case["reason"]
        if case.get("max_m") is not None:
            ok = ok and result.get("distance_m", 1e9) <= case["max_m"]
        # Segment case would be ~90 m if we matched the begin point only.
        if case["name"] == "bind_middle_of_segment":
            begin_m = abs(tube_offset_m())
            ok = ok and begin_m > 50
        check(case["name"], ok, f"{result['status']} {result.get('reason')} uid={result.get('uid')} d={result.get('distance_m')}")
    return out


def tube_offset_m() -> float:
    """Distance from the segment midpoint to the begin pin — must be large."""
    end_lon = LON + 0.002
    mid = (LON + end_lon) / 2
    return (mid - LON) * M_PER_DEG * math.cos(math.radians(LAT))


def run_js(py_results: list[dict]) -> None:
    node = shutil.which("node")
    if not node:
        print("[SKIP] js parity — node not on PATH")
        return
    payload = []
    for case in cases():
        lat, lon = case["at"]
        payload.append({
            "name": case["name"],
            "stops": case["stops"],
            "lat": lat,
            "lon": lon,
            "accuracy": case["accuracy"],
        })
    script = r"""
const fs = require('fs');
const vm = require('vm');
const src = fs.readFileSync(process.argv[1], 'utf8');
const cases = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const ctx = {};
vm.createContext(ctx);
vm.runInContext(src, ctx);
const L = ctx.TDLocal;
if (!L || !L.matchSite) { console.error('TDLocal.matchSite missing'); process.exit(2); }
const out = cases.map(function (c) {
  return { name: c.name, result: L.matchSite(c.stops, c.lat, c.lon, c.accuracy) };
});
process.stdout.write(JSON.stringify(out));
"""
    local_js = os.path.join(ROOT, "mobile_web", "static", "local.js")
    case_path = os.path.join(ROOT, "logs", "mobile_check", "_match_cases.json")
    os.makedirs(os.path.dirname(case_path), exist_ok=True)
    with open(case_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    proc = subprocess.run(
        [node, "-e", script, local_js, case_path],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        check("js_parity", False, proc.stderr[-400:] or proc.stdout[-400:])
    js_results = json.loads(proc.stdout)
    by_py = {row["name"]: row["result"] for row in py_results}
    for row in js_results:
        py = by_py[row["name"]]
        js = row["result"]
        ok = js["status"] == py["status"] and js.get("reason") == py.get("reason") and js.get("uid") == py.get("uid")
        check("js:" + row["name"], ok, f"js={js['status']}/{js.get('uid')} py={py['status']}/{py.get('uid')}")


def main() -> int:
    py_results = run_python()
    run_js(py_results)
    print("SITE MATCH PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
