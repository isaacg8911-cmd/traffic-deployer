"""Application state: the single source of truth for a shift.

Holds the origin, the ordered stops (with their install/pickup status and field
captures), and the computed route geometry. Persists itself encrypted + crash-safe
through the existing persistence.py module.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
    _CA_TZ = ZoneInfo("America/Los_Angeles")
except Exception:
    _CA_TZ = None

try:
    import persistence
except Exception:
    persistence = None

DEFAULT_HOME = (33.7715, -117.9431)


def ca_now() -> tuple[str, str]:
    """Return (date 'YYYY-MM-DD', exact 'YYYY-MM-DD HH:MM:SS') in California time."""
    now = datetime.now(_CA_TZ) if _CA_TZ else datetime.now()
    return now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d %H:%M:%S")


class RouteState:
    def __init__(self, data_dir: str, profile: str = "DEFAULT"):
        self.data_dir = data_dir
        self.profile = profile or "DEFAULT"
        self.session_id = str(uuid.uuid4())[:8]
        self.home: tuple[float, float] = DEFAULT_HOME
        self.stops: list[dict] = []           # ordered list of stop dicts
        self.active_files: list[str] = []     # map labels (days)
        self.mission_type: str = "INSTALLATION"
        self.route: dict = {"polyline": [], "miles": 0.0, "legs": [], "graph": False}
        self.theme: str = "sunny"
        self.default_home: tuple[float, float] | None = None
        self.offline_mode: bool = False
        self.excel_paths: list[str] = []
        self.est_paths: list[str] = []
        self.current_index: int = 0
        self.pickup_index: int = 0
        self.map_day_filter: str = "All maps"
        self.voice_nav: bool = True
        self.voice_style: str = "female"

    # --------------------------------------------------------------------- #
    #  Persistence
    # --------------------------------------------------------------------- #
    @property
    def backup_file(self) -> str:
        return os.path.join(self.data_dir, f"tds_backup_{self.profile}.json")

    def to_dict(self) -> dict:
        d = {
            "profile": self.profile,
            "home": list(self.home),
            "stops": self.stops,
            "active_files": self.active_files,
            "mission_type": self.mission_type,
            "route": self.route,
            "theme": self.theme,
            "offline_mode": self.offline_mode,
        }
        if self.default_home:
            d["default_home"] = list(self.default_home)
        d["excel_paths"] = list(self.excel_paths)
        d["est_paths"] = list(self.est_paths)
        d["current_index"] = int(self.current_index)
        d["pickup_index"] = int(self.pickup_index)
        d["map_day_filter"] = self.map_day_filter or "All maps"
        d["voice_nav"] = bool(self.voice_nav)
        d["voice_style"] = "female"
        return d

    def load(self) -> bool:
        data = {}
        if persistence is not None:
            data = persistence.load_state(self.backup_file, self.data_dir)
        if not data:
            return False
        self.home = tuple(data.get("home", DEFAULT_HOME))
        if data.get("default_home"):
            self.default_home = tuple(data["default_home"])
        self.stops = data.get("stops", [])
        for s in self.stops:
            st = str(s.get("street", "")).strip()
            if not st or st.lower() in ("nan", "none", "nat"):
                s["street"] = f"Site {s.get('id', '')}"
        self.active_files = data.get("active_files", [])
        self.mission_type = data.get("mission_type", "INSTALLATION")
        self.route = data.get("route", {"polyline": [], "miles": 0.0, "legs": [], "graph": False})
        from ui_themes import normalize_theme
        self.theme = normalize_theme(data.get("theme", "sunny"))
        self.offline_mode = bool(data.get("offline_mode", False))
        self.excel_paths = [str(p) for p in data.get("excel_paths", []) if p]
        self.est_paths = [str(p) for p in data.get("est_paths", []) if p]
        self.current_index = int(data.get("current_index", 0))
        self.pickup_index = int(data.get("pickup_index", 0))
        self.map_day_filter = str(data.get("map_day_filter", "All maps") or "All maps")
        self.voice_nav = bool(data.get("voice_nav", True))
        self.voice_style = "female"
        return True

    def apply_default_home(self):
        """Use the saved default GPS start if one exists."""
        if self.default_home:
            self.home = self.default_home

    def save_default_home(self, lat: float, lon: float):
        self.default_home = (float(lat), float(lon))
        self.home = self.default_home
        self.save()

    def save(self) -> bool:
        if persistence is None:
            return False
        return persistence.save_state(self.to_dict(), self.backup_file, self.data_dir)

    # --------------------------------------------------------------------- #
    #  Stop helpers
    # --------------------------------------------------------------------- #
    def stop_by_uid(self, uid: str) -> dict | None:
        return next((s for s in self.stops if s["uid"] == uid), None)

    def index_of(self, uid: str) -> int:
        return next((i for i, s in enumerate(self.stops) if s["uid"] == uid), -1)

    def point(self, s: dict) -> tuple[float, float]:
        if s.get("field_lat") is not None and s.get("field_lon") is not None:
            return float(s["field_lat"]), float(s["field_lon"])
        if s.get("cross_lat") is not None and s.get("cross_lon") is not None:
            return float(s["cross_lat"]), float(s["cross_lon"])
        lat = s.get("field_lat") or s.get("lat")
        lon = s.get("field_lon") or s.get("lon")
        return float(lat), float(lon)

    def progress_install(self) -> tuple[int, int]:
        done = sum(1 for s in self.stops if s.get("installed") or s.get("skipped"))
        return done, len(self.stops)

    def progress_pickup(self) -> tuple[int, int]:
        installed = [s for s in self.stops if s.get("installed")]
        done = sum(1 for s in installed if s.get("picked_up"))
        return done, len(installed)

    def clear_shift(self, *, wipe_upload_paths: bool = False) -> None:
        """Clear route + stops. Upload file paths kept unless wipe_upload_paths."""
        self.stops = []
        self.active_files = []
        self.route = {"polyline": [], "miles": 0.0, "legs": [], "graph": False}
        self.current_index = 0
        self.pickup_index = 0
        if wipe_upload_paths:
            self.excel_paths = []
            self.est_paths = []
        self.save()

    def reset_route(self):
        """Backward-compatible alias: clear shift but keep your file list."""
        self.clear_shift(wipe_upload_paths=False)
