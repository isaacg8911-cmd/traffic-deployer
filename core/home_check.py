"""Sanity checks: start point vs where today's sites actually are."""
from __future__ import annotations

import math

from core.state import DEFAULT_HOME


def _haversine_mi(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371.0
    dlat = math.radians(b[0] - a[0])
    dlon = math.radians(b[1] - a[1])
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(dlon / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h)) * 0.621371


def check_home_vs_stops(
    home: tuple[float, float],
    stops: list[dict],
    *,
    default_home: tuple[float, float] | None = None,
) -> list[str]:
    """Warnings when origin is far from the job or still the factory default."""
    if not stops:
        return []
    warnings: list[str] = []
    pts = [(float(s["lat"]), float(s["lon"])) for s in stops if s.get("lat") is not None]
    if not pts:
        return warnings

    dists = sorted(_haversine_mi(home, p) for p in pts)
    median_mi = dists[len(dists) // 2]
    min_mi = dists[0]

    dh = default_home or DEFAULT_HOME
    if abs(home[0] - dh[0]) < 1e-4 and abs(home[1] - dh[1]) < 1e-4 and median_mi > 8.0:
        warnings.append(
            "Start point is still the factory default (demo coords) but your sites are "
            f"~{median_mi:.0f} mi away. Set your real home: GPS, address search, or manual lat/lon."
        )
    elif median_mi > 25.0:
        warnings.append(
            f"Start point is ~{median_mi:.0f} mi from the middle of your sites (nearest site "
            f"~{min_mi:.0f} mi). Far-first routing will be wrong — fix origin on Setup."
        )
    elif median_mi > 12.0:
        warnings.append(
            f"Start point is ~{median_mi:.0f} mi from your site area. Confirm origin matches "
            "where you park / start the day."
        )
    return warnings
