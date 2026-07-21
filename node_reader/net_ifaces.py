"""List PC network interfaces (Ethernet, Wi-Fi, etc.) for scan and bind."""
from __future__ import annotations

import re
import socket
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class NetInterface:
    key: str          # stable id for combobox
    name: str         # display name
    ip: str
    subnet_prefix: str  # e.g. 10.7.15 for /24
    kind: str = ""    # ethernet | wifi | other
    is_up: bool = True

    @property
    def label(self) -> str:
        k = f" [{self.kind}]" if self.kind else ""
        return f"{self.name}{k} — {self.ip} ({self.subnet_prefix}.x)"


def _prefix_from_ip_mask(ip: str, mask: str | None = None) -> str:
    parts = ip.split(".")
    if len(parts) != 4:
        return ""
    if mask:
        try:
            mp = [int(x) for x in mask.split(".")]
            ipn = [int(x) for x in parts]
            return ".".join(str(ipn[i] & mp[i]) for i in range(3))
        except ValueError:
            pass
    return ".".join(parts[:3])


def _guess_kind(name: str) -> str:
    n = name.lower()
    if any(x in n for x in ("wi-fi", "wifi", "wlan", "wireless")):
        return "wifi"
    if any(x in n for x in ("ethernet", "eth", "lan", "realtek", "intel")):
        return "ethernet"
    return "other"


def _list_psutil() -> list[NetInterface]:
    try:
        import psutil
    except ImportError:
        return []
    out: list[NetInterface] = []
    stats = psutil.net_if_stats()
    for name, addrs in psutil.net_if_addrs().items():
        if name.lower().startswith("loopback"):
            continue
        st = stats.get(name)
        if st and not st.isup:
            continue
        for addr in addrs:
            if addr.family != socket.AF_INET:
                continue
            ip = addr.address
            if not ip or ip.startswith("127."):
                continue
            mask = getattr(addr, "netmask", None)
            prefix = _prefix_from_ip_mask(ip, mask)
            out.append(NetInterface(
                key=f"{name}|{ip}",
                name=name,
                ip=ip,
                subnet_prefix=prefix,
                kind=_guess_kind(name),
                is_up=True if not st else st.isup,
            ))
            break
    return out


def _list_windows_ipconfig() -> list[NetInterface]:
    if sys.platform != "win32":
        return []
    try:
        raw = subprocess.check_output(["ipconfig"], text=True, errors="replace", timeout=8)
    except (subprocess.SubprocessError, FileNotFoundError):
        return []
    out: list[NetInterface] = []
    current = ""
    for line in raw.splitlines():
        line = line.rstrip()
        if line and not line.startswith(" ") and ":" in line and "adapter" in line.lower():
            current = line.split(":", 1)[0].replace("adapter", "").strip()
            continue
        m_ip = re.search(r"IPv4 Address[^:]*:\s*([\d.]+)", line, re.I)
        m_mask = re.search(r"Subnet Mask[^:]*:\s*([\d.]+)", line, re.I)
        if m_ip and current:
            ip = m_ip.group(1).strip()
            if ip.startswith("127."):
                continue
            mask = m_mask.group(1).strip() if m_mask else None
            prefix = _prefix_from_ip_mask(ip, mask)
            out.append(NetInterface(
                key=f"{current}|{ip}",
                name=current,
                ip=ip,
                subnet_prefix=prefix,
                kind=_guess_kind(current),
            ))
            current = ""
    return out


def _list_linux_ip() -> list[NetInterface]:
    if sys.platform == "linux":
        try:
            raw = subprocess.check_output(["ip", "-4", "addr"], text=True, errors="replace", timeout=8)
        except (subprocess.SubprocessError, FileNotFoundError):
            return []
        out: list[NetInterface] = []
        iface = ""
        for line in raw.splitlines():
            m_if = re.match(r"^\d+:\s(\S+):", line)
            if m_if:
                iface = m_if.group(1)
                continue
            m_ip = re.search(r"inet\s+([\d.]+)/(\d+)", line)
            if m_ip and iface and iface != "lo":
                ip = m_ip.group(1)
                plen = int(m_ip.group(2))
                if plen >= 24:
                    prefix = ".".join(ip.split(".")[:3])
                else:
                    prefix = _prefix_from_ip_mask(ip)
                out.append(NetInterface(
                    key=f"{iface}|{ip}",
                    name=iface,
                    ip=ip,
                    subnet_prefix=prefix,
                    kind=_guess_kind(iface),
                ))
        return out
    return []


def list_interfaces() -> list[NetInterface]:
    """Return active IPv4 interfaces on this PC."""
    seen: set[str] = set()
    result: list[NetInterface] = []
    for fn in (_list_psutil, _list_windows_ipconfig, _list_linux_ip):
        for iface in fn():
            if iface.ip in seen:
                continue
            seen.add(iface.ip)
            result.append(iface)
        if result:
            break
    if not result:
        # fallback: OS default route
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            result.append(NetInterface(
                key=f"default|{ip}",
                name="Default route",
                ip=ip,
                subnet_prefix=_prefix_from_ip_mask(ip),
                kind="other",
            ))
        except OSError:
            pass
    return result


def find_interface(key_or_ip: str, interfaces: list[NetInterface] | None = None) -> NetInterface | None:
    ifaces = interfaces or list_interfaces()
    for iface in ifaces:
        if iface.key == key_or_ip or iface.ip == key_or_ip or iface.name == key_or_ip:
            return iface
    return None
