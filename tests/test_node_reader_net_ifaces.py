"""Tests for network interface helpers."""
from node_reader.net_ifaces import NetInterface, _prefix_from_ip_mask, find_interface


def test_prefix_from_ip_mask():
    assert _prefix_from_ip_mask("10.7.15.76", "255.255.255.0") == "10.7.15"
    assert _prefix_from_ip_mask("192.168.4.1") == "192.168.4"


def test_find_interface_by_ip():
    ifaces = [
        NetInterface(key="Wi-Fi|10.7.15.76", name="Wi-Fi", ip="10.7.15.76", subnet_prefix="10.7.15", kind="wifi"),
        NetInterface(key="Eth|10.7.15.50", name="Ethernet", ip="10.7.15.50", subnet_prefix="10.7.15", kind="ethernet"),
    ]
    found = find_interface("10.7.15.76", ifaces)
    assert found is not None
    assert found.kind == "wifi"
