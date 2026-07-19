"""
Smoke tests for above-market API surfaces (zones rules, sections, UWB deprecation).
"""
import json


def test_health_or_root(client):
    # App may expose health under different paths; page root should render
    res = client.get("/")
    assert res.status_code in (200, 302, 401)


def test_zone_create_with_rules(client, admin_headers):
    res = client.post(
        "/api/zones",
        headers=admin_headers,
        json={
            "name": "Smoke Restricted",
            "zone_type": "RESTRICTED",
            "pos_x": 10.0,
            "pos_y": 12.0,
            "pos_z": 0.0,
            "radius": 4.0,
            "rules": {
                "on_enter": True,
                "on_exit": False,
                "dwell_max_seconds": 90,
            },
        },
    )
    assert res.status_code in (200, 201), res.get_data(as_text=True)
    data = res.get_json()
    zone = data.get("zone") or data
    assert zone.get("name") == "Smoke Restricted"
    rules = zone.get("rules") or {}
    assert rules.get("dwell_max_seconds") == 90


def test_section_polygon_create(client, admin_headers):
    res = client.post(
        "/api/zones/sections",
        headers=admin_headers,
        json={
            "name": "Smoke Section",
            "polygon": [[0, 0], [10, 0], [10, 8], [0, 8]],
            "is_restricted": True,
            "color_hex": "#00e5ff",
        },
    )
    assert res.status_code in (200, 201), res.get_data(as_text=True)
    data = res.get_json()
    section = data.get("section") or data
    assert section.get("name") == "Smoke Section"
    assert len(section.get("polygon") or []) >= 3


def test_uwb_routes_marked_deprecated(client, auth_headers):
    res = client.get("/api/uwb/anchors", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json() or {}
    assert data.get("deprecated") is True


def test_backup_list(client, admin_headers):
    res = client.get("/api/backup", headers=admin_headers)
    assert res.status_code == 200
    assert "items" in (res.get_json() or {})


def test_backup_schedule_flags(client, admin_headers):
    res = client.get("/api/backup/schedule", headers=admin_headers)
    assert res.status_code == 200
    data = res.get_json() or {}
    assert "encryption_enabled" in data
    assert "remote_configured" in data
    assert "retention" in data


def test_nodes_include_metadata_field(client, auth_headers, app):
    from backend.extensions import db
    from backend.models import WifiNode
    with app.app_context():
        n = WifiNode(mac_address="AA:BB:CC:DD:EE:99", assigned_name="Cov",
                     pos_x=1.0, pos_y=2.0, metadata_json='{"coverage_radius_m":15}')
        db.session.add(n)
        db.session.commit()
    res = client.get("/api/nodes", headers=auth_headers)
    assert res.status_code == 200
    items = (res.get_json() or {}).get("items") or []
    hit = next((i for i in items if i.get("mac_address") == "AA:BB:CC:DD:EE:99"), None)
    assert hit is not None
    assert hit.get("metadata", {}).get("coverage_radius_m") == 15
