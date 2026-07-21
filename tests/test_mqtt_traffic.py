"""MQTT raw traffic log and STRATA node auto-detection."""
from backend.models.tracker import WifiNode
from backend.services.mqtt_node_detect import detect_node_from_mqtt, register_node_from_mqtt
from backend.services.mqtt_tag_ingest import init_mqtt_tag_ingest
from backend.services.mqtt_traffic_log import get_mqtt_traffic_log


STRATA_TOPIC = "strata/v1/bluetooth/1/273983315172900"
STRATA_PAYLOAD = "[1,1750690877,30,273983315172900,1,828033288983,-95]"


def test_detect_strata_from_topic():
    key, hints = detect_node_from_mqtt(STRATA_TOPIC, STRATA_PAYLOAD)
    assert key == "STRATA:273983315172900"
    assert hints["payload_format"] == "strata_v1_array"
    assert hints["strata_node_id"] == "273983315172900"


def test_detect_strata_from_payload_only():
    key, hints = detect_node_from_mqtt("unknown/topic", STRATA_PAYLOAD)
    assert key == "STRATA:273983315172900"


def test_traffic_log_ring_buffer():
    log = get_mqtt_traffic_log()
    before = log.total_received
    log.append(
        client_id="c1",
        topic=STRATA_TOPIC,
        payload=STRATA_PAYLOAD,
        node_key="STRATA:273983315172900",
        parsed=False,
        payload_format="strata_v1_array",
    )
    assert log.total_received == before + 1
    items = log.list_entries(limit=5, node_key="STRATA:273983315172900")
    assert items[0]["topic"] == STRATA_TOPIC
    assert items[0]["parsed"] is False


def test_ingest_registers_strata_node_without_parsing(app, db_session):
    with app.app_context():
        ingest = init_mqtt_tag_ingest(app=app)
        ingest.handle_message("client-1", STRATA_TOPIC, STRATA_PAYLOAD)

    node = db_session.query(WifiNode).filter_by(mac_address="STRATA:273983315172900").first()
    assert node is not None
    assert node.last_heartbeat is not None

    import json
    meta = json.loads(node.metadata_json)
    assert meta.get("mqtt_auto_detected") is True
    assert meta.get("strata_node_id") == "273983315172900"


def test_mqtt_traffic_api(client, auth_headers, app):
    with app.app_context():
        ingest = init_mqtt_tag_ingest(app=app)
        ingest.handle_message("c1", STRATA_TOPIC, STRATA_PAYLOAD)

    res = client.get("/api/nodes/mqtt-traffic?limit=10", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert "items" in data
    assert data["summary"]["total_received"] >= 1
    assert any(i["topic"] == STRATA_TOPIC for i in data["items"])


def test_acknowledge_node_api(client, admin_headers, db_session, app):
    with app.app_context():
        register_node_from_mqtt("STRATA:273983315172900", {"strata_node_id": "273983315172900"})

    node = db_session.query(WifiNode).filter_by(mac_address="STRATA:273983315172900").first()
    res = client.post(
        f"/api/nodes/{node.id}/acknowledge",
        json={"assigned_name": "Anchor East"},
        headers=admin_headers,
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["node"]["assigned_name"] == "Anchor East"
    import json
    meta = json.loads(db_session.query(WifiNode).get(node.id).metadata_json)
    assert meta.get("mqtt_acknowledged") is True
