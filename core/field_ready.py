"""Pre-field health checks — no job files required."""
from __future__ import annotations

import os
import urllib.request

# Item: {id, label, ok, level, detail}
# level: ok | warn | fail


def _item(iid: str, label: str, ok: bool, *, level: str = "fail", detail: str = "") -> dict:
    if ok:
        lvl = "ok"
    else:
        lvl = "warn" if level == "warn" else "fail"
    return {"id": iid, "label": label, "ok": ok, "level": lvl, "detail": detail}


def _gps_item(gps: dict | None) -> dict:
    if not gps:
        return _item("gps", "USB GPS", False, level="warn",
                     detail="Plug receiver in before launch; refresh ports on Setup")
    if gps.get("fix"):
        return _item("gps", "USB GPS fix", True, detail=f"{gps.get('satellites', 0)} satellites")
    if gps.get("connected"):
        return _item("gps", "USB GPS detected (no fix yet)", True, level="warn",
                      detail="Normal indoors — test outside before driving")
    return _item("gps", "USB GPS", False, level="warn",
                  detail="Plug receiver in before launch; refresh ports on Setup")


def check_all(
    app_dir: str,
    *,
    probe_gps: bool = True,
    probe_counter: bool = False,
    gps_snapshot: dict | None = None,
    stop_server_after: bool = True,
) -> dict:
    try:
        from ui.paths import DATA_DIR, IS_PORTABLE, LAUNCH_HINT, WEB_DIR
    except Exception:
        WEB_DIR = os.path.join(app_dir, "web")
        DATA_DIR = os.path.join(app_dir, "tds_data")
        IS_PORTABLE = False
        LAUNCH_HINT = "Run START.bat"

    web = WEB_DIR
    data = DATA_DIR
    pmtiles = os.path.join(data, "california.pmtiles")
    fonts = os.path.join(web, "vendor", "fonts", "Noto Sans Regular", "0-255.pbf")
    if not os.path.isfile(fonts):
        fonts = os.path.join(data, "vendor", "fonts", "Noto Sans Regular", "0-255.pbf")
    maplibre = os.path.join(web, "vendor", "maplibre-gl.js")
    if not os.path.isfile(maplibre):
        maplibre = os.path.join(data, "vendor", "maplibre-gl.js")

    map_fix = (
        "Setup -> Download California map (Wi-Fi), or use Work Laptop zip from home"
        if IS_PORTABLE
        else f"{LAUNCH_HINT} once on Wi-Fi, or copy tds_data from home PC"
    )

    items: list[dict] = []

    if os.path.isfile(pmtiles):
        mb = os.path.getsize(pmtiles) / (1024 * 1024)
        if mb < 100:
            items.append(_item("basemap", "California offline map", False, level="fail",
                               detail=f"Incomplete download ({mb:.0f} MB) — {map_fix}"))
        else:
            items.append(_item("basemap", f"California offline map ({mb:.0f} MB)", True))
    else:
        items.append(_item("basemap", "California offline map", False, level="fail",
                           detail=map_fix))

    items.append(_item("fonts", "Street label fonts", os.path.isfile(fonts), level="fail",
                       detail=(
                           "Re-extract Work Laptop zip (_internal/web/vendor)"
                           if IS_PORTABLE and not os.path.isfile(fonts)
                           else "Setup -> Download California map"
                       )))

    items.append(_item("maplibre", "Map engine (MapLibre)", os.path.isfile(maplibre), level="fail",
                       detail=(
                           "Re-extract Work Laptop zip (_internal/web/vendor)"
                           if IS_PORTABLE and not os.path.isfile(maplibre)
                           else "Setup -> Download California map"
                       )))

    for rel in ("style.js", "app.js", "index.html"):
        missing_detail = (
            "Re-extract full zip — need _internal/web beside exe"
            if IS_PORTABLE
            else f"Missing {rel} under web/"
        )
        items.append(_item(
            f"web_{rel}", f"Map UI ({rel})",
            os.path.isfile(os.path.join(web, rel)),
            detail=missing_detail if not os.path.isfile(os.path.join(web, rel)) else "",
        ))

    try:
        import road_router
        from core import hardware_profile as hw
        if road_router.graph_file_exists(data):
            if hw.is_work_laptop():
                mb = os.path.getsize(road_router.graph_path(data)) / (1024 * 1024)
                items.append(_item(
                    "roads", f"Road routing graph file ({mb:.0f} MB on disk)", mb > 0.01,
                    detail="Loads on first route use — skipped at startup on low RAM",
                ))
            elif road_router.has_graph(data):
                g = road_router.load_graph(data)
                n = len(g.nodes) if g else 0
                items.append(_item("roads", f"Road routing graph ({n:,} nodes)", n > 0))
            else:
                detail = "File on disk but will not load"
                if not road_router.HAS_ROUTING:
                    detail = (
                        "Re-extract Work Laptop zip from home"
                        if IS_PORTABLE
                        else f"road_graph.graphml present — {LAUNCH_HINT} (osmnx in .venv)"
                    )
                else:
                    detail = "road_graph.graphml may be corrupt — re-download or re-import"
                items.append(_item("roads", "Road routing graph", False, level="warn", detail=detail))
        else:
            items.append(_item("roads", "Road routing graph", False, level="warn",
                               detail="Setup → Download (WiFi) or Import road_graph.graphml from home PC"))
    except Exception as exc:
        items.append(_item("roads", "Road routing graph", False, level="warn", detail=str(exc)))

    try:
        from core import export
        eng_ok, eng_detail = export.excel_engine_ok()
        items.append(_item(
            "excel", "Excel export engine", eng_ok,
            level="warn" if not eng_ok else "ok",
            detail=eng_detail,
        ))
    except Exception as exc:
        items.append(_item("excel", "Excel export engine", False, level="warn", detail=str(exc)))

    try:
        import persistence
        items.append(_item("save", "Encrypted local save",
                           getattr(persistence, "HAS_CRYPTO", False), level="warn",
                           detail="Install cryptography for encrypted shifts"))
    except Exception:
        items.append(_item("save", "Local save", False, level="warn"))

    server_was_up = False
    try:
        import local_server
        server_was_up = local_server.is_running()
        port = local_server.start(web, data)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=4) as r:
            body = r.read(4000).decode("utf-8", errors="replace")
        items.append(_item("server", "Local map server", "Traffic Deployer Map" in body))
        if stop_server_after and not server_was_up:
            local_server.stop()
    except Exception as exc:
        items.append(_item("server", "Local map server", False, level="fail", detail=str(exc)))
        try:
            import local_server
            if stop_server_after and not server_was_up:
                local_server.stop()
        except Exception:
            pass

    try:
        from core import picocount

        items.append(_item(
            "picocount_doc",
            "PicoCount protocol reference",
            picocount.protocol_doc_present(),
            level="warn",
            detail="docs/PicoCountSerialProtocol.pdf (VehicleCounts developer PDF)",
        ))
        if probe_counter:
            ports = picocount.list_serial_ports()
            if ports:
                pr = picocount.probe_port()
                if pr.ok:
                    items.append(_item(
                        "picocount",
                        f"PicoCount USB ({pr.port})",
                        True,
                        detail="Counter responding — ready for install/pickup",
                    ))
                else:
                    items.append(_item(
                        "picocount",
                        "PicoCount USB",
                        False,
                        level="warn",
                        detail=pr.message,
                    ))
            else:
                items.append(_item(
                    "picocount",
                    "PicoCount USB (optional)",
                    False,
                    level="warn",
                    detail="Plug VehicleCounts download cable before install",
                ))
        else:
            pr = picocount.quick_counter_status()
            if pr.ok:
                label = (
                    f"PicoCount port ({pr.port})"
                    if pr.port
                    else "PicoCount USB (optional)"
                )
                items.append(_item("picocount", label, True, detail=pr.message))
            else:
                items.append(_item(
                    "picocount",
                    "PicoCount USB (optional)",
                    False,
                    level="warn",
                    detail=pr.message,
                ))
    except Exception as exc:
        items.append(_item(
            "picocount",
            "PicoCount support",
            False,
            level="warn",
            detail=str(exc),
        ))

    if gps_snapshot is not None:
        items.append(_gps_item(gps_snapshot))
    elif probe_gps:
        try:
            import gps_reader
            st = gps_reader.get_status(attempts=3)
            items.append(_gps_item(st))
        except Exception as exc:
            items.append(_item("gps", "USB GPS", False, level="warn", detail=str(exc)))

    fails = [i for i in items if i["level"] == "fail"]
    warns = [i for i in items if i["level"] == "warn"]
    score = max(0, 100 - len(fails) * 18 - len(warns) * 6)

    return {
        "items": items,
        "score": min(100, score),
        "field_ready": len(fails) == 0,
        "drive_ready": len(fails) == 0 and any(i["id"] == "roads" and i["ok"] for i in items),
        "fail_count": len(fails),
        "warn_count": len(warns),
    }


TOMORROW_STEPS = [
    "Tonight (WiFi): Excel + .EST loaded → Download road map → BUILD ROUTE.",
    "Tap READY FOR OFFLINE before you leave.",
    "In the field: plug GPS → START DRIVING → Follow Me on the map.",
    "Each stop: Grab GPS → INSTALL or SKIP → end of day Audit export.",
]
