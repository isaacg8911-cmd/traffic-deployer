# Always-on host image for the Traffic Deployer MOBILE PWA (share-only public mode).
# Build:  docker build -t td-mobile .
# Run:    docker run -p 8000:8000 -e TD_MOBILE_PUBLIC=1 -e TD_MOBILE_ADMIN_KEY=... td-mobile
#
# This serves the SAME FastAPI backend (mobile_web.server) as the laptop tunnel,
# but on an always-on box so the share link works without your laptop running.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TD_MOBILE_PUBLIC=1 \
    PORT=8000

WORKDIR /app

# Install deps first for layer caching.
COPY deploy/requirements-host.txt /app/deploy/requirements-host.txt
RUN pip install --no-cache-dir -r deploy/requirements-host.txt

# App code (see .dockerignore for what is excluded — .venv, logs, field data, etc.)
COPY . /app

# MapLibre is gitignored under web/vendor/ (desktop setup_maps.py fetches it locally).
# The hosted image must bundle it or the PWA JS crashes on boot (share links never open).
RUN python - <<'PY'
import os, urllib.request
vendor = "/app/web/vendor"
os.makedirs(vendor, exist_ok=True)
files = {
    "maplibre-gl.js": "https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.js",
    "maplibre-gl.css": "https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.css",
}
for name, url in files.items():
    dest = os.path.join(vendor, name)
    urllib.request.urlretrieve(url, dest)
    print("vendor:", name, os.path.getsize(dest), "bytes")
PY

# Job data lives here; mount a persistent disk at this path so jobs survive
# restarts/redeploys (Render disk / Fly volume). Without a mount it is ephemeral.
RUN mkdir -p /app/tds_data/mobile_jobs
VOLUME ["/app/tds_data"]

EXPOSE 8000

# --proxy-headers so share links come back as https behind the platform's edge
# (Render/Fly terminate TLS and forward X-Forwarded-Proto).
CMD ["sh", "-c", "uvicorn mobile_web.server:app --app-dir /app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=*"]
