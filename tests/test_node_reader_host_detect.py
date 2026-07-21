"""Tests for host type detection."""
from node_reader.blueapro_client import ROUTER_HINT, detect_host_type


def test_detect_openwrt():
    html = "<html><title>OpenWrt - LuCI</title><body>Powered by LuCI</body></html>"
    assert detect_host_type(html) == "openwrt"


def test_detect_blueapro():
    html = "<html><title>TinyGateway WiFi BLE - BlueUp</title></html>"
    assert detect_host_type(html) == "blueapro"


def test_router_hint_mentions_push():
    assert "Push mode" in ROUTER_HINT
