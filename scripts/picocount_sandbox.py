"""PicoCount 2500 sandbox — read-only by default; optional download to temp.

Usage (from repo root, venv):
  .venv\\Scripts\\python.exe scripts\\picocount_sandbox.py
  .venv\\Scripts\\python.exe scripts\\picocount_sandbox.py --port COM10
  .venv\\Scripts\\python.exe scripts\\picocount_sandbox.py --download
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

from core import picocount  # noqa: E402


def _section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    ap = argparse.ArgumentParser(description="PicoCount sandbox (safe reads)")
    ap.add_argument("--port", default=None, help="COM port (default: auto)")
    ap.add_argument(
        "--download",
        action="store_true",
        help="Download study to temp (does not clear counter)",
    )
    args = ap.parse_args()

    _section("Ports")
    ports = picocount.list_serial_ports()
    print(" ", ports or "(none)")

    _section("Probe")
    pr = picocount.probe_port(args.port)
    print(f"  ok={pr.ok} port={pr.port}")
    print(f"  {pr.message}")
    if not pr.ok or not pr.port:
        return 1

    port = pr.port
    from core.picocount import PicoCountClient, build_unit_id  # noqa: E402

    _section("Device info (]C ]V ]S ]I ]G ]M)")
    try:
        with PicoCountClient(port) as client:
            if not client.comm_check():
                print("  FAIL: no ACK on ]C")
                return 1
            model, fw = client.read_model_firmware()
            serial_no = client.read_serial_slow()
            unit_id = client.read_unit_id()
            volts = client.read_battery()
            mem = client.memory_info()
            print(f"  model={model!r} firmware={fw!r}")
            print(f"  serial={serial_no!r} unit_id={unit_id!r} battery={volts} V")
            print(f"  memory={json.dumps(mem, indent=2) if mem else None}")
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return 1

    _section("Unit ID builder (no write)")
    for site, direc in ((1234, "n"), (5678, "e"), (999, "s")):
        uid = build_unit_id(site, direc)
        print(f"  site={site} dir={direc} -> {uid}")

    if args.download:
        _section("Download study (read-only)")
        dest = os.path.join(
            tempfile.gettempdir(),
            "traffic_deployer_sandbox",
            f"sandbox_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pcbin",
        )
        res = picocount.download_study(dest, port=port, meta={"sandbox": True})
        print(json.dumps({k: res.get(k) for k in ("ok", "error", "path", "bytes", "port")}, indent=2))
        if not res.get("ok"):
            return 1
        print(f"  saved: {res.get('path')}")
    else:
        print("\n(skip download; pass --download to pull study to temp)")

    _section("PASS")
    print(f"  Counter on {port} — sandbox complete (no clear/configure).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
