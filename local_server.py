"""Tiny local HTTP server that supports HTTP Range requests.

MapLibre + PMTiles fetch the basemap with byte-range requests; Python's stock
http.server does NOT honour Range, so we provide a minimal handler that does.
Serves the web/ UI assets and the downloaded california.pmtiles from tds_data/.

Bind is 127.0.0.1 only (never exposed to the network). Reuses the daemon-thread
pattern from the original tile_cache.py.
"""
from __future__ import annotations

import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".pmtiles": "application/octet-stream",
    ".png": "image/png",
    ".pbf": "application/x-protobuf",
    ".svg": "image/svg+xml",
}
_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


class _Handler(BaseHTTPRequestHandler):
    # roots is injected per-server: {url_prefix: directory}
    roots: dict[str, str] = {}

    def log_message(self, *args):  # silence console spam
        pass

    def _resolve(self, path: str) -> str | None:
        path = unquote(path.split("?", 1)[0].split("#", 1)[0])
        if path in ("", "/"):
            path = "/index.html"
        for prefix, root in self.roots.items():
            if path.startswith(prefix):
                rel = path[len(prefix):].lstrip("/")
                full = os.path.normpath(os.path.join(root, rel))
                if os.path.commonpath([os.path.abspath(full), os.path.abspath(root)]) != os.path.abspath(root):
                    return None  # path traversal guard
                if os.path.isfile(full):
                    return full
        return None

    def _send_headers(self, code, length, ctype, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def do_HEAD(self):
        full = self._resolve(self.path)
        if not full:
            self.send_error(404)
            return
        size = os.path.getsize(full)
        self._send_headers(200, size, _MIME.get(os.path.splitext(full)[1].lower(), "application/octet-stream"))

    def do_GET(self):
        full = self._resolve(self.path)
        if not full:
            self.send_error(404)
            return
        size = os.path.getsize(full)
        ctype = _MIME.get(os.path.splitext(full)[1].lower(), "application/octet-stream")
        rng = self.headers.get("Range")

        if rng:
            m = _RANGE_RE.search(rng)
            if m:
                start = int(m.group(1)) if m.group(1) else 0
                end = int(m.group(2)) if m.group(2) else size - 1
                end = min(end, size - 1)
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                length = end - start + 1
                self._send_headers(206, length, ctype,
                                   {"Content-Range": f"bytes {start}-{end}/{size}"})
                with open(full, "rb") as f:
                    f.seek(start)
                    self.wfile.write(f.read(length))
                return

        self._send_headers(200, size, ctype)
        with open(full, "rb") as f:
            self.wfile.write(f.read())


_server = None
_port = None


def start(web_dir: str, data_dir: str) -> int:
    """Start (once) the server. Returns the chosen localhost port."""
    global _server, _port
    if _server is not None:
        return _port
    _Handler.roots = {"/": web_dir, "/data/": data_dir}
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    _port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    _server = httpd
    return _port


def base_url() -> str | None:
    return f"http://127.0.0.1:{_port}" if _port else None


def is_running() -> bool:
    return _server is not None


def stop():
    """Shut down the daemon server (for tests)."""
    global _server, _port
    if _server is not None:
        try:
            _server.shutdown()
            _server.server_close()
        except Exception:
            pass
        _server = None
        _port = None
