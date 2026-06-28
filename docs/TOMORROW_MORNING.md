# Tomorrow morning — field test (Traffic Deployer)

~45 min on the **work laptop**. Forge runs **PROVE** on home PC overnight; you confirm in the truck.

## Which laptop?

| Install | Launch | Doc |
|---------|--------|-----|
| **Work laptop zip** (usual) | `OPEN_APP.bat` | [WORK_LAPTOP.md](../WORK_LAPTOP.md) |
| Dev / source | `START.bat` | [HOW_TO_RUN.md](../HOW_TO_RUN.md) |

Check window title for current version (see `version.py`, e.g. **v1.0.8**).

## Before you leave the desk (home PC)

1. **`VERIFY_WORK_LAPTOP.bat`** — must print **WORK LAPTOP VERIFY PASS**.
2. Optional: **`PROVE.bat`** on home PC if you changed code today.
3. USB has **`dist\TrafficDeployer-WorkLaptop.zip`** (or already unzipped on work laptop).

## Work laptop — first open

1. Unzip if needed → open **`TrafficDeployer`** folder → **`OPEN_APP.bat`**.
2. Plug **USB GPS** before or right after launch.
3. Setup tab (Wi‑Fi, online):

| Step | Pass criteria |
|------|----------------|
| Starting point | Not factory default; search or GPS |
| Excel + .EST | Both lists populated |
| Road map | Green — included in zip, or import `tds_data\road_graph.graphml` |
| Field readiness | Score **82+** |
| **BUILD OPTIMIZED ROUTE** | Blue drive line on map |
| **READY FOR OFFLINE** | Checklist all green |

## PicoCount (Install)

1. Plug USB download cable → **Refresh** → **Connect** (green).
2. **Read serial** → Serial # fills.
3. **Clear & set ID** only for a **new** study (confirms dialog).
4. **Grab GPS** → street → **INSTALL**.

## Drive + Pickup

- **START DRIVING** — banner + map follow.
- **Pickup** — **SECURED**; **Download counter data** when study is done.

## Audit

- **Refresh shift summary**
- **Export Excel** — PicoCount columns present if counter used.

## Paste to Forge after field test

```text
FIELD-PROOF: YYYY-MM-DD app=traffic-deployer version=<from About>
pass: ...
fail: ...
feel: ...
trust: yes / no / with fixes
```

## If something breaks

| Symptom | Fix |
|---------|-----|
| App won't start | Unblock zip; extract again; run from `TrafficDeployer` folder |
| Orange route line | Import road graph or rebuild on Wi‑Fi |
| Map blank | Route tab → **Recover map** |
| VERIFY failed at home | Re-run `START.bat` + build route + `BUILD_WORK_LAPTOP.bat` |
| Counter no ACK | Cable, COM port, **Refresh**, sandbox script on dev PC |
