"""Bug ledger + pre-ship review record.

Every bug found and not fixed lives in qa/bug_ledger.json. The app update gate
refuses to ship while a field-critical bug is open (unless Director waived it)
or while the review record is older than the shipped source.

  python scripts/qa_ledger.py check            # gate: exit 1 on block
  python scripts/qa_ledger.py next             # ranked open bugs
  python scripts/qa_ledger.py report           # markdown for [Cursor Log]
  python scripts/qa_ledger.py record-review --since 1.0.19 --summary "..."
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QA_DIR = os.path.join(ROOT, "qa")
LEDGER = os.path.join(QA_DIR, "bug_ledger.json")
REVIEW = os.path.join(QA_DIR, "review_record.json")

SEVERITY_RANK = {"field-critical": 0, "major": 1, "minor": 2}
SOURCE_DIRS = ("core", "ui", "web")
SOURCE_EXT = (".py", ".js", ".html", ".css")
SKIP_PARTS = ("__pycache__", "vendor")


def source_files() -> list[str]:
    """Everything that ends up in the shipped exe or web folder."""
    out: list[str] = []
    for name in os.listdir(ROOT):
        if name.endswith(".py") and os.path.isfile(os.path.join(ROOT, name)):
            out.append(name)
    for top in SOURCE_DIRS:
        for dirpath, dirnames, files in os.walk(os.path.join(ROOT, top)):
            dirnames[:] = [d for d in dirnames if d not in SKIP_PARTS]
            for f in files:
                if f.endswith(SOURCE_EXT):
                    out.append(os.path.relpath(os.path.join(dirpath, f), ROOT))
    return sorted(p.replace("\\", "/") for p in out)


def source_fingerprint() -> str:
    h = hashlib.sha256()
    for rel in source_files():
        h.update(rel.encode("utf-8"))
        with open(os.path.join(ROOT, rel), "rb") as f:
            h.update(f.read().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def _load(path: str, default: dict) -> dict:
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_ledger() -> dict:
    return _load(LEDGER, {"bugs": []})


def open_bugs(ledger: dict | None = None) -> list[dict]:
    bugs = (ledger or load_ledger()).get("bugs", [])
    live = [b for b in bugs if b.get("status") == "open"]
    return sorted(live, key=lambda b: (SEVERITY_RANK.get(b.get("severity"), 9), b.get("rank", 999)))


def blockers(ledger: dict | None = None) -> list[str]:
    """Reasons the gate must refuse to ship. Empty list = clear."""
    ledger = ledger if ledger is not None else load_ledger()
    out: list[str] = []
    if not os.path.isfile(LEDGER):
        out.append("qa/bug_ledger.json missing")
    for b in open_bugs(ledger):
        if b.get("severity") == "field-critical" and not b.get("director_waiver"):
            out.append(f"open field-critical bug {b['id']}: {b['title']}")
    review = _load(REVIEW, {})
    if not review:
        out.append("no pre-ship review on record (qa/review_record.json)")
    elif review.get("source_fingerprint") != source_fingerprint():
        out.append(
            "code changed since the last review "
            f"({review.get('reviewed_at', '?')}); review the changes, log findings, "
            "then run qa_ledger.py record-review")
    return out


def next_up_lines(limit: int = 10) -> list[str]:
    lines = []
    for i, b in enumerate(open_bugs()[:limit], 1):
        waived = " (Director waived)" if b.get("director_waiver") else ""
        lines.append(f"{i}. [{b['severity']}] {b['id']}: {b['title']}{waived}")
    return lines


def cmd_check() -> int:
    blk = blockers()
    print("[bug ledger + review]")
    if blk:
        for b in blk:
            print(f"  FAIL {b}")
    else:
        print("  OK  review is current and no open field-critical bugs")
    nxt = next_up_lines()
    if nxt:
        print("\nNext up (open bugs, most serious first):")
        for ln in nxt:
            print(f"  {ln}")
    return 1 if blk else 0


def cmd_next() -> int:
    nxt = next_up_lines(limit=100)
    print("\n".join(nxt) if nxt else "No open bugs.")
    return 0


def cmd_report() -> int:
    bugs = open_bugs()
    crit = sum(1 for b in bugs if b.get("severity") == "field-critical")
    review = _load(REVIEW, {})
    current = review.get("source_fingerprint") == source_fingerprint()
    print(f"**Open bugs:** {len(bugs)} ({crit} field-critical). "
          f"Review {'current' if current else 'STALE'} "
          f"({review.get('reviewed_at', 'none')}).")
    for ln in next_up_lines():
        print(f"- {ln}")
    return 0


def cmd_record_review(since: str, summary: str) -> int:
    os.makedirs(QA_DIR, exist_ok=True)
    rec = {
        "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "since_version": since,
        "summary": summary,
        "source_fingerprint": source_fingerprint(),
        "open_bugs": len(open_bugs()),
    }
    with open(REVIEW, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2)
        f.write("\n")
    print(f"Review recorded for current source ({rec['open_bugs']} open bugs in ledger).")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sub.add_parser("next")
    sub.add_parser("report")
    rr = sub.add_parser("record-review")
    rr.add_argument("--since", required=True, help="last shipped version the review covers from")
    rr.add_argument("--summary", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "check":
        return cmd_check()
    if args.cmd == "next":
        return cmd_next()
    if args.cmd == "report":
        return cmd_report()
    return cmd_record_review(args.since, args.summary)


if __name__ == "__main__":
    sys.exit(main())
