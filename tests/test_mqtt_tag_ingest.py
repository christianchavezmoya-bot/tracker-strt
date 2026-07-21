"""Tests for MQTT tag ingest and anchor auto-registration."""
from backend.models.detection import DetectionEvent, WifiAnchor
from backend.models.tracker import WifiNode, NodeStatus
from backend.services.mqtt_tag_ingest import MqttTagIngestService


def test_mqtt_ingest_auto_registers_anchor_and_detection(app, db_session):
    ingest = MqttTagIngestService(app=app)
    payload = "00:C0:CA:A1:4B:18,F9:2F:B6:2C:DE:24,-72,98"
    ingest.handle_message("wifi-node-1", "rssi/data", payload)

    anchor = db_session.query(WifiAnchor).filter_by(mac_address="00:C0:CA:A1:4B:18").first()
    assert anchor is not None
    node = db_session.query(WifiNode).filter_by(mac_address="00:C0:CA:A1:4B:18").first()
    assert node is not None
    assert node.last_heartbeat is not None

    events = db_session.query(DetectionEvent).filter_by(anchor_id=anchor.id).all()
    assert len(events) == 1
    assert events[0].mac_address == "F9:2F:B6:2C:DE:24"
    assert events[0].rssi == -72


def test_load_anchors_from_db_uses_wifi_node_fields(app, db_session):
    from backend.services.positioning_service import PositioningService

    node = WifiNode(
        mac_address="AA:11:22:33:44:55",
        assigned_name="Test Anchor",
        pos_x=5.0,
        pos_y=10.0,
        pos_z=1.5,
        status=int(NodeStatus.ACTIVE),
    )
    db_session.add(node)
    db_session.commit()

    svc = PositioningService(db_session)
    count = svc.load_anchors_from_db()
    assert count == 1
    assert "AA:11:22:33:44:55" in svc._anchors
    assert svc._anchors["AA:11:22:33:44:55"] == (5.0, 10.0, 1.5)
