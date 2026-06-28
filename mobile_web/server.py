"""FastAPI backend for the Traffic Deployer mobile PWA.

Online-first, lean. Reuses desktop core:
  - core.ingest   : parse Excel/CSV + match .EST -> stops
  - core.routing  : order stops + trace route (degrades to straight lines with no road graph)
  - core.export   : IG TFC audit workbook / CSV
  - core.map_state: Qt-free map payload

No USB GPS, no PicoCount, no Qt. Location comes from the phone browser.
"""
from __future__ import annotations

import os
import tempfile

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from core import export, ingest, map_state, routing
from mobile_web import settings
from mobile_web.store import JobStore, link_status, public_job

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
VENDOR_DIR = os.path.join(ROOT, "web", "vendor")
DATA_DIR = os.path.join(ROOT, "tds_data")
JOBS_DIR = os.path.join(DATA_DIR, "mobile_jobs")
UPLOAD_DIR = os.path.join(DATA_DIR, "mobile_uploads")

# Online basemap (no API key). Configurable for a keyed provider in production.
TILE_URL = os.environ.get(
    "TD_MOBILE_TILE_URL",
    "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
)
TILE_ATTRIB = os.environ.get(
    "TD_MOBILE_TILE_ATTRIB",
    "(c) OpenStreetMap contributors",
)

store = JobStore(JOBS_DIR)

app = FastAPI(title="Traffic Deployer Mobile", version="1.0.0")


def _authorize(request: Request, job_id: str) -> dict:
    token = request.headers.get("x-job-token") or request.query_params.get("token", "")
    job = store.get_authorized(job_id, token)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found or token invalid")
    return job


def _require_admin(request: Request) -> None:
    """Gate job creation. In public/share-only mode this needs the admin key."""
    admin = request.headers.get("x-admin-key") or request.query_params.get("admin_key", "")
    if not settings.creation_allowed(admin):
        raise HTTPException(
            status_code=403,
            detail="Job creation is admin-only on this server. Open a job from its share link.",
        )


def _resolve_ttl(request: Request, form_value: float | None = None) -> float | None:
    """Per-job share-link TTL (hours): explicit value wins, else server default.

    Accepts a form/body value or an `expires_in_hours` query param. A value <= 0
    means "no expiry"; absence means "use TD_MOBILE_LINK_TTL_HOURS".
    """
    raw = form_value
    if raw is None:
        raw = request.query_params.get("expires_in_hours")
    if raw is None or str(raw).strip() == "":
        return settings.default_link_ttl_hours() or None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return settings.default_link_ttl_hours() or None
    return v if v > 0 else None


def _share_url(request: Request, job: dict) -> str:
    """Absolute share link: <public-or-origin>/join/<id>?token=<secret>."""
    base = settings.public_base_url()
    if not base:
        base = str(request.base_url).rstrip("/")
    from urllib.parse import quote

    return f"{base}/join/{job['id']}?token={quote(job['token'])}"


def _job_state(job: dict) -> dict:
    return map_state.build_map_state(job["stops"], job.get("home"), job.get("route"))


# --------------------------------------------------------------------------- #
#  Health + config
# --------------------------------------------------------------------------- #
@app.get("/api/healthz")
def healthz() -> dict:
    return {"ok": True, "service": "traffic-deployer-mobile"}


@app.get("/api/config")
def config() -> dict:
    return {
        "tile_url": TILE_URL,
        "tile_attribution": TILE_ATTRIB,
        # Public/share-only mode hides job creation on the phone start screen,
        # UNLESS the operator turned on open uploads (TD_MOBILE_OPEN_CREATE=1).
        "public_mode": settings.public_mode(),
        "can_create": settings.creation_allowed(None),
    }


# --------------------------------------------------------------------------- #
#  Job creation
# --------------------------------------------------------------------------- #
def _build_stops(excel_paths, est_configs, home):
    sites = ingest.parse_excel_sites(excel_paths)
    if not sites:
        raise HTTPException(
            status_code=422,
            detail="No site coordinates found in the Excel/CSV (need begin lat/lon columns).",
        )
    stops = ingest.match_est_files(est_configs, sites, home)
    if not stops:
        raise HTTPException(
            status_code=422,
            detail="0 sites matched. Check that site IDs appear in the .EST files.",
        )
    return stops


@app.post("/api/jobs/import")
async def import_job(
    request: Request,
    home_lat: float = Form(...),
    home_lon: float = Form(...),
    home_label: str = Form("Field start"),
    label: str = Form("Mobile job"),
    expires_in_hours: float = Form(-1.0),
    excel: list[UploadFile] = None,  # type: ignore[assignment]
    est: list[UploadFile] = None,  # type: ignore[assignment]
) -> JSONResponse:
    _require_admin(request)
    ttl = _resolve_ttl(request, None if expires_in_hours < 0 else expires_in_hours)
    excel = excel or []
    est = est or []
    if not excel or not est:
        raise HTTPException(
            status_code=422, detail="Upload at least one Excel/CSV and one .EST file."
        )

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    workdir = tempfile.mkdtemp(prefix="job_", dir=UPLOAD_DIR)
    excel_paths: list[str] = []
    est_configs: list[dict] = []
    try:
        for uf in excel:
            dest = os.path.join(workdir, os.path.basename(uf.filename or "sites.csv"))
            with open(dest, "wb") as f:
                f.write(await uf.read())
            excel_paths.append(dest)
        for i, uf in enumerate(est):
            name = os.path.basename(uf.filename or f"day{i+1}.EST")
            dest = os.path.join(workdir, name)
            with open(dest, "wb") as f:
                f.write(await uf.read())
            label_i = os.path.splitext(name)[0] or f"Day {i+1}"
            est_configs.append({"path": dest, "label": label_i})

        home = (float(home_lat), float(home_lon))
        stops = _build_stops(excel_paths, est_configs, home)
        job = store.create(
            home=home,
            home_label=home_label,
            stops=stops,
            active_files=[c["label"] for c in est_configs],
            label=label,
            expires_in_hours=ttl,
        )
    finally:
        # Raw uploads are not needed after ingest; exports regenerate from job state.
        for p in excel_paths + [c["path"] for c in est_configs]:
            try:
                os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(workdir)
        except OSError:
            pass

    return JSONResponse(
        {"job_id": job["id"], "token": job["token"], "job": public_job(job),
         "state": _job_state(job), "share_url": _share_url(request, job)}
    )


@app.post("/api/jobs/demo")
def import_demo(request: Request) -> JSONResponse:
    """Create a job from the bundled validation fixture (no upload needed)."""
    _require_admin(request)
    from scripts.field_job_fixtures import resolve_field_job

    fx = resolve_field_job()
    est_configs = [{"path": p, "label": lbl} for p, lbl in fx.ests]
    stops = _build_stops([fx.xls], est_configs, fx.home)
    job = store.create(
        home=fx.home,
        home_label=fx.home_label,
        stops=stops,
        active_files=[c["label"] for c in est_configs],
        label=fx.label,
        expires_in_hours=_resolve_ttl(request),
    )
    return JSONResponse(
        {"job_id": job["id"], "token": job["token"], "job": public_job(job),
         "state": _job_state(job), "share_url": _share_url(request, job)}
    )


@app.get("/api/jobs/{job_id}/share")
def job_share(job_id: str, request: Request) -> dict:
    """Return the share link for a job (requires the job token)."""
    job = _authorize(request, job_id)
    return {
        "job_id": job["id"],
        "share_url": _share_url(request, job),
        "link_status": link_status(job),
        "expires_at": job.get("expires_at"),
    }


# --------------------------------------------------------------------------- #
#  Share-link management (admin) — revoke / extend / status
# --------------------------------------------------------------------------- #
@app.get("/api/jobs/{job_id}/status")
def link_status_admin(job_id: str, request: Request) -> dict:
    """Admin: report a link's state without needing the job token."""
    _require_admin(request)
    job = store.load(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {
        "job_id": job_id,
        "link_status": link_status(job),
        "revoked": bool(job.get("revoked")),
        "expires_at": job.get("expires_at"),
    }


@app.post("/api/jobs/{job_id}/revoke")
def revoke_link(job_id: str, request: Request) -> dict:
    """Admin: cut off a share link (lost phone). The token stops working."""
    _require_admin(request)
    job = store.revoke(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"job_id": job_id, "link_status": link_status(job)}


@app.post("/api/jobs/{job_id}/extend")
async def extend_link(job_id: str, request: Request) -> dict:
    """Admin: re-activate / (re)set a link's expiry.

    Body or query `hours`: <= 0 or omitted = no expiry (never times out). Clears
    the revoked flag, so this also un-revokes a link.
    """
    _require_admin(request)
    hours = None
    try:
        body = await request.json()
        if isinstance(body, dict):
            hours = body.get("hours")
    except Exception:
        hours = None
    if hours is None:
        hours = request.query_params.get("hours")
    try:
        hours_f = float(hours) if hours is not None and str(hours).strip() != "" else None
    except (TypeError, ValueError):
        hours_f = None
    job = store.set_expiry(job_id, hours_f)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {
        "job_id": job_id,
        "link_status": link_status(job),
        "expires_at": job.get("expires_at"),
    }


# --------------------------------------------------------------------------- #
#  Job read / route / edits
# --------------------------------------------------------------------------- #
@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict:
    job = _authorize(request, job_id)
    return {"job": public_job(job), "state": _job_state(job)}


@app.get("/api/jobs/{job_id}/map-state")
def get_map_state(job_id: str, request: Request) -> dict:
    job = _authorize(request, job_id)
    return _job_state(job)


def _trace_current_order(job: dict) -> bool:
    """(Re)build the polyline for the job's CURRENT stop order — no re-optimize.

    Field-safe: any routing failure leaves the existing route intact and returns
    False instead of raising, so a phone never crashes on a bad graph/leg.
    """
    stops = job.get("stops") or []
    if not stops:
        job["route"] = {"polyline": [], "miles": 0.0, "graph": False}
        return True
    try:
        home = tuple(job["home"])
        route = routing.build_route(stops, home, DATA_DIR)
    except Exception:
        return False
    job["route"] = {
        "polyline": route.get("polyline", []),
        "miles": float(route.get("miles") or 0.0),
        "graph": bool(route.get("graph")),
    }
    return True


@app.post("/api/jobs/{job_id}/route")
def build_route(job_id: str, request: Request) -> dict:
    """Optimize stop order + trace the route. Runs in the threadpool (sync def)."""
    job = _authorize(request, job_id)
    stops = job["stops"]
    if not stops:
        raise HTTPException(status_code=422, detail="No stops to route.")
    home = tuple(job["home"])
    res = routing.optimize(stops, home, DATA_DIR)
    order = res["order"]
    route = routing.build_route(order, home, DATA_DIR)
    job["stops"] = order
    job["route"] = {
        "polyline": route.get("polyline", []),
        "miles": float(route.get("miles") or 0.0),
        "graph": bool(route.get("graph")),
    }
    store.save(job)
    return {"state": _job_state(job), "graph": res.get("graph", False)}


@app.post("/api/jobs/{job_id}/retrace")
def retrace_route(job_id: str, request: Request) -> dict:
    """Re-draw the drive line for the CURRENT manual order (no re-optimize)."""
    job = _authorize(request, job_id)
    if not (job.get("stops") or []):
        raise HTTPException(status_code=422, detail="No stops to route.")
    traced = _trace_current_order(job)
    store.save(job)
    return {"state": _job_state(job), "traced": traced}


@app.post("/api/jobs/{job_id}/stops/{uid}/move")
async def move_stop(job_id: str, uid: str, request: Request) -> dict:
    """Move a stop up/down in the manual order.

    Body/query `dir`: 'up' or 'down'. This is a cheap list reorder + renumber
    only — it does NOT re-trace the drive line (that can take seconds when a
    road graph is present). Stop numbers update instantly so rapid field taps
    stay snappy; the user taps "Re-trace line" once when the order is set.
    Hitting the top/bottom is a no-op (200), not an error.
    """
    job = _authorize(request, job_id)
    direction = ""
    try:
        body = await request.json()
        if isinstance(body, dict):
            direction = str(body.get("dir") or "")
    except Exception:
        direction = ""
    if not direction:
        direction = request.query_params.get("dir", "")
    if direction not in ("up", "down"):
        raise HTTPException(status_code=400, detail="dir must be 'up' or 'down'.")

    result = store.move_stop(job, uid, direction)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Stop not found.")
    if result == "moved":
        # Mark the traced line stale so the UI can prompt a re-trace.
        job["route"]["stale"] = True
        store.save(job)
    return {"state": _job_state(job), "moved": result == "moved"}


@app.patch("/api/jobs/{job_id}/stops/{uid}")
async def patch_stop(job_id: str, uid: str, request: Request) -> dict:
    job = _authorize(request, job_id)
    patch = await request.json()
    if not isinstance(patch, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object.")
    stop = store.update_stop(job, uid, patch)
    if stop is None:
        raise HTTPException(status_code=404, detail="Stop not found.")
    return {"stop": map_state.public_stop(stop), "state": _job_state(job)}


@app.post("/api/jobs/{job_id}/stops/{uid}/grab")
async def grab_location(job_id: str, uid: str, request: Request) -> dict:
    """Store an exact location from the phone browser geolocation (or a dropped pin)."""
    job = _authorize(request, job_id)
    body = await request.json()
    try:
        lat = float(body["lat"])
        lon = float(body["lon"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="lat and lon are required numbers.")
    if not (32.0 < lat < 42.5 and -125.0 < lon < -114.0):
        raise HTTPException(status_code=422, detail="Location outside California bounds.")
    source = str(body.get("source") or "phone_gps")
    accuracy = body.get("accuracy")

    found = None
    for stop in job["stops"]:
        if stop.get("uid") == uid:
            stop["field_lat"] = lat
            stop["field_lon"] = lon
            stop["field_coord_source"] = source if source in ("phone_gps", "manual") else "phone_gps"
            if accuracy is not None:
                try:
                    stop["field_accuracy_m"] = round(float(accuracy), 1)
                except (TypeError, ValueError):
                    pass
            found = stop
            break
    if found is None:
        raise HTTPException(status_code=404, detail="Stop not found.")
    store.save(job)
    return {"stop": map_state.public_stop(found), "state": _job_state(job)}


# --------------------------------------------------------------------------- #
#  Audit / export
# --------------------------------------------------------------------------- #
@app.get("/api/jobs/{job_id}/audit")
def job_audit(job_id: str, request: Request) -> dict:
    job = _authorize(request, job_id)
    return export.audit(job["stops"])


@app.get("/api/jobs/{job_id}/share.svg")
def share_qr(job_id: str, request: Request) -> Response:
    """QR code (SVG) for the job's share link, so crew can scan instead of type."""
    job = _authorize(request, job_id)
    url = _share_url(request, job)
    try:
        import io

        import segno
    except ImportError:
        raise HTTPException(status_code=503, detail="QR support not installed (segno).")
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=5, border=2)
    return Response(content=buf.getvalue(), media_type="image/svg+xml")


@app.get("/api/jobs/{job_id}/export.csv")
def export_csv(job_id: str, request: Request) -> Response:
    job = _authorize(request, job_id)
    text = export.to_csv_text(job["stops"])
    fname = f"IG_TFC_{job_id}.csv"
    return Response(
        content=text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/api/jobs/{job_id}/export.xlsx")
def export_xlsx(job_id: str, request: Request) -> Response:
    job = _authorize(request, job_id)
    data, err = export.to_excel_result(job["stops"], data_dir=DATA_DIR)
    if data is None:
        raise HTTPException(status_code=503, detail=err or "Excel export unavailable.")
    fname = f"IG_TFC_{job_id}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# --------------------------------------------------------------------------- #
#  Static PWA (mounted last so /api wins)
# --------------------------------------------------------------------------- #
if os.path.isdir(VENDOR_DIR):
    app.mount("/vendor", StaticFiles(directory=VENDOR_DIR), name="vendor")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/join/{job_id}")
def join(job_id: str) -> FileResponse:
    """Share-link entry. Serves the PWA shell; the client reads job_id + token
    from the URL (/join/<id>?token=...) and opens the job automatically."""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/sw.js")
def service_worker() -> FileResponse:
    # Served from root so its scope covers the whole app.
    return FileResponse(
        os.path.join(STATIC_DIR, "sw.js"), media_type="text/javascript"
    )


@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    return FileResponse(
        os.path.join(STATIC_DIR, "manifest.webmanifest"),
        media_type="application/manifest+json",
    )


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
