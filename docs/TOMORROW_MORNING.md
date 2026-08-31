# Tomorrow morning — 5 AM test run (Traffic Deployer v1.0.6)

One session (~45 min). Forge already ran **PROVE** overnight; you confirm on the truck laptop.

## Before you leave the desk

1. Double-click **`PROVE.bat`** (or `SMOKE.bat` if short on time) — expect **PROVE PASS**.
2. Optional with counter plugged in:  
   `.venv\Scripts\python.exe scripts\picocount_sandbox.py --port COM10`
3. Double-click **`START.bat`** — window title should show **v1.0.6**.

## Setup tab (Wi‑Fi, online)

| Step | Pass criteria |
|------|----------------|
| Starting point | Not factory default; search or GPS |
| Excel + .EST | Both lists populated |
| Road map | Download or import `road_graph.graphml` |
| Field readiness | Score **82+** (100 if basemap + counter connected) |
| **PLAN ROUTE** | Pick on map **or** auto-optimize |
| Route order window | Picks list updates; drag to reorder |
| **READY FOR OFFLINE** | Checklist all green |

## PicoCount (TrafficViewer — not this app)

Connect, clear, and download counters in **TrafficViewer**. This app tracks the site (GPS, serial you type, INSTALL / SECURED).

1. Type **Serial #** on the Install form (from the unit or TrafficViewer).
2. **Grab GPS**, street, **INSTALL**.

## Drive + Pickup

- **START DRIVING** — voice/banner, map follow.
- **Pickup** — **SECURED** per site. Download counts in **TrafficViewer**.

## Audit

- **Refresh shift summary**
- **Export Excel** — install/pickup columns. Volume/count files come from TrafficViewer.

## Paste to Forge after field test

```text
FIELD-PROOF: YYYY-MM-DD app=traffic-deployer version=1.0.6
pass: ...
fail: ...
feel: ...
trust: yes / no / with fixes
```

## If something breaks

| Symptom | Fix |
|---------|-----|
| Orange route line | Download/import road map, rebuild route |
| Map blank | Route tab → **Recover map** |
| Counter no ACK | Cable, COM port, **Refresh**, try sandbox script |
| PROVE fail | Send Forge the failing step number from the console |
