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
    assert "BXP_NORDIC" in ids
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
    assert t2 is None


def test_classify_detection_bxp_nordic_name():
    from backend.services.tracker_discovery import classify_detection

    assert classify_detection("E8:A7:3F:01:53:5C", adv_name="BXP-Nordic") == "BXP_NORDIC"


def test_run_discovery_prunes_unacknowledged_non_matching_but_keeps_active(db_session, monkeypatch):
    from backend.models import Tracker, TrackerAckStatus, AssetState
    from backend.models.settings import Setting
    from backend.services.tracker_discovery import run_discovery

    stale_unack = Tracker(
        hardware_id="AA:BB:CC:DD:EE:01",
        scan_type="EDDYSTONE",
        ack_status=int(TrackerAckStatus.UNACKNOWLEDGED),
        asset_state=int(AssetState.OFFLINE),
        last_report_time=1,
    )
    active_keep = Tracker(
        hardware_id="AA:BB:CC:DD:EE:02",
        scan_type="EDDYSTONE",
        ack_status=int(TrackerAckStatus.ACTIVE),
        asset_state=int(AssetState.ACTIVE),
        last_report_time=1,
    )
    db_session.add_all([
        stale_unack,
        active_keep,
        Setting(key="tracker_scan_types", value='["BXP_NORDIC"]'),
        Setting(key="tracker_scan_interval_sec", value='60'),
    ])
    db_session.commit()

    monkeypatch.setattr('backend.services.tracker_discovery._aggregate_from_detection_events', lambda since: {})
    monkeypatch.setattr('backend.services.tracker_discovery._try_bleak_scan', lambda duration=0: {})

    result = run_discovery()
    assert result['removed'] >= 1

    from backend.models import Tracker as TrackerModel
    assert TrackerModel.query.filter_by(hardware_id="AA:BB:CC:DD:EE:01").first() is None
    kept = TrackerModel.query.filter_by(hardware_id="AA:BB:CC:DD:EE:02").first()
    assert kept is not None
    assert kept.ack_status == int(TrackerAckStatus.ACTIVE)
