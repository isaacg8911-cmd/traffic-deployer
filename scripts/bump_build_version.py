"""Bump APP_VERSION patch before a complete AppUpdate / release build.

Every successful ship build gets a new number so the work-laptop title bar
proves progression (not a reused / false build).

Usage:
  python scripts/bump_build_version.py          # write version.py (patch +1)
  python scripts/bump_build_version.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_FILE = os.path.join(ROOT, "version.py")

_VERSION_RE = re.compile(
    r'^(APP_VERSION\s*=\s*")([^"]+)("\s*)$',
    re.MULTILINE,
)
_STAMP_RE = re.compile(
    r'^(APP_BUILD_STAMP\s*=\s*")([^"]*)("\s*)$',
    re.MULTILINE,
)


def parse_version(v: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in (v or "0").strip().split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts) if parts else (0,)


def bump_patch(v: str) -> str:
    parts = list(parse_version(v))
    while len(parts) < 3:
        parts.append(0)
    parts[-1] += 1
    return ".".join(str(p) for p in parts)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def bump_file(*, dry_run: bool = False) -> tuple[str, str]:
    if not os.path.isfile(VERSION_FILE):
        raise FileNotFoundError(f"missing {VERSION_FILE}")
    text = open(VERSION_FILE, encoding="utf-8").read()
    m = _VERSION_RE.search(text)
    if not m:
        raise ValueError("APP_VERSION not found in version.py")
    old = m.group(2)
    new = bump_patch(old)
    stamp = utc_stamp()
    text2 = _VERSION_RE.sub(rf"\g<1>{new}\g<3>", text, count=1)
    if _STAMP_RE.search(text2):
        text2 = _STAMP_RE.sub(rf"\g<1>{stamp}\g<3>", text2, count=1)
    else:
        lines = text2.splitlines(keepends=True)
        out: list[str] = []
        inserted = False
        for line in lines:
            out.append(line)
            if (not inserted) and line.lstrip().startswith("APP_VERSION"):
                ending = "\n" if line.endswith("\n") else ("\r\n" if line.endswith("\r\n") else "\n")
                out.append(f'APP_BUILD_STAMP = "{stamp}"{ending}')
                inserted = True
        text2 = "".join(out)
        if not inserted:
            text2 += f'\nAPP_BUILD_STAMP = "{stamp}"\n'
    if not dry_run:
        tmp = VERSION_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text2)
            if not text2.endswith("\n"):
                f.write("\n")
        os.replace(tmp, VERSION_FILE)
    return old, new


def main() -> int:
    ap = argparse.ArgumentParser(description="Bump APP_VERSION patch for release builds")
    ap.add_argument("--dry-run", action="store_true", help="Print only; do not write")
    args = ap.parse_args()
    try:
        old, new = bump_file(dry_run=args.dry_run)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    mode = "dry-run" if args.dry_run else "wrote"
    print(f"VERSION BUMP ({mode}): {old} -> {new}")
    print(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
