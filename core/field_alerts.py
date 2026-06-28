"""Field banners: pickup downloads pending, shift-complete export."""
from __future__ import annotations


def pending_counter_downloads(stops: list[dict]) -> list[dict]:
    """Installed sites with Unit ID but no local study file yet."""
    out: list[dict] = []
    for s in stops:
        if not s.get("installed"):
            continue
        if not str(s.get("counter_unit_id") or "").strip():
            continue
        if str(s.get("counter_download_path") or "").strip():
            continue
        out.append(s)
    return out


def pending_download_count(stops: list[dict]) -> int:
    return len(pending_counter_downloads(stops))


def pickup_reminder_text(stops: list[dict]) -> str:
    pending = pending_counter_downloads(stops)
    if not pending:
        return ""
    ids = ", ".join(str(s.get("id", "?")) for s in pending[:6])
    if len(pending) > 6:
        ids += ", …"
    return (
        f"{len(pending)} installed site(s) need counter download"
        f" — Site {ids} · open Pickup tab"
    )


def shift_closed(stops: list[dict]) -> bool:
    if not stops:
        return False
    return all(s.get("installed") or s.get("skipped") for s in stops)
