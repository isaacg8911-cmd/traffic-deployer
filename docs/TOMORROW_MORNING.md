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

## PicoCount (Install)

1. Plug USB download cable → **Refresh** ports → **Connect** (green status chip).
2. **Read serial** → Serial # fills on form.
3. **Clear & set ID** only when starting a **new** study at that site (confirms dialog).
4. Complete **Grab GPS**, street, **INSTALL**.

## Drive + Pickup

- **START DRIVING** — voice/banner, map follow.
- **Pickup** — **SECURED** per site; **Download counter data** when study is done (needs counts in counter).
- If download says empty: run a study on the counter first, or counter was cleared.

## Audit

- **Refresh shift summary** — should mention PicoCount counts if configured.
- **Export Excel** — columns include `CounterUnitID`, `CounterSerial`, `CounterCleared`, `CounterDownload`.

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
