"""Tests for BlueApro HTTP payload parsing."""
from node_reader.blueapro_client import parse_device_payload, parse_push_payload


def test_parse_json_devices_list():
    body = '[{"mac":"F9:2F:B6:2C:DE:24","rssi":-72,"name":"MOKO-H7"}]'
    devices = parse_device_payload(body, "application/json")
    assert len(devices) == 1
    assert devices[0].mac == "F9:2F:B6:2C:DE:24"
    assert devices[0].rssi == -72


def test_parse_json_wrapped():
    body = '{"devices":[{"mac_address":"AA:BB:CC:DD:EE:01","RSSI":-65}]}'
    devices = parse_device_payload(body, "application/json")
    assert len(devices) == 1
    assert devices[0].mac == "AA:BB:CC:DD:EE:01"


def test_parse_csv_holo():
    body = "NODE01,F9:2F:B6:2C:DE:24,-72,98"
    devices = parse_device_payload(body, "text/plain")
    assert len(devices) == 1
    assert devices[0].rssi == -72


def test_parse_push_bytes():
    body = b'{"mac":"11:22:33:44:55:66","rssi":-80}'
    devices = parse_push_payload(body, "application/json")
    assert len(devices) == 1
    assert devices[0].source == "node-push"
