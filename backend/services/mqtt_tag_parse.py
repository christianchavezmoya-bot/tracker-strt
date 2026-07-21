"""Parse MQTT payloads from WiFi/BLE gateways (CSV or JSON)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class MqttTagReading:
    tag_mac: str
    rssi: float
    battery: Optional[float] = None
    anchor_mac: Optional[str] = None
    topic: str = ""
    raw: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def parse_mqtt_payload(text: str, topic: str = "") -> list[MqttTagReading]:
    """Parse tag data from an MQTT message body."""
    body = (text or "").strip()
    if not body:
        return []

    # HOLO / ESP32 CSV: NodeMAC,TagMAC,RSSI,Battery
    if "," in body and not body.startswith(("{", "[")):
        parts = [p.strip() for p in body.split(",")]
        if len(parts) >= 3:
            anchor_mac = _norm_mac(parts[0])
            tag_mac = _norm_mac(parts[1])
            if not tag_mac:
                return []
            try:
                rssi = float(parts[2])
            except ValueError:
                rssi = -999.0
            battery = None
            if len(parts) > 3:
                try:
                    battery = float(parts[3])
                except ValueError:
                    pass
            return [
                MqttTagReading(
                    tag_mac=tag_mac,
                    rssi=rssi,
                    battery=battery,
                    anchor_mac=anchor_mac or None,
                    topic=topic,
                    raw=body,
                )
            ]

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return []

    return _parse_json_payload(data, topic=topic, raw=body)


def group_by_anchor(readings: list[MqttTagReading]) -> dict[str, list[MqttTagReading]]:
    grouped: dict[str, list[MqttTagReading]] = {}
    for reading in readings:
        anchor = (reading.anchor_mac or "").upper()
        if not anchor:
            continue
        grouped.setdefault(anchor, []).append(reading)
    return grouped


def readings_to_detections(readings: list[MqttTagReading]) -> list[dict]:
    detections = []
    for r in readings:
        det = {
            "mac_address": r.tag_mac,
            "rssi": r.rssi,
            "signal_type": 2,  # BLE
        }
        if r.battery is not None:
            det["battery"] = r.battery
        detections.append(det)
    return detections


def _parse_json_payload(data: Any, *, topic: str, raw: str) -> list[MqttTagReading]:
    readings: list[MqttTagReading] = []

    if isinstance(data, list):
        for item in data:
            readings.extend(_parse_json_object(item, topic=topic, raw=raw))
        return readings

    if isinstance(data, dict):
        if "devices" in data and isinstance(data["devices"], list):
            for item in data["devices"]:
                readings.extend(_parse_json_object(item, topic=topic, raw=raw))
            return readings
        if "detections" in data and isinstance(data["detections"], list):
            anchor = _norm_mac(str(data.get("anchor_mac") or data.get("node_mac") or ""))
            for item in data["detections"]:
                readings.extend(_parse_json_object(item, topic=topic, raw=raw, anchor_mac=anchor))
            return readings
        readings.extend(_parse_json_object(data, topic=topic, raw=raw))
    return readings


def _parse_json_object(
    obj: Any,
    *,
    topic: str,
    raw: str,
    anchor_mac: Optional[str] = None,
) -> list[MqttTagReading]:
    if not isinstance(obj, dict):
        return []
    mac = _norm_mac(str(obj.get("mac") or obj.get("mac_address") or obj.get("bssid") or ""))
    if not mac:
        return []
    try:
        rssi = float(obj.get("rssi", obj.get("signal_strength", -70)))
    except (TypeError, ValueError):
        rssi = -70.0
    anchor = _norm_mac(str(obj.get("anchor_mac") or obj.get("node_mac") or anchor_mac or ""))
    battery = obj.get("battery")
    try:
        battery = float(battery) if battery is not None else None
    except (TypeError, ValueError):
        battery = None
    return [
        MqttTagReading(
            tag_mac=mac,
            rssi=rssi,
            battery=battery,
            anchor_mac=anchor or None,
            topic=topic,
            raw=raw,
        )
    ]


def _norm_mac(mac: str) -> str:
    mac = (mac or "").strip().upper()
    if not mac:
        return ""
    if ":" in mac or "-" in mac:
        return mac.replace("-", ":")
    if len(mac) == 12 and re.fullmatch(r"[0-9A-F]{12}", mac):
        return ":".join(mac[i : i + 2] for i in range(0, 12, 2))
    return mac
