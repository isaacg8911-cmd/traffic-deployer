# Traffic Deployer

Desktop field tool for traffic deployers: offline California map, **Excel + `.EST`** ingest, **efficient multi-stop routing on real streets**, USB GPS live trace, install/pickup tracking, and audit export. Data stays on the laptop.

## Quick start

1. Install [Python 3.10+](https://www.python.org/downloads/)
2. Double-click **`START.bat`**
3. Follow **[HOW_TO_RUN.md](HOW_TO_RUN.md)**

## Documentation

| Doc | Contents |
|-----|----------|
| [HOW_TO_RUN.md](HOW_TO_RUN.md) | Daily workflow, GPS, offline mode, smoke tests |
| **PROVE.bat** | One-click: smoke + demo + preflight (no GUI) |
| [ROUTING_AND_MAP.md](ROUTING_AND_MAP.md) | **How efficient routes are built and traced on the map** (segment lines, OSM graph, ordering, polylines) |
| [PORTABLE_INSTALL.txt](PORTABLE_INSTALL.txt) | Work-laptop unzip checklist |

## Routing in one sentence

Sites are **street segments** (begin/end); the app downloads a local **road graph**, **orders** segments to minimize drive miles between **line crossings**, then **traces** the tour on OSM drive geometry for the map and turn-by-turn driving.

## License / data

Field job files and `tds_data/` are local and git-ignored. Map tiles from [Protomaps](https://protomaps.com/); routing from [OpenStreetMap](https://www.openstreetmap.org/) via [OSMnx](https://osmnx.readthedocs.io/).
