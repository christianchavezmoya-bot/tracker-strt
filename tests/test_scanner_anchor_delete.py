"""Scanner anchor DELETE API."""
from backend.models.detection import DetectionEvent, WifiAnchor, SignalType


def test_delete_scanner_anchor(client, admin_headers, db_session):
    anchor = WifiAnchor(mac_address="DE:AD:BE:EF:00:01", name="Temp")
    db_session.add(anchor)
    db_session.flush()
    db_session.add(
        DetectionEvent(
            anchor_id=anchor.id,
            mac_address="11:22:33:44:55:66",
            rssi=-70,
            signal_type=int(SignalType.BLE),
        )
    )
    db_session.commit()
    anchor_id = anchor.id

    resp = client.delete(f"/api/scanner/anchors/{anchor_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert db_session.query(WifiAnchor).get(anchor_id) is None
    assert db_session.query(DetectionEvent).filter_by(anchor_id=anchor_id).count() == 0
