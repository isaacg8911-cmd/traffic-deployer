# Offline contract (field mode)

When **READY FOR OFFLINE** is on (`offline_mode` + `core.offline_policy`):

## Allowed (local only)

- `tds_data/california.pmtiles` — basemap
- `tds_data/road_graph.graphml` — routing
- Encrypted profile / shift save
- `http://127.0.0.1` — local map server (`local_server.py`)
- USB GPS serial

## Blocked (no public internet)

- Address geocode (`core/geo.py` — Census, Nominatim, Photon)
- Online reverse geocode
- Road map download (Overpass / osmnx)
- `core/connectivity.geocode_hosts_reachable()` — skipped

## Home setup (online mode)

- Address search, road download, connectivity hints
- Tap **RESUME ONLINE MODE** when back on Wi‑Fi

## Proof

- `scripts/smoke_full.py` — `[offline field — no internet]`
- `scripts/test_offline_session.py` — field contract
- `scripts/diagnose_network.py` — home Wi‑Fi only (WARN if blocked, not field-critical)
