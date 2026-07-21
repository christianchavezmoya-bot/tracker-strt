"""Tests for UDP payload diagnosis (router syslog vs BlueApro JSON)."""
from node_reader.payload_diagnose import diagnose_payload


def test_detect_openwrt_syslog():
    payload = b"<30>Jul 21 15:16:47 openwrt dnsmasq-dhcp: DHCPACK(wlan0) 192.168.1.50"
    hint = diagnose_payload(payload, "192.168.1.1")
    assert "syslog" in hint.lower()
    assert "openwrt" in hint.lower() or "router" in hint.lower()


def test_detect_router_ip_non_json():
    hint = diagnose_payload(b"hello from router", "192.168.1.1")
    assert "192.168.1.1" in hint or "router" in hint.lower()


def test_json_without_mac():
    hint = diagnose_payload(b'{"status":"ok","uptime":123}', "192.168.1.55")
    assert "no tag" in hint.lower() or "mac" in hint.lower()
