"""Mobile app check — run user + stress, then emit an improvement audit.

Mirrors scripts/app_check.py for the mobile lane. Produces:
  logs/mobile_check/latest.json
  logs/mobile_check/latest.md   (Strengths / Weaknesses / Improvements)

Usage:
  .venv\\Scripts\\python.exe scripts\\mobile_app_check.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_DIR = os.path.join(ROOT, "logs", "mobile_check")
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
if not os.path.isfile(PY):
    PY = sys.executable

STEPS = [
    ("user_prove", "scripts/mobile_user_prove.py"),
    ("stress_loop", "scripts/mobile_stress_loop.py"),
]

# Known improvement backlog — surfaced every run so they are not forgotten.
KNOWN_IMPROVEMENTS = [
    "Phone geolocation needs HTTPS over LAN (works on localhost); host behind TLS for field use",
    "No real multi-user auth yet — job token only (phase 2)",
    "Offline field mode not implemented — online-first; brief drops not yet queued in IndexedDB",
    "Server-side road graph optional — without it, routes are straight-line, not street-traced",
    "No undo on mobile install/skip (desktop has undo)",
    "Browser/device E2E (Playwright) not wired — current proof is in-process API simulation",
]


def _run(name: str, script: str) -> dict:
    path = os.path.join(ROOT, script)
    t0 = time.perf_counter()
    try:
        proc = subprocess.run([PY, path], cwd=ROOT, capture_output=True, text=True, timeout=600)
        out = (proc.stdout or "") + (proc.stderr or "")
        tail = out.encode("ascii", "replace").decode("ascii")[-2500:]
        return {"name": name, "ok": proc.returncode == 0,
                "seconds": round(time.perf_counter() - t0, 1), "tail": tail}
    except subprocess.TimeoutExpired:
        return {"name": name, "ok": False, "seconds": 600.0, "tail": "TIMEOUT"}


def _load(path: str) -> dict | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _audit(results: list[dict]) -> dict:
    strengths: list[str] = []
    weaknesses: list[str] = []
    improvements: list[str] = list(KNOWN_IMPROVEMENTS)
    by = {r["name"]: r for r in results}

    up = _load(os.path.join(REPORT_DIR, "proofs", "user_prove.json"))
    if by.get("user_prove", {}).get("ok") and up:
        strengths.append(
            f"User flow: {up['passed']}/{up['total']} checks pass "
            "(import, route, phone GPS grab, pin fallback, install, pickup, export, error paths)"
        )
        strengths.append("Job token enforced; out-of-bounds GPS and bad uploads rejected with clear errors")
    elif up and up.get("failed"):
        weaknesses.append("User test failures: " + ", ".join(up["failed"]))
    elif not by.get("user_prove", {}).get("ok"):
        weaknesses.append("User test did not pass — see logs/mobile_check tail")

    # Latency + load signal from the freshest stress log line.
    stress = _latest_stress()
    if by.get("stress_loop", {}).get("ok") and stress:
        for sc in stress.get("scenarios", []):
            m = sc.get("metrics", {})
            if sc["name"] == "rapid_map_state":
                strengths.append(
                    f"Map-state latency p50={m.get('p50_ms')}ms p95={m.get('p95_ms')}ms "
                    f"(budget {m.get('budget_ms')}ms)"
                )
                if m.get("p95_ms", 0) > 0.6 * m.get("budget_ms", 1):
                    improvements.append("Map-state p95 approaching budget — consider ETag/diff payloads")
            if sc["name"] == "install_cycle" and sc["ok"]:
                strengths.append(f"Full install cycle clean over {m.get('stops')} stops")
            if sc["name"] == "concurrent_writes" and sc["ok"]:
                strengths.append("Concurrent grab+patch on one stop: no lost writes, job intact")
            if sc["name"] == "large_job_80":
                improvements.append(
                    f"80-stop job: map-state {m.get('map_state_kb')}KB, edit p95 {m.get('edit_p95_ms')}ms "
                    "— add list virtualization/search if payload grows; background heavy route builds"
                )
        if stress.get("failed_required"):
            weaknesses.append("Stress failures: " + ", ".join(stress["failed_required"]))
    elif not by.get("stress_loop", {}).get("ok"):
        weaknesses.append("Stress loop did not pass — see logs/mobile_stress")

    if not weaknesses:
        weaknesses.append("(none blocking) — see improvements for next-step polish")

    return {"strengths": strengths, "weaknesses": weaknesses, "improvements": improvements}


def _latest_stress() -> dict | None:
    d = os.path.join(ROOT, "logs", "mobile_stress")
    if not os.path.isdir(d):
        return None
    files = sorted(f for f in os.listdir(d) if f.endswith(".jsonl"))
    if not files:
        return None
    path = os.path.join(d, files[-1])
    last = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                last = line
    return json.loads(last) if last else None


def _write_md(report: dict, path: str) -> None:
    a = report["audit"]
    lines = [
        "# Mobile app check",
        "",
        f"- When: {report['when']}",
        f"- Result: {'PASS' if report['pass'] else 'FAIL'}",
        f"- Duration: {report['seconds']}s",
        "",
        "## Steps",
        "",
    ]
    for r in report["results"]:
        lines.append(f"- [{'OK' if r['ok'] else 'FAIL'}] `{r['name']}` — {r['seconds']}s")
    for title, key in (("Strengths", "strengths"), ("Weaknesses", "weaknesses"),
                       ("Improvements / next steps", "improvements")):
        lines += ["", f"## {title}", ""]
        for item in a.get(key) or ["(none)"]:
            lines.append(f"- {item}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    os.makedirs(REPORT_DIR, exist_ok=True)
    print(f"MOBILE APP CHECK — {ROOT}\n")
    t0 = time.perf_counter()
    results = []
    for name, script in STEPS:
        print(f"=== {name} ({script}) ===")
        results.append(_run(name, script))
    audit = _audit(results)
    report = {
        "when": datetime.now(timezone.utc).isoformat(),
        "pass": all(r["ok"] for r in results),
        "seconds": round(time.perf_counter() - t0, 1),
        "results": results,
        "audit": audit,
    }
    with open(os.path.join(REPORT_DIR, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    _write_md(report, os.path.join(REPORT_DIR, "latest.md"))

    print("\n--- AUDIT ---")
    print("Strengths:")
    for s in audit["strengths"]:
        print("  +", s)
    print("Weaknesses:")
    for w in audit["weaknesses"]:
        print("  -", w)
    print("Improvements:")
    for i in audit["improvements"]:
        print("  >", i)
    print(f"\nReport: logs/mobile_check/latest.md   ({'PASS' if report['pass'] else 'FAIL'})")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
