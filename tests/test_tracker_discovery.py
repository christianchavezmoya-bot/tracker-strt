"""Tests for tracker discovery scan config and acknowledge."""
import json


def test_scan_config_get(client, auth_headers):
    res = client.get("/api/trackers/scan/config", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert "scan_types" in data
    assert data.get("interval_sec") in (30, 60, 120)


def test_scan_types_catalog(client, auth_headers):
    res = client.get("/api/trackers/scan/types", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    ids = {t["id"] for t in data["scan_types"]}
    assert "MOKO_H7" in ids
    assert "EDDYSTONE" in ids


def test_scan_run_operator(client, auth_headers):
    res = client.post("/api/trackers/scan/run", headers=auth_headers, json={})
    assert res.status_code == 200
    data = res.get_json()
    assert "discovered" in data


def test_org_positions_list(client, auth_headers):
    res = client.get("/api/settings/org/positions", headers=auth_headers)
    assert res.status_code == 200
    items = res.get_json().get("items", [])
    assert len(items) >= 5
    names = {p["name"] for p in items}
    assert "Manager" in names
    assert "Operator" in names


def test_acknowledge_tracker(client, auth_headers, db_session):
    from backend.models import Tracker, TrackerAckStatus

    t = Tracker(hardware_id="AA:BB:CC:DD:EE:99", device_model="MOKO H7", scan_type="MOKO_H7",
                ack_status=int(TrackerAckStatus.UNACKNOWLEDGED))
    db_session.add(t)
    db_session.commit()

    res = client.post(
        f"/api/trackers/{t.id}/acknowledge",
        headers=auth_headers,
        json={"nickname": "Alpha", "first_name": "John", "surname": "Smith", "features": {"proximity": True}},
    )
    assert res.status_code == 200
    data = res.get_json()["tracker"]
    assert data["ack_status"] == "ACTIVE"
    assert data["nickname"] == "Alpha"


def test_tracker_last_seen_at_in_list(client, auth_headers, db_session):
    from backend.models import Tracker, TrackerAckStatus

    t = Tracker(
        hardware_id="AA:BB:CC:DD:EE:77",
        ack_status=int(TrackerAckStatus.ACTIVE),
        last_report_time=1700000000,
    )
    db_session.add(t)
    db_session.commit()

    res = client.get("/api/trackers", headers=auth_headers)
    assert res.status_code == 200
    items = res.get_json().get("items", [])
    row = next(x for x in items if x["id"] == t.id)
    assert row["last_seen_at"] is not None
    assert "2023" in row["last_seen_at"]


def test_presence_timeline(client, auth_headers, db_session):
    from datetime import datetime, timezone

    from backend.models import Tracker, TrackerAckStatus
    from backend.models.positioning import TrackerPresenceLog

    t = Tracker(
        hardware_id="AA:BB:CC:DD:EE:66",
        nickname="Chart Tag",
        device_model="MOKO H7",
        ack_status=int(TrackerAckStatus.ACTIVE),
    )
    db_session.add(t)
    db_session.flush()
    db_session.add(TrackerPresenceLog(
        tracker_id=t.id,
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        online=True,
        rssi=-65.0,
    ))
    db_session.commit()

    res = client.get("/api/trackers/presence/timeline?minutes=60", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["window_minutes"] == 60
    assert len(data["trackers"]) == 1
    assert data["trackers"][0]["id"] == t.id
    assert len(data["trackers"][0]["samples"]) == 1
    assert data["trackers"][0]["samples"][0]["online"] is True


def test_purge_tracker(client, auth_headers, db_session):
    from backend.models import Tracker, TrackerAckStatus

    t = Tracker(
        hardware_id="AA:BB:CC:DD:EE:88", nickname="Test", first_name="A",
        ack_status=int(TrackerAckStatus.ACTIVE),
    )
    db_session.add(t)
    db_session.commit()

    res = client.post("/api/trackers/bulk/purge", headers=auth_headers, json={"ids": [t.id]})
    assert res.status_code == 200
    assert res.get_json()["purged"] == 1

    t2 = Tracker.query.get(t.id)
    assert t2.ack_status == int(TrackerAckStatus.UNACKNOWLEDGED)
    assert t2.nickname is None
