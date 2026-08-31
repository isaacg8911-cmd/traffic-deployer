"""Independent route sections when two (or more) .EST maps are loaded.

Each map keeps its own pick order and polyline. Cycling the Map control
must not rebuild or wipe the other section.
"""
from __future__ import annotations

DAY_FILTER_ALL = "All days"
DAY_FILTER_ALL_ALIASES = frozenset({DAY_FILTER_ALL, "All maps", ""})


def empty_route() -> dict:
    return {"polyline": [], "miles": 0.0, "legs": [], "graph": False}


def is_all_days(label: str | None) -> bool:
    return str(label or "") in DAY_FILTER_ALL_ALIASES


def section_labels(stops: list[dict], active_files: list[str] | None = None) -> list[str]:
    """Stable map names: upload labels first, then any extra sheets on stops."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in list(active_files or []):
        name = str(raw or "").strip()
        if name and name not in seen and not is_all_days(name):
            out.append(name)
            seen.add(name)
    for stop in stops or []:
        name = str(stop.get("sheet") or "").strip()
        if name and name not in seen and not is_all_days(name):
            out.append(name)
            seen.add(name)
    return out


def multi_section(stops: list[dict], active_files: list[str] | None = None) -> bool:
    return len(section_labels(stops, active_files)) >= 2


def stops_for_section(stops: list[dict], label: str) -> list[dict]:
    if is_all_days(label):
        return list(stops or [])
    return [s for s in (stops or []) if str(s.get("sheet") or "") == str(label)]


def merge_section_order(all_stops: list[dict], section_ordered: list[dict]) -> list[dict]:
    """Replace one map's visit order; leave every other map's order untouched."""
    if not section_ordered:
        return list(all_stops or [])
    sheet = str(section_ordered[0].get("sheet") or "")
    inserted = False
    out: list[dict] = []
    for stop in all_stops or []:
        if str(stop.get("sheet") or "") == sheet:
            if not inserted:
                out.extend(section_ordered)
                inserted = True
            continue
        out.append(stop)
    if not inserted:
        out.extend(section_ordered)
    return out


def preserve_other_section_orders(
    old_stops: list[dict],
    fresh_stops: list[dict],
    *,
    rebuild_sheet: str | None,
) -> list[dict]:
    """On re-match, keep visit order for maps that are not being rebuilt."""
    fresh_by_sheet: dict[str, list[dict]] = {}
    for stop in fresh_stops or []:
        fresh_by_sheet.setdefault(str(stop.get("sheet") or ""), []).append(stop)
    old_uids_by_sheet: dict[str, list[str]] = {}
    for stop in old_stops or []:
        old_uids_by_sheet.setdefault(str(stop.get("sheet") or ""), []).append(stop["uid"])

    sheets: list[str] = []
    seen: set[str] = set()
    for stop in old_stops or []:
        sheet = str(stop.get("sheet") or "")
        if sheet not in seen:
            sheets.append(sheet)
            seen.add(sheet)
    for sheet in fresh_by_sheet:
        if sheet not in seen:
            sheets.append(sheet)
            seen.add(sheet)

    fresh_by_uid = {s["uid"]: s for s in (fresh_stops or [])}
    out: list[dict] = []
    rebuild = str(rebuild_sheet or "")
    for sheet in sheets:
        group = fresh_by_sheet.get(sheet, [])
        if not group:
            continue
        if not rebuild or sheet == rebuild or sheet not in old_uids_by_sheet:
            out.extend(group)
            continue
        used: set[str] = set()
        for uid in old_uids_by_sheet[sheet]:
            nxt = fresh_by_uid.get(uid)
            if nxt is not None:
                out.append(nxt)
                used.add(uid)
        for stop in group:
            if stop["uid"] not in used:
                out.append(stop)
    return out


def cycle_label(labels: list[str], current: str, delta: int) -> str | None:
    if not labels:
        return None
    if current not in labels:
        return labels[0] if delta >= 0 else labels[-1]
    return labels[(labels.index(current) + delta) % len(labels)]
