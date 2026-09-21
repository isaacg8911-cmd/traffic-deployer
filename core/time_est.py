"""Field time estimates: drive minutes from road miles, plus hose setup per stop.

Offline — no Google. Calibrated to typical no-traffic urban / freeway speeds.
Each hose stop is ~5–8 min of setup (default 6).
"""
from __future__ import annotations

import math

SETUP_MIN = 6.0
SETUP_MIN_LO = 5.0
SETUP_MIN_HI = 8.0
# Crow-flies → road when the graph is missing.
_NO_GRAPH_ROAD = 1.3
EST_VERSION = 2


def drive_min_from_miles(miles: float) -> float:
    """Minutes behind the wheel from a road (or scaled) mile count."""
    m = max(0.0, float(miles or 0.0))
    if m < 0.02:
        return 0.0
    if m <= 2.0:
        mph = 16.0
    elif m <= 8.0:
        mph = 18.0  # Week 28 Google typical city hops (~18 mph)
    else:
        mph = 48.0
    return m / mph * 60.0


def fmt_min(minutes: float) -> str:
    m = max(0.0, float(minutes or 0.0))
    if m < 0.5:
        return "<1 min"
    if m < 90:
        return f"{int(round(m))} min"
    hr = m / 60.0
    if abs(hr - round(hr)) < 0.05:
        return f"{int(round(hr))} hr"
    return f"{hr:.1f} hr"


def _haversine_mi(a: tuple[float, float], b: tuple[float, float]) -> float:
    dlat = math.radians(b[0] - a[0])
    dlon = math.radians(b[1] - a[1])
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(a[0]))
        * math.cos(math.radians(b[0]))
        * math.sin(dlon / 2) ** 2
    )
    km = 6371.0 * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))
    return km * 0.621371


def _home_usable(home: tuple[float, float] | None) -> bool:
    """Factory default is not a real origin — do not invent a commute clock."""
    if home is None:
        return False
    try:
        from core.state import RouteState
        return not RouteState.is_factory_home(float(home[0]), float(home[1]))
    except Exception:
        try:
            float(home[0]); float(home[1])
        except (TypeError, ValueError, IndexError):
            return False
        return True


def remaining_job_drive_min(route: dict, stops: list[dict] | None) -> float:
    """Minutes still to drive between open sites (not hops already done)."""
    legs = list(route.get("site_legs") or [])
    total = 0.0
    for i, s in enumerate(stops or []):
        if s.get("installed") or s.get("skipped"):
            continue
        if i == 0:
            continue
        if i < len(legs):
            total += float(legs[i].get("drive_min") or 0.0)
    return total


def commute_miles_min(
    a: tuple[float, float] | None,
    b: tuple[float, float] | None,
    graph=None,
) -> tuple[float, float]:
    """Home↔site (or any two pins): miles, minutes."""
    if a is None or b is None:
        return 0.0, 0.0
    try:
        a = (float(a[0]), float(a[1]))
        b = (float(b[0]), float(b[1]))
    except (TypeError, ValueError):
        return 0.0, 0.0
    miles = 0.0
    if graph is not None:
        try:
            import road_router
            if road_router.HAS_ROUTING:
                leg = road_router.route_between(graph, a, b, include_turns=False)
                if leg.get("ok"):
                    miles = float(leg.get("miles") or 0.0)
        except Exception:
            miles = 0.0
    if miles <= 0.02:
        miles = _haversine_mi(a, b) * _NO_GRAPH_ROAD
    return miles, drive_min_from_miles(miles)


def _stop_ll(stop: dict) -> tuple[float, float] | None:
    for keys in (("cross_lat", "cross_lon"), ("lat", "lon"), ("begin_lat", "begin_lon")):
        la, lo = stop.get(keys[0]), stop.get(keys[1])
        if la is not None and lo is not None:
            try:
                return float(la), float(lo)
            except (TypeError, ValueError):
                continue
    return None


def pending_stops(stops: list[dict]) -> list[dict]:
    return [
        s for s in stops
        if not s.get("installed") and not s.get("skipped")
    ]


def setup_band(n: int) -> tuple[float, float, float]:
    n = max(0, int(n))
    return n * SETUP_MIN_LO, n * SETUP_MIN, n * SETUP_MIN_HI


def attach_to_route(
    route: dict,
    stops: list[dict],
    home: tuple[float, float] | None,
    graph=None,
) -> dict:
    """Write drive/setup estimates onto route + each site_leg. Returns route."""
    legs = list(route.get("site_legs") or [])
    job_min = 0.0
    job_mi = float(route.get("miles") or 0.0)
    for i, leg in enumerate(legs):
        mi = float(leg.get("miles") or 0.0)
        dmin = drive_min_from_miles(mi)
        leg["drive_min"] = round(dmin, 1)
        if i > 0:
            job_min += dmin
    if job_min <= 0 and job_mi > 0:
        job_min = drive_min_from_miles(job_mi)

    first_ll = _stop_ll(stops[0]) if stops else None
    last_ll = _stop_ll(stops[-1]) if stops else None
    home_ok = _home_usable(home)
    if home_ok:
        out_mi, out_min = commute_miles_min(home, first_ll, graph)
        back_mi, back_min = commute_miles_min(last_ll, home, graph)
    else:
        out_mi = out_min = back_mi = back_min = 0.0
    if legs:
        if home_ok:
            legs[0]["from_home_miles"] = round(out_mi, 2)
            legs[0]["from_home_min"] = round(out_min, 1)
            legs[-1]["to_home_miles"] = round(back_mi, 2)
            legs[-1]["to_home_min"] = round(back_min, 1)
        else:
            legs[0].pop("from_home_miles", None)
            legs[0].pop("from_home_min", None)
            legs[-1].pop("to_home_miles", None)
            legs[-1].pop("to_home_min", None)

    n = len(stops)
    slo, smid, shi = setup_band(n)
    drive_all = out_min + job_min + back_min
    route["est_version"] = EST_VERSION
    route["home_clocks"] = home_ok
    route["job_drive_min"] = round(job_min, 1)
    route["home_out_min"] = round(out_min, 1)
    route["home_out_miles"] = round(out_mi, 2)
    route["home_back_min"] = round(back_min, 1)
    route["home_back_miles"] = round(back_mi, 2)
    route["setup_min"] = round(smid, 1)
    route["setup_min_lo"] = round(slo, 1)
    route["setup_min_hi"] = round(shi, 1)
    route["day_min"] = round(drive_all + smid, 1)
    route["day_min_lo"] = round(drive_all + slo, 1)
    route["day_min_hi"] = round(drive_all + shi, 1)
    route["site_legs"] = legs
    return route


def ensure(route: dict, stops: list[dict], home: tuple[float, float] | None, graph=None) -> dict:
    """Fill estimates if BUILD ROUTE ran before this field existed."""
    if not route:
        return route
    stale = int(route.get("est_version") or 0) < EST_VERSION or "job_drive_min" not in route
    home_mismatch = bool(route.get("home_clocks")) != _home_usable(home)
    if not stale and not home_mismatch:
        return route
    return attach_to_route(route, stops or [], home, graph)


def summary_clause(
    route: dict,
    *,
    pending: int | None = None,
    stops: list[dict] | None = None,
) -> str:
    """One line of clock estimates, or empty."""
    if not route or route.get("job_drive_min") is None:
        return ""
    job = float(route.get("job_drive_min") or 0)
    out_m = float(route.get("home_out_min") or 0)
    back = float(route.get("home_back_min") or 0)
    n = pending
    if n is None:
        slo = float(route.get("setup_min_lo") or 0)
        shi = float(route.get("setup_min_hi") or 0)
        day_lo = float(route.get("day_min_lo") or 0)
        day_hi = float(route.get("day_min_hi") or 0)
    else:
        slo, _smid, shi = setup_band(n)
        if stops is not None:
            job = remaining_job_drive_min(route, stops)
            if stops and (stops[0].get("installed") or stops[0].get("skipped")):
                out_m = 0.0
            if n <= 0:
                back = 0.0
        drive = out_m + job + back
        day_lo, day_hi = drive + slo, drive + shi
    parts = []
    if out_m >= 1:
        parts.append(f"{fmt_min(out_m)} from home")
    if job >= 1:
        parts.append(f"{fmt_min(job)} between sites")
    if n is None:
        n_setup = int(round(float(route.get("setup_min") or 0) / SETUP_MIN)) if route.get("setup_min") else 0
        if n_setup:
            parts.append(f"{fmt_min(slo)}–{fmt_min(shi)} setup ({n_setup}×5–8 min)")
    elif n > 0:
        parts.append(f"{fmt_min(slo)}–{fmt_min(shi)} setup ({n}×5–8 min)")
    if back >= 1:
        parts.append(f"{fmt_min(back)} home")
    if day_hi >= 1:
        if abs(day_lo - day_hi) < 2:
            parts.append(f"day {fmt_min(day_lo)}")
        else:
            parts.append(f"day {fmt_min(day_lo)}–{fmt_min(day_hi)}")
    return " · ".join(parts)


def stop_suffix(
    leg: dict | None,
    *,
    first: bool,
    last: bool,
    remaining: bool,
    home_back_min: float = 0.0,
) -> str:
    """Short clock bit for a stop-list row."""
    bits = []
    if not remaining:
        return ""
    if first and leg and float(leg.get("from_home_min") or 0) >= 1:
        bits.append(f"from home {fmt_min(float(leg['from_home_min']))}")
    elif leg and float(leg.get("drive_min") or 0) >= 0.5:
        bits.append(f"{fmt_min(float(leg['drive_min']))} drive")
    bits.append("~6 min setup")
    home_m = 0.0
    if last:
        home_m = float((leg or {}).get("to_home_min") or home_back_min or 0)
    if home_m >= 1:
        bits.append(f"then {fmt_min(home_m)} home")
    return " · " + " · ".join(bits) if bits else ""
