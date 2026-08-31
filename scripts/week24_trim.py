"""Week 24 data trim: Day 1 through Sat 2026-08-29 09:00; Day 2 window 8/25-8/28.

Writes original filenames into C:\\Users\\isaac\\Downloads\\WEEK 24 1.
Does not modify source files. TVP rewrite uses the proven method:
patch stream length, patch PicoCount clocks, truncate (never zero-pad).
"""
from __future__ import annotations

import csv
import re
import shutil
import struct
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from core import picocount_hits  # noqa: E402

SRC = Path(r"C:\Users\isaac\Downloads\week 24 ig (2)\week 24 ig")
OUT = Path(r"C:\Users\isaac\Downloads\WEEK 24 1")
REPORT = OUT / "WEEK24_TRIM_SUMMARY.txt"

DAY1_CUTOFF = datetime(2026, 8, 29, 9, 0, 0)
DAY2_START_DATE = date(2026, 8, 25)
DAY2_END_DATE = date(2026, 8, 28)
EXCEL_BASE = datetime(1899, 12, 30)
MAGIC = b"TrafficViewerPro.Data"

DAY1_SITES = {
    "3836", "3858", "3964", "3988", "4033", "4047", "4110", "4119", "4173", "4196",
}
DAY2_SITES = {
    "10912", "10913", "10951", "10968", "10974", "10975", "11022", "11030",
    "11042", "11053", "11059", "11073", "11086", "11100", "11120", "11132",
    "11909", "10909",
}
DAY1_SERIAL_PREFIXES = (
    "001712", "002036", "002049", "002307", "002313", "002442", "002534",
    "002595", "002798", "002803", "003001", "003007", "200205", "200975",
)
DAY2_CSV_SITES = {
    "10892", "10897", "10942", "10961", "11026", "11057", "11087",
}


def site_of(name: str) -> str:
    m = re.match(r"(\d+)", name)
    return m.group(1) if m else ""


def locate_stream(data: bytes) -> tuple[int, list[dict], int]:
    """Return (offset, hits_with_offsets, stream_end). Prefers 26642 then marker walk."""
    def try_off(off: int) -> tuple[list[dict], int] | None:
        if off < 0 or off >= len(data) - 8:
            return None
        hits, consumed = walk_hits(data, off)
        if hits and consumed and len(hits) >= 50:
            return hits, consumed
        return None

    for cand in (26642,):
        got = try_off(cand)
        if got:
            return cand, got[0], cand + got[1]

    marker = data.find(b"Multi-Unit - 7 Axles or More")
    start = (marker + 64) if marker >= 0 else 0
    best_off, best_hits, best_cons = 0, [], 0
    off = start
    n = len(data)
    while off < n - 8:
        hits, consumed = walk_hits(data, off)
        if hits and consumed and len(hits) >= 50:
            if len(hits) > len(best_hits):
                best_off, best_hits, best_cons = off, hits, consumed
            off += consumed
        else:
            off += 1
    if not best_hits:
        raise ValueError("no hose-hit stream found")
    return best_off, best_hits, best_off + best_cons


def walk_hits(data: bytes, start: int) -> tuple[list[dict], int]:
    tick = bytearray(6)
    hits: list[dict] = []
    i = start
    n = len(data)
    while i < n:
        hit_off = i
        info = data[i]
        i += 1
        ch = info & 0x0F
        n_high = info >> 4
        if n_high < 9 or n_high > 14:
            break
        nbytes = n_high - 8
        if i + nbytes > n:
            break
        for b in range(nbytes):
            tick[b] = data[i + b]
        i += nbytes
        ticks = int.from_bytes(tick, "little")
        hits.append(
            {
                "channel": picocount_hits.CHANNEL.get(ch, f"CH{ch}"),
                "seconds": ticks / picocount_hits.TICKS_PER_SEC,
                "offset": hit_off,
                "end": i,
            }
        )
    consumed = (hits[-1]["end"] - start) if hits else 0
    return hits, consumed


def is_pc_clock(buf: bytes, off: int) -> datetime | None:
    cs, sec, minute, hour, day, mon_b, ylo, yhi = buf[off : off + 8]
    year = ylo | (yhi << 8)
    month = mon_b if 1 <= mon_b <= 12 else mon_b + 1
    if not (
        2020 <= year <= 2035
        and 1 <= day <= 31
        and hour <= 23
        and minute <= 59
        and sec <= 59
        and cs <= 127
        and 1 <= month <= 12
    ):
        return None
    try:
        return datetime(year, month, day, hour, minute, sec)
    except ValueError:
        return None


def pc_clocks(buf: bytes) -> list[tuple[int, datetime, bytes]]:
    out = []
    off = 0
    while off <= len(buf) - 8:
        dt = is_pc_clock(buf, off)
        if dt:
            out.append((off, dt, bytes(buf[off : off + 8])))
            off += 8
        else:
            off += 1
    return out


def pack_pc(old8: bytes, new_dt: datetime) -> bytes:
    cs = old8[0]
    new_mon = new_dt.month if 1 <= old8[5] <= 12 else new_dt.month - 1
    year = new_dt.year
    return bytes(
        [
            cs,
            new_dt.second,
            new_dt.minute,
            new_dt.hour,
            new_dt.day,
            new_mon,
            year & 0xFF,
            (year >> 8) & 0xFF,
        ]
    )


def excel_serials(buf: bytes) -> list[tuple[int, float, datetime]]:
    out = []
    off = 0
    while off <= len(buf) - 8:
        d = struct.unpack_from("<d", buf, off)[0]
        if 45800 <= d <= 46300:
            dt = EXCEL_BASE + timedelta(days=d)
            if dt.year >= 2024:
                out.append((off, d, dt))
                off += 8
                continue
        off += 1
    return out


def rewrite_tvp(
    src: Path,
    dst: Path,
    *,
    new_start: datetime,
    cutoff: datetime,
    orig_start: datetime,
) -> dict:
    orig = src.read_bytes()
    if not orig.startswith(MAGIC):
        raise ValueError(f"{src.name}: missing TrafficViewerPro.Data magic")
    data = bytearray(orig)
    stream_off, hits, stream_end = locate_stream(orig)

    keep = 0
    trim_at = stream_end
    last_kept: datetime | None = None
    max_s = 86400 * 8
    for h in hits:
        if not (0 <= h["seconds"] <= max_s):
            break
        ts = new_start + timedelta(seconds=h["seconds"])
        if ts <= cutoff:
            keep += 1
            last_kept = ts
            trim_at = h["end"]
        else:
            break
    if keep < 20:
        raise ValueError(f"{src.name}: only {keep} hits on/before cutoff")

    old_len = struct.unpack_from("<I", orig, stream_off - 4)[0]
    new_len = trim_at - stream_off
    struct.pack_into("<I", data, stream_off - 4, new_len)

    # Never patch inside the hit stream — false-positive serials corrupt TVP.
    for o, dt, raw in pc_clocks(orig):
        if o >= stream_off:
            continue
        if abs((dt - orig_start).total_seconds()) < 2:
            new_dt = new_start
        else:
            new_dt = last_kept or cutoff
        data[o : o + 8] = pack_pc(raw, new_dt)

    end_serial = ((last_kept or cutoff) - EXCEL_BASE).total_seconds() / 86400.0
    for o, _d, _dt in excel_serials(orig):
        if o < stream_off:
            struct.pack_into("<d", data, o, end_serial)

    trimmed = bytes(data[:trim_at])
    dst.write_bytes(trimmed)

    return {
        "bytes_in": len(orig),
        "bytes_out": len(trimmed),
        "hits_in": len(hits),
        "hits_out": keep,
        "dropped": len(hits) - keep,
        "stream_off": stream_off,
        "old_len": old_len,
        "new_len": new_len,
        "last_kept": last_kept,
        "new_start": new_start,
        "cutoff": cutoff,
    }


def verify_tvp(path: Path, *, expect_start: datetime, cutoff: datetime) -> dict:
    data = path.read_bytes()
    if not data.startswith(MAGIC):
        raise ValueError(f"{path.name}: magic missing after write")
    start = picocount_hits.decode_start_time_tvp(data)
    if start is None:
        raise ValueError(f"{path.name}: no start clock after write")
    if abs((start - expect_start).total_seconds()) > 2:
        raise ValueError(f"{path.name}: start {start} != {expect_start}")
    off, hits, _end = locate_stream(data)
    valid = [h for h in hits if 0 <= h["seconds"] <= 86400 * 8]
    last = expect_start + timedelta(seconds=valid[-1]["seconds"])
    if last > cutoff:
        raise ValueError(f"{path.name}: last hit {last} after cutoff {cutoff}")
    stored_len = struct.unpack_from("<I", data, off - 4)[0]
    actual_len = len(data) - off
    if stored_len != actual_len:
        raise ValueError(
            f"{path.name}: stream_len {stored_len} != file-tail {actual_len}"
        )
    return {"start": start, "last": last, "hits": len(hits), "bytes": len(data)}


def parse_60min(path: Path) -> dict:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    lines = text.splitlines()
    start = end = None
    loc = None
    header_idx = None
    rows: list[tuple[datetime, str]] = []
    for i, line in enumerate(lines):
        if line.startswith("Study Start:"):
            parts = next(csv.reader([line]))
            start = datetime.strptime(parts[1].strip(), "%Y-%m-%d %H:%M:%S")
        elif line.startswith("Study End:"):
            parts = next(csv.reader([line]))
            end = datetime.strptime(parts[1].strip(), "%Y-%m-%d %H:%M:%S")
        elif line.startswith('"Study Location:"') or line.startswith("Study Location:"):
            loc = line
        elif line.startswith("DATE,"):
            header_idx = i
        elif header_idx is not None and re.match(r"^\d{4}-\d{2}-\d{2},", line):
            parts = next(csv.reader([line]))
            ts = datetime.strptime(f"{parts[0].strip()} {parts[1].strip()}", "%Y-%m-%d %H:%M")
            rows.append((ts, line))
    if start is None or end is None or header_idx is None:
        raise ValueError(f"{path.name}: could not parse 60min CSV")
    return {
        "lines": lines,
        "start": start,
        "end": end,
        "loc": loc,
        "header_idx": header_idx,
        "rows": rows,
        "newline": b"\r\n" if b"\r\n" in raw else b"\n",
        "bom": raw.startswith(b"\xef\xbb\xbf"),
    }


def write_60min(path: Path, parsed: dict, cutoff: datetime) -> dict:
    kept = [(ts, line) for ts, line in parsed["rows"] if ts < cutoff]
    dropped = len(parsed["rows"]) - len(kept)
    new_end = min(parsed["end"], cutoff) if parsed["end"] > cutoff else parsed["end"]
    if kept:
        last_interval_end = kept[-1][0] + timedelta(hours=1)
        if parsed["end"] > cutoff:
            new_end = min(cutoff, last_interval_end)
    duration_h = int(round((new_end - parsed["start"]).total_seconds() / 3600.0))
    total = 0
    for _ts, line in kept:
        parts = next(csv.reader([line]))
        for cell in parts[2:]:
            cell = cell.strip()
            if cell:
                try:
                    total += int(float(cell))
                except ValueError:
                    pass
    lines = list(parsed["lines"])
    # rebuild from header block
    out_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("Study Start:"):
            orig_parts = next(csv.reader([line]))
            out_lines.append(_join_like(line, [
                orig_parts[0],
                parsed["start"].strftime("%Y-%m-%d %H:%M:%S"),
                *orig_parts[2:],
            ]))
        elif line.startswith("Study End:"):
            orig_parts = next(csv.reader([line]))
            out_lines.append(_join_like(line, [
                orig_parts[0],
                new_end.strftime("%Y-%m-%d %H:%M:%S"),
                *orig_parts[2:],
            ]))
        elif line.startswith("Duration:"):
            orig_parts = next(csv.reader([line]))
            out_lines.append(_join_like(line, [
                orig_parts[0],
                str(duration_h),
                *orig_parts[2:],
            ]))
        elif line.startswith("Total Vehicles:"):
            orig_parts = next(csv.reader([line]))
            # original uses a leading space before the number
            out_lines.append(_join_like(line, [
                orig_parts[0],
                f" {total}",
                *orig_parts[2:],
            ]))
        elif line.startswith("DATE,"):
            out_lines.append(line)
            for _ts, row in kept:
                out_lines.append(row)
            # skip original data rows
            i += 1
            while i < len(lines) and re.match(r"^\d{4}-\d{2}-\d{2},", lines[i]):
                i += 1
            continue
        else:
            out_lines.append(line)
        i += 1

    nl = "\r\n" if parsed["newline"] == b"\r\n" else "\n"
    body = nl.join(out_lines) + nl
    data = body.encode("utf-8")
    if parsed["bom"]:
        data = b"\xef\xbb\xbf" + data
    path.write_bytes(data)
    return {
        "rows_in": len(parsed["rows"]),
        "rows_out": len(kept),
        "dropped": dropped,
        "new_end": new_end,
        "orig_end": parsed["end"],
        "total": total,
        "first": kept[0][0] if kept else None,
        "last": kept[-1][0] if kept else None,
    }


def _join_like(original: str, parts: list[str]) -> str:
    """Rebuild a CSV line keeping the original trailing-comma shape."""
    n_commas = original.count(",")
    # csv.writer would quote; keep simple join like the source files
    line = ",".join(parts)
    extra = n_commas - line.count(",")
    if extra > 0:
        line += "," * extra
    return line


_DAY_RE = re.compile(
    r'^"?([A-Za-z]+),\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})"?,'
)
_HOUR_RE = re.compile(r"^(\d{2}):(\d{2}),")
_STARTED_RE = re.compile(
    r"Started:,(.+?),,,Ended:,(.+?),",
)


def _parse_mdy_dt(s: str) -> datetime:
    s = s.strip().strip('"')
    for fmt in (
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M %p",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"unparsed datetime: {s!r}")


def _fmt_mdy_dt(dt: datetime) -> str:
    return dt.strftime("%#m/%#d/%Y %#I:%M:%S %p") if sys.platform == "win32" else dt.strftime("%-m/%-d/%Y %-I:%M:%S %p")


def parse_volume_csv(path: Path) -> dict:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    lines = text.splitlines()
    started = ended = None
    days: list[dict] = []
    current: dict | None = None
    dirs_line = None
    preamble: list[str] = []
    footer: list[str] = []
    mode = "pre"
    for line in lines:
        if line.startswith("Started:"):
            m = _STARTED_RE.search(line)
            if not m:
                raise ValueError(f"{path.name}: Started/Ended line")
            started = _parse_mdy_dt(m.group(1))
            ended = _parse_mdy_dt(m.group(2))
            preamble.append(line)
            mode = "body"
            continue
        dm = _DAY_RE.match(line)
        if dm:
            if current:
                days.append(current)
            day = datetime.strptime(
                f"{dm.group(2)} {dm.group(3)} {dm.group(4)}", "%B %d %Y"
            ).date()
            current = {"date": day, "header": line, "intervals": [], "dir_line": None}
            mode = "day"
            continue
        if mode == "pre":
            preamble.append(line)
            continue
        if line.startswith("Interval,"):
            if current is not None:
                current["dir_line"] = line
                dirs_line = line
            continue
        if line.startswith("Daily Total,") or line.startswith("AM Peak,") or line.startswith("PM Peak,"):
            continue
        if line.startswith("Average Interval,") or line.startswith("Maximum in one Interval,") or line.startswith("Grand Total,"):
            mode = "foot"
            footer.append(line)
            continue
        if mode == "foot" or line.startswith('"Array Type') or line.startswith("Array Type") or line.startswith(',"Report Generated') or line.startswith(",Report Generated"):
            mode = "foot"
            footer.append(line)
            continue
        hm = _HOUR_RE.match(line)
        if hm and current is not None:
            hour = int(hm.group(1))
            minute = int(hm.group(2))
            parts = next(csv.reader([line]))
            # Interval,,East,West,,,Total  -> values at 2, 3, 6
            nums = []
            for cell in parts[2:]:
                cell = cell.strip()
                if cell == "":
                    nums.append(None)
                else:
                    try:
                        nums.append(int(float(cell)))
                    except ValueError:
                        nums.append(None)
            a = next((n for n in nums if n is not None), 0)
            b = next((n for n in nums[1:] if n is not None), 0)
            # last numeric is total
            nums_rev = [n for n in nums if n is not None]
            total = nums_rev[-1] if nums_rev else a + b
            current["intervals"].append({
                "hour": hour,
                "minute": minute,
                "line": line,
                "a": a,
                "b": b,
                "total": total,
                "parts": parts,
            })
            continue
        if mode == "body":
            preamble.append(line)
    if current:
        days.append(current)
    if started is None or ended is None or not days:
        raise ValueError(f"{path.name}: volume CSV parse failed")
    return {
        "preamble": preamble,
        "started": started,
        "ended": ended,
        "days": days,
        "dirs_line": dirs_line,
        "footer": footer,
        "newline": b"\r\n" if b"\r\n" in raw else b"\n",
        "bom": raw.startswith(b"\xef\xbb\xbf"),
        "orig_started_line": next(l for l in preamble if l.startswith("Started:")),
    }


def write_volume_csv(path: Path, parsed: dict, *, new_started: datetime, new_ended: datetime, shift_days: int) -> dict:
    cutoff = new_ended
    shift = timedelta(days=shift_days)
    kept_days: list[dict] = []
    dropped_intervals = 0
    for day in parsed["days"]:
        new_date = day["date"] - shift
        intervals = []
        for iv in day["intervals"]:
            ts = datetime(new_date.year, new_date.month, new_date.day, iv["hour"], iv["minute"])
            if ts > cutoff:
                dropped_intervals += 1
                continue
            # hour starting at cutoff is after end (e.g. 09:00 when cutoff is 09:00)
            if ts >= datetime(cutoff.year, cutoff.month, cutoff.day, cutoff.hour, cutoff.minute) and cutoff.minute == 0 and cutoff.second == 0:
                # keep 08:00 when cutoff is 09:00; drop 09:00
                if ts >= cutoff:
                    dropped_intervals += 1
                    continue
            intervals.append({**iv, "ts": ts})
        if not intervals:
            continue
        kept_days.append({"date": new_date, "dir_line": day["dir_line"], "intervals": intervals, "orig_header": day["header"]})

    # actual ended = last interval start + 1h - 1s, capped at requested new_ended
    if kept_days:
        last_ts = kept_days[-1]["intervals"][-1]["ts"]
        actual_end = last_ts + timedelta(hours=1) - timedelta(seconds=1)
        if actual_end > new_ended:
            actual_end = new_ended
    else:
        actual_end = new_ended

    def day_header(d: date) -> str:
        dt = datetime(d.year, d.month, d.day)
        return f'"{dt.strftime("%A, %B")} {d.day}, {d.year}",,,,,,,'

    def hour_line(iv: dict) -> str:
        parts = list(iv["parts"])
        hh = f"{iv['hour']:02d}:{iv['minute']:02d}"
        parts[0] = hh
        return ",".join("" if p is None else str(p) for p in parts)

    def totals_block(intervals: list[dict]) -> list[str]:
        sa = sum(iv["a"] for iv in intervals)
        sb = sum(iv["b"] for iv in intervals)
        st = sum(iv["total"] for iv in intervals)
        am = [iv for iv in intervals if iv["hour"] < 12]
        pm = [iv for iv in intervals if iv["hour"] >= 12]
        lines = [f"Daily Total,,{sa},{sb},,,{st},"]
        if am:
            best = max(am, key=lambda iv: iv["total"])
            lines.append(f"AM Peak,,{best['total']} (starting at {best['hour']:02d}:{best['minute']:02d}:00),,,,,")
        if pm:
            best = max(pm, key=lambda iv: iv["total"])
            lines.append(f"PM Peak,,{best['total']} (starting at {best['hour']:02d}:{best['minute']:02d}:00),,,,,")
        return lines

    all_iv = [iv for d in kept_days for iv in d["intervals"]]
    n = len(all_iv) or 1
    sa = sum(iv["a"] for iv in all_iv)
    sb = sum(iv["b"] for iv in all_iv)
    st = sum(iv["total"] for iv in all_iv)
    avg_a = round(sa / n)
    avg_b = round(sb / n)
    avg_t = round(st / n)
    mx_a = max((iv["a"] for iv in all_iv), default=0)
    mx_b = max((iv["b"] for iv in all_iv), default=0)
    mx_t = max((iv["total"] for iv in all_iv), default=0)

    started_line = parsed["orig_started_line"]
    started_line = _STARTED_RE.sub(
        lambda _m: f"Started:,{_fmt_mdy_dt(new_started)},,,Ended:,{_fmt_mdy_dt(actual_end)},",
        started_line,
        count=1,
    )

    out: list[str] = []
    for line in parsed["preamble"]:
        if line.startswith("Started:"):
            out.append(started_line)
        else:
            out.append(line)
    for day in kept_days:
        out.append(day_header(day["date"]))
        out.append(day["dir_line"] or parsed["dirs_line"] or "Interval,,East,West,,,Total,")
        for iv in day["intervals"]:
            out.append(hour_line(iv))
        out.extend(totals_block(day["intervals"]))
    out.append(f"Average Interval,,{avg_a},{avg_b},,,{avg_t},")
    out.append(f"Maximum in one Interval,,{mx_a},{mx_b},,,{mx_t},")
    out.append(f"Grand Total,,{sa},{sb},,,{st},")
    # keep original footer notes (Array Type / Report Generated) without the old summary rows
    for line in parsed["footer"]:
        if line.startswith("Average Interval,") or line.startswith("Maximum in one Interval,") or line.startswith("Grand Total,"):
            continue
        out.append(line)

    nl = "\r\n" if parsed["newline"] == b"\r\n" else "\n"
    body = nl.join(out) + nl
    data = body.encode("utf-8")
    if parsed["bom"]:
        data = b"\xef\xbb\xbf" + data
    path.write_bytes(data)
    return {
        "days_out": len(kept_days),
        "intervals_out": len(all_iv),
        "dropped_intervals": dropped_intervals,
        "new_started": new_started,
        "actual_end": actual_end,
        "grand_total": st,
        "first": all_iv[0]["ts"] if all_iv else None,
        "last": all_iv[-1]["ts"] if all_iv else None,
    }


def process_tvp(src: Path, dst: Path, day: str, lines: list[str]) -> None:
    data = src.read_bytes()
    orig_start = picocount_hits.decode_start_time_tvp(data)
    if orig_start is None:
        raise ValueError(f"{src.name}: no study start")
    if day == "D1":
        new_start = orig_start
        cutoff = DAY1_CUTOFF
    else:
        shift = (orig_start.date() - DAY2_START_DATE).days
        new_start = orig_start - timedelta(days=shift)
        _off, hits, _end = locate_stream(data)
        valid = [h for h in hits if 0 <= h["seconds"] <= 86400 * 8]
        orig_last = orig_start + timedelta(seconds=valid[-1]["seconds"])
        shifted_last = orig_last - timedelta(days=shift)
        end_cap = datetime.combine(DAY2_END_DATE, orig_last.time())
        cutoff = min(shifted_last, end_cap)

    info = rewrite_tvp(src, dst, new_start=new_start, cutoff=cutoff, orig_start=orig_start)
    v = verify_tvp(dst, expect_start=new_start, cutoff=cutoff)
    lines.append(
        f"TVP {src.name} {day}: start {orig_start} -> {v['start']}; "
        f"last {v['last']}; hits {info['hits_in']} -> {info['hits_out']} "
        f"(drop {info['dropped']}); bytes {info['bytes_in']} -> {info['bytes_out']}"
    )


def process_60min(src: Path, dst: Path, lines: list[str]) -> None:
    parsed = parse_60min(src)
    info = write_60min(dst, parsed, DAY1_CUTOFF)
    # verify no data row on/after cutoff
    check = parse_60min(dst)
    bad = [ts for ts, _ in check["rows"] if ts >= DAY1_CUTOFF]
    if bad:
        raise ValueError(f"{src.name}: leftover rows after cutoff: {bad[:3]}")
    if check["end"] > DAY1_CUTOFF:
        raise ValueError(f"{src.name}: Study End {check['end']} after cutoff")
    lines.append(
        f"CSV {src.name} D1: end {info['orig_end']} -> {info['new_end']}; "
        f"rows {info['rows_in']} -> {info['rows_out']} (drop {info['dropped']}); "
        f"span {info['first']} .. {info['last']}"
    )


def process_volume(src: Path, dst: Path, lines: list[str]) -> None:
    parsed = parse_volume_csv(src)
    shift = (parsed["started"].date() - DAY2_START_DATE).days
    new_started = parsed["started"] - timedelta(days=shift)
    new_ended = datetime(
        DAY2_END_DATE.year,
        DAY2_END_DATE.month,
        DAY2_END_DATE.day,
        parsed["ended"].hour,
        parsed["ended"].minute,
        parsed["ended"].second,
    )
    info = write_volume_csv(
        dst, parsed, new_started=new_started, new_ended=new_ended, shift_days=shift
    )
    check = parse_volume_csv(dst)
    if check["started"].date() != DAY2_START_DATE:
        raise ValueError(f"{src.name}: started {check['started']} not on {DAY2_START_DATE}")
    if check["ended"] > new_ended:
        raise ValueError(f"{src.name}: ended {check['ended']} after {new_ended}")
    for day in check["days"]:
        for iv in day["intervals"]:
            ts = datetime(day["date"].year, day["date"].month, day["date"].day, iv["hour"], iv["minute"])
            if ts > check["ended"]:
                raise ValueError(f"{src.name}: interval {ts} after ended")
            if ts.date() > DAY2_END_DATE:
                raise ValueError(f"{src.name}: interval {ts} after 8/28")
    lines.append(
        f"CSV {src.name} D2: {parsed['started']}..{parsed['ended']} -> "
        f"{info['new_started']}..{info['actual_end']}; "
        f"intervals {info['intervals_out']} drop {info['dropped_intervals']}; "
        f"grand {info['grand_total']}"
    )


def classify(path: Path) -> tuple[str, str] | None:
    name = path.name
    if name.lower().endswith(".tvp"):
        if "minus" in name.lower():
            return None
        site = site_of(name)
        if site in DAY1_SITES:
            return "tvp", "D1"
        if site in DAY2_SITES:
            return "tvp", "D2"
        return None
    if name.lower().endswith(".csv"):
        if name.startswith(DAY1_SERIAL_PREFIXES) or any(name.startswith(p) for p in DAY1_SERIAL_PREFIXES):
            return "csv60", "D1"
        site = site_of(name)
        if site in DAY2_CSV_SITES:
            return "vol", "D2"
        return None
    return None


def main() -> int:
    if not SRC.is_dir():
        raise SystemExit(f"missing source {SRC}")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    lines: list[str] = [
        "Week 24 trim",
        f"source: {SRC}",
        f"output: {OUT}",
        f"Day 1 TVP/CSV end: {DAY1_CUTOFF} (or last hit/row before)",
        f"Day 2 start date {DAY2_START_DATE} end date {DAY2_END_DATE} (clock times kept)",
        "",
    ]
    errors: list[str] = []
    n_ok = 0
    for src in sorted(SRC.iterdir()):
        if not src.is_file():
            continue
        kind = classify(src)
        if not kind:
            continue
        dst = OUT / src.name
        try:
            typ, day = kind
            print(f"processing {src.name} {typ} {day}", flush=True)
            if typ == "tvp":
                process_tvp(src, dst, day, lines)
            elif typ == "csv60":
                process_60min(src, dst, lines)
            elif typ == "vol":
                process_volume(src, dst, lines)
            n_ok += 1
        except Exception as e:
            errors.append(f"FAIL {src.name}: {e}")
            lines.append(f"FAIL {src.name}: {e}")

    lines.append("")
    lines.append(f"wrote {n_ok} files, errors {len(errors)}")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.buffer.write(("\n".join(lines) + "\n").encode("utf-8", errors="replace"))
    if errors:
        print("ERRORS:", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
