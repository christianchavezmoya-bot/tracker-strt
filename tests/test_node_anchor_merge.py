"""Tests for merging multiple STRATA IDs that share one physical unit IP."""
import json

from backend.models.tracker import NodeStatus, WifiNode
from backend.services.mqtt_node_detect import register_node_from_mqtt
from backend.services.mqtt_tag_ingest import init_mqtt_tag_ingest
from backend.services.node_anchor_merge import consolidate_duplicate_ip_nodes
from backend.services.node_scan import scan_nodes
from backend.services.node_utils import get_node_metadata


def test_consolidate_marks_duplicate_ip_rows(app, db_session):
    with app.app_context():
        canonical = WifiNode(
            mac_address="STRATA:214282185227987",
            assigned_name="STRATA-227987",
            status=int(NodeStatus.CALIBRATING),
            metadata_json=json.dumps({
                "mqtt_auto_detected": True,
                "node_ip": "10.60.1.10",
                "strata_node_id": "214282185227987",
            }),
        )
        duplicate = WifiNode(
            mac_address="STRATA:214282185228770",
            assigned_name="STRATA-228770",
            status=int(NodeStatus.CALIBRATING),
            metadata_json=json.dumps({
                "mqtt_auto_detected": True,
                "node_ip": "10.60.1.10",
                "strata_node_id": "214282185228770",
            }),
        )
        db_session.add_all([canonical, duplicate])
        db_session.commit()

        merged = consolidate_duplicate_ip_nodes(db_session)
        assert merged == 1

        dup_meta = get_node_metadata(db_session.query(WifiNode).filter_by(mac_address="STRATA:214282185228770").one())
        can_meta = get_node_metadata(db_session.query(WifiNode).filter_by(mac_address="STRATA:214282185227987").one())
        assert dup_meta.get("merged_into") == canonical.id
        assert "214282185228770" in can_meta.get("merged_strata_ids", [])


def test_scan_after_consolidate_shows_one_row(app, db_session):
    with app.app_context():
        canonical = WifiNode(
            mac_address="STRATA:214282185227987",
            assigned_name="STRATA-227987",
            status=int(NodeStatus.CALIBRATING),
            metadata_json=json.dumps({
                "mqtt_auto_detected": True,
                "node_ip": "10.60.1.10",
                "strata_node_id": "214282185227987",
                "last_payload_at": "2026-07-23T14:37:16+00:00",
            }),
        )
        duplicate = WifiNode(
            mac_address="STRATA:214282185228770",
            assigned_name="STRATA-228770",
            status=int(NodeStatus.CALIBRATING),
            metadata_json=json.dumps({
                "mqtt_auto_detected": True,
                "node_ip": "10.60.1.10",
                "strata_node_id": "214282185228770",
                "last_payload_at": "2026-07-23T14:37:16+00:00",
            }),
        )
        db_session.add_all([canonical, duplicate])
        db_session.commit()

        data = scan_nodes(db_session)
        assert data["total"] == 1
        row = data["items"][0]
        assert row["node_ip"] == "10.60.1.10"
        assert row["logical_count"] >= 2
        assert not data["ip_conflicts"]


def test_ingest_routes_new_strata_id_to_canonical(app, db_session):
    with app.app_context():
        register_node_from_mqtt(
            "STRATA:214282185227987",
            {"strata_node_id": "214282185227987"},
            client_id="c1",
            client_ip="10.60.1.10",
            payload="[1,1750730515,28,214282185227987,1,828033288983,-94]",
        )
        register_node_from_mqtt(
            "STRATA:214282185228770",
            {"strata_node_id": "214282185228770"},
            client_id="c2",
            client_ip="10.60.1.10",
            payload="[1,1750730516,28,214282185228770,1,828033288983,-93]",
        )

        nodes = db_session.query(WifiNode).all()
        visible = [n for n in nodes if not get_node_metadata(n).get("merged_into")]
        assert len(visible) == 1
        meta = get_node_metadata(visible[0])
        assert meta.get("node_ip") == "10.60.1.10"
        assert "214282185228770" in meta.get("merged_strata_ids", [])


def test_ingest_via_mqtt_service_merges_same_ip(app, db_session):
    with app.app_context():
        ingest = init_mqtt_tag_ingest(app=app)
        ingest.handle_message(
            "c1",
            "strata/v1/bluetooth/1/214282185227987",
            "[1,1750730515,28,214282185227987,1,828033288983,-94]",
            "10.60.1.10",
        )
        ingest.handle_message(
            "c2",
            "strata/v1/bluetooth/1/214282185228770",
            "[1,1750730516,28,214282185228770,1,828033288983,-93]",
            "10.60.1.10",
        )
        data = scan_nodes(db_session)

    assert data["total"] == 1
    assert data["items"][0]["logical_count"] == 2
