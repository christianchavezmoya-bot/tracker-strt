"""MQTT client IP registry."""
from backend.services.mqtt_client_registry import (
    get_ip_for_client,
    get_ip_for_node,
    link_node_key,
    normalize_client_ip,
    note_node_ip,
    register_client,
)


def test_normalize_client_ip():
    assert normalize_client_ip("10.60.1.50") == "10.60.1.50"
    assert normalize_client_ip("10.60.1.50:54321") == "10.60.1.50"
    assert normalize_client_ip("('10.60.1.50', 54321)") == "10.60.1.50"


def test_link_node_key_with_explicit_ip():
    register_client("ephemeral-1", "10.60.1.22")
    link_node_key("STRATA:111", "ephemeral-1", client_ip="10.60.1.22")
    assert get_ip_for_node("STRATA:111") == "10.60.1.22"
    assert get_ip_for_client("ephemeral-1") == "10.60.1.22"


def test_note_node_ip_updates_node_mapping():
    note_node_ip("STRATA:222", "10.60.1.33")
    assert get_ip_for_node("STRATA:222") == "10.60.1.33"
