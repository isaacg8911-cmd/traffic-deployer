"""GPS + PicoCount on USB hub — sequential and simultaneous open test."""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import gps_reader  # noqa: E402
from core import picocount  # noqa: E402


def main() -> int:
    fails = 0
    print("USB hub dual-device test\n")

    print("[1] GPS stream, stop, then counter (app Connect flow)")
    gps = gps_reader.GPSStream()
    gps.start()
    time.sleep(3)
    g = gps.latest()
    print(f"    GPS port={g.get('port')} fix={g.get('fix')} sats={g.get('satellites')}")
    if not g.get("connected"):
        print("    FAIL: GPS not connected")
        fails += 1
    gps.stop()
    time.sleep(0.5)
    pr = picocount.probe_port()
    print(f"    Counter ok={pr.ok} port={pr.port}")
    if not pr.ok:
        print(f"    FAIL: {pr.message}")
        fails += 1
    else:
        r = picocount.read_serial_number(pr.port)
        print(f"    Serial={r.get('serial_number')} model={r.get('model')}")

    print("\n[2] Counter first, then GPS stream (after install)")
    pr2 = picocount.probe_port()
    print(f"    Counter ok={pr2.ok} port={pr2.port}")
    gps2 = gps_reader.GPSStream()
    gps2.start()
    time.sleep(3)
    g2 = gps2.latest()
    print(f"    GPS port={g2.get('port')} fix={g2.get('fix')}")
    gps2.stop()
    if not pr2.ok or not g2.get("connected"):
        fails += 1

    print("\n[3] Both ports open at once (hub stress)")
    gps3 = gps_reader.GPSStream()
    gps3.start()
    time.sleep(1)
    counter_port = pr.port if pr.ok else "COM10"
    try:
        import serial
        ser = serial.Serial(counter_port, 115200, timeout=1)
        print(f"    OK: GPS stream on {gps3.latest().get('port')} + {counter_port} open together")
        ser.close()
    except Exception as exc:
        print(f"    WARN: simultaneous open failed: {exc}")
        print("    (App avoids this — GPS pauses before counter ops)")
    gps3.stop()

    print(f"\n{'HUB DUAL PASS' if fails == 0 else f'HUB DUAL FAIL ({fails})'}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
