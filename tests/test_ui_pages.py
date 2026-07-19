"""Server-side smoke: key pages render without 500."""


def test_login_page(client):
    res = client.get("/login")
    assert res.status_code == 200
    assert b"HOLO" in res.data or b"login" in res.data.lower()


def test_trackers_page(client):
    res = client.get("/trackers")
    assert res.status_code == 200


def test_settings_page(client):
    res = client.get("/settings")
    assert res.status_code == 200


def test_integrations_page(client):
    res = client.get("/integrations")
    assert res.status_code == 200


def test_reports_page(client):
    res = client.get("/reports")
    assert res.status_code == 200


def test_muster_page(client):
    res = client.get("/muster")
    assert res.status_code == 200
