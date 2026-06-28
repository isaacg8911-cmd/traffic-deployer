# Traffic Deployer - Desktop (Local & Private)

A desktop program (like Microsoft Streets & Trips) that opens straight into an
offline **California street map**. Upload your `.EST` + Excel files, and it builds
the **best driving route along real streets** using your USB GPS. Your field files
**never leave this laptop**.

## Work laptop (no Python) — start here

Full handover: **[WORK_LAPTOP.md](WORK_LAPTOP.md)**

| Home PC tonight | Work laptop tomorrow |
|-----------------|----------------------|
| `BUILD_WORK_LAPTOP.bat` then `VERIFY_WORK_LAPTOP.bat` | Unzip → `OPEN_APP.bat` |
| Copy `dist\TrafficDeployer-WorkLaptop.zip` to USB | Setup → BUILD ROUTE → **READY FOR OFFLINE** |

**App update later (map already on laptop):** home PC → **`BUILD_APP_UPDATE.bat`** → copy `dist\TrafficDeployer-AppUpdate\TrafficDeployer\` to USB (~800 MB folder, no zip). On laptop, replace exe + `_internal\` + `web\`; **keep** `tds_data\`. See **WORK_LAPTOP.md**.

Do **not** use `START.bat` on the work laptop zip — use **`OPEN_APP.bat`**.

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

## At home (Wi‑Fi) vs on the road (no internet)

The app has two modes:

| Phase | When | What works |
|--------|------|------------|
| **Home setup (online)** | Default when you open the app at home | Address search, download road map, BUILD ROUTE |
| **Field mode (offline)** | After you tap **Go offline** (top bar) | Map, GPS, driving, installs, export — all local; no internet calls |

**At home:** leave the app in online mode until setup is done, then tap **Go offline** (top bar)
(Setup → *Before you leave*). Status bar shows `Home setup · online`.

**On the road:** field mode stays on until you are home again and tap **I'm online** (top bar)
for the next day’s files/route. In field mode the app **does not call the internet** (no address
lookup, no downloads) and avoids blocking error popups — map, GPS, driving, installs, and export
use only local data.

**Import road map from file** works in both modes (no internet — copy `road_graph.graphml`
from another PC).

**Before you leave:** Setup → **Setup checklist** (all green) → **Test home Wi‑Fi** →
**READY FOR OFFLINE**. New: **Quick setup wizard** (3 steps: start → files → build).
On Route: colored **zones**, route summary, **Move stop up/down** + **Re-trace route only**,
field strip with **next-stop distance**, **Recover map** if the canvas goes blank.
Install tab: **Attach install photo** (saved under `tds_data/field_photos/`).
Audit tab: **shift summary** + export (includes **PicoCount** columns in Excel).

**Before a field day:** see **[docs/TOMORROW_MORNING.md](docs/TOMORROW_MORNING.md)** for the 5 AM checklist.  
**Proof overnight:** `PROVE.bat` (smoke + demo + golden + benchmark + optional counter sandbox).

## The workflow

1. **Setup tab** *(at home on Wi‑Fi — online mode)*
   - Set your **starting point**: **Search address** (`street, city, CA zip`), USB GPS,
     or coordinates. Wrong home = wrong route order.
   - **Choose** your Excel/CSV (site coordinates) and your `.EST` map file(s).
     Map names come from the upload filename (e.g. `Day5.EST` → Day5).
   - **Download road map** for these sites (or import `.graphml` from home PC if work Wi‑Fi blocks download).
   - **BUILD OPTIMIZED ROUTE**, then **READY FOR OFFLINE** before you leave.
2. **Route tab** - see the ordered stops (numbered **1, 2, 3…** on the map), total miles,
   and the **blue drive line** traced on real streets (needs road map downloaded).
   Optional **work-site lines** are dashed purple (Excel segment, not the drive path).
   Click a numbered stop to open it.
3. **Map** — standard **Protomaps light** colors (not tied to Sunny/Cloudy/Night panel
   themes). Zoom to neighborhood level for street names. If labels are still sparse,
   re-run `python setup_maps.py` once (wifi) to refresh tiles at zoom 15 + fonts.
4. **START DRIVING** - turn-by-turn banner on the Route tab. Light blue line to the next stop only.
5. **Install tab** - per stop: **PicoCount 2500 (USB)** — **Connect**, **Read serial**
   (auto-fills Serial # when empty), **Clear & set ID** (clears counter + sets Unit ID
   like `1234nc1b` from site + N/E direction + `c1b`). Then **Grab GPS Here**, compass,
   lanes, **INSTALL** or **SKIP**.
6. **Pickup tab** - mark each site **SECURED**; **Download counter data** saves the study to
   `tds_data/counter_downloads/<profile>/` (`.pcbin` + `.json` sidecar).
7. **Audit tab** - it flags missing data, then exports the **Excel** (or CSV) report.

## Live GPS tracing

Your position shows as a green dot on the map as you drive. Tap **Follow Me** on the map
to lock/unlock recentering. **FOLLOW GPS** on the Route tab hides the side panel for a
full-screen map and lower battery use.

**Battery (field laptop):** plug in while driving for full GPS/map rate. When unplugged,
the status bar shows **Battery saver** — GPS and map updates throttle automatically.
When plugged in, **Plugged in** restores full rate. On **4 GB work laptops**, status shows **Work laptop** even on AC — map/GPS stay throttled for stability. SwiftShader map rendering is
CPU-heavy; **FOLLOW GPS** also collapses the side panel to reduce drain. After
**READY FOR OFFLINE**, the Setup tab is hidden; use Route / Install / Pickup / Audit only on the road.

## USB GPS (GlobalSat BU-353N)

- Plug it in **before** launching and give it a clear view of the sky.
- First fix outdoors can take 30-60 seconds (cold start), then it's fast.
- Diagnose from a terminal in this folder:

```
.venv\Scripts\activate
python gps_reader.py
```

## Offline vs online (after READY FOR OFFLINE)

| Feature | On the road (field mode) |
|---|---|
| California street map + street names | Yes |
| USB GPS + live tracing | Yes |
| Driving the built route | Yes |
| Install / pick-up tracking | Yes |
| Excel / CSV export | Yes |
| Address **search** | No (use at home before you leave) |
| Download road map | No (do at home; import file still OK) |
| Auto street-name on Grab GPS | Uses local road map if downloaded; else type street |

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

Full proof chain (smoke + demo + preflight + golden routes + benchmark):

```powershell
PROVE.bat
```

**User-input proofs** (real Qt + map — run after UI/map/install changes):

```powershell
USER_PROVE.bat
```

**Full app check** (headless + user paths + audit report at `logs/app_check/latest.md`):

```powershell
APP_CHECK.bat
```

Portable `.exe` folder (optional, needs PyInstaller once):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_portable.ps1
```

Output: `dist\TrafficDeployer\` — copy your `tds_data\` road graph beside it for offline use.

```powershell
.\scripts\smoke_test.ps1
```

Headless only:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_full.py
```

Do **not** use bare `python` for smoke — it may miss `xlsxwriter` / `osmnx` even when the app works via `START.bat`.

Full suite checks: imports, persistence, export, web map assets, local server, basemap, routing graph load, and field readiness.
