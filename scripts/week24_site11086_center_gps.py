"""Week 24 DEMAND: site 11086 Day 2 GPS = center of the street segment.

11086 is installed on TFC Day 2 with blank LAT/LON. Map 2 HTML has begin/end
on REDWOOD LN; EST pin sat at the end. Writes the segment midpoint to TFC,
patches Map 2.est, and marks Map 2.html installed with that field GPS.

Does not touch Day 1 TFC or Map 1 files.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import openpyxl

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from core.est_field_gps import apply_field_gps_to_est  # noqa: E402
from core.est_viewer import pushpins_from_est, to_html_map  # noqa: E402

WORK = Path(r"C:\Users\isaac\Downloads\week 24 ig (2)\week 24 ig")
TFC = WORK / "Week 24 IG TFC.xlsx"
HTML = WORK / "Week 24 Map 2.html"
EST = WORK / "Week 24 Map 2.est"
DAY2 = "Week 24 Day 2 Isaac"
DAY1 = "Week 24 Day 1 Isaac"
SITE = "11086"
ROWS_RE = re.compile(r"var sites = (\[.*?\]);", re.S)


def _cell_id(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    s = str(v).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def _backup(path: Path) -> Path | None:
    bak = path.with_suffix(path.suffix + ".bak")
    if path.is_file() and not bak.exists():
        shutil.copy2(path, bak)
        return bak
    return None


def load_html_sites(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = ROWS_RE.search(text)
    if not m:
        raise SystemExit(f"No var sites = [...] in {path}")
    rows = json.loads(m.group(1))
    if not isinstance(rows, list) or not rows:
        raise SystemExit(f"Empty sites list in {path}")
    return rows


def find_site(rows: list[dict], site: str) -> dict:
    for row in rows:
        if str(row.get("site", "")).strip() == site:
            return row
    raise SystemExit(f"site {site} not in {HTML.name}")


def site_center(row: dict) -> tuple[float, float]:
    try:
        blat, blon = float(row["begin_lat"]), float(row["begin_lon"])
        elat, elon = float(row["end_lat"]), float(row["end_lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"site {SITE} missing begin/end coords: {exc}") from exc
    lat = round((blat + elat) / 2.0, 6)
    lon = round((blon + elon) / 2.0, 6)
    if not (25 < lat < 50 and -125 < lon < -65):
        raise SystemExit(f"center out of CA range: {lat}, {lon}")
    return lat, lon


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def patch_tfc_excel_com(tfc: Path, lat: float, lon: float) -> tuple[str, int]:
    """Write LAT/LON into the already-open Excel workbook (file lock fallback)."""
    script = f"""
$ErrorActionPreference = 'Stop'
$path = {_ps_quote(str(tfc))}
$day1 = {_ps_quote(DAY1)}
$day2 = {_ps_quote(DAY2)}
$site = {_ps_quote(SITE)}
$lat = {lat}
$lon = {lon}
$excel = [Runtime.InteropServices.Marshal]::GetActiveObject('Excel.Application')
$wb = $null
foreach ($w in @($excel.Workbooks)) {{
  if ($w.FullName -eq $path) {{ $wb = $w; break }}
}}
if ($wb -eq $null) {{ throw "open workbook not found: $path" }}
foreach ($ws in @($wb.Worksheets)) {{
  if ($ws.Name -eq $day1) {{
    $used = $ws.UsedRange.Rows.Count
    for ($r = 2; $r -le $used; $r++) {{
      $v = [string]$ws.Cells.Item($r, 2).Text
      if ($v -eq $site) {{ throw "site $site found on $day1" }}
    }}
  }}
}}
$ws2 = $null
foreach ($ws in @($wb.Worksheets)) {{ if ($ws.Name -eq $day2) {{ $ws2 = $ws; break }} }}
if ($ws2 -eq $null) {{ throw "missing sheet $day2" }}
$lastCol = [Math]::Max(11, [int]$ws2.UsedRange.Columns.Count)
$siteCol = $latCol = $lonCol = 0
for ($c = 1; $c -le $lastCol; $c++) {{
  $h = ([string]$ws2.Cells.Item(1, $c).Text).Trim().ToUpper()
  if ($h -eq 'SITE') {{ $siteCol = $c }}
  if ($h -eq 'LAT') {{ $latCol = $c }}
  if ($h -eq 'LON') {{ $lonCol = $c }}
}}
if (-not $siteCol -or -not $latCol -or -not $lonCol) {{ throw "Day 2 missing Site/LAT/LON" }}
$hit = 0
$lastRow = [Math]::Max(2, [int]$ws2.UsedRange.Rows.Count)
for ($r = 2; $r -le $lastRow; $r++) {{
  $v = [string]$ws2.Cells.Item($r, $siteCol).Text
  if ($v -eq $site) {{ $hit = $r; break }}
}}
if ($hit -eq 0) {{ throw "site $site not on $day2" }}
$ws2.Cells.Item($hit, $latCol).Value2 = $lat
$ws2.Cells.Item($hit, $lonCol).Value2 = $lon
$wb.Save()
Write-Output ("COM_OK row=" + $hit + " lat=" + $ws2.Cells.Item($hit, $latCol).Value2 + " lon=" + $ws2.Cells.Item($hit, $lonCol).Value2)
"""
    import subprocess
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True,
    )
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    if r.returncode != 0:
        raise SystemExit(f"Excel COM write failed ({r.returncode}): {err or out}")
    print(out)
    m = re.search(r"row=(\d+)", out)
    hit_row = int(m.group(1)) if m else 0
    return DAY2, hit_row


def patch_tfc(tfc: Path, lat: float, lon: float) -> tuple[str, int]:
    wb = openpyxl.load_workbook(tfc)
    if DAY1 in wb.sheetnames:
        for row in wb[DAY1].iter_rows(min_row=2, max_col=2):
            if _cell_id(row[1].value) == SITE:
                raise SystemExit(f"site {SITE} found on {DAY1} — refusing (Day 2 only)")
    if DAY2 not in wb.sheetnames:
        raise SystemExit(f"missing sheet {DAY2!r}; have {wb.sheetnames}")
    ws = wb[DAY2]
    headers = {str(ws.cell(1, c).value or "").strip().upper(): c for c in range(1, ws.max_column + 1)}
    site_col = headers.get("SITE")
    lat_col = headers.get("LAT")
    lon_col = headers.get("LON")
    if not site_col or not lat_col or not lon_col:
        raise SystemExit(f"Day 2 missing Site/LAT/LON columns: {headers}")
    hit_row = None
    for r in range(2, ws.max_row + 1):
        if _cell_id(ws.cell(r, site_col).value) == SITE:
            hit_row = r
            break
    if hit_row is None:
        raise SystemExit(f"site {SITE} not on {DAY2}")
    ws.cell(hit_row, lat_col).value = lat
    ws.cell(hit_row, lon_col).value = lon
    try:
        wb.save(tfc)
    except PermissionError:
        print("TFC locked by Excel — writing via open workbook")
        return patch_tfc_excel_com(tfc, lat, lon)
    return DAY2, hit_row


def patch_html(path: Path, rows: list[dict], site: str, lat: float, lon: float) -> None:
    for row in rows:
        if str(row.get("site", "")).strip() != site:
            continue
        row["status"] = "installed"
        row["field_lat"] = lat
        row["field_lon"] = lon
        break
    path.write_text(to_html_map(rows, title=path.stem + ".est"), encoding="utf-8")


def _read_tfc_gps(tfc: Path) -> tuple[float | None, float | None]:
    try:
        wb = openpyxl.load_workbook(tfc, data_only=True)
    except PermissionError:
        return None, None
    ws = wb[DAY2]
    headers = {str(ws.cell(1, c).value or "").strip().upper(): c for c in range(1, ws.max_column + 1)}
    for r in range(2, ws.max_row + 1):
        if _cell_id(ws.cell(r, headers["SITE"]).value) == SITE:
            return ws.cell(r, headers["LAT"]).value, ws.cell(r, headers["LON"]).value
    return None, None


def prove(tfc: Path, est: Path, html: Path, lat: float, lon: float) -> None:
    got_lat, got_lon = _read_tfc_gps(tfc)
    if got_lat is None and got_lon is None:
        print("TFC still locked — GPS prove from Excel COM write + EST/HTML")
        got_lat, got_lon = lat, lon
    elif abs(float(got_lat) - lat) > 1e-9 or abs(float(got_lon) - lon) > 1e-9:
        raise SystemExit(f"TFC prove fail: got {got_lat},{got_lon} want {lat},{lon}")
    pin = next((p for p in pushpins_from_est(est) if p["site"] == SITE), None)
    if not pin:
        raise SystemExit("EST prove fail: 11086 pin missing")
    # Inline EST slots are fixed-width ASCII (lat ~8, lon often 8 → 3 decimals).
    if abs(pin["lat"] - lat) > 5e-5 or abs(pin["lon"] - lon) > 5e-4:
        raise SystemExit(f"EST prove fail: pin {pin} want {lat},{lon}")
    print(f"EST pin truncated to slot width: {pin['lat']},{pin['lon']} (TFC/HTML keep 6 dp)")
    html_row = find_site(load_html_sites(html), SITE)
    if html_row.get("status") != "installed":
        raise SystemExit(f"HTML prove fail: status={html_row.get('status')}")
    if abs(float(html_row["field_lat"]) - lat) > 1e-9 or abs(float(html_row["field_lon"]) - lon) > 1e-9:
        raise SystemExit(f"HTML prove fail: field {html_row.get('field_lat')},{html_row.get('field_lon')}")
    print(f"PROVE ok TFC={got_lat},{got_lon} EST={pin['lat']},{pin['lon']} HTML field={html_row['field_lat']},{html_row['field_lon']}")


def main() -> int:
    for p in (TFC, HTML, EST):
        if not p.is_file():
            print(f"missing {p}", file=sys.stderr)
            return 1

    rows = load_html_sites(HTML)
    row = find_site(rows, SITE)
    lat, lon = site_center(row)
    print(
        f"{SITE} {row.get('street')} "
        f"begin={row['begin_lat']},{row['begin_lon']} "
        f"end={row['end_lat']},{row['end_lon']} "
        f"center={lat},{lon}"
    )

    for p in (TFC, HTML, EST):
        bak = _backup(p)
        if bak:
            print(f"backup {bak.name}")

    sheet, hit_row = patch_tfc(TFC, lat, lon)
    print(f"TFC {sheet} row {hit_row} LAT/LON set")

    est_result = apply_field_gps_to_est(EST, {SITE: (lat, lon)}, EST)
    print(
        f"EST patched={est_result.get('sites_patched')} "
        f"missing={est_result.get('missing_in_est')} "
        f"warn={est_result.get('warnings')}"
    )
    if SITE in (est_result.get("missing_in_est") or []):
        print("FAIL 11086 not in Map 2.est", file=sys.stderr)
        return 1

    patch_html(HTML, rows, SITE, lat, lon)
    print(f"HTML {HTML.name} status=installed field GPS set")

    prove(TFC, EST, HTML, lat, lon)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
