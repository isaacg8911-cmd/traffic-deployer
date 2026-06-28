"""End-of-day shift summary text (install / skip / miles)."""
from __future__ import annotations


def summarize(stops: list[dict], route: dict | None = None) -> dict:
    """Return {text, installed, skipped, pending, miles, picked_up}."""
    if not stops:
        return {
            "text": "No stops loaded.",
            "installed": 0,
            "skipped": 0,
            "pending": 0,
            "miles": 0.0,
            "picked_up": 0,
        }
    installed = sum(1 for s in stops if s.get("installed"))
    skipped = sum(1 for s in stops if s.get("skipped"))
    pending = len(stops) - installed - skipped
    picked = sum(1 for s in stops if s.get("installed") and s.get("picked_up"))
    pending_pickup = sum(
        1 for s in stops if s.get("installed") and not s.get("picked_up"))
    miles = float((route or {}).get("miles", 0) or 0)
    counter_cfg = sum(1 for s in stops if s.get("counter_unit_id"))
    counter_dl = sum(1 for s in stops if s.get("counter_download_path"))
    lines = [
        f"Shift: {len(stops)} stops · {installed} installed · {skipped} skipped · {pending} open",
        f"Route plan: {miles:.1f} mi",
        f"Pickup: {picked} secured · {pending_pickup} still on street",
    ]
    if counter_cfg or counter_dl:
        lines.append(
            f"PicoCount: {counter_cfg} configured at install · {counter_dl} study file(s) downloaded")
    if pending == 0 and installed > 0:
        lines.append("All stops closed — ready to export.")
    return {
        "text": "\n".join(lines),
        "installed": installed,
        "skipped": skipped,
        "pending": pending,
        "miles": miles,
        "picked_up": picked,
    }
