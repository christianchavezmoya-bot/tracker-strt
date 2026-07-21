"""Parse MQTT payloads from WiFi/BLE gateways (CSV or JSON)."""
from __future__ import annotations

from node_reader.blueapro_client import NodeDevice, parse_device_payload, parse_push_payload


def parse_mqtt_payload(text: str, topic: str = "") -> list[NodeDevice]:
    """Parse tag data from MQTT message body."""
    body = (text or "").strip()
    if not body:
        return []

    # HOLO / ESP32 CSV: NodeMAC,TagMAC,RSSI,Battery
    if "," in body and not body.startswith(("{", "[")):
        parts = [p.strip() for p in body.split(",")]
        if len(parts) >= 3:
            tag_mac = parts[1]
            try:
                rssi = int(float(parts[2]))
            except ValueError:
                rssi = -999
            mac = _norm_csv_mac(tag_mac)
            if mac:
                return [NodeDevice(mac=mac, rssi=rssi, source="mqtt", raw={"topic": topic, "csv": body})]

    devices = parse_device_payload(body, "application/json")
    if not devices:
        devices = parse_push_payload(body.encode("utf-8"), "application/json")
    for d in devices:
        d.source = "mqtt"
        if d.raw is None:
            d.raw = {"topic": topic}
        elif isinstance(d.raw, dict):
            d.raw.setdefault("topic", topic)
    return devices


def _norm_csv_mac(mac: str) -> str:
    mac = (mac or "").strip().upper()
    if not mac:
        return ""
    if ":" in mac or "-" in mac:
        return mac.replace("-", ":")
    if len(mac) == 12:
        return ":".join(mac[i : i + 2] for i in range(0, 12, 2))
    return mac
