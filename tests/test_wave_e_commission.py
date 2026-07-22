"""Wave E — anchor commission scan, activate, timeline."""
import json

from backend.models.positioning import NodePresenceLog
from backend.models.tracker import NodeStatus, WifiNode
from backend.services.mqtt_node_detect import register_node_from_mqtt
from backend.services.mqtt_tag_ingest import init_mqtt_tag_ingest
from backend.services.node_presence import log_node_presence
from backend.services.node_scan import scan_nodes, commission_queue


STRATA_TOPIC = "strata/v1/bluetooth/1/214282185227987"
STRATA_PAYLOAD = "[1,1750730515,28,214282185227987,1,828033288983,-94]"


def test_scan_nodes_api(client, auth_headers, app, db_session):
    with app.app_context():
        ingest = init_mqtt_tag_ingest(app=app)
        ingest.handle_message("c1", STRATA_TOPIC, STRATA_PAYLOAD)

    res = client.get("/api/nodes/scan", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["total"] >= 1
    row = next(i for i in data["items"] if i["mac_address"] == "STRATA:214282185227987")
    assert "name" in row
    assert "node_ip" in row
    assert "last_heard_at" in row


def test_commission_queue(client, auth_headers, app, db_session):
    with app.app_context():
        register_node_from_mqtt("STRATA:999999999999999", {"strata_node_id": "999999999999999"})
    res = client.get("/api/nodes/commission-queue", headers=auth_headers)
    assert res.status_code == 200
    assert "detected" in res.get_json()


def test_activate_node(client, admin_headers, db_session):
    node = WifiNode(
        mac_address="STRATA:111111111111111",
        assigned_name="Test",
        status=int(NodeStatus.CALIBRATING),
        metadata_json='{"mqtt_acknowledged":true,"placed_on_map":false}',
    )
    db_session.add(node)
    db_session.commit()
    res = client.post(
        f"/api/nodes/{node.id}/activate",
        json={"assigned_name": "Gate A", "pos_x": 10.0, "pos_y": 20.0, "node_ip": "10.60.1.50"},
        headers=admin_headers,
    )
    assert res.status_code == 200
    data = res.get_json()["node"]
    assert data["assigned_name"] == "Gate A"
    meta = json.loads(db_session.query(WifiNode).get(node.id).metadata_json)
    assert meta.get("placed_on_map") is True
    assert meta.get("node_ip") == "10.60.1.50"


def test_node_presence_timeline(client, auth_headers, db_session):
    node = WifiNode(mac_address="STRATA:222222222222222", assigned_name="TL")
    db_session.add(node)
    db_session.flush()
    db_session.add(NodePresenceLog(node_id=node.id, online=True, rssi=-90.0, node_ip="10.60.1.51"))
    db_session.commit()
    res = client.get("/api/nodes/presence/timeline?minutes=60", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["window_minutes"] == 60
    assert any(n["id"] == node.id for n in data["nodes"])


def test_decommission_node(client, admin_headers, db_session):
    node = WifiNode(mac_address="STRATA:333333333333333", assigned_name="X")
    db_session.add(node)
    db_session.commit()
    res = client.post(f"/api/nodes/{node.id}/decommission", headers=admin_headers)
    assert res.status_code == 200
    meta = json.loads(db_session.query(WifiNode).get(node.id).metadata_json)
    assert meta.get("decommissioned") is True


def test_presence_logged_on_mqtt(app, db_session):
    with app.app_context():
        ingest = init_mqtt_tag_ingest(app=app)
        ingest.handle_message("c1", STRATA_TOPIC, STRATA_PAYLOAD)
    node = db_session.query(WifiNode).filter_by(mac_address="STRATA:214282185227987").first()
    assert node is not None
    logs = db_session.query(NodePresenceLog).filter_by(node_id=node.id).all()
    assert len(logs) >= 1
