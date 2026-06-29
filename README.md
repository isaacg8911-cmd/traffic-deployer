# Traffic Deployer

Two delivery surfaces only (**SCOPE.md**):

| Surface | For |
|---------|-----|
| **Work laptop exe** | Offline field desktop — USB GPS, PicoCount, California map |
| **Render web app** | Hosted mobile PWA — crew share links |

## Work laptop — quick start

1. Home PC: `BUILD_WORK_LAPTOP.bat` → `VERIFY_WORK_LAPTOP.bat`
2. Copy `dist\TrafficDeployer-WorkLaptop.zip` to field laptop
3. Unzip → **`OPEN_APP.bat`**

Full handover: **[WORK_LAPTOP.md](WORK_LAPTOP.md)** · daily dev: **[HOW_TO_RUN.md](HOW_TO_RUN.md)**

## Render mobile — quick start

1. Deploy via `render.yaml` on Render
2. Prove: `scripts/mobile_host_smoke.py`

Guide: **[docs/MOBILE_HOST_DEPLOY.md](docs/MOBILE_HOST_DEPLOY.md)**

## Documentation

| Doc | Contents |
|-----|----------|
| [HOW_TO_RUN.md](HOW_TO_RUN.md) | Desktop workflow, GPS, offline mode, smoke tests |
| [WORK_LAPTOP.md](WORK_LAPTOP.md) | Zip handover, updates, USB fixes |
| [docs/MOBILE_HOST_DEPLOY.md](docs/MOBILE_HOST_DEPLOY.md) | Render deploy + share links |
| [ROUTING_AND_MAP.md](ROUTING_AND_MAP.md) | Route build and map trace |

## Routing in one sentence

Sites are **street segments**; the app downloads a local **road graph**, **orders** segments to minimize drive miles, then **traces** the tour on OSM geometry.

## License / data

Field job files and `tds_data/` are local and git-ignored. Map tiles from [Protomaps](https://protomaps.com/); routing from [OpenStreetMap](https://www.openstreetmap.org/) via [OSMnx](https://osmnx.readthedocs.io/).
