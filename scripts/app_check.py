"""Universal app check — headless + user-input proofs with audit report.

Tiers (use --tier):
  smoke     — routing/core/persistence only (fast)
  headless  — PROVE.bat chain without GUI
  user      — real Qt + map user simulations (where applicable)
  full      — headless then user (default for ship / UI changes)

Artifacts: logs/app_check/latest.json + latest.md
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_DIR = os.path.join(ROOT, "logs", "app_check")
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
if not os.path.isfile(PY):
    PY = sys.executable

HEADLESS_STEPS = [
    ("smoke_full", "smoke_full.py", True),
    ("demo_workflow", "demo_workflow.py", True),
    ("quick_preflight", "quick_preflight.py", True),
    ("golden_routes", "golden_routes.py", True),
    ("benchmark_route", "benchmark_route.py", True),
    ("picocount_sandbox", "picocount_sandbox.py", False),
]

USER_STEPS = [
    ("drop_pin_enter", "prove_drop_pin_enter.py", True),
    ("manual_grab_site", "prove_manual_grab_15228.py", True),
    ("install_no_block", "prove_install_no_block.py", True),
    ("install_drop_pin_desk", "test_install_drop_pin.py", True),
    ("map_bridge", "verify_manual_grab_map.py", True),
    ("ui_wiring", "test_ui_wiring.py", True),
    ("demo_workflow", "demo_workflow.py", True),
    ("field_sim", "test_field_sim.py", True),
]

PROOF_ARTIFACTS = {
    "drop_pin_enter": os.path.join(ROOT, "logs", "manual_grab_proof", "drop_pin_enter_proof.json"),
    "manual_grab_site": os.path.join(ROOT, "logs", "manual_grab_proof", "15228_proof.json"),
    "install_no_block": os.path.join(ROOT, "logs", "manual_grab_proof", "install_no_block_proof.json"),
}

COVERAGE_GAPS = [
    "Route pick dialog drag/reorder — static wiring only, no live GUI reorder proof",
    "Pickup tab end-of-shift flow — field_sim covers export, not full pickup UI",
    "FOLLOW GPS / compass while driving — wiring audit only",
    "Offline tile render — preflight checks files, not WebGL frame",
    "PicoCount USB — optional picocount_sandbox; hardware Isaac-only",
    "Multi-day map filter (Map on screen) — not exercised in user proofs",
]


def _run_step(name: str, script: str, *, timeout: int) -> dict:
    path = os.path.join(ROOT, "scripts", script)
    t0 = time.monotonic()
    proc = subprocess.run(
        [PY, path],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    elapsed = round(time.monotonic() - t0, 1)
    out = (proc.stdout or "") + (proc.stderr or "")
    safe = out.encode("ascii", errors="replace").decode("ascii")
    tail = safe[-2500:] if len(safe) > 2500 else safe
    return {
        "name": name,
        "script": script,
        "exit": proc.returncode,
        "seconds": elapsed,
        "ok": proc.returncode == 0,
        "output_tail": tail,
    }


def _load_proof(path: str) -> dict | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _audit_from_results(results: list[dict]) -> dict:
    strengths: list[str] = []
    weaknesses: list[str] = []
    improvements: list[str] = []

    by_name = {r["name"]: r for r in results}

    if by_name.get("drop_pin_enter", {}).get("ok"):
        proof = _load_proof(PROOF_ARTIFACTS["drop_pin_enter"]) or {}
        checks = proof.get("checks") or {}
        if checks.get("no_corner_pin") and checks.get("zoom_works"):
            strengths.append("Drop pin enter: map stays responsive; no corner pin before click")
        after = next(
            (s.get("detail") for s in proof.get("steps", []) if s.get("step") == "after_enter"),
            {},
        )
        if isinstance(after, dict) and after.get("markerCount", 0) > 0:
            weaknesses.append(
                "Drop pin enter: stale map marker may remain visible before click "
                f"(markerCount={after.get('markerCount')}) — cosmetic, not blocking"
            )
            improvements.append("Clear non-field markers when entering manual grab / drop pin mode")
    elif "drop_pin_enter" in by_name:
        weaknesses.append("Drop pin enter proof failed — map freeze or corner-pin regression likely")

    if by_name.get("manual_grab_site", {}).get("ok"):
        strengths.append("Manual grab site 15228: bridge click saves segment midpoint + screenshot artifact")
    elif "manual_grab_site" in by_name:
        weaknesses.append("Manual grab midpoint proof failed — field GPS save path broken")

    if by_name.get("install_no_block", {}).get("ok"):
        strengths.append("INSTALL advisory checklist: site can install without GPS pin or counter clear")
    elif "install_no_block" in by_name:
        weaknesses.append("Install-without-GPS proof failed — field blocker may have returned")

    if by_name.get("install_drop_pin_desk", {}).get("ok"):
        strengths.append("Drop pin + offline geocode + install commit covered in desk simulation")

    if by_name.get("map_bridge", {}).get("ok"):
        strengths.append("Map bridge: tdmap URL parse, AppWebPage handler, fireMapClick bridge-first wiring")

    if by_name.get("ui_wiring", {}).get("ok"):
        strengths.append("UI wiring audit: 52+ click targets connected to handlers")

    if by_name.get("field_sim", {}).get("ok"):
        strengths.append("Field sim: bundled job ingest → route → install → audit export pipeline")

    if by_name.get("smoke_full", {}).get("ok"):
        strengths.append("Headless smoke: imports, persistence, routing graph, web assets")

    failed = [r["name"] for r in results if not r.get("ok") and r.get("required", True)]
    optional_failed = [r["name"] for r in results if not r.get("ok") and not r.get("required", True)]

    if optional_failed:
        improvements.append(
            f"Optional steps failed ({', '.join(optional_failed)}) — OK if counter unplugged"
        )

    for gap in COVERAGE_GAPS:
        improvements.append(f"Coverage gap: {gap}")

    if not failed:
        improvements.append("Re-run USER_PROVE.bat after any Install/Route/Map UI change before ship")

    return {
        "strengths": strengths,
        "weaknesses": weaknesses,
        "improvements": improvements,
        "failed_required": failed,
        "failed_optional": optional_failed,
    }


def _write_markdown(report: dict, path: str) -> None:
    audit = report.get("audit") or {}
    lines = [
        f"# App check — {report.get('tier', '?')}",
        "",
        f"- **When:** {report.get('timestamp', '')}",
        f"- **Result:** {'PASS' if report.get('pass') else 'FAIL'}",
        f"- **Duration:** {report.get('seconds', 0)}s",
        "",
        "## Steps",
        "",
    ]
    for r in report.get("results", []):
        mark = "OK" if r.get("ok") else ("WARN" if not r.get("required", True) else "FAIL")
        req = "" if r.get("required", True) else " (optional)"
        lines.append(f"- [{mark}] `{r['name']}` — {r.get('seconds', 0)}s{req}")
    lines.extend(["", "## Strengths", ""])
    for s in audit.get("strengths") or ["(none recorded)"]:
        lines.append(f"- {s}")
    lines.extend(["", "## Weaknesses", ""])
    for w in audit.get("weaknesses") or ["(none)"]:
        lines.append(f"- {w}")
    lines.extend(["", "## Improvements / gaps", ""])
    for i in audit.get("improvements") or []:
        lines.append(f"- {i}")
    if audit.get("failed_required"):
        lines.extend(["", "## Failed (required)", ""])
        for f in audit["failed_required"]:
            lines.append(f"- {f}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _steps_for_tier(tier: str) -> list[tuple[str, str, bool]]:
    if tier == "smoke":
        return [HEADLESS_STEPS[0]]
    if tier == "headless":
        return HEADLESS_STEPS
    if tier == "user":
        return USER_STEPS
    if tier == "full":
        # demo_workflow runs in both chains — run once in headless portion
        user = [s for s in USER_STEPS if s[0] != "demo_workflow"]
        return HEADLESS_STEPS + user
    raise ValueError(f"unknown tier: {tier}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Universal Traffic Deployer app check")
    parser.add_argument(
        "--tier",
        choices=("smoke", "headless", "user", "full"),
        default="full",
        help="smoke=fast; headless=PROVE; user=GUI paths; full=both (ship)",
    )
    parser.add_argument("--timeout", type=int, default=300, help="per-step timeout seconds")
    args = parser.parse_args()

    os.makedirs(REPORT_DIR, exist_ok=True)
    steps = _steps_for_tier(args.tier)
    print(f"APP CHECK tier={args.tier} — {ROOT}\n")

    t0 = time.monotonic()
    results: list[dict] = []
    for name, script, required in steps:
        print(f"=== [{args.tier}] {name} ({script}) ===")
        try:
            row = _run_step(name, script, timeout=args.timeout)
        except subprocess.TimeoutExpired:
            row = {
                "name": name,
                "script": script,
                "exit": -1,
                "seconds": args.timeout,
                "ok": False,
                "output_tail": f"TIMEOUT after {args.timeout}s",
            }
        row["required"] = required
        results.append(row)
        mark = "OK" if row["ok"] else ("WARN" if not required else "FAIL")
        print(row["output_tail"][-1200:] if row.get("output_tail") else "")
        print(f"{mark} {name} ({row['seconds']}s)\n")

    audit = _audit_from_results(results)
    required_fail = [r for r in results if not r["ok"] and r["required"]]
    passed = not required_fail
    report = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tier": args.tier,
        "pass": passed,
        "seconds": round(time.monotonic() - t0, 1),
        "results": results,
        "audit": audit,
    }
    json_path = os.path.join(REPORT_DIR, "latest.json")
    md_path = os.path.join(REPORT_DIR, "latest.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    _write_markdown(report, md_path)

    if passed:
        print("APP CHECK PASS")
    else:
        print("APP CHECK FAIL:")
        for r in required_fail:
            print(f"  - {r['name']} exit {r['exit']}")
    print(f"  report  {json_path}")
    print(f"  audit   {md_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
