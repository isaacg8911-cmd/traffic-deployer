"""Online geo helpers (address search + reverse street lookup) and the notes parser.

These are the only pieces that touch the internet, and only when the laptop has
signal. Everything degrades gracefully to empty results when offline.
"""
from __future__ import annotations

import re

from core.offline_policy import internet_features_allowed

try:
    import requests
    _HAS_REQUESTS = True
except Exception:
    _HAS_REQUESTS = False

_UA = "TrafficDeployer-Desktop/1.0 (field-ops tool)"
_cache: dict[str, object] = {}

# California bias for field work (lon/lat).
_CA_VIEWBOX = "-124.6,32.4,-114.0,42.1"


def _address_variants(address: str) -> list[str]:
    """Try common California field formats when search fails."""
    a = address.strip()
    if not a:
        return []
    out = [a]
    low = a.lower()
    if "california" not in low and ", ca" not in low and not re.search(r"\bca\s+\d{5}\b", low):
        out.append(f"{a}, CA")
        out.append(f"{a}, California")
    return out


def geocode_available() -> bool:
    return _HAS_REQUESTS


def geocode_candidates(address: str, *, limit: int = 5) -> list[dict]:
    """Forward geocode -> [{lat, lon, label}, ...]. Tries several providers + CA variants."""
    if not internet_features_allowed() or not _HAS_REQUESTS or not address.strip():
        return []
    key = f"cands:{address.strip().lower()}:{limit}"
    if key in _cache:
        return list(_cache[key])  # type: ignore[arg-type]

    seen: set[tuple[float, float]] = set()
    out: list[dict] = []

    def _add(lat: float, lon: float, label: str) -> None:
        if len(out) >= limit:
            return
        k = (round(lat, 5), round(lon, 5))
        if k in seen:
            return
        if not (32.0 < lat < 42.5 and -125.0 < lon < -114.0):
            return
        seen.add(k)
        out.append({"lat": lat, "lon": lon, "label": label})

    for variant in _address_variants(address):
        _census_candidates(variant, _add)
        if len(out) >= limit:
            break
    for variant in _address_variants(address):
        _nominatim_candidates(variant, _add, limit=limit)
        if len(out) >= limit:
            break
    for variant in _address_variants(address):
        _photon_candidates(variant, _add, limit=limit)
        if len(out) >= limit:
            break

    _cache[key] = out
    return out


def geocode_address(address: str) -> tuple[float | None, float | None]:
    """Forward geocode an address -> (lat, lon). Uses first good candidate."""
    cands = geocode_candidates(address, limit=1)
    if cands:
        return cands[0]["lat"], cands[0]["lon"]
    return None, None


def _census_candidates(address: str, add) -> None:
    try:
        url = (
            "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
            f"?address={requests.utils.quote(address)}&benchmark=Public_AR_Current&format=json"
        )
        matches = requests.get(url, timeout=12).json().get("result", {}).get("addressMatches", [])
        for m in matches[:3]:
            coords = m.get("coordinates", {})
            lat, lon = float(coords["y"]), float(coords["x"])
            label = m.get("matchedAddress") or address
            add(lat, lon, str(label))
    except Exception:
        pass


def _nominatim_candidates(address: str, add, *, limit: int = 5) -> None:
    """Try CA-biased search first; retry without strict viewbox if empty."""
    for bounded in (1, 0):
        try:
            url = (
                "https://nominatim.openstreetmap.org/search"
                f"?format=json&q={requests.utils.quote(address)}"
                f"&countrycodes=us&viewbox={_CA_VIEWBOX}&bounded={bounded}&limit={limit}"
            )
            rows = requests.get(url, headers={"User-Agent": _UA}, timeout=12).json()[:limit]
            for row in rows:
                add(float(row["lat"]), float(row["lon"]), row.get("display_name", address))
            if rows:
                return
        except Exception:
            pass


def _photon_candidates(address: str, add, *, limit: int = 5) -> None:
    try:
        url = (
            "https://photon.komoot.io/api/"
            f"?q={requests.utils.quote(address)}&limit={limit}&bbox=-124.6,32.4,-114.0,42.1"
        )
        for feat in requests.get(url, headers={"User-Agent": _UA}, timeout=12).json().get("features", []):
            geom = feat.get("geometry", {}).get("coordinates", [])
            if len(geom) >= 2:
                lon, lat = float(geom[0]), float(geom[1])
                props = feat.get("properties", {})
                parts = [
                    props.get("housenumber"),
                    props.get("street"),
                    props.get("city"),
                    props.get("state"),
                ]
                label = ", ".join(str(p) for p in parts if p) or address
                add(lat, lon, label)
    except Exception:
        pass


def street_offline(lat: float, lon: float, data_dir: str) -> str:
    """Road name from the local OSM drive graph (no internet)."""
    try:
        import road_router
        return road_router.street_name_at(data_dir, lat) or ""
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
    if not internet_features_allowed() or not _HAS_REQUESTS:
        return ""
    key = f"rev:{round(float(lat), 5)},{round(float(lon), 5)}"
    if key in _cache:
        return _cache[key]
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}"
        addr = requests.get(url, headers={"User-Agent": _UA}, timeout=8).json().get("address", {})
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
