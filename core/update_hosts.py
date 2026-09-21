"""Home-PC update bind addresses: LAN + Tailscale (MagicDNS / 100.x)."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess


DEFAULT_PORT = 8765
# Stable fallbacks when Tailscale CLI is missing (this home PC's last-known IPs).
FALLBACK_TAILSCALE_IP = "100.93.14.32"
FALLBACK_LAN_IP = "192.168.1.30"


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.strip().rstrip("/").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip().rstrip("/"))
    return out


def _tailscale_exe() -> str | None:
    found = shutil.which("tailscale")
    if found:
        return found
    for path in (
        r"C:\Program Files\Tailscale\tailscale.exe",
        r"C:\Program Files (x86)\Tailscale\tailscale.exe",
    ):
        if os.path.isfile(path):
            return path
    return None


def tailscale_status() -> dict:
    exe = _tailscale_exe()
    if not exe:
        return {}
    try:
        raw = subprocess.check_output(
            [exe, "status", "--json"],
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def tailscale_self_dns() -> str:
    data = tailscale_status()
    name = str((data.get("Self") or {}).get("DNSName") or "").strip().rstrip(".")
    return name


def tailscale_self_ip4() -> str:
    data = tailscale_status()
    for ip in (data.get("Self") or {}).get("TailscaleIPs") or []:
        text = str(ip).strip()
        if text.count(".") == 3 and not text.startswith("fd"):
            return text
    return ""


def list_bind_ips() -> list[str]:
    """IPv4 addresses this PC can serve on (LAN + Tailscale, never loopback)."""
    env = os.environ.get("TD_RELEASES_HOST", "").strip()
    if env:
        return [env]
    ips: list[str] = []
    ts_ip = tailscale_self_ip4()
    if ts_ip:
        ips.append(ts_ip)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127.") or ip.startswith("169.254."):
                continue
            if ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        ip = probe.getsockname()[0]
        probe.close()
        if ip and not ip.startswith("127.") and ip not in ips:
            ips.append(ip)
    except OSError:
        pass
    if not ips:
        ips = [FALLBACK_LAN_IP]
    # Tailscale 100.x first so work laptop off home Wi-Fi still hits the server.
    ips.sort(key=lambda x: (0 if x.startswith("100.") else 1, x))
    return ips


def list_base_urls(port: int | None = None) -> list[str]:
    port = int(port or os.environ.get("TD_RELEASES_PORT", DEFAULT_PORT) or DEFAULT_PORT)
    urls: list[str] = []
    dns = tailscale_self_dns()
    if dns:
        urls.append(f"http://{dns}:{port}")
    for ip in list_bind_ips():
        urls.append(f"http://{ip}:{port}")
    urls.append(f"http://{FALLBACK_TAILSCALE_IP}:{port}")
    urls.append(f"http://{FALLBACK_LAN_IP}:{port}")
    return _dedupe(urls)


def preferred_base_url(port: int | None = None) -> str:
    bases = list_base_urls(port)
    return bases[0] if bases else f"http://{FALLBACK_TAILSCALE_IP}:{DEFAULT_PORT}"


def channel_document(port: int | None = None) -> dict:
    bases = list_base_urls(port)
    urls = [f"{base}/version.json" for base in bases]
    return {
        "version_url": urls[0] if urls else "",
        "version_urls": urls,
    }


def windows_peers_online() -> list[dict]:
    """Other online Windows Tailscale nodes (work laptop)."""
    data = tailscale_status()
    self_name = str((data.get("Self") or {}).get("HostName") or "").strip().lower()
    out: list[dict] = []
    peers = data.get("Peer") or {}
    if not isinstance(peers, dict):
        return out
    for peer in peers.values():
        if not isinstance(peer, dict) or not peer.get("Online"):
            continue
        os_name = str(peer.get("OS") or "").lower()
        if os_name in ("android", "ios", "ipados"):
            continue
        host = str(peer.get("HostName") or "").strip()
        if host.lower() == self_name:
            continue
        ipv4 = ""
        for ip in peer.get("TailscaleIPs") or []:
            text = str(ip).strip()
            if text.count(".") == 3:
                ipv4 = text
                break
        out.append(
            {
                "hostname": host,
                "dns": str(peer.get("DNSName") or "").strip().rstrip("."),
                "ip": ipv4,
                "os": os_name,
            }
        )
    return out
