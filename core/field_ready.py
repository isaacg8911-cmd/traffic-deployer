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
    gps_snapshot: dict | None = None,
    stop_server_after: bool = True,
) -> dict:
    web = os.path.join(app_dir, "web")
    data = os.path.join(app_dir, "tds_data")
    pmtiles = os.path.join(data, "california.pmtiles")
    fonts = os.path.join(web, "vendor", "fonts", "Noto Sans Regular", "0-255.pbf")
    maplibre = os.path.join(web, "vendor", "maplibre-gl.js")

    items: list[dict] = []

    if os.path.isfile(pmtiles):
        mb = os.path.getsize(pmtiles) / (1024 * 1024)
        items.append(_item("basemap", f"California offline map ({mb:.0f} MB)", True))
    else:
        items.append(_item("basemap", "California offline map", False, level="fail",
                           detail="Run setup_maps.py once on WiFi"))

    items.append(_item("fonts", "Street label fonts", os.path.isfile(fonts), level="fail",
                       detail="Re-run setup_maps.py"))

    items.append(_item("maplibre", "Map engine (MapLibre)", os.path.isfile(maplibre), level="fail",
                       detail="Run setup_maps.py"))

    for rel in ("style.js", "app.js", "index.html"):
        items.append(_item(f"web_{rel}", f"Map UI ({rel})", os.path.isfile(os.path.join(web, rel))))

    try:
        import road_router
        has_g = road_router.has_graph(data)
        if has_g:
            g = road_router.load_graph(data)
            n = len(g.nodes) if g else 0
            items.append(_item("roads", f"Road routing graph ({n:,} nodes)", True))
        else:
            items.append(_item("roads", "Road routing graph", False, level="warn",
                               detail="Setup → Download road map (needs WiFi + your sites)"))
    except Exception as exc:
        items.append(_item("roads", "Road routing graph", False, level="warn", detail=str(exc)))

    try:
        import voice_nav
        items.append(_item("voice", "Voice navigation (pyttsx3)",
                           voice_nav.tts_available(), level="warn",
                           detail=voice_nav.tts_error() or "pip install pyttsx3"))
    except Exception as exc:
        items.append(_item("voice", "Voice navigation", False, level="warn", detail=str(exc)))

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
    "Tonight (WiFi): Excel + .EST loaded → Download road map → BUILD ROUTE → Test voice (Zira).",
    "Tap READY FOR OFFLINE before you leave.",
    "In the field: plug GPS → START DRIVING → Follow Me (street-name zoom).",
    "Each stop: Grab GPS → INSTALL or SKIP → end of day Audit export.",
]
