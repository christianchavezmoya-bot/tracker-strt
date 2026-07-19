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


def test_positioning_sources(client, auth_headers):
    res = client.get("/api/positioning/sources", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json() or {}
    assert data.get("location_core") is True
    assert "sources" in data
    assert any(s.get("id") == "uwb_demo" and s.get("deprecated") for s in data["sources"])


def test_uwb_deprecation_header(client, auth_headers):
    res = client.get("/api/uwb/anchors", headers=auth_headers)
    assert res.status_code == 200
    assert res.headers.get("Deprecation") == "true"
    assert "positioning" in (res.headers.get("Link") or "")


def test_tracking_redirects_to_setup(client):
    res = client.get("/tracking", follow_redirects=False)
    assert res.status_code in (301, 302)
    assert "/?mode=setup" in (res.headers.get("Location") or "")


def test_proximity_meters_default_on_fresh(client, admin_headers):
    res = client.get("/api/settings/proximity_meters", headers=admin_headers)
    assert res.status_code == 200, res.get_data(as_text=True)
    setting = (res.get_json() or {}).get("setting") or {}
    assert setting.get("value") in ("2.0", 2.0, "2")


def test_tracking_legacy_redirects(client):
    res = client.get("/tracking?legacy=1", follow_redirects=False)
    assert res.status_code in (301, 302)
    assert "/?mode=setup" in (res.headers.get("Location") or "")


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


def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert (res.get_json() or {}).get("ok") is True
    res2 = client.get("/api/health")
    assert res2.status_code == 200


def test_settings_status_has_bridge_flag(client, auth_headers):
    res = client.get("/api/settings/status", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json() or {}
    assert "bridge_online" in data
    assert "ingestion_running" in data
    assert data.get("ok") is True


def test_pdf_bytes_are_valid_pdf():
    from backend.services.pdf_report import rows_to_pdf
    pdf = rows_to_pdf(
        "Smoke Report",
        [{"id": 1, "name": "Tag A", "battery": 88}],
        subtitle="unit test",
        site_name="Test Site",
    )
    assert pdf.startswith(b"%PDF")
    assert b"%%EOF" in pdf
    assert b"HOLO-RTLS" in pdf


def test_pdf_summary_includes_bar_chart():
    from backend.services.pdf_report import rows_to_pdf, _summary_bar_chart_lines
    rows = [
        {"metric": "trackers", "value": 120},
        {"metric": "alerts_24h", "value": 8},
        {"metric": "history_samples_24h", "value": 4500},
        {"metric": "generated_at", "value": "2026-07-19T00:00:00Z"},
    ]
    chart = _summary_bar_chart_lines(rows)
    assert len(chart) >= 3
    assert any("trackers" in line for line in chart)
    pdf = rows_to_pdf("Summary", rows, site_name="Test")
    assert b"Summary chart" in pdf
    assert b"trackers" in pdf
    assert b"/DCTDecode" in pdf


def test_create_report_schedule(client, auth_headers):
    res = client.post(
        "/api/reports/schedules",
        headers=auth_headers,
        json={
            "name": "Smoke Daily",
            "recipients": "ops@example.com",
            "report_type": "summary",
            "format": "pdf",
            "cron": "0 7 * * *",
        },
    )
    assert res.status_code in (200, 201), res.get_data(as_text=True)
    data = res.get_json() or {}
    sch = data.get("schedule") or data
    assert sch.get("name") == "Smoke Daily"
    assert sch.get("format") == "pdf"


def test_integrations_status(client, admin_headers):
    res = client.get("/api/settings/integrations/status", headers=admin_headers)
    assert res.status_code == 200
    data = res.get_json() or {}
    assert "mail_enabled" in data
    assert "mail_can_send" in data
    assert "twilio_configured" in data


def test_integrations_test_email(client, admin_headers):
    res = client.post("/api/settings/integrations/test-email", headers=admin_headers, json={})
    assert res.status_code == 200
    data = res.get_json() or {}
    assert data.get("to") == "admin@example.com"
    assert "message" in data


def test_proximity_alert_engine(app, db_session):
    from backend.models import Tracker, Setting
    from backend.services.alert_service import AlertService

    with app.app_context():
        t1 = Tracker(hardware_id="HW-PROX-1", assigned_name="Alpha", pos_x=0.0, pos_y=0.0, pos_z=0.0)
        t2 = Tracker(hardware_id="HW-PROX-2", assigned_name="Beta", pos_x=1.0, pos_y=0.0, pos_z=0.0)
        db_session.add_all([t1, t2])
        db_session.commit()
        db_session.add(Setting(key="proximity_meters", value="2.0"))
        db_session.commit()

        svc = AlertService.__new__(AlertService)
        svc._app = app
        alerts = svc._check_proximity(t1.id, 0.0, 0.0, 0.0)
        assert len(alerts) == 1
        assert alerts[0].alert_type == 9
        assert "Beta" in alerts[0].message

        far = svc._check_proximity(t1.id, 100.0, 100.0, 0.0)
        assert len(far) == 0


def test_audit_export_csv(client, admin_headers, app):
    from backend.models import AuditLog
    from backend.extensions import db

    with app.app_context():
        AuditLog.log(action="smoke.test", user_id=1, entity_type="Test", entity_id=1, details='{}')
        db.session.commit()

    res = client.get("/api/audit/export", headers=admin_headers)
    assert res.status_code == 200
    assert "text/csv" in (res.headers.get("Content-Type") or "")
    body = res.get_data(as_text=True)
    assert "timestamp" in body
    assert "smoke.test" in body


def test_push_subscribe_and_vapid(client, auth_headers, app, monkeypatch):
    monkeypatch.setattr("backend.config.WEB_PUSH_ENABLED", True)
    monkeypatch.setattr("backend.config.VAPID_PUBLIC_KEY", "BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U")
    monkeypatch.setattr("backend.config.VAPID_PRIVATE_KEY", "test-private-key")

    res = client.get("/api/push/vapid-public-key", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json() or {}
    assert data.get("configured") is True
    assert data.get("public_key")

    sub = client.post(
        "/api/push/subscribe",
        headers=auth_headers,
        json={
            "endpoint": "https://push.example.com/sub/abc123",
            "keys": {"p256dh": "key1", "auth": "auth1"},
        },
    )
    assert sub.status_code == 201

    lst = client.get("/api/push/subscriptions", headers=auth_headers)
    assert lst.status_code == 200
    assert len((lst.get_json() or {}).get("items") or []) >= 1

    unsub = client.delete(
        "/api/push/subscribe",
        headers=auth_headers,
        json={"endpoint": "https://push.example.com/sub/abc123"},
    )
    assert unsub.status_code == 200
