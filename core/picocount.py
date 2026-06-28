"""PicoCount 2500 serial protocol (VehicleCounts developer PDF, June 2017)."""
from __future__ import annotations

import os
import struct
import time
from dataclasses import dataclass
from datetime import datetime

try:
    import serial
    import serial.tools.list_ports
except ImportError:  # pragma: no cover
    serial = None  # type: ignore

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROTOCOL_DOC = os.path.join(
    APP_DIR, "docs", "PicoCountSerialProtocol.pdf")
BAUD_NORMAL = 115200
BAUD_FAST = 921600
LAYOUT_SUFFIX = "c1b"
CMD_GAP_S = 0.45  # pace commands — protect counter battery / hourly limit
OPEN_SETTLE_S = 0.30  # FTDI + sleeping counter need UART wake time after open
COMM_RETRIES = 3


@dataclass
class ProbeResult:
    ok: bool
    port: str | None
    message: str
    ports: list[str]


@dataclass
class DeviceInfo:
    port: str
    model: str
    firmware: str
    serial_number: str
    unit_id: str
    battery_volts: float | None = None


def protocol_doc_present() -> bool:
    return os.path.isfile(PROTOCOL_DOC)


def list_serial_ports() -> list[str]:
    if serial is None:
        return []
    return [p.device for p in serial.tools.list_ports.comports()]


def counter_ports_labeled() -> list[tuple[str, str]]:
    """COM ports for PicoCount UI — GPS adapters (e.g. COM4) are excluded."""
    out: list[tuple[str, str]] = []
    for device in list_serial_ports():
        if _is_gps_port(device):
            continue
        if _is_counter_port(device):
            label = f"{device} (PicoCount)"
        else:
            label = f"{device} (USB serial)"
        out.append((device, label))
    return out


def wait_port_free(port: str, *, timeout_s: float = 4.0) -> bool:
    """Probe-open until Windows releases the COM port (GPS thread exited)."""
    if serial is None or not port:
        return False
    deadline = time.time() + max(0.5, timeout_s)
    while time.time() < deadline:
        try:
            probe = serial.Serial(port, BAUD_NORMAL, timeout=0)
            probe.close()
            time.sleep(0.12)
            return True
        except PermissionError:
            time.sleep(0.2)
        except OSError as exc:
            if getattr(exc, "errno", None) == 13:
                time.sleep(0.2)
            else:
                return False
        except Exception:
            return False
    return False


def preferred_counter_port(ports: list[str] | None = None) -> str | None:
    """Public: best COM port guess for PicoCount (FTDI adapter first)."""
    ports = ports or list_serial_ports()
    return _preferred_counter_port(ports)


def _port_blob(device: str) -> str:
    if serial is None:
        return ""
    try:
        for p in serial.tools.list_ports.comports():
            if p.device == device:
                return f"{p.description or ''} {p.manufacturer or ''} {p.hwid or ''}".lower()
    except Exception:
        pass
    return ""


def _is_gps_port(device: str) -> bool:
    """Skip NMEA GPS adapters when probing for PicoCount."""
    blob = _port_blob(device)
    if not blob:
        return False
    keywords = (
        "prolific", "pl2303", "globalsat", "bu-353", "bu353", "gps",
        "u-blox", "ublox", "garmin", "nmea",
    )
    return any(k in blob for k in keywords)


def _is_counter_port(device: str) -> bool:
    blob = _port_blob(device)
    if not blob:
        return False
    keywords = ("ftdi", "picocount", "vehiclecounts", "vehicle counts", "vid_0403")
    return any(k in blob for k in keywords)


def is_gps_port(device: str) -> bool:
    return _is_gps_port(device)


def is_counter_port(device: str) -> bool:
    return _is_counter_port(device)


def _preferred_counter_port(ports: list[str]) -> str | None:
    """Prefer VehicleCounts FTDI adapter over other COM devices (e.g. GPS)."""
    if not ports or serial is None:
        return ports[0] if ports else None
    non_gps = [p for p in ports if not _is_gps_port(p)]
    pool = non_gps or ports
    for device in pool:
        if _is_counter_port(device):
            return device
    for device in pool:
        if device.upper().startswith("COM"):
            return device
    return pool[0]


def facing_n_or_e(direction: str, heading_deg: float | None = None) -> str:
    d = (direction or "n").strip().lower()[:1]
    if d in ("n", "e"):
        return d
    if d == "s":
        return "n"
    if d == "w":
        return "e"
    if heading_deg is not None:
        h = float(heading_deg) % 360.0
        return "e" if abs(h - 90) < abs(h - 0) else "n"
    return "n"


def build_unit_id(
    site_id: str | int,
    direction: str,
    *,
    heading_deg: float | None = None,
) -> str:
    raw = str(site_id).strip()
    digits = "".join(c for c in raw if c.isdigit())
    sid = digits or raw.lower()
    face = facing_n_or_e(direction, heading_deg)
    unit = f"{sid}{face}{LAYOUT_SUFFIX}"
    return unit[:32]


def _checksum(cmd_byte: int, count: int, data: bytes) -> int:
    return (cmd_byte + count + sum(data)) & 0xFFFF


def _build_packet(prefix: bytes, cmd: str, data: bytes = b"") -> bytes:
    cmd_b = ord(cmd)
    cnt = len(data)
    cs = _checksum(cmd_b, cnt, data)
    return b"\x00\x00" + prefix + bytes([cmd_b, cnt]) + data + struct.pack("<H", cs)


def _pack_zero_time(when: datetime | None = None) -> bytes:
    dt = when or datetime.now()
    return bytes([
        int(dt.microsecond / 10000) % 128,
        dt.second,
        dt.minute,
        dt.hour,
        dt.day,
        dt.month - 1,
        dt.year & 0xFF,
        (dt.year >> 8) & 0xFF,
    ])


def _pad_unit_id(unit_id: str) -> bytes:
    raw = unit_id.encode("ascii", errors="ignore")[:32]
    return raw + b"\x00" * (32 - len(raw))


def _parse_response(buf: bytes) -> tuple[bool, bytes]:
    if not buf:
        return False, b""
    if buf[0] == 0x15:
        return False, b""
    if buf[0] != 0x06:
        return False, b""
    if len(buf) < 2:
        return False, b""
    cnt = buf[1]
    off = 2
    if cnt == 255:
        if len(buf) < 4:
            return False, b""
        cnt = buf[2] | (buf[3] << 8)
        off = 4
    data = buf[off: off + cnt] if cnt else b""
    return True, data


class PicoCountClient:
    """Talk to PicoCount 2500 on VehicleCounts USB adapter (FTDI COM port)."""

    def __init__(self, port: str, *, baud: int = BAUD_NORMAL):
        self.port = port
        self._baud = baud
        self._ser: serial.Serial | None = None

    def open(self) -> None:
        if serial is None:
            raise RuntimeError("pyserial is not installed")
        if not wait_port_free(self.port, timeout_s=4.0):
            raise PermissionError(_port_busy_message(self.port))
        self._ser = serial.Serial(
            self.port,
            self._baud,
            timeout=1.2,
            write_timeout=2.0,
            dsrdtr=False,
            rtscts=False,
        )
        # Default pyserial DTR=True can confuse VehicleCounts FTDI; leave lines idle.
        try:
            self._ser.dtr = False
            self._ser.rts = False
        except Exception:
            pass
        self._ser.reset_input_buffer()
        time.sleep(OPEN_SETTLE_S)

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            try:
                self._ser.dtr = False
                self._ser.rts = False
            except Exception:
                pass
            self._ser.close()
        self._ser = None

    def __enter__(self) -> PicoCountClient:
        self.open()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def _read_available(self, timeout: float = 1.5) -> bytes:
        assert self._ser is not None
        deadline = time.time() + timeout
        chunks: list[bytes] = []
        while time.time() < deadline:
            n = self._ser.in_waiting
            if n:
                chunks.append(self._ser.read(n))
                deadline = time.time() + 0.25
            else:
                time.sleep(0.05)
        return b"".join(chunks)

    def _command(self, prefix: bytes, cmd: str, data: bytes = b"") -> tuple[bool, bytes]:
        assert self._ser is not None
        self._ser.reset_input_buffer()
        pkt = _build_packet(prefix, cmd, data)
        self._ser.write(pkt)
        self._ser.flush()
        time.sleep(CMD_GAP_S)
        return _parse_response(self._read_available())

    def _generic(self, cmd: str, data: bytes = b"") -> tuple[bool, bytes]:
        return self._command(b"]", cmd, data)

    def _product(self, cmd: str, data: bytes = b"") -> tuple[bool, bytes]:
        return self._command(b"@", cmd, data)

    def comm_check(self) -> bool:
        for attempt in range(COMM_RETRIES):
            ok, _ = self._generic("C")
            if ok:
                return True
            if attempt + 1 < COMM_RETRIES:
                time.sleep(CMD_GAP_S)
        return False

    def read_model_firmware(self) -> tuple[str, str]:
        ok, data = self._generic("V")
        if not ok or len(data) < 23:
            return "", ""
        raw = data[:23].decode("ascii", errors="replace")
        model = raw[:16].strip()
        fw = raw[16:23].strip()
        return model, fw

    def read_serial_slow(self) -> str:
        """Read etched serial — paced for counter battery."""
        time.sleep(CMD_GAP_S)
        ok, data = self._generic("S")
        if not ok or len(data) < 8:
            return ""
        return data[:8].decode("ascii", errors="replace").strip("\x00 ")

    def read_unit_id(self) -> str:
        ok, data = self._generic("I")
        if not ok:
            return ""
        return data.split(b"\x00", 1)[0].decode("ascii", errors="replace")

    def write_unit_id(self, unit_id: str) -> bool:
        ok, _ = self._generic("i", _pad_unit_id(unit_id))
        return ok

    def zero_data(self, when: datetime | None = None) -> bool:
        ok, _ = self._generic("z", _pack_zero_time(when))
        return ok

    def read_battery(self) -> float | None:
        ok, data = self._generic("G")
        if not ok or len(data) < 2:
            return None
        v = data[0] | (data[1] << 8)
        return round(v / 100.0, 2)

    def memory_info(self) -> dict | None:
        ok, data = self._generic("M")
        if not ok or len(data) < 13:
            return None
        page_size = data[1] | (data[2] << 8)
        block_pages = data[3] | (data[4] << 8)
        max_blocks = data[5] | (data[6] << 8)
        page_ptr = data[7] | (data[8] << 8)
        block_ptr = data[9] | (data[10] << 8)
        buf_ptr = data[11] | (data[12] << 8)
        return {
            "page_size": page_size,
            "block_pages": block_pages,
            "max_blocks": max_blocks,
            "page_ptr": page_ptr,
            "block_ptr": block_ptr,
            "buffer_ptr": buf_ptr,
        }

    def set_baud_fast(self) -> bool:
        ok, _ = self._generic("b", bytes([3]))
        if ok:
            self._ser.baudrate = BAUD_FAST  # type: ignore[union-attr]
            time.sleep(0.05)
        return ok

    def read_nand_page(self, page: int, block: int) -> bytes:
        ok, raw = self._product("R", bytes([page & 0xFF]) + struct.pack("<H", block))
        if not ok or len(raw) < 2:
            return b""
        page_size = raw[0] | (raw[1] << 8)
        return raw[2: 2 + page_size]

    def read_buffer_page(self) -> bytes:
        return self.read_nand_page(0xFF, 0)

    def connect_info(self) -> DeviceInfo | None:
        if not self.comm_check():
            return None
        model, fw = self.read_model_firmware()
        serial_no = self.read_serial_slow()
        unit_id = self.read_unit_id()
        volts = self.read_battery()
        return DeviceInfo(
            port=self.port,
            model=model,
            firmware=fw,
            serial_number=serial_no,
            unit_id=unit_id,
            battery_volts=volts,
        )

    def clear_and_configure(self, unit_id: str) -> dict:
        info = self.connect_info()
        if info is None:
            return {"ok": False, "error": "Counter not responding on serial port."}
        before = summarize_memory(self.memory_info())
        cleared_at = datetime.now()
        if not self.zero_data(cleared_at):
            return {"ok": False, "error": "Clear data (]z) failed — NAK or timeout."}
        time.sleep(CMD_GAP_S)
        if not self.write_unit_id(unit_id):
            return {"ok": False, "error": "Set Unit ID (]i) failed — NAK or timeout."}
        time.sleep(CMD_GAP_S)
        after = summarize_memory(self.memory_info())
        return {
            "ok": True,
            "serial_number": info.serial_number,
            "unit_id": unit_id,
            "model": info.model,
            "firmware": info.firmware,
            "battery_volts": info.battery_volts,
            "bytes_before": before.get("bytes", 0),
            "bytes_after": after.get("bytes", 0),
            "memory_label": after.get("label", "0 bytes — empty"),
            "cleared_at": cleared_at.isoformat(timespec="seconds"),
            "study_start": cleared_at.isoformat(timespec="seconds"),
        }

    def download_raw(self) -> tuple[bytes, dict]:
        mem = self.memory_info()
        if not mem:
            return b"", {"ok": False, "error": "Could not read memory info (]M)."}
        page_size = mem["page_size"] or 2048
        block_pages = mem["block_pages"] or 64
        block_ptr = mem["block_ptr"]
        page_ptr = mem["page_ptr"]
        buf_ptr = mem["buffer_ptr"]
        if block_ptr == 0 and page_ptr == 0 and buf_ptr == 0:
            return b"", {"ok": True, "empty": True, "bytes": 0, **mem}

        def _buffer_slice() -> bytes:
            buf = self.read_buffer_page()
            if not buf or buf_ptr <= 0:
                return b""
            slice_ = buf[: min(buf_ptr, len(buf))]
            if slice_ and any(b != 0xFF for b in slice_):
                return slice_
            return b""

        # Short studies may live only in the RAM buffer (block 0 / page 0).
        if block_ptr == 0 and page_ptr == 0 and buf_ptr > 0:
            buf_only = _buffer_slice()
            if buf_only:
                return buf_only, {
                    "ok": True,
                    "bytes": len(buf_only),
                    "empty": False,
                    "source": "buffer",
                    **mem,
                }

        parts: list[bytes] = []
        # Prefer paced 115200 read for single-block studies (fast baud can NAK on some units).
        if block_ptr == 0 and page_ptr > 0:
            for page in range(page_ptr + 1):
                chunk = self.read_nand_page(page, 0)
                if chunk and any(b != 0xFF for b in chunk):
                    parts.append(chunk)
                time.sleep(0.08)
            buf = _buffer_slice()
            if buf:
                parts.append(buf)
            blob_slow = b"".join(parts)
            if blob_slow:
                return blob_slow, {
                    "ok": True,
                    "bytes": len(blob_slow),
                    "empty": False,
                    "source": "nand_115200",
                    **mem,
                }

        if not self.set_baud_fast():
            buf_only = _buffer_slice()
            if buf_only:
                return buf_only, {
                    "ok": True,
                    "bytes": len(buf_only),
                    "empty": False,
                    "source": "buffer_slow",
                    **mem,
                }
            return b"", {"ok": False, "error": "Could not switch to 921600 baud (]b)."}

        for block in range(block_ptr + 1):
            last_page = page_ptr if block == block_ptr else (block_pages - 1)
            for page in range(last_page + 1):
                chunk = self.read_nand_page(page, block)
                if chunk and any(b != 0xFF for b in chunk):
                    parts.append(chunk)
                time.sleep(0.02)
        buf = _buffer_slice()
        if buf:
            parts.append(buf)
        blob = b"".join(parts)
        if len(blob) == 0:
            return b"", {
                "ok": True,
                "empty": True,
                "bytes": 0,
                "hint": "Counter memory pointers set but no readable pages (cleared or corrupt).",
                **mem,
            }
        return blob, {"ok": True, "bytes": len(blob), "empty": False, **mem}


def quick_counter_status() -> ProbeResult:
    """List COM ports without opening serial (fast preflight / stress loops)."""
    ports = list_serial_ports()
    if not ports:
        return ProbeResult(
            True,
            None,
            "Optional at desk — plug download cable before install stops",
            ports,
        )
    pref = _preferred_counter_port(ports) or ports[0]
    return ProbeResult(
        True,
        pref,
        f"Port {pref} detected — Install → Refresh to connect",
        ports,
    )


def _probe_candidates(port: str | None, ports: list[str]) -> list[str]:
    if port:
        return [port]
    out: list[str] = []
    pref = _preferred_counter_port(ports)
    if pref:
        out.append(pref)
    for p in ports:
        if p not in out and not _is_gps_port(p):
            out.append(p)
    return out


def _port_busy_message(port: str) -> str:
    return (
        f"Port {port} is busy — close other apps using it, then tap Refresh "
        "(GPS pauses briefly while the counter connects).")


def probe_port(port: str | None = None) -> ProbeResult:
    ports = list_serial_ports()
    if serial is None:
        return ProbeResult(False, None, "pyserial not installed", ports)
    candidates = _probe_candidates(port, ports)
    if not candidates:
        return ProbeResult(
            False, None, "No COM port — plug in the PicoCount download cable.", ports)
    last_msg = ""
    for target in candidates:
        try:
            with PicoCountClient(target) as client:
                if client.comm_check():
                    return ProbeResult(
                        True, target, f"Counter responding on {target}", ports)
            last_msg = (
                f"Port {target} open but counter did not ACK ]C (comm check).\n"
                "Try Refresh again, re-seat the USB cable, or wait if the counter "
                "hit its hourly command limit.")
        except PermissionError:
            last_msg = _port_busy_message(target)
            if _is_counter_port(target):
                break
        except OSError as exc:
            if getattr(exc, "errno", None) == 13:
                last_msg = _port_busy_message(target)
                if _is_counter_port(target):
                    break
            else:
                last_msg = str(exc)
        except Exception as exc:  # noqa: BLE001
            last_msg = str(exc)
    return ProbeResult(False, candidates[0], last_msg, ports)


def read_serial_number(port: str | None = None) -> dict:
    """Slow-paced serial read for Install auto-fill."""
    pr = probe_port(port)
    if not pr.ok or not pr.port:
        return {"ok": False, "error": pr.message, "ports": pr.ports}
    try:
        with PicoCountClient(pr.port) as client:
            if not client.comm_check():
                return {"ok": False, "error": "No ACK from counter."}
            serial_no = client.read_serial_slow()
            model, fw = client.read_model_firmware()
            unit_id = client.read_unit_id()
            return {
                "ok": True,
                "port": pr.port,
                "serial_number": serial_no,
                "model": model,
                "firmware": fw,
                "unit_id": unit_id,
            }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "ports": pr.ports}


def summarize_memory(mem: dict | None) -> dict:
    """Estimate stored study size from ]M memory pointers (no full download)."""
    if not mem:
        return {"ok": False, "empty": True, "bytes": 0, "label": "0 bytes — empty"}
    page_size = int(mem.get("page_size") or 2048)
    block_pages = int(mem.get("block_pages") or 64)
    block_ptr = int(mem.get("block_ptr") or 0)
    page_ptr = int(mem.get("page_ptr") or 0)
    buf_ptr = int(mem.get("buffer_ptr") or 0)
    if block_ptr == 0 and page_ptr == 0 and buf_ptr == 0:
        return {"ok": True, "empty": True, "bytes": 0, "label": "0 bytes — empty", **mem}
    pages = block_ptr * block_pages + page_ptr + (1 if buf_ptr > 0 else 0)
    est = pages * page_size
    if buf_ptr > 0 and buf_ptr < page_size:
        est = max(est - page_size + buf_ptr, buf_ptr)
    return {
        "ok": True,
        "empty": False,
        "bytes": est,
        "label": f"~{est:,} bytes stored",
        **mem,
    }


def read_counter_status(port: str | None = None) -> dict:
    """Connect, ACK, and read unit id + memory fill level."""
    pr = probe_port(port)
    if not pr.ok or not pr.port:
        return {"ok": False, "error": pr.message, "ports": pr.ports}
    try:
        with PicoCountClient(pr.port) as client:
            if not client.comm_check():
                return {"ok": False, "error": "No ACK from counter.", "ports": pr.ports}
            info = client.connect_info()
            mem = client.memory_info()
            summary = summarize_memory(mem)
            return {
                "ok": True,
                "port": pr.port,
                "message": f"Counter responding on {pr.port}",
                "ports": pr.ports,
                "unit_id": (info.unit_id if info else "") or "",
                "serial_number": (info.serial_number if info else "") or "",
                "model": (info.model if info else "") or "",
                "firmware": (info.firmware if info else "") or "",
                "battery_volts": info.battery_volts if info else None,
                **summary,
            }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "ports": pr.ports}


def rename_unit_id(unit_id: str, port: str | None = None) -> dict:
    """Write Unit ID only — does not clear study data."""
    pr = probe_port(port)
    if not pr.ok or not pr.port:
        return {"ok": False, "error": pr.message}
    try:
        with PicoCountClient(pr.port) as client:
            info = client.connect_info()
            if info is None:
                return {"ok": False, "error": "Counter not responding on serial port."}
            if not client.write_unit_id(unit_id):
                return {"ok": False, "error": "Set Unit ID (]i) failed — NAK or timeout."}
            time.sleep(CMD_GAP_S)
            read_back = client.read_unit_id()
            return {
                "ok": True,
                "unit_id": read_back or unit_id,
                "serial_number": info.serial_number,
                "model": info.model,
                "firmware": info.firmware,
            }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def clear_and_configure(
    unit_id: str,
    port: str | None = None,
) -> dict:
    pr = probe_port(port)
    if not pr.ok or not pr.port:
        return {"ok": False, "error": pr.message}
    try:
        with PicoCountClient(pr.port) as client:
            return client.clear_and_configure(unit_id)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def download_study(
    dest_path: str,
    *,
    port: str | None = None,
    meta: dict | None = None,
) -> dict:
    pr = probe_port(port)
    if not pr.ok or not pr.port:
        return {"ok": False, "error": pr.message}
    try:
        with PicoCountClient(pr.port) as client:
            if not client.comm_check():
                return {"ok": False, "error": "Counter not connected."}
            blob, info = client.download_raw()
            if not info.get("ok"):
                return info
            if info.get("empty"):
                hint = info.get("hint") or "No count data in counter (empty or cleared study)."
                return {"ok": False, "error": hint}
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            header = {
                "magic": "TrafficDeployer.PicoCountRaw",
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "port": pr.port,
            }
            if meta:
                header.update(meta)
            import json
            sidecar = dest_path + ".json"
            with open(sidecar, "w", encoding="utf-8") as f:
                json.dump({**header, **info}, f, indent=2)
            with open(dest_path, "wb") as f:
                f.write(blob)
            return {
                "ok": True,
                "path": dest_path,
                "meta_path": sidecar,
                "bytes": len(blob),
                "port": pr.port,
            }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
