"""Resolve which local network interface handles traffic to a peer IP."""
from __future__ import annotations

import re
import socket
import subprocess
import sys
from functools import lru_cache


def _guess_kind(name: str) -> str:
    n = (name or "").lower()
    if any(x in n for x in ("wi-fi", "wifi", "wlan", "wireless")):
        return "wifi"
    if any(x in n for x in ("ethernet", "eth", "en", "lan")):
        return "ethernet"
    return "other"


def _route_dev_linux(peer_ip: str) -> str | None:
    try:
        proc = subprocess.run(
            ["ip", "-4", "route", "get", peer_ip],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout:
            return None
        parts = proc.stdout.strip().split()
        for i, part in enumerate(parts):
            if part == "dev" and i + 1 < len(parts):
                return parts[i + 1]
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return None


def _route_dev_windows(peer_ip: str) -> str | None:
    try:
        proc = subprocess.run(
            ["route", "print", peer_ip],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if proc.returncode != 0:
            return None
        for line in proc.stdout.splitlines():
            if peer_ip in line and "On-link" not in line:
                cols = line.split()
                if len(cols) >= 4 and cols[0] == "0.0.0.0":
                    return cols[3] if len(cols) > 3 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return None


@lru_cache(maxsize=256)
def resolve_server_interface(peer_ip: str | None) -> str | None:
    """
    Return local interface name (eth0, wlan0, Ethernet, …) the server uses to reach peer_ip.
    Cached per IP for hot MQTT paths.
    """
    ip = (peer_ip or "").strip()
    if not ip or ip.startswith("127."):
        return None

    dev = None
    if sys.platform == "linux":
        dev = _route_dev_linux(ip)
    elif sys.platform == "win32":
        dev = _route_dev_windows(ip)

    if not dev:
        return None
    return dev


def interface_label(peer_ip: str | None, iface: str | None = None) -> str:
    """Human label e.g. wlan0 (wifi) or eth0 (ethernet)."""
    name = iface or resolve_server_interface(peer_ip)
    if not name:
        return "—"
    kind = _guess_kind(name)
    if kind == "wifi":
        return f"{name} (Wi‑Fi)"
    if kind == "ethernet":
        return f"{name} (Ethernet)"
    return name


def list_local_ipv4() -> list[dict]:
    """Server LAN addresses for diagnostics."""
    out: list[dict] = []
    if sys.platform == "linux":
        try:
            raw = subprocess.check_output(["ip", "-4", "addr"], text=True, timeout=5)
            iface = ""
            for line in raw.splitlines():
                m_if = re.match(r"^\d+:\s(\S+):", line)
                if m_if:
                    iface = m_if.group(1)
                    continue
                m_ip = re.search(r"inet\s+([\d.]+)/", line)
                if m_ip and iface and iface != "lo":
                    ip = m_ip.group(1)
                    out.append({"interface": iface, "ip": ip, "kind": _guess_kind(iface)})
        except (OSError, subprocess.SubprocessError):
            pass
    if not out:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            out.append({"interface": "default", "ip": ip, "kind": "other"})
        except OSError:
            pass
    return out
