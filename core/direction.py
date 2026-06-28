"""Install direction rules (n/e for PicoCount) — inferred from data, never guessed."""
from __future__ import annotations

import math

MIN_SEGMENT_M = 15.0


def _segment_length_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = (lat2 - lat1) * 111_320.0
    dlon = (lon2 - lon1) * 111_320.0 * math.cos(math.radians((lat1 + lat2) / 2.0))
    return (dlat * dlat + dlon * dlon) ** 0.5


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    y = math.radians(lat2 - lat1)
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2.0))
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def _axis_ne(bearing_deg: float) -> str:
    """Road segment axis → PicoCount facing n or e (never s/w)."""
    axis = float(bearing_deg) % 180.0
    if axis > 90.0:
        axis = 180.0 - axis
    return "n" if axis <= 45.0 else "e"


def _heading_ne(heading_deg: float) -> str:
    """GPS course/heading when stopped → n or e."""
    h = float(heading_deg) % 360.0
    dist_n = min(abs(h - 0.0), abs(h - 360.0), abs(h - 180.0))
    dist_e = min(abs(h - 90.0), abs(h - 270.0))
    return "e" if dist_e < dist_n else "n"


def infer_from_segment(
    begin_lat: float,
    begin_lon: float,
    end_lat: float,
    end_lon: float,
) -> dict:
    """
    Infer n/e from Excel begin→end segment geometry.
    Returns direction=None when the segment is too short to trust.
    """
    dist = _segment_length_m(begin_lat, begin_lon, end_lat, end_lon)
    if dist < MIN_SEGMENT_M:
        return {
            "direction": None,
            "source": "needs_gps",
            "confidence": "none",
            "bearing_deg": None,
            "segment_m": round(dist, 1),
        }
    bearing = _bearing_deg(begin_lat, begin_lon, end_lat, end_lon)
    return {
        "direction": _axis_ne(bearing),
        "source": "segment",
        "confidence": "high" if dist >= 50.0 else "medium",
        "bearing_deg": round(bearing, 1),
        "segment_m": round(dist, 1),
    }


def infer_from_heading(heading_deg: float) -> dict:
    """Infer n/e from a locked GPS heading (vehicle stopped)."""
    return {
        "direction": _heading_ne(heading_deg),
        "source": "gps",
        "confidence": "high",
        "bearing_deg": round(float(heading_deg) % 360.0, 1),
    }


def apply_segment_hint(stop: dict) -> None:
    """Set direction fields on a fresh stop from begin/end coords."""
    hint = infer_from_segment(
        float(stop["begin_lat"]),
        float(stop["begin_lon"]),
        float(stop["end_lat"]),
        float(stop["end_lon"]),
    )
    stop["direction"] = hint.get("direction") or ""
    stop["direction_source"] = hint.get("source") or "needs_gps"
    if hint.get("bearing_deg") is not None:
        stop["direction_bearing"] = hint["bearing_deg"]
    if hint.get("segment_m") is not None:
        stop["segment_m"] = hint["segment_m"]


def direction_hint_text(stop: dict) -> str:
    """Human-readable note for Install UI."""
    src = str(stop.get("direction_source") or "").strip()
    d = str(stop.get("direction") or "").strip().lower()
    if src == "segment":
        b = stop.get("direction_bearing")
        seg = stop.get("segment_m")
        extra = f" · {seg} m segment" if seg else ""
        return f"Direction {d or '?'} from Excel segment{extra}" + (f" ({b}°)" if b else "")
    if src == "gps":
        return f"Direction {d or '?'} from GPS compass"
    if src == "manual":
        return f"Direction {d or '?'} — set manually"
    if src == "needs_gps":
        return "Segment too short — set direction from compass at site"
    return ""
