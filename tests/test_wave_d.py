"""Wave D — anchor sync, refresh-positions, broker port reachability."""
from backend.models.detection import WifiAnchor
from backend.models.tracker import NodeStatus, WifiNode
from backend.services.anchor_sync import (
    count_placed_nodes,
    delete_anchor_for_node,
    refresh_tag_positions,
    sync_node_full,
)


def test_sync_node_full_creates_and_updates_anchor(db_session):
    node = WifiNode(
        mac_address="SY:NC:00:00:00:01",
        assigned_name="Sync Node",
        pos_x=12.0,
        pos_y=34.0,
        pos_z=0.0,
        status=int(NodeStatus.ACTIVE),
        metadata_json='{"placed_on_map": true}',
    )
    db_session.add(node)
    db_session.flush()

    anchor = sync_node_full(node)
    db_session.commit()

    assert anchor.mac_address == "SY:NC:00:00:00:01"
    assert anchor.name == "Sync Node"
    assert anchor.real_x == 12.0
    assert anchor.real_y == 34.0

    node.pos_x = 20.0
    sync_node_full(node)
    db_session.commit()
    refreshed = db_session.query(WifiAnchor).filter_by(mac_address="SY:NC:00:00:00:01").one()
    assert refreshed.real_x == 20.0


def test_delete_node_removes_scanner_anchor(client, admin_headers, db_session):
    node = WifiNode(
        mac_address="DE:LE:TE:00:00:01",
        assigned_name="To Delete",
        status=int(NodeStatus.ACTIVE),
    )
    anchor = WifiAnchor(mac_address="DE:LE:TE:00:00:01", name="To Delete")
    db_session.add_all([node, anchor])
    db_session.commit()
    node_id = node.id

    resp = client.delete(f"/api/nodes/{node_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert db_session.query(WifiNode).filter_by(id=node_id).first() is None
    assert db_session.query(WifiAnchor).filter_by(mac_address="DE:LE:TE:00:00:01").first() is None


def test_delete_anchor_for_node_helper(db_session):
    node = WifiNode(mac_address="HE:LP:ER:00:00:01", assigned_name="H")
    anchor = WifiAnchor(mac_address="HE:LP:ER:00:00:01", name="H")
    db_session.add_all([node, anchor])
    db_session.commit()

    delete_anchor_for_node("HE:LP:ER:00:00:01")
    db_session.commit()
    assert db_session.query(WifiAnchor).filter_by(mac_address="HE:LP:ER:00:00:01").first() is None


def test_count_placed_nodes(db_session):
    db_session.add_all([
        WifiNode(
            mac_address="PL:01:00:00:00:01",
            pos_x=1.0,
            pos_y=2.0,
            metadata_json='{"placed_on_map": true}',
        ),
        WifiNode(mac_address="PL:02:00:00:00:02"),
    ])
    db_session.commit()
    assert count_placed_nodes(db_session) == 1


def test_refresh_positions_api(client, auth_headers, db_session):
    for i, mac in enumerate(["RF:01:00:00:00:01", "RF:02:00:00:00:02", "RF:03:00:00:00:03"]):
        db_session.add(
            WifiNode(
                mac_address=mac,
                assigned_name=f"A{i}",
                pos_x=float(i + 1),
                pos_y=float(i + 2),
                metadata_json='{"placed_on_map": true}',
            )
        )
    db_session.commit()

    res = client.post("/api/nodes/refresh-positions", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["anchors_placed"] == 3
    assert data["ready"] is True
    assert data["anchors_required"] == 3


def test_refresh_tag_positions_returns_counts(db_session):
    db_session.add(
        WifiNode(
            mac_address="RF:04:00:00:00:04",
            pos_x=5.0,
            pos_y=6.0,
            metadata_json='{"placed_on_map": true}',
        )
    )
    db_session.commit()
    result = refresh_tag_positions(db_session)
    assert "positions_computed" in result
    assert result["anchors_placed"] == 1


def test_mqtt_broker_includes_port_reachable(client, admin_headers):
    client.post("/api/system/mqtt-broker", json={"enabled": True}, headers=admin_headers)
    res = client.get("/api/system/mqtt-broker", headers=admin_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert "port_reachable" in data
    client.post("/api/system/mqtt-broker", json={"enabled": False}, headers=admin_headers)


def test_nodes_diagnostics_includes_port_reachable(client, auth_headers, db_session):
    res = client.get("/api/nodes/diagnostics", headers=auth_headers)
    assert res.status_code == 200
    broker = res.get_json()["broker"]
    assert "port_reachable" in broker
