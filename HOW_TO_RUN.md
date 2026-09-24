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

## At home (Wi‑Fi) vs on the road (no internet)

The app has two modes:

| Phase | When | What works |
|--------|------|------------|
| **Home setup (online)** | Default when you open the app at home | Address search, download road map, BUILD ROUTE |
| **Field mode (offline)** | After you tap **Go offline** (top bar) | Map, GPS, driving, installs, export — all local; no internet calls |

**At home or on Tailscale:** leave the app in online mode until setup is done, then tap **Go offline**
(top bar, or the bottom of Setup once the route is built). Each tab keeps one main button.
Extra tools sit under **Show more**.

**App update (work laptop):** on the home PC run **`UPDATE_LAPTOP.bat`**. On the laptop keep Tailscale
connected, then **OPEN_APP.bat** or **WIFI_UPDATE_NOW.bat**. Map and shift data in `tds_data\` stay put.
See **[packaging/WIFI_AUTO_UPDATE.txt](packaging/WIFI_AUTO_UPDATE.txt)**.

**On the road:** field mode stays on until you are home again and tap **I'm online** (top bar)
for the next day’s files/route. In field mode the app **does not call the internet** (no address
lookup, no downloads) and avoids blocking error popups — map, GPS, driving, installs, and export
use only local data. Field-mode warnings use the **status bar** (no blocking popups) and are
still saved under **`tds_data/crashes/`** (`notice_*.log`, `error_*.log`) for USB handoff.

**Import road map from file** works in both modes (no internet — copy `road_graph.graphml`
from another PC).

**Before you leave:** Setup → **Setup checklist** (all green) → **Test home Wi‑Fi** →
**READY FOR OFFLINE**. New: **Quick setup wizard** (3 steps: start → files → build).
On Route: colored **zones**, route summary, **Move stop up/down** + **Re-trace route only**,
field strip with **next-stop distance**, **Recover map** if the canvas goes blank.
Install tab: **Attach install photo** (saved under `tds_data/field_photos/`).
Audit tab: **shift summary** + export.

**Before a field day:** see **[docs/TOMORROW_MORNING.md](docs/TOMORROW_MORNING.md)** for the 5 AM checklist.  
**Proof overnight:** `PROVE.bat` (smoke + demo + golden + benchmark + optional counter sandbox).

## The workflow

1. **Setup tab** *(at home on Wi‑Fi — online mode)*
   - Set your **starting point**: **Search address** (`street, city, CA zip`), USB GPS,
     or coordinates. Wrong home = wrong route order.
   - **Choose** your Excel/CSV (site coordinates) and your `.EST` map file(s).
     Map names come from the upload filename (e.g. `Day5.EST` → Day5).
     **Two maps:** Build opens the map. Tap stop order yourself — blue dot = begin,
     red dot = end. Pick Day 1, then Day 2. Then you can **Merge** — one new best
     driving order from every site, by location from your start.
     Cycle **Map ◀ ▶** to work one day at a time; merge is optional.
   - **Download road map** for these sites (or import `.graphml` from home PC if work Wi‑Fi blocks download).
   - **BUILD OPTIMIZED ROUTE**, then **READY FOR OFFLINE** before you leave.
2. **Route tab** - see the ordered stops (numbered **1, 2, 3…** on the map), total miles,
   estimated drive (from home, between sites, back home), and **~5–8 min setup per hose**.
   The **blue drive line** is traced on real streets (needs road map downloaded).
   Optional **work-site lines** are dashed purple (Excel segment, not the drive path).
   Click a numbered stop to open it.
3. **Map** — standard **Protomaps light** colors (not tied to Sunny/Cloudy/Night panel
   themes). Zoom to neighborhood level for street names. If labels are still sparse,
   re-run `python setup_maps.py` once (wifi) to refresh tiles at zoom 16 + fonts.
4. **START DRIVING** - turn-by-turn banner + offline voice (female Windows guide). Light blue line to the next stop only.
5. **Install tab** — per stop: street, direction, lanes, **Serial #** (type it), **Grab GPS** / drop pin, then **INSTALL** or **SKIP**. Counter USB (connect, clear, download) is **TrafficViewer**, not this app.
   - **Drop pin:** click then drag the orange pin — the final spot is saved. Install / Next will not snap it back.
   - **HTML route / pickup** (Route tab): merged (both days) or separate (one file per map). Pickup links drive to each site’s **install GPS / pin**, not the Excel begin/end dots.
6. **Pickup tab** — mark each site **SECURED**. Download counts in **TrafficViewer**.
7. **Audit tab** - it flags missing data, then **Handoff export** (Excel + Map `.est`). The IG TFC sheet lists sites in **install order** (time marked INSTALL/SKIP), not original office site order. Zip Excel + `.est` for the office — **do not include `.html` or `.kml`** (email antivirus treats extra map viewers as a virus).

## Phone field app (same tabs, smaller screen)

Double-click **`RUN_MOBILE.bat`** and open the printed URL on the phone. First
screen matches laptop Setup: **start address** (search or GPS), Excel + `.EST`,
then **Download / Open job file** (`.tdjob.json`) if the server cannot save.
Tabs: **Setup · Route · Install · Pickup · Audit**.

If the server cannot save (no signal), the phone keeps the shift locally. Tap
**Download job file** (`.tdjob.json`) and later **Open job file** on the start
screen to pick up where you left off. Details: **[docs/MOBILE_WEB.md](docs/MOBILE_WEB.md)**.

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
2. Setup: Excel + `.EST` → **Download road map** → **Build**. Build opens click-to-order (blue = begin, red = end). Two maps: pick each day, then optional Merge. HTML install lists are **HTML route** on the Route tab (`tds_data/exports/`).
3. Route tab: **Map** filter = one day (that day’s pins) or **All days** (both). **HTML route** can save merged or separate lists.
4. Install: **Grab GPS** fills street from internet or **offline road map**; use compass when stopped.
5. End: Audit export (includes MapDay, cross point, wide-street warning).

## Smoke test

Double-click **`SMOKE.bat`** at the project root (uses the project `.venv`).

Full proof chain (smoke + demo + preflight + golden routes + benchmark):

## Cursor / Forge (building this app)

MindLink has two ways to open Cursor for code work:

| How you open Cursor | What it is | When to use |
|---------------------|------------|-------------|
| **This folder only** — `C:\MindLink AI\projects\traffic-deployer` | **App workspace** | Normal daily Forge work on Traffic Deployer |
| **MindLink OS** — `mindlink-os.code-workspace` or `director\02_forge\Open Forge.bat` | **OS workspace** (platform only) | Rules, `mindlink/`, scripts, memory — **not** this app |

**Recommended:** open **this app folder** in Cursor (or `-Lane App -Slug traffic-deployer`), then new Agent chat → `DEMAND: …`. Never multi-root OS + app in one workspace.

On workspace open, `.cursor/hooks.json` writes a ground packet to  
`C:\MindLink AI\logs\system\forge_ground_latest.md` (PRIOR CONTEXT + KEY FILES).  
Read that file first in new chats, or run from OS repo:

```powershell
cd "C:\MindLink AI"
python scripts\forge_ground.py --project traffic-deployer --goal "DEMAND: your task"
```

Ship logs go to **`logs/cursor/forge/YYYY-MM-DD.md`** in this folder (Mind ingests them overnight).

```powershell
PROVE.bat
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
