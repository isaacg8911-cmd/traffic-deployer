"""Match a phone GPS fix to the unfinished site the operator is standing at.

Distance is to the count segment (begin → end) from the map file. A previous
field grab is ignored — that point is where the truck was, and it must not
pull the next match off the pin.

Thresholds are mirrored in mobile_web/static/local.js (matchSite).
"""
from __future__ import annotations

import math

# Standing on the tube: save without asking.
AUTO_M = 80.0
# Farther than this: do not offer the site.
CONFIRM_M = 200.0
# Two unfinished sites this close in distance: ask which one.
AMBIGUOUS_GAP_M = 35.0
# A finished site this much closer than the nearest unfinished one: stay off it.
DONE_CLOSER_M = 10.0
# Browser accuracy worse than this: ask even if one site looks clear.
FUZZY_ACCURACY_M = 65.0


def _finite(value) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


def _accuracy_m(accuracy) -> float | None:
    if not _finite(accuracy):
        return None
    number = float(accuracy)
    if number < 0:
        return None
    return number


def _local_xy(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat0))
    return (lon - lon0) * m_per_deg_lon, (lat - lat0) * m_per_deg_lat


def _hav_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    to_r = math.pi / 180.0
    dlat = (lat2 - lat1) * to_r
    dlon = (lon2 - lon1) * to_r
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1 * to_r) * math.cos(lat2 * to_r) * math.sin(dlon / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def segment_distance_m(
    plat: float, plon: float,
    a_lat: float, a_lon: float,
    b_lat: float, b_lon: float,
) -> float:
    """Meters from a point to the segment A→B (flat local projection)."""
    ax, ay = _local_xy(a_lat, a_lon, a_lat, a_lon)
    bx, by = _local_xy(b_lat, b_lon, a_lat, a_lon)
    px, py = _local_xy(plat, plon, a_lat, a_lon)
    abx, aby = bx - ax, by - ay
    apx, apy = px - ax, py - ay
    ab2 = abx * abx + aby * aby
    if ab2 < 1e-6:
        return _hav_m(plat, plon, a_lat, a_lon)
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab2))
    cx, cy = ax + t * abx, ay + t * aby
    return math.hypot(px - cx, py - cy)


def site_segment(stop: dict) -> tuple[float, float, float, float] | None:
    """Begin/end of the count. Falls back to the map midpoint. Never field GPS."""
    blat, blon = stop.get("begin_lat"), stop.get("begin_lon")
    if not (_finite(blat) and _finite(blon)):
        blat, blon = stop.get("lat"), stop.get("lon")
    if not (_finite(blat) and _finite(blon)):
        return None
    elat, elon = stop.get("end_lat"), stop.get("end_lon")
    if not (_finite(elat) and _finite(elon)):
        elat, elon = blat, blon
    return float(blat), float(blon), float(elat), float(elon)


def _pack(row: dict) -> dict:
    return {
        "uid": row["uid"],
        "id": row["id"],
        "street": row["street"],
        "distance_m": row["distance_m"],
        "installed": row["installed"],
        "skipped": row["skipped"],
    }


def match_site(stops: list[dict] | None, lat: float, lon: float, accuracy=None) -> dict:
    """Decide what a Grab GPS press should do.

    status:
      bind  — one unfinished site, close, GPS tight enough to save now
      choose — operator must tap the site (ambiguous, fuzzy, or only nearby)
      done  — the closest site is already installed or skipped
      none  — nothing unfinished close enough
    """
    ranked: list[dict] = []
    for stop in stops or []:
        segment = site_segment(stop)
        if segment is None:
            continue
        distance = segment_distance_m(lat, lon, *segment)
        ranked.append({
            "uid": stop.get("uid"),
            "id": stop.get("id"),
            "street": str(stop.get("street") or ""),
            "distance_m": round(distance, 1),
            "installed": bool(stop.get("installed")),
            "skipped": bool(stop.get("skipped")),
            "done": bool(stop.get("installed") or stop.get("skipped")),
        })
    ranked.sort(key=lambda row: row["distance_m"])
    pending = [row for row in ranked if not row["done"]]
    finished = [row for row in ranked if row["done"]]

    empty = {
        "status": "none",
        "reason": "empty",
        "options": [],
        "nearest": None,
        "nearby_done": None,
    }
    if not ranked:
        return empty

    nearest_done = finished[0] if finished else None
    nearest_pending = pending[0] if pending else None
    force_choose = False

    if nearest_done and nearest_done["distance_m"] <= AUTO_M:
        pending_dist = nearest_pending["distance_m"] if nearest_pending else 1e12
        if pending_dist > nearest_done["distance_m"] + DONE_CLOSER_M:
            return {
                "status": "done",
                "reason": "already",
                "uid": nearest_done["uid"],
                "distance_m": nearest_done["distance_m"],
                "options": [],
                "nearest": _pack(nearest_done),
                "nearby_done": _pack(nearest_done),
            }
        force_choose = True

    if nearest_pending is None or nearest_pending["distance_m"] > CONFIRM_M:
        near = _pack(nearest_pending) if nearest_pending else (
            _pack(nearest_done) if nearest_done else None
        )
        return {
            "status": "none",
            "reason": "far" if nearest_pending else "empty",
            "options": [],
            "nearest": near,
            "nearby_done": _pack(nearest_done) if nearest_done else None,
        }

    options = [_pack(row) for row in pending if row["distance_m"] <= CONFIRM_M][:3]
    second = pending[1]["distance_m"] if len(pending) > 1 else 1e12
    gap = second - nearest_pending["distance_m"]
    acc = _accuracy_m(accuracy)
    fuzzy = acc is not None and acc > FUZZY_ACCURACY_M
    ambiguous = gap < AMBIGUOUS_GAP_M and second <= CONFIRM_M
    close_enough = nearest_pending["distance_m"] <= AUTO_M
    packed = _pack(nearest_pending)
    nearby = _pack(nearest_done) if nearest_done else None

    if close_enough and not ambiguous and not fuzzy and not force_choose:
        return {
            "status": "bind",
            "reason": "clear",
            "uid": nearest_pending["uid"],
            "distance_m": nearest_pending["distance_m"],
            "options": options,
            "nearest": packed,
            "nearby_done": nearby,
        }

    if ambiguous:
        reason = "ambiguous"
    elif fuzzy:
        reason = "fuzzy"
    elif force_choose:
        reason = "already_near"
    else:
        reason = "confirm"
    return {
        "status": "choose",
        "reason": reason,
        "uid": nearest_pending["uid"],
        "distance_m": nearest_pending["distance_m"],
        "options": options,
        "nearest": packed,
        "nearby_done": nearby,
    }
