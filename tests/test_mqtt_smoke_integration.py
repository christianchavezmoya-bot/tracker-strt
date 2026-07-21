"""Live smoke test: embedded broker + publish + ingest end-to-end."""
from __future__ import annotations

import asyncio
import os
import threading
import time

import pytest

SMOKE_PORT = 1888


@pytest.fixture(scope="module")
def broker_port():
    return int(os.getenv("MQTT_SMOKE_PORT", SMOKE_PORT))


def test_embedded_broker_receives_and_parses_csv(broker_port):
    """Broker capture plugin receives a CSV publish and parse yields tag MAC."""
    from backend.services.mqtt_broker_service import MqttBrokerService
    from backend.services.mqtt_tag_parse import parse_mqtt_payload

    captured = []
    broker = MqttBrokerService(
        bind="127.0.0.1",
        port=broker_port,
        on_message=lambda cid, topic, payload: captured.append((cid, topic, payload)),
    )
    ok, msg = broker.start()
    assert ok, msg
    try:
        time.sleep(0.5)
        import paho.mqtt.client as mqtt

        try:
            pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="smoke-publisher")
        except AttributeError:
            pub = mqtt.Client(client_id="smoke-publisher")
        pub.connect("127.0.0.1", broker_port, keepalive=30)
        pub.loop_start()
        payload = "00:C0:CA:A1:4B:18,F9:2F:B6:2C:DE:24,-72,98"
        pub.publish("rssi/data", payload, qos=0)
        deadline = time.time() + 5
        while time.time() < deadline and not captured:
            time.sleep(0.1)
        pub.loop_stop()
        pub.disconnect()
    finally:
        broker.stop()

    assert captured, "broker did not capture any MQTT message"
    _cid, topic, body = captured[0]
    assert topic == "rssi/data"
    readings = parse_mqtt_payload(body, topic)
    assert len(readings) == 1
    assert readings[0].tag_mac == "F9:2F:B6:2C:DE:24"
    assert readings[0].anchor_mac == "00:C0:CA:A1:4B:18"
    assert broker.message_count >= 1


def test_full_pipeline_broker_to_db(app, db_session, broker_port):
    """Publish via broker → ingest handler → DB rows for anchor + detection."""
    from backend.models.detection import DetectionEvent, WifiAnchor
    from backend.models.tracker import WifiNode
    from backend.services.mqtt_broker_service import MqttBrokerService
    from backend.services.mqtt_tag_ingest import MqttTagIngestService

    ingest = MqttTagIngestService(app=app)
    ready = threading.Event()

    def on_msg(cid, topic, payload):
        ingest.handle_message(cid, topic, payload)
        ready.set()

    broker = MqttBrokerService(bind="127.0.0.1", port=broker_port + 1, on_message=on_msg)
    ok, msg = broker.start()
    assert ok, msg
    try:
        time.sleep(0.5)
        import paho.mqtt.client as mqtt

        try:
            pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="smoke-e2e")
        except AttributeError:
            pub = mqtt.Client(client_id="smoke-e2e")
        pub.connect("127.0.0.1", broker_port + 1, keepalive=30)
        pub.loop_start()
        pub.publish(
            "rssi/data",
            "AA:BB:CC:DD:EE:01,11:22:33:44:55:66,-68,95",
            qos=0,
        )
        assert ready.wait(timeout=5), "ingest handler never fired"
        pub.loop_stop()
        pub.disconnect()
    finally:
        broker.stop()

    anchor = db_session.query(WifiAnchor).filter_by(mac_address="AA:BB:CC:DD:EE:01").first()
    node = db_session.query(WifiNode).filter_by(mac_address="AA:BB:CC:DD:EE:01").first()
    assert anchor is not None, "WifiAnchor not auto-created"
    assert node is not None, "WifiNode not auto-created"
    assert node.last_heartbeat is not None, "heartbeat not updated"
    events = db_session.query(DetectionEvent).filter_by(anchor_id=anchor.id).all()
    assert len(events) == 1
    assert events[0].mac_address == "11:22:33:44:55:66"
    assert events[0].rssi == -68
    assert ingest.message_count >= 1


def test_phase0_anchor_load_smoke(app, db_session):
    """PositioningService loads active WifiNode coordinates."""
    from backend.models.tracker import NodeStatus, WifiNode
    from backend.services.positioning_service import PositioningService

    db_session.add(
        WifiNode(
            mac_address="SM:OK:E0:00:00:01",
            assigned_name="Smoke Anchor",
            pos_x=12.0,
            pos_y=34.0,
            pos_z=2.0,
            status=int(NodeStatus.ACTIVE),
        )
    )
    db_session.commit()

    svc = PositioningService(db_session)
    n = svc.load_anchors_from_db()
    assert n >= 1
    assert svc._anchors["SM:OK:E0:00:00:01"] == (12.0, 34.0, 2.0)


def test_phase0_scanner_delete_smoke(client, admin_headers, db_session):
    """DELETE /api/scanner/anchors/:id removes anchor."""
    from backend.models.detection import WifiAnchor

    anchor = WifiAnchor(mac_address="SM:OK:E0:00:00:02", name="Delete Me")
    db_session.add(anchor)
    db_session.commit()
    resp = client.delete(f"/api/scanner/anchors/{anchor.id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.get_json().get("ok") is True
    assert db_session.query(WifiAnchor).filter_by(id=anchor.id).first() is None
