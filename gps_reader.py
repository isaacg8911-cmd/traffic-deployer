"""
USB GPS reader for the GlobalSat BU-353N (and similar NMEA-0183 USB receivers).

Reads NMEA sentences directly from the serial/COM port and returns a (lat, lon)
fix. Fully local: no network, no wifi. Safe no-op if pyserial/pynmea2 or the
hardware are missing, so the app never crashes when the GPS is unplugged.

Standalone diagnostic:  python gps_reader.py
"""
from __future__ import annotations

import math

try:
    import serial
    import serial.tools.list_ports as list_ports
    import pynmea2
    HAS_SERIAL = True
except Exception:
    HAS_SERIAL = False

# BU-353N typically enumerates at 4800 or 9600 baud; try the common set.
COMMON_BAUDS = [4800, 9600, 38400, 115200]


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def list_serial_ports() -> list[str]:
    """Return available COM port device names (empty if libs/hardware absent)."""
    if not HAS_SERIAL:
        return []
    try:
        return [p.device for p in list_ports.comports()]
    except Exception:
        return []


def describe_ports() -> list[dict]:
    """Return richer port info for troubleshooting (device + description)."""
    if not HAS_SERIAL:
        return []
    try:
        return [{"device": p.device, "description": p.description} for p in list_ports.comports()]
    except Exception:
        return []


def _valid_fix(msg) -> tuple[float, float] | None:
    lat = getattr(msg, "latitude", None)
    lon = getattr(msg, "longitude", None)
    if lat is None or lon is None:
        return None
    if lat == 0.0 and lon == 0.0:
        return None
    # RMC/GLL expose .status ('A' = valid, 'V' = void). GGA has no status attr.
    status = getattr(msg, "status", "A")
    if status in (None, "", "A"):
        return float(lat), float(lon)
    return None


def _read_fix_from_port(port: str, baud: int, timeout: float = 2.0, attempts: int = 50):
    try:
        with serial.Serial(port, baud, timeout=timeout) as ser:
            for _ in range(attempts):
                raw = ser.readline().decode("ascii", errors="replace").strip()
                if not raw.startswith("$"):
                    continue
                try:
                    msg = pynmea2.parse(raw)
                except Exception:
                    continue
                fix = _valid_fix(msg)
                if fix:
                    return fix
    except Exception:
        return None
    return None


def get_fix(preferred_port: str | None = None, bauds: list[int] | None = None):
    """
    Return (lat, lon) from the first port that yields a valid NMEA fix.
    Returns (None, None) if no fix / no hardware. Receiver needs clear sky view.
    """
    if not HAS_SERIAL:
        return None, None
    bauds = bauds or COMMON_BAUDS
    ports = [preferred_port] if preferred_port else list_serial_ports()
    for port in ports:
        if not port:
            continue
        for baud in bauds:
            fix = _read_fix_from_port(port, baud)
            if fix:
                return fix
    return None, None


def get_status(preferred_port: str | None = None, bauds: list[int] | None = None,
               attempts: int = 40) -> dict:
    """
    Read the receiver briefly and report fix quality for the UI header.
    Returns: {connected, port, fix(bool), satellites, lat, lon}.
    """
    out = {"connected": False, "port": None, "fix": False,
           "satellites": 0, "lat": None, "lon": None}
    if not HAS_SERIAL:
        return out
    bauds = bauds or COMMON_BAUDS
    ports = [preferred_port] if preferred_port else list_serial_ports()
    for port in ports:
        if not port:
            continue
        for baud in bauds:
            try:
                with serial.Serial(port, baud, timeout=2.0) as ser:
                    got_data = False
                    for _ in range(attempts):
                        raw = ser.readline().decode("ascii", errors="replace").strip()
                        if not raw.startswith("$"):
                            continue
                        got_data = True
                        try:
                            msg = pynmea2.parse(raw)
                        except Exception:
                            continue
                        # Satellite count from GGA
                        nsat = getattr(msg, "num_sats", None)
                        if nsat not in (None, ""):
                            try:
                                out["satellites"] = max(out["satellites"], int(nsat))
                            except Exception:
                                pass
                        fix = _valid_fix(msg)
                        if fix:
                            out.update({"connected": True, "port": port, "fix": True,
                                        "lat": fix[0], "lon": fix[1]})
                            return out
                    if got_data:
                        out.update({"connected": True, "port": port})
                        return out
            except Exception:
                continue
    return out


class GPSStream:
    """Continuous NMEA reader for smooth live tracing on the map.

    Unlike get_fix()/get_status() (which open-read-close on every call), this keeps
    the serial port open on a background thread and continuously updates the latest
    position, heading and satellite count. Fully offline. Safe no-op without libs.

    Usage:
        stream = GPSStream(); stream.start()
        fix = stream.latest()   # {"fix", "lat", "lon", "heading", "satellites", "connected"}
        stream.stop()
    """

    def __init__(self, preferred_port: str | None = None, bauds: list[int] | None = None):
        self.preferred_port = preferred_port
        self.bauds = bauds or COMMON_BAUDS
        self._thread = None
        self._stop = False
        self._lock = None
        self._state = {"connected": False, "port": None, "fix": False,
                       "satellites": 0, "lat": None, "lon": None, "heading": None,
                       "heading_locked": None, "heading_mode": "none", "speed_mps": 0.0}
        self._heading_buf: list[float] = []
        self._last_pos: tuple[float, float] | None = None
        if HAS_SERIAL:
            import threading
            self._lock = threading.Lock()

    def start(self) -> bool:
        if not HAS_SERIAL or self._thread is not None:
            return False
        import threading
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop = True
        t = self._thread
        if t is not None:
            t.join(timeout=2.0)
        self._thread = None

    def latest(self) -> dict:
        if self._lock is None:
            return dict(self._state)
        with self._lock:
            out = dict(self._state)
            h = out.get("heading_locked") if out.get("heading_mode") == "locked" else out.get("heading")
            if h is not None:
                out["heading_display"] = h
            return out

    def _update(self, **kw):
        if self._lock is None:
            self._state.update(kw)
            return
        with self._lock:
            self._state.update(kw)

    def _bearing_from_motion(self, lat: float, lon: float) -> float | None:
        if self._last_pos is None:
            self._last_pos = (lat, lon)
            return None
        d = _haversine_m(self._last_pos[0], self._last_pos[1], lat, lon)
        if d < 2.0:
            return None
        y0, x0 = self._last_pos
        y1, x1 = lat, lon
        self._last_pos = (lat, lon)
        return (math.degrees(math.atan2(x1 - x0, y1 - y0)) + 360.0) % 360.0

    def _push_heading_sample(self, deg: float):
        self._heading_buf.append(deg)
        if len(self._heading_buf) > 12:
            self._heading_buf.pop(0)

    def _locked_heading(self) -> float | None:
        if not self._heading_buf:
            return None
        xs = [math.cos(math.radians(h)) for h in self._heading_buf]
        ys = [math.sin(math.radians(h)) for h in self._heading_buf]
        return (math.degrees(math.atan2(sum(ys), sum(xs))) + 360.0) % 360.0

    def _heading_from_msg(self, msg) -> float | None:
        for attr in ("heading", "true_heading", "true_course", "track", "cog"):
            raw = getattr(msg, attr, None)
            if raw not in (None, ""):
                try:
                    return float(raw) % 360.0
                except Exception:
                    pass
        return None

    def _speed_mps_from_msg(self, msg) -> float | None:
        for attr in ("spd_over_grnd", "speed"):
            raw = getattr(msg, attr, None)
            if raw not in (None, ""):
                try:
                    # NMEA ground speed is usually knots.
                    return float(raw) * 0.514444
                except Exception:
                    pass
        return None

    def _apply_motion(self, fix: tuple[float, float], msg):
        lat, lon = fix
        spd = self._speed_mps_from_msg(msg)
        hdg = self._heading_from_msg(msg)
        if hdg is None:
            hdg = self._bearing_from_motion(lat, lon)
        else:
            self._last_pos = (lat, lon)

        moving = spd is not None and spd >= 1.0
        if moving and hdg is not None:
            self._push_heading_sample(hdg)
            mode = "moving"
            display = hdg
        else:
            locked = self._locked_heading()
            if locked is not None:
                mode = "locked"
                display = locked
            elif hdg is not None:
                self._push_heading_sample(hdg)
                mode = "slow"
                display = hdg
            else:
                mode = "none"
                display = None

        upd = {
            "connected": True, "fix": True, "lat": lat, "lon": lon,
            "heading": hdg, "heading_locked": self._locked_heading(),
            "heading_mode": mode, "speed_mps": spd or 0.0,
        }
        if display is not None:
            upd["heading_display"] = display
        self._update(**upd)

    def _open_port(self):
        """Find a port/baud that produces NMEA data and return an open Serial."""
        ports = [self.preferred_port] if self.preferred_port else list_serial_ports()
        for port in ports:
            if not port:
                continue
            for baud in self.bauds:
                try:
                    ser = serial.Serial(port, baud, timeout=2.0)
                    for _ in range(30):
                        raw = ser.readline().decode("ascii", errors="replace").strip()
                        if raw.startswith("$"):
                            self._update(connected=True, port=port)
                            return ser
                    ser.close()
                except Exception:
                    continue
        return None

    def _run(self):
        while not self._stop:
            ser = self._open_port()
            if ser is None:
                self._update(connected=False, fix=False)
                # No hardware yet; wait a moment before re-scanning.
                import time as _t
                _t.sleep(2.0)
                continue
            try:
                with ser:
                    while not self._stop:
                        raw = ser.readline().decode("ascii", errors="replace").strip()
                        if not raw.startswith("$"):
                            continue
                        try:
                            msg = pynmea2.parse(raw)
                        except Exception:
                            continue
                        nsat = getattr(msg, "num_sats", None)
                        if nsat not in (None, ""):
                            try:
                                self._update(satellites=int(nsat))
                            except Exception:
                                pass
                        h_only = self._heading_from_msg(msg)
                        if h_only is not None and not _valid_fix(msg):
                            self._push_heading_sample(h_only)
                        fix = _valid_fix(msg)
                        if fix:
                            self._apply_motion(fix, msg)
            except Exception:
                self._update(connected=False, fix=False)
                import time as _t
                _t.sleep(1.0)


def diagnose() -> dict:
    """Human-readable status for the UI / command line."""
    info = {"has_serial_libs": HAS_SERIAL, "ports": describe_ports(), "fix": None}
    if HAS_SERIAL and info["ports"]:
        lat, lon = get_fix()
        if lat is not None:
            info["fix"] = {"lat": lat, "lon": lon}
    return info


if __name__ == "__main__":
    import json

    if not HAS_SERIAL:
        print("pyserial / pynmea2 not installed. Run: pip install pyserial pynmea2")
    result = diagnose()
    print(json.dumps(result, indent=2))
    if result.get("fix"):
        f = result["fix"]
        print(f"\nGPS FIX OK -> lat={f['lat']:.6f}, lon={f['lon']:.6f}")
    elif result.get("ports"):
        print("\nPorts found but no fix yet. Ensure the BU-353N has clear sky view, then retry.")
    else:
        print("\nNo COM ports detected. Plug in the BU-353N and check its driver in Device Manager.")
