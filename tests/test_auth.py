"""
HOLO-RTLS — Auth Tests
"""
import pytest


class TestAuthRegister:
    def test_register_success(self, client, app):
        resp = client.post("/api/auth/register", json={
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "StrongPass123!",
            "display_name": "New User",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["user"]["email"] == "newuser@example.com"
        assert data["user"]["username"] == "newuser"
        assert "password" not in data["user"]

    def test_register_duplicate_email(self, client, sample_user):
        resp = client.post("/api/auth/register", json={
            "email": "testuser@example.com",
            "username": "different",
            "password": "StrongPass123!",
        })
        assert resp.status_code == 400
        assert "already" in resp.get_json()["error"].lower()

    def test_register_short_password(self, client):
        resp = client.post("/api/auth/register", json={
            "email": "short@example.com",
            "username": "short",
            "password": "abc",
        })
        assert resp.status_code == 400
        assert "password" in resp.get_json()["error"].lower()


class TestAuthLogin:
    def test_login_success(self, client, sample_user):
        resp = client.post("/api/auth/login", json={
            "email_or_username": "testuser@example.com",
            "password": "TestPass123!",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == "testuser@example.com"

    def test_login_by_username(self, client, sample_user):
        resp = client.post("/api/auth/login", json={
            "email_or_username": "testuser",
            "password": "TestPass123!",
        })
        assert resp.status_code == 200
        assert "access_token" in resp.get_json()

    def test_login_wrong_password(self, client, sample_user):
        resp = client.post("/api/auth/login", json={
            "email_or_username": "testuser@example.com",
            "password": "WrongPassword!",
        })
        assert resp.status_code == 401
        assert "invalid" in resp.get_json()["error"].lower()

    def test_login_nonexistent_user(self, client):
        resp = client.post("/api/auth/login", json={
            "email_or_username": "ghost@nowhere.com",
            "password": "anypass",
        })
        assert resp.status_code == 401

    def test_login_increments_failed_attempts(self, client, sample_user):
        for i in range(3):
            resp = client.post("/api/auth/login", json={
                "email_or_username": "testuser@example.com",
                "password": "wrong",
            })
        data = resp.get_json()
        assert data["error"] == "Invalid credentials"

    def test_login_lockout_after_max_attempts(self, client, sample_user):
        # With LOGIN_MAX_ATTEMPTS = 3, the 3rd wrong attempt locks the account
        for _ in range(3):
            client.post("/api/auth/login", json={
                "email_or_username": "testuser@example.com",
                "password": "wrong",
            })
        resp = client.post("/api/auth/login", json={
            "email_or_username": "testuser@example.com",
            "password": "TestPass123!",
        })
        assert resp.status_code == 401
        assert "locked" in resp.get_json()["error"].lower()


class TestAuthMe:
    def test_me_returns_user(self, client, auth_headers, sample_user):
        resp = client.get("/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user"]["email"] == "testuser@example.com"
        assert data["user"]["role"] == "OPERATOR"

    def test_me_requires_auth(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401


class TestAuthPermissions:
    def test_permissions_endpoint(self, client, auth_headers, sample_user):
        resp = client.get("/api/auth/permissions", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "OPERATOR" == data["role"]
        assert "view_map" in data["permissions"]
        assert "manage_user" not in data["permissions"]   # Operator can't manage users

    def test_admin_permissions(self, client, admin_headers, admin_user):
        resp = client.get("/api/auth/permissions", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "ADMIN" == data["role"]
        assert "manage_user" in data["permissions"]


class TestAuth2FA:
    def test_2fa_setup_returns_qr_code(self, client, auth_headers, sample_user):
        resp = client.post("/api/auth/2fa/setup", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["qr_code"].startswith("data:image/png;base64,")
        assert "secret" in data["message"] or "totp_code" in data["message"].lower()

    def test_2fa_confirm_invalid_code(self, client, auth_headers, sample_user):
        resp = client.post("/api/auth/2fa/confirm", json={"totp_code": "000000"}, headers=auth_headers)
        assert resp.status_code == 400


class TestAuthLogout:
    def test_logout_success(self, client, auth_headers, sample_user):
        resp = client.post("/api/auth/logout", headers=auth_headers)
        assert resp.status_code == 200
        assert "logged out" in resp.get_json()["message"].lower()


class TestAuthPasswordReset:
    def test_reset_request_hides_existence(self, client):
        """Email enumeration should not be possible."""
        resp1 = client.post("/api/auth/password/reset-request", json={"email": "real@example.com"})
        resp2 = client.post("/api/auth/password/reset-request", json={"email": "fake@example.com"})
        # Both should return 200 with the same message
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.get_json() == resp2.get_json()
