"""Wave C — node diagnostics API."""
from datetime import datetime, timedelta

from backend.models.detection import DetectionEvent, SignalType, WifiAnchor
from backend.models.tracker import NodeStatus, WifiNode
from backend.services.mqtt_tag_ingest import init_mqtt_tag_ingest
from backend.services.node_diagnostics import compute_all_diagnostics, compute_node_stats


def test_all_nodes_diagnostics_api(client, auth_headers, db_session):
    node = WifiNode(
        mac_address="DI:AG:00:00:00:01",
        assigned_name="Diag Node",
        status=int(NodeStatus.ACTIVE),
        last_heartbeat=datetime.utcnow(),
    )
    db_session.add(node)
    db_session.commit()

    res = client.get("/api/nodes/diagnostics", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert "broker" in data
    assert "nodes" in data
    assert data["summary"]["total"] >= 1


def test_node_diagnostics_and_stats(client, auth_headers, db_session, app):
    node = WifiNode(
        mac_address="DI:AG:00:00:00:02",
        assigned_name="Stats Node",
        status=int(NodeStatus.ACTIVE),
        last_heartbeat=datetime.utcnow(),
    )
    anchor = WifiAnchor(mac_address="DI:AG:00:00:00:02", name="Stats Node")
    db_session.add_all([node, anchor])
    db_session.flush()
    db_session.add(
        DetectionEvent(
            anchor_id=anchor.id,
            mac_address="TA:GA:AA:BB:CC:01",
            rssi=-68.0,
            signal_type=int(SignalType.BLE),
            timestamp=datetime.utcnow(),
        )
    )
    db_session.commit()

    ingest = init_mqtt_tag_ingest(app=app)
    ingest.handle_message("test", "rssi/data", "DI:AG:00:00:00:02,TA:GA:AA:BB:CC:02,-70,90")

    dres = client.get(f"/api/nodes/{node.id}/diagnostics", headers=auth_headers)
    assert dres.status_code == 200
    diag = dres.get_json()["diagnostics"]
    assert diag["mac_address"] == "DI:AG:00:00:00:02"
    assert diag["connectivity"] in ("online", "weak", "offline", "unknown")

    sres = client.get(f"/api/nodes/{node.id}/stats?since=24h", headers=auth_headers)
    assert sres.status_code == 200
    stats = sres.get_json()["stats"]
    assert stats["detection_count"] >= 1
    assert stats["unique_tags"] >= 1


def test_diagnostics_tracks_last_payload(app, db_session):
    with app.app_context():
        ingest = init_mqtt_tag_ingest(app=app)
        payload = "AA:BB:CC:DD:EE:01,11:22:33:44:55:66,-72,98"
        ingest.handle_message("n1", "rssi/data", payload)
        d = ingest.diagnostics()
        assert d["per_node_last_payload"]["AA:BB:CC:DD:EE:01"] == payload
