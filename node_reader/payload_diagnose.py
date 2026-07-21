"""Detect non-BLE UDP/TCP payloads (e.g. OpenWrt syslog vs BlueApro JSON)."""
from __future__ import annotations


def diagnose_payload(data: bytes, src_ip: str = "") -> str:
    """Return a human-readable hint when incoming data is not BlueApro tag JSON."""
    if not data:
        return "Empty packet"

    text = data.decode("utf-8", errors="replace").strip()
    if not text:
        return f"Non-text/binary payload ({len(data)} bytes) — set BlueApro encoding to JSON Parsed"

    if _looks_like_syslog(text):
        hint = "Router syslog detected (not BLE tags)."
        if src_ip.endswith(".1") or src_ip in ("192.168.1.1", "10.0.0.1"):
            hint += (
                " You configured OpenWrt LuCI → System → Logging → External log server."
                " Turn that OFF. Configure BlueApro web UI → Transport → Raw UDP Client instead."
            )
        return hint

    if src_ip.endswith(".1"):
        return (
            f"Traffic from {src_ip} is usually your router, not BlueApro."
            " Find the BlueApro IP (scan again, check device label, or try 192.168.4.1 in AP mode)."
        )

    if text.startswith("{") or text.startswith("["):
        preview = text[:120].replace("\n", " ")
        return f"JSON received but no tag MAC found. Preview: {preview}"

    if not all(c.isprintable() or c in "\r\n\t" for c in text):
        return f"Binary payload ({len(data)} bytes) — use JSON Parsed on BlueApro"

    preview = text[:80].replace("\n", " ")
    return f"Unrecognized text ({len(data)} bytes): {preview!r}"


def _looks_like_syslog(text: str) -> bool:
    t = text.lstrip()
    if t.startswith("<") and ">" in t[:20]:
        return True
    lower = text.lower()
    return any(
        k in lower
        for k in (
            "openwrt",
            "dnsmasq",
            "kernel:",
            "dropbear",
            "hostapd",
            "procd:",
            "ubus",
            "logread",
        )
    )
