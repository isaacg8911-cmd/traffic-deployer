# Traffic Deployer - Desktop (Local & Private)

A desktop program (like Microsoft Streets & Trips) that opens straight into an
offline **California street map**. Upload your `.EST` + Excel files, and it builds
the **best driving route along real streets** using your USB GPS. Your field files
**never leave this laptop**.

**How routing and map tracing work (segment lines, road graph, efficient order):**
see **[ROUTING_AND_MAP.md](ROUTING_AND_MAP.md)**.

## First time (needs internet, ~5-10 minutes)

1. Make sure Python is installed (`python --version` in a terminal).
2. Double-click **`START.bat`**.
   - Builds a private local environment (`.venv`) and installs everything.
   - Downloads the **California street map** + map libraries for offline use
     (one time only - this is the longest step).
   - Then the app window opens.

## Every day after that

- Double-click **`START.bat`**. It opens straight to the map (no re-download).
- Close the window when you're done.

## The workflow

1. **Setup tab**
   - Set your **starting point**: read the USB GPS, search an address (online), or
     type coordinates.
   - **Choose** your Excel/CSV (site coordinates) and your `.EST` map file(s).
     Map names come from the upload filename (e.g. `Day5.EST` → Day5).
   - While you still have wifi at work, click **"Download road map for these
     sites"** so routing follows real streets offline. *(Skip it and routes fall
     back to straight lines with a warning.)*
   - Click **BUILD OPTIMIZED ROUTE** (orders sites to cross each street line efficiently,
     then traces home → crossings → home on the downloaded road network).
2. **Route tab** - see the ordered stops, total miles, and the route line drawn on
   actual streets. Toggle guide route / site lines. Click any stop to open it.
3. **Map** — standard **Protomaps light** colors (not tied to Sunny/Cloudy/Night panel
   themes). Zoom to neighborhood level for street names. If labels are still sparse,
   re-run `python setup_maps.py` once (wifi) to refresh tiles at zoom 15 + fonts.
4. **START DRIVING** - turn-by-turn banner + offline voice (female Windows guide). Light blue line to the next stop only.
5. **Install tab** - per stop: **Grab GPS Here** (precise field coordinate +
   auto street name when online), compass + **Set direction from compass** when
   stopped, set serial/lanes, then **INSTALL** or **SKIP**. Prev/Next to move along.
6. **Pickup tab** - work the installed sites and mark each **SECURED**.
7. **Audit tab** - it flags missing data, then exports the **Excel** (or CSV) report.

## Live GPS tracing

Your position shows as a moving dot with a breadcrumb trail as you drive. The map
auto-follows you; tap **Follow Me** on the map to lock/unlock recentring. Use the
**Sunny / Cloudy / Night** (top right) changes only the **side panels** — the map always uses the default Protomaps basemap.

## USB GPS (GlobalSat BU-353N)

- Plug it in **before** launching and give it a clear view of the sky.
- First fix outdoors can take 30-60 seconds (cold start), then it's fast.
- Diagnose from a terminal in this folder:

```
.venv\Scripts\activate
python gps_reader.py
```

## Offline vs online

| Feature | Works offline? |
|---|---|
| California street map + street names (zoom in) | Yes (after setup_maps.py — includes fonts) |
| USB GPS + live tracing | Yes |
| Route building on real streets | Yes (after downloading the area's road map at work) |
| Install / pick-up tracking | Yes |
| Excel / CSV export | Yes |
| Address **search** | No - needs internet |
| Auto street-name on Grab GPS | No - needs internet |

## Your private data

- Everything you capture is saved encrypted in **`tds_data/`** on this laptop
  (git-ignored, atomic + `.bak` so a mid-shift close won't corrupt it).
- **Auto-save**: install fields save as you type; the full shift saves every ~45s and
  when you close the app. Use **Save progress now** on Setup anytime.
- **Profiles**: each name (e.g. `DEFAULT`, `WEEK9`) is its own file
  `tds_backup_<NAME>.json`. **Save as new profile** copies your current shift to a new
  name without losing the old one.
- **Re-build route** keeps install/pickup/GPS data for matching sites. Only
  **Clear shift data** (Route tab) or **Clear file lists** (Setup) remove what you choose.
- The California map lives at `tds_data/california.pmtiles`; the area road network
  for routing lives at `tds_data/road_graph.graphml`.

## Refreshing the map later

Run `python setup_maps.py` any time (online) to re-pull the latest California map and
label fonts.

## One-laptop field checklist (raises readiness)

1. Run **`SMOKE.bat`** (or `.\scripts\smoke_test.ps1` for smoke + demo + preflight) after any update.
2. Setup: Excel + `.EST` → **Download road map** → **BUILD OPTIMIZED ROUTE**.
3. Route tab: set **Map on screen** to today's Day# if you only want that day visible.
4. Install: **Grab GPS** fills street from internet or **offline road map**; use compass when stopped.
5. End: Audit export (includes MapDay, cross point, wide-street warning).

## Smoke test

Double-click **`SMOKE.bat`** at the project root (uses the project `.venv`).

Full proof chain (smoke + demo + preflight):

```powershell
PROVE.bat
```

```powershell
.\scripts\smoke_test.ps1
```

Headless only:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_full.py
```

Do **not** use bare `python` for smoke — it may miss `xlsxwriter` / `osmnx` even when the app works via `START.bat`.

Full suite checks: imports, persistence, export, web map assets, local server, basemap, routing graph load, and field readiness.
