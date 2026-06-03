# PicoCount 2500 — Traffic Deployer integration (spec)

**Hardware:** PicoCount 2500 via VehicleCounts USB download adapter (FTDI → COM port, typically **921600** baud).  
**Protocol:** `docs/PicoCountSerialProtocol.pdf` (VehicleCounts developer PDF — in repo).  
**Implementation:** `core/picocount.py` — no TrafficViewer Pro install required.

---

## Director workflow (target)

### Install (counter plugged in at site)

1. Traffic Deployer shows **Counter: Connected** (or error) on the Install tab.
2. Director taps **Clear & configure counter**.
3. App:
   - **Clears** unit memory (same intent as TrafficViewer *Clear Unit Data* — syncs clock, one study only).
   - Sets **Unit ID** from current stop + direction + layout tag.
4. Director completes install (street, serial, INSTALL) as today.

### Pickup (same counter, study complete)

1. Director taps **Download counter data**.
2. App downloads study to `tds_data/counter_downloads/<profile>/` as `.tvp` (native) plus metadata on the stop record.
3. Later: professional report from downloaded files (separate package).

---

## Unit ID format (locked)

Pattern:

```text
{site_id}{facing}c1b
```

| Part | Rule | Example |
|------|------|---------|
| `site_id` | Site number from route (Excel id), digits only | `1234` |
| `facing` | **`n` or `e` only** — from Install **Dir** when N/E; otherwise from GPS heading (nearest of N/E) | `n` or `e` |
| suffix | Fixed hose/layout tag | `c1b` |

Examples: `1234nc1b`, `1234ec1b`.

Stored on stop: `counter_unit_id`, `counter_cleared_at`, `counter_download_path`.

---

## Implementation map (Forge)

| Step | Module | Status |
|------|--------|--------|
| Unit ID builder | `core/picocount.py` → `build_unit_id()` | Ready |
| List COM / probe open | `core/picocount.py` → `probe_port()` | Ready (link only) |
| Clear + set Unit ID | `core/picocount.py` → `clear_and_configure()` | **Done** |
| Download study | `core/picocount.py` → `download_study()` → `.pcbin` + `.json` | **Done** |
| Install UI | Install tab → PicoCount 2500 (USB) | **Done** |
| Pickup UI | Download counter data | **Done** |
| Audit / Excel | `CounterUnitID`, `CounterSerial`, `CounterCleared`, `CounterDownload` columns | **Done** (v1.0.5) |
| Field readiness | Protocol PDF + optional COM probe in Setup report | **Done** (v1.0.5) |
| Reports | Professional PDF/Excel from `.pcbin` | **Next** (needs sample study + template) |

---

## Isaac — one action to unblock

1. Open https://vehiclecounts.com/downloads.html  
2. Download **PicoCount Serial Communications Protocol for Developers (PDF)**  
3. Save as: `projects/traffic-deployer/docs/PicoCountSerialProtocol.pdf`  
4. Tell Forge: **protocol PDF in docs**

No guesswork on COM10 until that file is in the repo.

---

## Out of scope (until approved)

- Replacing TrafficViewer Pro reports 1:1 without sample outputs  
- Cloud upload of count data  
- Non–PicoCount 2500 models without separate spec  
