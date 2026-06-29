# Traffic Deployer mobile PWA — lean hosted image (no Qt / osmnx).
# Straight-line routing on host; street-traced routing needs a bundled road graph.
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TD_MOBILE_PUBLIC=1 \
    TD_MOBILE_LINK_TTL_HOURS=16

COPY mobile_web/requirements.txt /tmp/requirements-mobile.txt
RUN pip install --no-cache-dir -r /tmp/requirements-mobile.txt \
    pandas openpyxl xlrd xlsxwriter numpy networkx

COPY core/ core/
COPY mobile_web/ mobile_web/
COPY web/vendor/ web/vendor/
COPY road_router.py .
COPY demo_data/ demo_data/
COPY scripts/field_job_fixtures.py scripts/field_job_fixtures.py

RUN mkdir -p /app/tds_data/mobile_jobs /app/tds_data/mobile_uploads

EXPOSE 10000

# Render sets PORT; default 8800 for local docker run.
CMD uvicorn mobile_web.server:app --host 0.0.0.0 --port ${PORT:-8800} --proxy-headers --forwarded-allow-ips='*'
