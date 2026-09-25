"""Keep install GPS grabs / pin drops inside the chosen site's area.

Distance is measured to the site's Excel segment (begin->end line) plus its
crossing / anchor point — never to a previously saved field pin, which may be
the very mistake we are trying to catch.
"""
from __future__ import annotations

import math

SITE_WINDOW_M = 300.0
FAR_FROM_SITE_M = 1500.0

_R = 6_371_000.0


def _pt(stop: dict, lat_key: str, lon_key: str) -> tuple[float, float] | None:
    lat, lon = stop.get(lat_key), stop.get(lon_key)
    if lat is None or lon is None:
        return None
    try:
        la, lo = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if math.isnan(la) or math.isnan(lo):
        return None
    return la, lo


def _xy(lat0: float, p: tuple[float, float]) -> tuple[float, float]:
    k = math.cos(math.radians(lat0))
    return math.radians(p[1]) * k * _R, math.radians(p[0]) * _R


def _seg_dist_m(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    lat0 = p[0]
    px, py = _xy(lat0, p)
    ax, ay = _xy(lat0, a)
    bx, by = _xy(lat0, b)
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def distance_to_site_m(stop: dict, lat: float, lon: float) -> float | None:
    """Metres from (lat, lon) to the site's segment / anchors; None if site has no coords."""
    p = (float(lat), float(lon))
    begin = _pt(stop, "begin_lat", "begin_lon")
    end = _pt(stop, "end_lat", "end_lon")
    best: float | None = None
    if begin and end:
        best = _seg_dist_m(p, begin, end)
    for anchor in (begin, end, _pt(stop, "cross_lat", "cross_lon"), _pt(stop, "lat", "lon")):
        if anchor is None:
            continue
        d = _seg_dist_m(p, anchor, anchor)
        if best is None or d < best:
            best = d
    return best


def check(stops: list[dict], idx: int, lat: float, lon: float) -> dict:
    """Is (lat, lon) inside the window of stops[idx]?

    Returns {"ok", "reason", "dist_m", "nearest_idx", "nearest_dist_m"}.
    reason: "" | "other_site" (another site is clearly closer) | "far".
    """
    out = {"ok": True, "reason": "", "dist_m": None, "nearest_idx": None, "nearest_dist_m": None}
    if not stops or idx < 0 or idx >= len(stops):
        return out
    d_sel = distance_to_site_m(stops[idx], lat, lon)
    out["dist_m"] = d_sel
    if d_sel is None or d_sel <= SITE_WINDOW_M:
        return out
    best_i, best_d = None, None
    for i, s in enumerate(stops):
        if i == idx:
            continue
        d = distance_to_site_m(s, lat, lon)
        if d is not None and (best_d is None or d < best_d):
            best_i, best_d = i, d
    out["nearest_idx"], out["nearest_dist_m"] = best_i, best_d
    if best_d is not None and best_d <= SITE_WINDOW_M and best_d < d_sel / 2:
        out.update(ok=False, reason="other_site")
    elif d_sel > FAR_FROM_SITE_M:
        out.update(ok=False, reason="far")
    return out


def fmt_m(d: float | None) -> str:
    if d is None:
        return "?"
    return f"{d / 1000:.1f} km" if d >= 1000 else f"{int(round(d))} m"
