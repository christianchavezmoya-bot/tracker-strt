"""Tests for MQTT payload parsing."""
from node_reader.mqtt_parse import parse_mqtt_payload


def test_parse_mqtt_csv():
    devices = parse_mqtt_payload("00:C0:CA:A1:4B:18,F9:2F:B6:2C:DE:24,-72,98", "rssi/data")
    assert len(devices) == 1
    assert devices[0].mac == "F9:2F:B6:2C:DE:24"
    assert devices[0].rssi == -72
    assert devices[0].source == "mqtt"


def test_parse_mqtt_json():
    devices = parse_mqtt_payload('{"mac":"AA:BB:CC:DD:EE:01","rssi":-65,"name":"MOKO"}', "ble/rssi")
    assert len(devices) == 1
    assert devices[0].source == "mqtt"
