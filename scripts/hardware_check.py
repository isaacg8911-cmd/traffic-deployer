"""Quick GPS + PicoCount hardware check before a field day.

Usage:
  .venv\\Scripts\\python.exe scripts\\hardware_check.py
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import picocount  # noqa: E402
from core import hardware_profile  # noqa: E402
import gps_reader  # noqa: E402


def main() -> int:
    print("Traffic Deployer hardware check\n")
    hw = hardware_profile.detect_hardware()
    ram = f"{hw.ram_gb:.1f} GB" if hw.ram_gb is not None else "unknown"
    print(f"[System] RAM {ram} — work-laptop mode={'yes' if hw.work_laptop else 'no'} ({hw.reason})")
    fails = 0

    print("[GPS]")
    ports = gps_reader.describe_ports()
    for p in ports:
        tag = "GPS" if picocount.is_gps_port(p["device"]) else (
            "counter" if picocount.is_counter_port(p["device"]) else "other")
        print(f"  {p['device']}: {p['description']} ({tag})")
    info = gps_reader.diagnose(wait_s=8.0)
    stream = info.get("stream") or {}
    if info.get("fix"):
        f = info["fix"]
        print(f"  FIX OK on {stream.get('port')} — {f['lat']:.5f}, {f['lon']:.5f}")
    elif stream.get("connected"):
        print(
            f"  Connected on {stream.get('port')} — no fix yet "
            f"({stream.get('satellites', 0)} sats). Move to open sky.")
    else:
        print("  No GPS detected — plug BU-353N before launch.")
        fails += 1

    print("\n[PicoCount]")
    cports = picocount.list_serial_ports()
    print(" ", cports or "(none)")
    pr = picocount.probe_port()
    print(f"  probe ok={pr.ok} port={pr.port}")
    print(f"  {pr.message}")
    if not pr.ok:
        fails += 1
        if "busy" in pr.message.lower() or "denied" in pr.message.lower():
            print(
                "\n  Tip: close Traffic Deployer / other serial apps, "
                "unplug counter USB, wait 3s, replug, retry.")

    print(f"\n{'HARDWARE PASS' if fails == 0 else f'HARDWARE FAIL ({fails})'}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
