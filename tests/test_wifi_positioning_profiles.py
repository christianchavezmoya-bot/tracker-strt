import math


def _rssi_for_distance(distance: float, tx_power: float = -40.0, n: float = 2.5) -> float:
    return tx_power - (10.0 * n * math.log10(distance))


def test_wifi_positioning_tunnel_profile_supports_two_anchor_linear_fix(db_session):
    from backend.models import Setting
    from backend.models.detection import AnchorStatus, DetectionEvent, WifiAnchor
    from backend.services.wifi_positioning import WifiPositioningService

    db_session.add(Setting(key="positioning_application_profile", value="tunnel", value_type="select"))
    a1 = WifiAnchor(mac_address="10:00:00:00:00:01", real_x=0.0, real_y=0.0, real_z=0.0, status=int(AnchorStatus.ACTIVE), tx_power=-40.0)
    a2 = WifiAnchor(mac_address="10:00:00:00:00:02", real_x=10.0, real_y=0.0, real_z=0.0, status=int(AnchorStatus.ACTIVE), tx_power=-40.0)
    db_session.add_all([a1, a2])
    db_session.flush()

    tag_mac = "AA:BB:CC:DD:EE:FF"
    db_session.add_all([
        DetectionEvent(anchor_id=a1.id, mac_address=tag_mac, rssi=_rssi_for_distance(4.0), signal_type=1),
        DetectionEvent(anchor_id=a2.id, mac_address=tag_mac, rssi=_rssi_for_distance(6.0), signal_type=1),
    ])
    db_session.commit()

    fixes = WifiPositioningService(db_session).compute_all_positions()
    assert len(fixes) == 1
    fix = fixes[0]
    assert fix.source == "LINEAR_TUNNEL"
    assert fix.anchors_used == 2
    assert fix.profile_id == "tunnel"
    assert fix.quality_state == "approximate"
    assert 3.0 <= fix.x <= 5.0
    assert abs(fix.y) < 0.5

    DetectionEvent.query.delete(synchronize_session=False)
    WifiAnchor.query.delete(synchronize_session=False)
    Setting.query.filter_by(key="positioning_application_profile").delete(synchronize_session=False)
    db_session.commit()


def test_wifi_positioning_open_space_requires_three_anchors(db_session):
    from backend.models import Setting
    from backend.models.detection import AnchorStatus, DetectionEvent, WifiAnchor
    from backend.services.wifi_positioning import WifiPositioningService

    db_session.add(Setting(key="positioning_application_profile", value="open_space", value_type="select"))
    a1 = WifiAnchor(mac_address="20:00:00:00:00:01", real_x=0.0, real_y=0.0, real_z=0.0, status=int(AnchorStatus.ACTIVE), tx_power=-40.0)
    a2 = WifiAnchor(mac_address="20:00:00:00:00:02", real_x=10.0, real_y=0.0, real_z=0.0, status=int(AnchorStatus.ACTIVE), tx_power=-40.0)
    db_session.add_all([a1, a2])
    db_session.flush()

    tag_mac = "11:22:33:44:55:66"
    db_session.add_all([
        DetectionEvent(anchor_id=a1.id, mac_address=tag_mac, rssi=_rssi_for_distance(4.0), signal_type=1),
        DetectionEvent(anchor_id=a2.id, mac_address=tag_mac, rssi=_rssi_for_distance(6.0), signal_type=1),
    ])
    db_session.commit()

    fixes = WifiPositioningService(db_session).compute_all_positions()
    assert fixes == []

    DetectionEvent.query.delete(synchronize_session=False)
    WifiAnchor.query.delete(synchronize_session=False)
    Setting.query.filter_by(key="positioning_application_profile").delete(synchronize_session=False)
    db_session.commit()
