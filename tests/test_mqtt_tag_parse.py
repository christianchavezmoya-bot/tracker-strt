"""Tests for server-side MQTT tag payload parsing."""
from backend.services.mqtt_tag_parse import (
    group_by_anchor,
    parse_mqtt_payload,
    readings_to_detections,
)


def test_parse_csv_payload():
    payload = "00:C0:CA:A1:4B:18,F9:2F:B6:2C:DE:24,-72,98"
    readings = parse_mqtt_payload(payload, "rssi/data")
    assert len(readings) == 1
    r = readings[0]
    assert r.anchor_mac == "00:C0:CA:A1:4B:18"
    assert r.tag_mac == "F9:2F:B6:2C:DE:24"
    assert r.rssi == -72
    assert r.battery == 98


def test_parse_csv_compact_mac():
    payload = "00C0CAA14B18,F92FB62CDE24,-65,100"
    readings = parse_mqtt_payload(payload, "rssi/data")
    assert readings[0].tag_mac == "F9:2F:B6:2C:DE:24"
    assert readings[0].anchor_mac == "00:C0:CA:A1:4B:18"


def test_group_by_anchor():
    payload = "AA:BB:CC:DD:EE:01,11:22:33:44:55:66,-70,90"
    readings = parse_mqtt_payload(payload)
    grouped = group_by_anchor(readings)
    assert "AA:BB:CC:DD:EE:01" in grouped
    dets = readings_to_detections(grouped["AA:BB:CC:DD:EE:01"])
    assert dets[0]["mac_address"] == "11:22:33:44:55:66"
    assert dets[0]["rssi"] == -70


def test_parse_json_devices():
    payload = '{"devices":[{"mac":"AA:BB:CC:DD:EE:FF","rssi":-68}]}'
    readings = parse_mqtt_payload(payload, "ble/rssi")
    assert len(readings) == 1
    assert readings[0].tag_mac == "AA:BB:CC:DD:EE:FF"
    assert readings[0].rssi == -68
