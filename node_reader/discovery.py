"""Discover BlueApro / HOLO nodes on the local network."""
from __future__ import annotations

import socket
import threading
from dataclasses import dataclass


@dataclass
class DiscoveredNode:
    ip: str
    port: int
    open_ports: list[int]
    label: str = ""


def _local_subnet_prefix() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ".".join(ip.split(".")[:3])
    except OSError:
        return None


def probe_port(ip: str, port: int, timeout: float = 0.35, bind_ip: str | None = None) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        if bind_ip:
            sock.bind((bind_ip, 0))
        ok = sock.connect_ex((ip, port)) == 0
        sock.close()
        return ok
    except OSError:
        return False


def scan_network(
    ports: list[int] | None = None,
    timeout: float = 0.35,
    subnet_prefix: str | None = None,
    bind_ip: str | None = None,
) -> list[DiscoveredNode]:
    """Scan /24 for hosts with common HTTP ports open on the chosen interface subnet."""
    ports = ports or [80, 8080, 8765, 5000]
    prefix = subnet_prefix or _local_subnet_prefix()
    if not prefix:
        return []

    candidates = {f"{prefix}.{i}" for i in range(1, 255)}
    candidates.add("192.168.4.1")

    found: dict[str, list[int]] = {}
    lock = threading.Lock()
    threads: list[threading.Thread] = []

    def check(ip: str, port: int) -> None:
        if probe_port(ip, port, timeout, bind_ip=bind_ip):
            with lock:
                found.setdefault(ip, []).append(port)

    for ip in candidates:
        for port in ports:
            t = threading.Thread(target=check, args=(ip, port), daemon=True)
            t.start()
            threads.append(t)
    for t in threads:
        t.join(timeout=timeout + 0.2)

    nodes: list[DiscoveredNode] = []
    for ip, open_ports in sorted(found.items()):
        open_ports = sorted(set(open_ports))
        primary = open_ports[0]
        label = "BlueApro AP?" if ip == "192.168.4.1" else ""
        if ip.endswith(".1"):
            label = (label + " " if label else "") + "Often router — verify"
        if bind_ip and ip == bind_ip:
            label = "This PC"
        nodes.append(DiscoveredNode(ip=ip, port=primary, open_ports=open_ports, label=label.strip()))
    return nodes
