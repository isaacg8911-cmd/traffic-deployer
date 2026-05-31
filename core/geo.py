"""Online geo helpers (address search + reverse street lookup) and the notes parser.

These are the only pieces that touch the internet, and only when the laptop has
signal. Everything degrades gracefully to empty results when offline.
"""
from __future__ import annotations

import re

try:
    import requests
    _HAS_REQUESTS = True
except Exception:
    _HAS_REQUESTS = False

_UA = "TrafficDeployer-Desktop/1.0 (field-ops tool)"
_cache: dict[str, object] = {}


def geocode_address(address: str) -> tuple[float | None, float | None]:
    """Forward geocode an address -> (lat, lon). Census first, then Nominatim."""
    if not _HAS_REQUESTS or not address:
        return None, None
    key = f"fwd:{address.strip().lower()}"
    if key in _cache:
        c = _cache[key]
        return (c[0], c[1]) if c else (None, None)
    try:
        url = ("https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
               f"?address={requests.utils.quote(address)}&benchmark=Public_AR_Current&format=json")
        matches = requests.get(url, timeout=5).json().get("result", {}).get("addressMatches", [])
        if matches:
            lat = float(matches[0]["coordinates"]["y"])
            lon = float(matches[0]["coordinates"]["x"])
            _cache[key] = [lat, lon]
            return lat, lon
    except Exception:
        pass
    try:
        url = f"https://nominatim.openstreetmap.org/search?format=json&q={requests.utils.quote(address)}"
        resp = requests.get(url, headers={"User-Agent": _UA}, timeout=5).json()
        if resp:
            lat, lon = float(resp[0]["lat"]), float(resp[0]["lon"])
            _cache[key] = [lat, lon]
            return lat, lon
    except Exception:
        pass
    return None, None


def street_offline(lat: float, lon: float, data_dir: str) -> str:
    """Road name from the local OSM drive graph (no internet)."""
    try:
        import road_router
        return road_router.street_name_at(data_dir, lat, lon) or ""
    except Exception:
        return ""


def street_for_field(lat: float, lon: float, data_dir: str, prefer_online: bool = True) -> tuple[str, str]:
    """Return (street, source) where source is 'online', 'offline', or ''."""
    if prefer_online:
        online = street_from_coords(lat, lon)
        if online:
            return online, "online"
    offline = street_offline(lat, lon, data_dir)
    if offline:
        return offline, "offline"
    return "", ""


def street_from_coords(lat: float, lon: float) -> str:
    """Reverse geocode -> street/road name. Empty string when offline/unknown."""
    if not _HAS_REQUESTS:
        return ""
    key = f"rev:{round(float(lat), 5)},{round(float(lon), 5)}"
    if key in _cache:
        return _cache[key]
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}"
        addr = requests.get(url, headers={"User-Agent": _UA}, timeout=3).json().get("address", {})
        road = addr.get("road", "")
        if road:
            _cache[key] = road
            return road
    except Exception:
        pass
    return ""


def parse_dictation(text: str, direction: str, lanes: int, serial: str):
    """Pull direction / lane count / serial out of free-text field notes."""
    if not text or str(text).strip() == "":
        return direction, lanes, serial
    t = str(text).lower()
    if "north" in t:
        direction = "n"
    elif "south" in t:
        direction = "s"
    elif "east" in t:
        direction = "e"
    elif "west" in t:
        direction = "w"
    m = re.search(r"(\d+)\s*lane", t)
    if m:
        lanes = int(m.group(1))
    m = re.search(r"serial.*?(\w+)", t)
    if m:
        serial = str(m.group(1)).upper()
    return direction, lanes, serial
