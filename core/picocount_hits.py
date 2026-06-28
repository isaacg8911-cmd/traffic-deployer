"""PicoCount compressed hose-hit stream — parse from .tvp or raw .pcbin."""
from __future__ import annotations

import json
import os
import struct
from datetime import datetime, timedelta

TICKS_PER_SEC = 32768
CHANNEL = {1: "A", 2: "B", 3: "C", 4: "D", 12: "START", 13: "STOP", 14: "COUNTBUDDY"}

# Defaults tuned for 2-hose volume (Tube–Tube); not TrafficViewer-identical.
DEFAULT_DWELL_S = 0.040
DEFAULT_PAIR_MAX_S = 0.12


def decompress_hits(data: bytes, start: int = 0) -> tuple[list[dict], int | None]:
    """Return hose hits from compressed stream; None if parse fails early."""
    tick = bytearray(6)
    hits: list[dict] = []
    i = start
    n = len(data)
    while i < n:
        info = data[i]
        i += 1
        ch = info & 0x0F
        n_high = info >> 4
        if n_high < 9 or n_high > 14:
            if hits:
                break
            return [], i - start
        nbytes = n_high - 8
        if i + nbytes > n:
            break
        for b in range(nbytes):
            tick[b] = data[i + b]
        i += nbytes
        ticks = int.from_bytes(tick, "little")
        hits.append(
            {
                "channel": CHANNEL.get(ch, f"CH{ch}"),
                "channel_code": ch,
                "ticks": ticks,
                "seconds": ticks / TICKS_PER_SEC,
            }
        )
    if len(hits) < 10:
        return [], None
    return hits, i - start


def find_best_stream(data: bytes) -> tuple[int, list[dict]]:
    """Locate the longest valid compressed hit stream in study bytes."""
    best_off = 0
    best: list[dict] = []
    fallback_off = 0
    fallback: list[dict] = []
    scan_from = data.find(b"Multi-Unit - 7 Axles or More")
    if scan_from < 0:
        scan_from = 0
    else:
        scan_from += 64
    for off in range(scan_from, len(data) - 64):
        hits, consumed = decompress_hits(data, off)
        if not hits or consumed is None:
            continue
        duration = hits[-1]["seconds"] - hits[0]["seconds"]
        if len(hits) > len(fallback):
            fallback = hits
            fallback_off = off
        if duration < 3600:
            continue
        if len(hits) > len(best):
            best = hits
            best_off = off
    if best:
        return best_off, best
    if len(fallback) >= 100:
        return fallback_off, fallback
    return 0, []


def decode_start_time_tvp(data: bytes) -> datetime | None:
    """Study start from TrafficViewer Pro .tvp metadata (before FHWA label)."""
    fhwa = data.find(b"FHWA")
    if fhwa < 32:
        return None
    window = data[max(0, fhwa - 128): fhwa]
    best: datetime | None = None
    for off in range(max(0, len(window) - 8)):
        cs, sec, minute, hour, day, mon_b, ylo, yhi = window[off: off + 8]
        year = ylo | (yhi << 8)
        if not (2020 <= year <= 2035 and 1 <= day <= 31):
            continue
        if hour > 23 or minute > 59 or sec > 59:
            continue
        month = mon_b if 1 <= mon_b <= 12 else mon_b + 1
        if not 1 <= month <= 12:
            continue
        try:
            dt = datetime(year, month, day, hour, minute, sec)
        except ValueError:
            continue
        if best is None or dt < best:
            best = dt
    return best


def decode_start_time_raw(data: bytes) -> datetime | None:
    """Best-effort study start from raw NAND / .pcbin (no TVP header)."""
    for off in range(0, len(data) - 8):
        cs, sec, minute, hour, day, mon_b, ylo, yhi = data[off: off + 8]
        year = ylo | (yhi << 8)
        if not (2020 <= year <= 2035 and 1 <= day <= 31):
            continue
        if hour > 23 or minute > 59 or sec > 59:
            continue
        month = mon_b if 1 <= mon_b <= 12 else mon_b + 1
        if not 1 <= month <= 12:
            continue
        try:
            return datetime(year, month, day, hour, minute, sec)
        except ValueError:
            continue
    return None


def file_downloaded_at(data: bytes) -> datetime | None:
    """Excel serial date sometimes stored in TVP tail."""
    base = datetime(1899, 12, 30)
    for off in range(len(data) - 8):
        d = struct.unpack_from("<d", data, off)[0]
        if 45800 <= d <= 46300:
            dt = base + timedelta(days=d)
            if dt.year >= 2024:
                return dt
    return None


def load_study_bytes(path: str) -> tuple[bytes, str]:
    """Return (bytes, format) where format is 'tvp' or 'pcbin'."""
    with open(path, "rb") as f:
        data = f.read()
    if data.startswith(b"TrafficViewerPro.Data"):
        return data, "tvp"
    return data, "pcbin"


def trim_hits(
    hits: list[dict],
    *,
    max_seconds: float = 86400 * 8,
) -> list[dict]:
    """Drop corrupt NAND tail hits (tick overflow / parse noise)."""
    return [
        h for h in hits
        if h["channel"] in ("A", "B") and 0 <= h["seconds"] <= max_seconds
    ]


def study_start_from_sidecar(path: str, duration_s: float) -> datetime | None:
    """Study start from download sidecar — prefers counter clear time."""
    sidecar = path + ".json"
    if not os.path.isfile(sidecar):
        return None
    try:
        with open(sidecar, encoding="utf-8") as f:
            meta = json.load(f)
        for key in ("study_start", "counter_cleared_at", "cleared_at"):
            raw = meta.get(key)
            if raw:
                return _parse_wall_time(str(raw))
        raw = meta.get("saved_at")
        if raw:
            # Last resort: download time minus span (desk/sandbox pulls only).
            dt = _parse_wall_time(str(raw))
            if dt:
                return dt - timedelta(seconds=max(0.0, duration_s))
    except Exception:
        return None
    return None


def _parse_wall_time(raw: str) -> datetime | None:
    """Parse ISO or stop-record timestamp (YYYY-MM-DD HH:MM:SS)."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(raw[: len(fmt)], fmt)
        except ValueError:
            continue
    return None


def parse_hits(path: str, *, study_start: datetime | None = None) -> dict:
    """Parse a .tvp or .pcbin file into debounce-ready hose hits."""
    data, fmt = load_study_bytes(path)
    off, hits = find_best_stream(data)
    if not hits:
        return {"ok": False, "error": "Could not locate compressed hose-hit stream."}

    hits = trim_hits(hits)
    if len(hits) < 20:
        return {"ok": False, "error": "Study stream too short after trim."}

    first_sec = hits[0]["seconds"]
    last_sec = hits[-1]["seconds"]
    duration_s = max(0.0, last_sec - first_sec)

    source = "explicit" if study_start is not None else ""
    if study_start is None:
        study_start = study_start_from_sidecar(path, duration_s)
        if study_start is not None:
            source = "sidecar"
    if study_start is None:
        if fmt == "tvp":
            study_start = decode_start_time_tvp(data)
            if study_start is not None:
                source = "tvp_header"
        if study_start is None:
            study_start = decode_start_time_raw(data)
            if study_start is not None:
                source = "raw_header"
    if study_start is None:
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            study_start = mtime - timedelta(seconds=duration_s)
            source = "download_minus_span"
        except Exception:
            study_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            source = "fallback_midnight"

    start = study_start

    return {
        "ok": True,
        "path": path,
        "format": fmt,
        "stream_offset": off,
        "hits": hits,
        "study_start": start,
        "study_start_source": source,
        "first_hit_at": start + timedelta(seconds=first_sec),
        "last_hit_at": start + timedelta(seconds=last_sec),
        "downloaded_at": file_downloaded_at(data) if fmt == "tvp" else None,
        "hit_count": len(hits),
        "duration_s": duration_s,
    }


def debounce_hits(
    hits: list[dict],
    *,
    dwell_s: float = DEFAULT_DWELL_S,
) -> list[dict]:
    """Collapse same-hose hits within dwell (axle bursts)."""
    out: list[dict] = []
    last: dict[str, float] = {}
    for h in sorted(hits, key=lambda x: x["seconds"]):
        if h["channel"] not in ("A", "B"):
            continue
        ch = h["channel"]
        if ch in last and h["seconds"] - last[ch] < dwell_s:
            continue
        last[ch] = h["seconds"]
        out.append(h)
    return out


def pair_vehicles(
    hits: list[dict],
    *,
    dwell_s: float = DEFAULT_DWELL_S,
    pair_max_s: float = DEFAULT_PAIR_MAX_S,
    study_start: datetime,
) -> list[dict]:
    """
    Pair debounced A/B hose hits into directional vehicle events.

    Returns list of {datetime, direction_key} where direction_key is 'ab' or 'ba'.
    """
    db = debounce_hits(hits, dwell_s=dwell_s)
    ab = sorted(db, key=lambda x: x["seconds"])
    used: set[int] = set()
    events: list[dict] = []

    def _match(first_ch: str, second_ch: str, key: str) -> None:
        nonlocal used, events
        for i, a in enumerate(ab):
            if a["channel"] != first_ch or i in used:
                continue
            best_j = None
            best_dt = None
            for j, b in enumerate(ab):
                if j in used or b["channel"] != second_ch:
                    continue
                dt = b["seconds"] - a["seconds"]
                if dt <= 0 or dt > pair_max_s:
                    continue
                if best_dt is None or dt < best_dt:
                    best_dt = dt
                    best_j = j
            if best_j is not None:
                used.add(i)
                used.add(best_j)
                ts = study_start + timedelta(seconds=a["seconds"])
                events.append({"datetime": ts, "direction_key": key})

    _match("A", "B", "ab")
    _match("B", "A", "ba")
    events.sort(key=lambda e: e["datetime"])
    return events
