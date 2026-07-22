"""IP conflict detection and interface resolution."""
from backend.services.net_interface_resolve import interface_label, resolve_server_interface
from backend.services.node_ip_diagnostics import build_ip_conflict_map, enrich_scan_item


def test_build_ip_conflict_map():
    items = [
        {"mac_address": "STRATA:111", "node_ip": "10.60.1.10"},
        {"mac_address": "STRATA:222", "node_ip": "10.60.1.10"},
        {"mac_address": "STRATA:333", "node_ip": "10.60.1.20"},
    ]
    conflicts = build_ip_conflict_map(items)
    assert "10.60.1.10" in conflicts
    assert len(conflicts["10.60.1.10"]) == 2
    assert "10.60.1.20" not in conflicts


def test_enrich_scan_item_flags_conflict():
    items = [
        {"mac_address": "STRATA:111", "node_ip": "10.60.1.10"},
        {"mac_address": "STRATA:222", "node_ip": "10.60.1.10"},
    ]
    conflicts = build_ip_conflict_map(items)
    a = enrich_scan_item(dict(items[0]), conflicts)
    assert a["ip_conflict"] is True
    assert "STRATA:222" in a["ip_shared_with"]


def test_interface_label_fallback():
    assert interface_label(None, None) == "—"
    assert "eth0" in interface_label("10.60.1.10", "eth0")
