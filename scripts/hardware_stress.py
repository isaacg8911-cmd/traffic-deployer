"""Hardware stress — GPS + PicoCount with live USB (Director plug-in).

Proves auto-detect stays fast with Bluetooth COMs present, GPS stream
survives pause/resume (counter connect pattern), and counter probe does
not hang on Bluetooth ports.

Logs: logs/hardware_stress/YYYY-MM-DD.jsonl
Exit 0 = no required scenario failed.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

LOG_DIR = os.path.join(ROOT, "logs", "hardware_stress")
AUTO_DETECT_BUDGET_S = 8.0
PROBE_BUDGET_S = 12.0
# TD_GPS_ONLY=1 — skip PicoCount probe (Director: GPS stress only)
GPS_ONLY = os.environ.get("TD_GPS_ONLY", "").strip() in ("1", "true", "yes")

FAILURES: list[str] = []
WARNS: list[str] = []
SCENARIOS: list[dict] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"  FAIL {msg}", flush=True)


def warn(msg: str) -> None:
    WARNS.append(msg)
    print(f"  WARN {msg}", flush=True)


def ok(msg: str, detail: str = "") -> None:
    print(f"  OK  {msg}" + (f" — {detail}" if detail else ""), flush=True)


def record(name: str, seconds: float, *, ok_flag: bool, detail: str = "") -> None:
    SCENARIOS.append({
        "name": name,
        "seconds": round(seconds, 3),
        "ok": ok_flag,
        "detail": detail,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    if ok_flag:
        ok(name, f"{seconds:.2f}s {detail}".strip())
    else:
        fail(f"{name}: {detail} ({seconds:.2f}s)")


def main() -> int:
    import gps_reader
    from core import picocount

    print(
        "HARDWARE STRESS — GPS only\n" if GPS_ONLY else "HARDWARE STRESS — GPS + PicoCount\n",
        flush=True,
    )

    ports = gps_reader.describe_ports()
    print(f"Ports ({len(ports)}):", flush=True)
    for p in ports:
        print(f"  {p['device']}: {p['description']}", flush=True)

    # ---- GPS auto-detect must stay fast (no Bluetooth hang)
    t0 = time.perf_counter()
    cands = gps_reader.candidate_gps_ports()
    elapsed = time.perf_counter() - t0
    bt_in = [p for p in cands if picocount.is_bluetooth_port(p)]
    record(
        "gps_candidates",
        elapsed,
        ok_flag=not bt_in and elapsed < 2.0,
        detail=f"ports={cands}" + (f" bluetooth={bt_in}" if bt_in else ""),
    )

    t0 = time.perf_counter()
    st = gps_reader.get_status(attempts=25)
    elapsed = time.perf_counter() - t0
    gps_ok = bool(st.get("connected") and st.get("fix") and st.get("port"))
    if elapsed > AUTO_DETECT_BUDGET_S:
        record("gps_auto_status", elapsed, ok_flag=False,
               detail=f"too slow (budget {AUTO_DETECT_BUDGET_S}s) {st}")
    elif not gps_ok:
        record("gps_auto_status", elapsed, ok_flag=False,
               detail=f"no fix — {st}")
    else:
        record(
            "gps_auto_status",
            elapsed,
            ok_flag=True,
            detail=f"{st['port']} lat={st['lat']:.5f} lon={st['lon']:.5f} sats={st.get('satellites')}",
        )

    # ---- GPSStream continuous + pause/resume (counter connect pattern)
    stream = gps_reader.GPSStream()
    t0 = time.perf_counter()
    stream.start()
    time.sleep(3.0)
    latest = stream.latest()
    stream_ok = bool(latest.get("fix") and latest.get("lat") is not None)
    record(
        "gps_stream_live",
        time.perf_counter() - t0,
        ok_flag=stream_ok,
        detail=str({k: latest.get(k) for k in ("port", "fix", "satellites", "lat", "lon")}),
    )

    t0 = time.perf_counter()
    stream.stop(join_timeout=3.5)
    stop_elapsed = time.perf_counter() - t0
    record("gps_pause_for_counter", stop_elapsed, ok_flag=stop_elapsed < 5.0,
           detail="stop join")

    # Pause window (same pattern as counter connect) then resume GPS
    if GPS_ONLY:
        time.sleep(0.5)
        record("counter_probe_auto", 0.0, ok_flag=True, detail="skipped (TD_GPS_ONLY=1)")
    else:
        t0 = time.perf_counter()
        labeled = picocount.counter_ports_labeled()
        bt_labeled = [d for d, _ in labeled if picocount.is_bluetooth_port(d)]
        probe = picocount.probe_port()
        probe_elapsed = time.perf_counter() - t0
        if bt_labeled:
            record("counter_ports_no_bluetooth", probe_elapsed, ok_flag=False,
                   detail=f"bluetooth still listed: {bt_labeled}")
        elif probe_elapsed > PROBE_BUDGET_S:
            record("counter_probe_auto", probe_elapsed, ok_flag=False,
                   detail=f"too slow — {probe.message}")
        elif probe.ok:
            record("counter_probe_auto", probe_elapsed, ok_flag=True,
                   detail=f"{probe.port} {probe.message}")
        else:
            # Required: probe must finish fast. Missing FTDI is WARN (hardware).
            record("counter_probe_auto", probe_elapsed, ok_flag=True,
                   detail=f"no counter ACK (hardware) — {probe.message}")
            warn(f"PicoCount not responding: {probe.message}")
            if not labeled:
                warn(
                    "No FTDI/counter COM — Device Manager shows Unknown COM10/COM11? "
                    "Run packaging\\FIX_USB.bat"
                )

    t0 = time.perf_counter()
    stream.start()
    time.sleep(2.5)
    resumed = stream.latest()
    resume_ok = bool(resumed.get("fix") and resumed.get("lat") is not None)
    record(
        "gps_resume_after_pause",
        time.perf_counter() - t0,
        ok_flag=resume_ok,
        detail=str({k: resumed.get(k) for k in ("port", "fix", "satellites", "lat", "lon")}),
    )
    stream.stop(join_timeout=3.5)

    # ---- Rapid get_status x5 (field-ready / header polls)
    latencies: list[float] = []
    for _ in range(5):
        s = time.perf_counter()
        gps_reader.get_status(attempts=15)
        latencies.append(time.perf_counter() - s)
    p95 = sorted(latencies)[int(0.95 * (len(latencies) - 1))]
    record(
        "gps_status_x5",
        sum(latencies),
        ok_flag=p95 <= AUTO_DETECT_BUDGET_S,
        detail=f"p95={p95:.2f}s samples={[round(x, 2) for x in latencies]}",
    )

    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, f"{datetime.now().strftime('%Y-%m-%d')}.jsonl")
    payload = {
        "failures": FAILURES,
        "warnings": WARNS,
        "scenarios": SCENARIOS,
        "passed": not FAILURES,
        "ports": ports,
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")

    print(f"\nLog: {log_path}", flush=True)
    print(f"{'PASS' if not FAILURES else 'FAIL'} — fails={len(FAILURES)} warns={len(WARNS)}", flush=True)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
