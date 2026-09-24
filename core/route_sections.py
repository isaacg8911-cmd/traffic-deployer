"""Independent route sections when two (or more) .EST maps are loaded.

Each map keeps its own pick order and polyline. Day 1 and Day 2 are separate
sections. Together (All days) shows both without mixing their routes.
"""
from __future__ import annotations

import re

DAY_FILTER_ALL = "All days"
TOGETHER_LABEL = "Together"
DAY_FILTER_ALL_ALIASES = frozenset({
    DAY_FILTER_ALL, "All maps", "", TOGETHER_LABEL, "together",
})

_DAY_NUM = re.compile(r"\bday\s+(\d+)\b", re.I)


def empty_route() -> dict:
    return {"polyline": [], "miles": 0.0, "legs": [], "graph": False}


def is_all_days(label: str | None) -> bool:
    return str(label or "").strip() in DAY_FILTER_ALL_ALIASES


def day_number(label: str | None) -> int | None:
    """``Week 27 Day 1 Isaac`` → 1. Names with no day number stay None."""
    m = _DAY_NUM.search(str(label or ""))
    if not m:
        return None
    return int(m.group(1))


def canonical_section(label: str | None) -> str:
    """One key for a day. ``Week 14 Day 1 Isaac`` and ``Day 1`` are the same section."""
    raw = str(label or "").strip()
    if is_all_days(raw):
        return DAY_FILTER_ALL
    n = day_number(raw)
    if n is not None:
        return f"Day {n}"
    return raw


def section_for_site(
    *,
    excel_sheet: str = "",
    est_label: str = "",
    est_index: int = 0,
    est_count: int = 1,
) -> tuple[str, str]:
    """Return ``(section, source)``.

    Excel sheet wins when it says Day N (Map 1.est is often Day 2).
    Otherwise the .EST filename, otherwise upload order: first file = Day 1.
    """
    for src, kind in ((excel_sheet, "excel"), (est_label, "est")):
        if day_number(src) is not None:
            return canonical_section(src), kind
    if est_count >= 2:
        return f"Day {est_index + 1}", "order"
    return (str(est_label or "").strip() or "Day 1"), "est"


def _order_days(labels: list[str]) -> list[str]:
    nums = [day_number(x) for x in labels]
    if labels and all(n is not None for n in nums):
        return [lab for _, lab in sorted(zip(nums, labels), key=lambda pair: pair[0])]
    return labels


def section_labels(stops: list[dict], active_files: list[str] | None = None) -> list[str]:
    """Day names that actually have sites.

    A filename with no matching sites is left out, so Day 1 / Day 2 are not
    empty entries next to a Together view that has every pin.
    """
    stop_names: list[str] = []
    seen_stops: set[str] = set()
    for stop in stops or []:
        name = canonical_section(stop.get("sheet"))
        if name and not is_all_days(name) and name not in seen_stops:
            stop_names.append(name)
            seen_stops.add(name)
    if not stop_names:
        out: list[str] = []
        seen: set[str] = set()
        for raw in list(active_files or []):
            name = canonical_section(raw)
            if name and not is_all_days(name) and name not in seen:
                out.append(name)
                seen.add(name)
        return _order_days(out)

    out = []
    seen = set()
    for raw in list(active_files or []):
        name = canonical_section(raw)
        if name in seen_stops and name not in seen:
            out.append(name)
            seen.add(name)
    for name in stop_names:
        if name not in seen:
            out.append(name)
            seen.add(name)
    return _order_days(out)


def multi_section(stops: list[dict], active_files: list[str] | None = None) -> bool:
    return len(section_labels(stops, active_files)) >= 2


def stops_for_section(stops: list[dict], label: str) -> list[dict]:
    if is_all_days(label):
        return list(stops or [])
    want = canonical_section(label)
    return [
        s for s in (stops or [])
        if canonical_section(s.get("sheet")) == want
    ]


def merge_section_order(all_stops: list[dict], section_ordered: list[dict]) -> list[dict]:
    """Replace one map's visit order; leave every other map's order untouched."""
    if not section_ordered:
        return list(all_stops or [])
    sheet = canonical_section(section_ordered[0].get("sheet"))
    inserted = False
    out: list[dict] = []
    for stop in all_stops or []:
        if canonical_section(stop.get("sheet")) == sheet:
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
        fresh_by_sheet.setdefault(canonical_section(stop.get("sheet")), []).append(stop)
    old_uids_by_sheet: dict[str, list[str]] = {}
    for stop in old_stops or []:
        old_uids_by_sheet.setdefault(canonical_section(stop.get("sheet")), []).append(stop["uid"])

    sheets: list[str] = []
    seen: set[str] = set()
    for stop in old_stops or []:
        sheet = canonical_section(stop.get("sheet"))
        if sheet not in seen:
            sheets.append(sheet)
            seen.add(sheet)
    for sheet in fresh_by_sheet:
        if sheet not in seen:
            sheets.append(sheet)
            seen.add(sheet)

    fresh_by_uid = {s["uid"]: s for s in (fresh_stops or [])}
    out: list[dict] = []
    rebuild = canonical_section(rebuild_sheet) if rebuild_sheet else ""
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


def compose_section_routes(
    routes_by_map: dict[str, dict] | None,
    labels: list[str],
) -> dict:
    """Overlay independently built day routes for the All-days view.

    Polylines stay in ``polylines`` (one list per map) so a fake drive line
    is not drawn between the last stop of day 1 and the first stop of day 2.
    """
    out = empty_route()
    chunks: list[list] = []
    miles = 0.0
    graph = False
    site_legs: list = []
    stored = routes_by_map or {}
    for label in labels or []:
        if is_all_days(label):
            continue
        route = stored.get(label) or {}
        poly = list(route.get("polyline") or [])
        if poly:
            chunks.append(poly)
        miles += float(route.get("miles") or 0)
        if route.get("graph"):
            graph = True
        legs = route.get("site_legs") or route.get("legs") or []
        if isinstance(legs, list):
            site_legs.extend(legs)
    if chunks:
        # Single polyline for maps that only read ``polyline``; keep a gap
        # marker-free concat only when there is exactly one day.
        if len(chunks) == 1:
            out["polyline"] = chunks[0]
        else:
            out["polyline"] = []
        out["polylines"] = chunks
    out["miles"] = round(miles, 2)
    out["graph"] = graph
    if site_legs:
        out["site_legs"] = site_legs
    return out
