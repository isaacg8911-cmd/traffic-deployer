"""Extract PicoCount compressed hose hits from TrafficViewer Pro .tvp files.

Thin CLI over core.picocount_hits — prefer scripts/volume_report.py for volume CSV.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

from core import picocount_hits  # noqa: E402


def bin_hourly(hits: list[dict], start: datetime, cutoff: datetime) -> list[dict]:
    buckets: dict[datetime, dict[str, int]] = {}
    for h in hits:
        if h["channel"] not in ("A", "B"):
            continue
        ts = start + timedelta(seconds=h["seconds"])
        if ts < start or ts > cutoff:
            continue
        hour = ts.replace(minute=0, second=0, microsecond=0)
        buckets.setdefault(hour, {"A": 0, "B": 0, "total_hits": 0})
        buckets[hour][h["channel"]] += 1
        buckets[hour]["total_hits"] += 1
    return [
        {
            "hour_start": hour.isoformat(sep=" "),
            "channel_a_hits": b["A"],
            "channel_b_hits": b["B"],
            "total_hits": b["total_hits"],
            "approx_vehicles_half": b["total_hits"] // 2,
        }
        for hour in sorted(buckets)
        for b in [buckets[hour]]
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract hose hits from .tvp / .pcbin")
    ap.add_argument("tvp", type=Path)
    ap.add_argument("--cutoff", default="2026-06-13 07:00:00")
    ap.add_argument("--out-dir", type=Path, default=None)
    args = ap.parse_args()

    parsed = picocount_hits.parse_hits(str(args.tvp))
    if not parsed.get("ok"):
        raise SystemExit(parsed.get("error", "parse failed"))

    cutoff = datetime.strptime(args.cutoff, "%Y-%m-%d %H:%M:%S")
    start = parsed["study_start"]
    hits = parsed["hits"]
    off = parsed["stream_offset"]
    downloaded = parsed.get("downloaded_at")

    kept = [
        h
        for h in hits
        if start + timedelta(seconds=h["seconds"]) <= cutoff
    ]

    out_dir = args.out_dir or args.tvp.parent
    stem = args.tvp.stem
    hits_csv = out_dir / f"{stem}_hose_hits_to_{cutoff.strftime('%Y%m%d_%H%M')}.csv"
    hourly_csv = out_dir / f"{stem}_hourly_volume_to_{cutoff.strftime('%Y%m%d_%H%M')}.csv"
    summary_txt = out_dir / f"{stem}_extract_summary.txt"

    with hits_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["datetime", "channel", "seconds_since_start", "ticks"],
        )
        w.writeheader()
        for h in kept:
            ts = start + timedelta(seconds=h["seconds"])
            w.writerow(
                {
                    "datetime": ts.isoformat(sep=" "),
                    "channel": h["channel"],
                    "seconds_since_start": round(h["seconds"], 6),
                    "ticks": h["ticks"],
                }
            )

    hourly = bin_hourly(hits, start, cutoff)
    with hourly_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(hourly[0].keys()) if hourly else [])
        if hourly:
            w.writeheader()
            w.writerows(hourly)

    duration = kept[-1]["seconds"] - kept[0]["seconds"] if len(kept) > 1 else 0
    summary = f"""TVP extract: {args.tvp.name}
Stream offset: {off}
Study start: {start}
Cutoff: {cutoff}
File downloaded/saved (~): {downloaded}
Total hose hits parsed: {len(hits)}
Hits on/before cutoff: {len(kept)}
Study span (kept): {duration / 86400:.2f} days
Outputs:
  {hits_csv}
  {hourly_csv}
"""
    summary_txt.write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
