"""PicoCount fleet inventory — one record per serial, auto-updated from USB + shift."""
from __future__ import annotations

import json
import os

from core.state import ca_now
from ui.paths import DATA_DIR

INVENTORY_FILE = os.path.join(DATA_DIR, "counter_inventory.json")
INVENTORY_LOG = os.path.join(DATA_DIR, "counter_inventory_log.jsonl")

VOLT_OK = 2.90
VOLT_WARN = 2.75

_store: dict | None = None


def volt_level(volts: float | None) -> str:
    if volts is None:
        return "unknown"
    if volts >= VOLT_OK:
        return "ok"
    if volts >= VOLT_WARN:
        return "warn"
    return "fail"


def format_battery(volts: float | None) -> str:
    if volts is None:
        return "—"
    tag = {"ok": "OK", "warn": "LOW", "fail": "REPLACE"}.get(volt_level(volts), "")
    return f"{volts:.2f} V ({tag})"


def volt_check_message(volts: float | None, *, serial: str = "") -> str:
    if volts is None:
        return "Battery voltage unavailable — reconnect counter."
    prefix = f"{serial} · " if serial else ""
    if volts >= VOLT_OK:
        return f"{prefix}Battery {volts:.2f} V — good"
    if volts >= VOLT_WARN:
        return f"{prefix}Battery {volts:.2f} V — low, plan replacement soon"
    return f"{prefix}Battery {volts:.2f} V — replace counter battery"


def _empty_store() -> dict:
    return {"version": 1, "counters": {}}


def _load_disk() -> dict:
    if not os.path.isfile(INVENTORY_FILE):
        return _empty_store()
    try:
        with open(INVENTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _empty_store()
        data.setdefault("version", 1)
        data.setdefault("counters", {})
        return data
    except Exception:
        return _empty_store()


def _store_data() -> dict:
    global _store
    if _store is None:
        _store = _load_disk()
    return _store


def _save_store() -> bool:
    os.makedirs(os.path.dirname(INVENTORY_FILE), exist_ok=True)
    tmp = INVENTORY_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_store_data(), f, indent=2)
        os.replace(tmp, INVENTORY_FILE)
        return True
    except Exception:
        if os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        return False


def _norm_serial(serial: str) -> str:
    return str(serial or "").strip().upper()


def _log_event(entry: dict) -> None:
    try:
        os.makedirs(os.path.dirname(INVENTORY_LOG), exist_ok=True)
        with open(INVENTORY_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except Exception:
        pass


def _shift_status(stop: dict) -> str:
    if stop.get("picked_up"):
        if str(stop.get("counter_download_path") or "").strip():
            return "Returned"
        return "Needs download"
    if stop.get("installed"):
        return "Deployed"
    if str(stop.get("counter_unit_id") or "").strip():
        return "Configured"
    return "In stock"


def _assignment_label(stop: dict) -> str:
    site = stop.get("id", "")
    street = str(stop.get("street") or "").strip()
    base = f"Site {site}"
    if street:
        base += f" · {street[:28]}"
    return base


def sync_from_shift(stops: list[dict]) -> bool:
    """Merge shift assignment into inventory records (one row per serial)."""
    counters = _store_data().setdefault("counters", {})
    changed = False
    seen: set[str] = set()
    _, ts = ca_now()

    for s in stops:
        serial = _norm_serial(s.get("counter_serial") or s.get("serial") or "")
        if not serial:
            continue
        seen.add(serial)
        status = _shift_status(s)
        assignment = _assignment_label(s) if s.get("installed") or s.get("counter_unit_id") else ""
        unit_id = str(s.get("counter_unit_id") or "").strip()
        prev = counters.get(serial, {})
        rec = dict(prev)
        rec["serial_number"] = serial
        if unit_id:
            rec["unit_id"] = unit_id
        if (
            rec.get("shift_status") != status
            or rec.get("assignment") != assignment
            or (unit_id and rec.get("unit_id") != unit_id)
        ):
            rec["shift_status"] = status
            rec["assignment"] = assignment
            rec["shift_updated_at"] = ts
            counters[serial] = rec
            changed = True
            _log_event({
                "t": ts,
                "serial": serial,
                "event": "shift",
                "state": status,
                "unit_id": unit_id or rec.get("unit_id", ""),
                "site_id": s.get("id", ""),
            })

    for serial, rec in list(counters.items()):
        if serial in seen:
            continue
        if rec.get("shift_status") in ("Deployed", "Needs download", "Configured", "Returned"):
            rec = dict(rec)
            rec["shift_status"] = "In stock"
            rec["assignment"] = ""
            rec["shift_updated_at"] = ts
            counters[serial] = rec
            changed = True
            _log_event({"t": ts, "serial": serial, "event": "shift", "state": "In stock"})

    if changed:
        _save_store()
    return changed


def record_usb(probe: dict, *, event: str = "usb") -> dict | None:
    """Upsert by serial from a live counter read — no duplicates."""
    if not probe.get("ok"):
        return None
    serial = _norm_serial(probe.get("serial_number") or "")
    if not serial:
        return None
    _, ts = ca_now()
    counters = _store_data().setdefault("counters", {})
    prev = counters.get(serial, {})
    record = {
        "serial_number": serial,
        "unit_id": str(probe.get("unit_id") or prev.get("unit_id") or "").strip(),
        "battery_volts": probe.get("battery_volts", prev.get("battery_volts")),
        "memory_bytes": int(probe.get("bytes") if probe.get("bytes") is not None else prev.get("memory_bytes") or 0),
        "memory_label": str(probe.get("label") or prev.get("memory_label") or ""),
        "model": str(probe.get("model") or prev.get("model") or "").strip(),
        "firmware": str(probe.get("firmware") or prev.get("firmware") or "").strip(),
        "port": str(probe.get("port") or prev.get("port") or "").strip(),
        "shift_status": prev.get("shift_status") or "In stock",
        "assignment": prev.get("assignment") or "",
        "last_seen_at": ts,
    }
    counters[serial] = record
    _save_store()
    _log_event({
        "t": ts,
        "serial": serial,
        "event": event,
        "state": record.get("shift_status", "In stock"),
        "volts": record.get("battery_volts"),
        "unit_id": record.get("unit_id", ""),
        "bytes": record.get("memory_bytes"),
    })
    return record


def upsert_from_probe(probe: dict) -> dict | None:
    """Compat alias — use record_usb."""
    return record_usb(probe, event="usb")


def build_rows(stops: list[dict] | None = None) -> list[dict]:
    counters = _store_data().get("counters", {})
    rows = [dict(v) for v in counters.values()]
    rows.sort(key=lambda r: (
        r.get("shift_status") not in ("Deployed", "Needs download"),
        r.get("shift_status") == "In stock",
        str(r.get("serial_number") or ""),
    ))
    return rows


def inventory_summary(stops: list[dict] | None = None) -> dict:
    rows = build_rows(stops)
    return {
        "total": len(rows),
        "deployed": sum(1 for r in rows if r.get("shift_status") == "Deployed"),
        "needs_download": sum(1 for r in rows if r.get("shift_status") == "Needs download"),
        "low_battery": sum(
            1 for r in rows
            if r.get("battery_volts") is not None and volt_level(r["battery_volts"]) != "ok"
        ),
    }


def load_inventory() -> dict:
    return _store_data()
