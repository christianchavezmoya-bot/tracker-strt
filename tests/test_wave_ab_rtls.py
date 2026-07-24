"""Wave A/B — RTLS readiness and MQTT admin control."""
from backend.models.tracker import NodeStatus, WifiNode
from backend.services.node_utils import is_node_placed
from backend.services.rtls_readiness import compute_readiness, MIN_ANCHORS_FOR_TAGS


def test_rtls_readiness_needs_anchors(app, db_session):
    r = compute_readiness(db_session)
    assert r["anchors_required"] == MIN_ANCHORS_FOR_TAGS
    assert r["ready"] is False
    assert len(r["checklist"]) >= 4


def test_rtls_readiness_tunnel_profile_requires_two_anchors(app, db_session):
    from backend.models import Setting

    db_session.add(Setting(key="positioning_application_profile", value="tunnel", value_type="select"))
    for i, mac in enumerate(["AA:00:00:00:10:01", "AA:00:00:00:10:02"]):
        db_session.add(
            WifiNode(
                mac_address=mac,
                assigned_name=f"T{i}",
                pos_x=float(i + 1),
                pos_y=float(i + 2),
                status=int(NodeStatus.ACTIVE),
                metadata_json='{"placed_on_map": true}',
            )
        )
    db_session.commit()

    r = compute_readiness(db_session)
    assert r["anchors_required"] == 2
    assert r["anchors_needed"] == 0
    assert r["positioning_profile"]["id"] == "tunnel"

    WifiNode.query.filter(WifiNode.mac_address.in_(["AA:00:00:00:10:01", "AA:00:00:00:10:02"])).delete(synchronize_session=False)
    from backend.models import Setting as SettingModel
    SettingModel.query.filter_by(key="positioning_application_profile").delete(synchronize_session=False)
    db_session.commit()


def test_rtls_readiness_with_placed_anchors(app, db_session):
    for i, mac in enumerate(["AA:00:00:00:00:01", "AA:00:00:00:00:02", "AA:00:00:00:00:03"]):
        db_session.add(
            WifiNode(
                mac_address=mac,
                assigned_name=f"A{i}",
                pos_x=float(i + 1),
                pos_y=float(i + 2),
                status=int(NodeStatus.ACTIVE),
                metadata_json='{"placed_on_map": true}',
            )
        )
    db_session.commit()
    r = compute_readiness(db_session)
    assert r["anchors_placed"] == 3
    assert r["anchors_needed"] == 0
    item = next(x for x in r["checklist"] if x["id"] == "anchors_placed")
    assert item["ok"] is True


def test_nodes_filter_discovered(client, auth_headers, db_session):
    db_session.add(
        WifiNode(mac_address="DIS:CO:VE:RE:00:01", assigned_name="New", status=int(NodeStatus.CALIBRATING))
    )
    db_session.add(
        WifiNode(
            mac_address="PL:AC:ED:00:00:01",
            assigned_name="Placed",
            pos_x=5.0,
            pos_y=5.0,
            status=int(NodeStatus.ACTIVE),
            metadata_json='{"placed_on_map": true}',
        )
    )
    db_session.commit()

    res = client.get("/api/nodes?filter=discovered", headers=auth_headers)
    assert res.status_code == 200
    items = res.get_json()["items"]
    macs = [n["mac_address"] for n in items]
    assert "DIS:CO:VE:RE:00:01" in macs
    assert "PL:AC:ED:00:00:01" not in macs


def test_wifi_unit_setup_api(client, auth_headers):
    res = client.get("/api/system/wifi-unit-setup", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["topic"] == "rssi/data"
    assert "broker_host" in data
    assert "example_payload" in data


def test_patch_node_marks_placed(app, db_session):
    from backend.services.node_utils import is_node_placed

    node = WifiNode(
        mac_address="PL:AC:EM:EN:T:01",
        assigned_name="Test",
        status=int(NodeStatus.CALIBRATING),
    )
    db_session.add(node)
    db_session.commit()
    node.pos_x = 10.0
    node.pos_y = 20.0
    from backend.services.node_utils import mark_node_placed
    mark_node_placed(node)
    db_session.commit()
    assert is_node_placed(node)
    assert node.status == int(NodeStatus.ACTIVE)


def test_mqtt_broker_toggle_admin(client, admin_headers, app):
    res = client.post("/api/system/mqtt-broker", json={"enabled": True}, headers=admin_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["enabled"] is True

    res2 = client.get("/api/system/mqtt-broker", headers=admin_headers)
    assert res2.status_code == 200
    assert res2.get_json()["enabled"] is True

    res3 = client.post("/api/system/mqtt-broker", json={"enabled": False}, headers=admin_headers)
    assert res3.status_code == 200
    assert res3.get_json()["enabled"] is False
