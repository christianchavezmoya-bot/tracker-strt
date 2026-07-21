"""Tests for host type detection."""
from node_reader.blueapro_client import OPENWRT_STRATA_HINT, ROUTER_HINT, detect_host_type


def test_detect_openwrt():
    html = "<html><title>OpenWrt - LuCI</title><body>Powered by LuCI</body></html>"
    assert detect_host_type(html) == "openwrt"


def test_detect_openwrt_strata():
    html = "<html><title>OpenWrt - LuCI</title>STRATA uCentral powered by OpenWrt</html>"
    assert detect_host_type(html) == "openwrt_strata"


def test_detect_blueapro():
    html = "<html><title>TinyGateway WiFi BLE - BlueUp</title></html>"
    assert detect_host_type(html) == "blueapro"


def test_router_hint_mentions_blueup_ap():
    assert "192.168.4.1" in ROUTER_HINT
    assert "TinyGateway" in ROUTER_HINT


def test_strata_hint_mentions_services():
    assert "Services" in OPENWRT_STRATA_HINT
