"""TrafficViewer Pro .tvp data file — metadata import (Phase 1).

Official files begin with the magic string ``TrafficViewerPro.Data`` (see
VehicleCounts version history). Full volume/timestamp bins are binary; this
module extracts header fields we can read reliably and attaches them to a stop.

For counts and intervals, export CSV from TrafficViewer Pro until bin parsing
is reverse-engineered or we use the PicoCount serial protocol directly.
"""
from __future__ import annotations

import os
import re

MAGIC = b"TrafficViewerPro.Data"
_DIR_RE = re.compile(r"\b(Northbound|Southbound|Eastbound|Westbound)\b", re.I)
_CLASS_RE = re.compile(
    r"(Motorcycles|Passenger Cars|Pickup Trucks|Buses|Single Unit|Double Unit|Multi-Unit)"
    r"[^\x00]{0,60}"
)


def _clean(s: str) -> str:
    return re.sub(r"\x00+", "", s).strip()


def parse_metadata(path: str) -> dict:
    """Read a .tvp file and return proven metadata (no volume table yet)."""
    with open(path, "rb") as f:
        data = f.read()
    if not data.startswith(MAGIC):
        raise ValueError("Not a TrafficViewer Pro data file (missing TrafficViewerPro.Data header)")

    latin = data.decode("latin-1", errors="ignore")
    head = latin[:4000]
    stem = os.path.splitext(os.path.basename(path))[0]

    unit_serial = None
    m = re.search(r"\b(\d{8})\b", head)
    if m:
        unit_serial = m.group(1)

    unit_id = stem
    if stem not in head:
        m2 = re.search(r"\b([0-9a-f]{5,12})\b", head[50:250], re.I)
        if m2:
            unit_id = m2.group(1)

    directions = [d.title() for d in dict.fromkeys(_DIR_RE.findall(latin))]
    scheme = "FHWA" if "FHWA" in latin else ""

    classes: list[str] = []
    if scheme:
        idx = latin.find("FHWA")
        block = latin[idx : idx + 12000]
        for m in _CLASS_RE.finditer(block):
            name = _clean(m.group(0))
            if name and name not in classes:
                classes.append(name)

    return {
        "ok": True,
        "path": os.path.abspath(path),
        "filename": os.path.basename(path),
        "size_bytes": len(data),
        "format": "TrafficViewerPro.Data",
        "unit_serial": unit_serial,
        "unit_id": unit_id,
        "directions": directions,
        "classification_scheme": scheme,
        "vehicle_classes": classes,
        "has_binary_counts": len(data) > 17000,
    }
