"""Install readiness checklist + duplicate serial guard."""
from __future__ import annotations


def checklist_for_stop(stop: dict) -> list[dict]:
    """Field hints before INSTALL — advisory only; INSTALL is never blocked here."""
    gps = stop.get("field_lat") is not None and stop.get("field_lon") is not None
    cleared = bool(str(stop.get("counter_cleared_at") or "").strip())
    serial = bool(str(stop.get("counter_serial") or stop.get("serial") or "").strip())
    return [
        {"key": "gps", "label": "GPS / pin", "done": gps, "optional": True},
        {"key": "clear", "label": "Counter cleared", "done": cleared, "optional": True},
        {"key": "serial", "label": "Serial read", "done": serial, "optional": True},
    ]


def format_checklist_text(items: list[dict]) -> str:
    return "   ".join(
        f"{'✓' if it['done'] else '○'} {it['label']}" for it in items
    )


def all_ready(items: list[dict]) -> bool:
    """True when every advisory checklist item is done (visual green only)."""
    return bool(items) and all(it["done"] for it in items)


def find_duplicate_serial(
    stops: list[dict],
    skip_uid: str,
    serial: str,
) -> dict | None:
    """Another stop today already has this PicoCount serial."""
    sn = str(serial or "").strip().upper()
    if len(sn) < 3:
        return None
    for s in stops:
        if s.get("uid") == skip_uid:
            continue
        other = str(s.get("counter_serial") or s.get("serial") or "").strip().upper()
        if other and other == sn:
            return s
    return None


def find_duplicate_unit_id(
    stops: list[dict],
    skip_uid: str,
    unit_id: str,
) -> dict | None:
    """Another stop already has this PicoCount Unit ID."""
    uid = str(unit_id or "").strip().lower()
    if len(uid) < 4:
        return None
    for s in stops:
        if s.get("uid") == skip_uid:
            continue
        other = str(s.get("counter_unit_id") or "").strip().lower()
        if other and other == uid:
            return s
    return None


def missing_labels(items: list[dict]) -> list[str]:
    return [it["label"] for it in items if not it.get("done")]


def install_block_reason(stop: dict) -> str | None:
    """INSTALL is never blocked by the checklist (counter may already be cleared in the field)."""
    return None
