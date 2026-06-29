# Work laptop handover (Traffic Deployer)

**Goal:** One zip, no Python on the work laptop, offline map + routing included.

**Your laptop (LAPTOP-FLHPOPIS):** Intel N200 · 4 GB RAM · Intel UHD · ~24 GB free disk.  
The app enables **work-laptop mode** automatically (also forced by `OPEN_APP.bat`). Expect a smaller window, leaner map in the field, and throttled GPS updates so SwiftShader does not exhaust RAM.

**Before you leave Wi‑Fi:** close Chrome/Edge tabs, pause OneDrive if the install folder syncs, keep **10+ GB free** on `C:`. Install to `C:\TrafficDeployer` — not Documents.

---

## Tonight on home PC (Wi‑Fi)

| Step | Do this | Pass |
|------|---------|------|
| 1 | `START.bat` once if you have not already (downloads ~1.4 GB California map) | Map file in `tds_data\california.pmtiles` |
| 2 | Setup tab: load **Excel + .EST** → **Download road map** → **BUILD OPTIMIZED ROUTE** | `tds_data\road_graph.graphml` exists |
| 3 | Double-click **`BUILD_WORK_LAPTOP.bat`** | Builds exe + packs map/graph into zip (~15–20 min first time) |
| 4 | Double-click **`VERIFY_WORK_LAPTOP.bat`** | Prints **WORK LAPTOP VERIFY PASS** |
| 5 | Copy **`dist\TrafficDeployer-WorkLaptop.zip`** to USB or work laptop | Zip ~1.5 GB |

Optional proof: `SMOKE.bat` or `PROVE.bat` on home PC before step 3.

---

## Tomorrow on work laptop (one time)

**Clean laptop / deleted old copy?** Read **`WORK_LAPTOP_FRESH_INSTALL.txt`** inside the zip — you only need the new zip from home.

1. **Unzip** `TrafficDeployer-WorkLaptop.zip` anywhere (e.g. `C:\TrafficDeployer`).
2. Right-click zip → **Properties** → **Unblock** (if shown) → OK.
3. Open the **`TrafficDeployer`** folder inside the unzip location.
4. Double-click **`OPEN_APP.bat`** — unblocks Windows security and starts the app.  
   (Do **not** use `START.bat` — dev/source only.)
5. Window title should show current version (e.g. **v1.0.8**).

**You do not need** anything left on the work laptop from a previous install. Shift data will save fresh in `tds_data\` after you run the app.

### First launch checklist (Setup tab, Wi‑Fi)

1. **Starting point** — search address or USB GPS (not factory default).
2. **Excel + .EST** — choose this week’s files (or **Load demo files** for desk test).
3. **Road map** — should already be green (included in zip). If not: **Import road map from file** → pick `tds_data\road_graph.graphml` beside the exe.
4. **BUILD OPTIMIZED ROUTE** → confirm stops and segment lines on map.
5. **READY FOR OFFLINE** — all checklist green before you leave.

After **READY FOR OFFLINE**, Setup hides on the road — use Route / Install / Pickup / Audit only.

---

## Data rules (do not mix these up)

| What | Where it lives | Rule |
|------|----------------|------|
| App + offline map | Inside unzipped `TrafficDeployer\` folder | Replace from a **new zip** when updating the app |
| Shift / install / pickup data | `TrafficDeployer\tds_data\` on **work laptop** | **Stays on work laptop** — your field truth |
| Road graph for this job | `tds_data\road_graph.graphml` | Built at home for your sites; included in zip if you ran step 2 above |
| Counter downloads | `tds_data\counter_downloads\` | Created in the field; do not delete |

## Updating the app (already installed on work laptop)

**Use the small update — not the full 1.6 GB zip.**

| Home PC | Work laptop |
|---------|-------------|
| Double-click **`BUILD_APP_UPDATE.bat`** | Copy `dist\TrafficDeployer-AppUpdate\TrafficDeployer\` to USB (~800 MB, **no zip**) |
| | Copy **exe + `_internal\` + `web\`** over existing install |
| | **Keep** `tds_data\` — map + shift data stay put |

Steps on the laptop: read **`APP_UPDATE.txt`** in the update folder (also in `packaging\`).  
**Tip:** pause OneDrive if install is in Documents; copy to `C:\TDUpdate` first, then replace the three app pieces.

**Full zip (`BUILD_WORK_LAPTOP.bat`) only when:** first install, new laptop, or `tds_data\california.pmtiles` is missing.

**Do not** copy home `tds_data` onto work laptop unless you intentionally want to overwrite work shift files.

---

## If something breaks

| Symptom | Fix |
|---------|-----|
| App won’t start | Unblock zip (right‑click zip → Properties → Unblock), extract again |
| Map blank | Route tab → **Recover map** |
| Orange segments / weak routing | Import `road_graph.graphml` or rebuild route on Wi‑Fi |
| “Incomplete map” | Zip was built without home map — re-run `START.bat` + `BUILD_WORK_LAPTOP.bat` |
| Counter no COM / wrong port | Plug PicoCount USB; Install → **Refresh** (GPS COM hidden from list) |
| **Left USB “not recognized”** — right port OK | Run **`FIX_USB.bat`** as Administrator → reboot → retest left port; see **One bad laptop USB port** below |
| Must swap GPS and Pico on one USB port | Use **two laptop USB ports** — see **USB GPS + PicoCount** below |
| App crashed on counter | Copy `tds_data\crashes\` to USB — see **Crash logs** below |
| Slow map / fan loud | Normal on 4 GB — status bar shows **Work laptop**; use **FOLLOW GPS** |
| Out of disk space | Need ~2 GB free beside the zip; delete old zips, clear Downloads |
| VERIFY fails on home PC | Read FAIL lines; usually missing map or road graph |

Full field morning list: **`docs/TOMORROW_MORNING.md`**.

---

## One bad laptop USB port (left fails, right works)

Windows shows **“USB device not recognized”** before Traffic Deployer ever sees a COM port. The app cannot fix a dead port — fix Windows/hardware or use a good port.

### Field tonight (no admin)

1. Plug **GPS** and **PicoCount** into **right-side USB ports** (two separate ports if you have them).
2. If only one good port: GPS in truck for driving; swap to PicoCount at each install (unplug → wait 3 s → replug → Install → **Refresh**).
3. Optional: **powered USB 3 hub** into the **working** port, then plug both cables into the hub.

### Fix at home (admin, ~10 min)

**Fast path:** double-click **`FIX_USB.bat`** as Administrator (included in zip, or copy **`dist\USB-Fix-Kit.zip`** from home via **`BUILD_USB_FIX_KIT.bat`**). Reboot when prompted, then retest the left port.

Manual steps if you prefer Device Manager:

| Step | Action |
|------|--------|
| 1 | **Device Manager** → **View** → **Show hidden devices** → under **Universal Serial Bus devices**, uninstall grey **Unknown USB Device** entries (check **Delete driver** if offered). Reboot. |
| 2 | **Device Manager** → expand **Universal Serial Bus controllers** → for **each USB Root Hub** and **USB Composite Device** → **Properties** → **Power Management** → **uncheck** “Allow the computer to turn off this device to save power”. Reboot. |
| 3 | **Settings** → **System** → **Power** → when plugged in, set **Sleep** to **Never** (field laptops should stay on AC in the truck). |
| 4 | Laptop maker’s support site → download latest **chipset** + **USB** drivers for **LAPTOP-FLHPOPIS** → install → reboot. |
| 5 | Plug GPS into **left** port only → Device Manager → **Ports (COM & LPT)** — if nothing appears, left port is likely **hardware** (bent pin, loose jack). Use right port permanently or get IT/repair. |

**Proof the port is OK:** Device Manager shows **Prolific** / **u-blox** / **USB Serial** under Ports when the device is plugged in, and Install → **Refresh** lists the PicoCount port.

---

## USB GPS + PicoCount (field)

| Do | Why |
|----|-----|
| Plug **GPS** and **PicoCount download cable** into **separate working laptop USB ports** | One hub/port often cannot keep both COM ports stable |
| Use a **powered USB 3 hub** only if both cables must share a hub | Under-powered hubs drop COM3/COM4 |
| Install → **Refresh** only when on site (app pauses GPS ~1 s while counter talks) | Windows allows one app per COM port |
| If a laptop port shows no devices in Device Manager → Ports | Try another port, re-seat cable, reboot |

**Install tab:** Port dropdown shows PicoCount/USB serial only — GPS COM is hidden on purpose.

---

## Crash logs (copy to home PC)

If the app closes unexpectedly or shows a counter error with a log filename:

1. Open `TrafficDeployer\tds_data\crashes\`
2. Copy the newest `crash_*.log` or `error_*.log` to USB
3. Send to creator laptop for Forge review

Shift data in `tds_data\` is separate — crash logs do not contain client job files.

---

## Two install paths (pick one)

| Path | When |
|------|------|
| **Work laptop zip** (this doc) | Work PC has no Python — use `TrafficDeployer.exe` |
| **Home dev PC** | Build/test source with `START.bat` — ships via `BUILD_WORK_LAPTOP.bat`, not as a field product |
