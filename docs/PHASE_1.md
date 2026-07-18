# Phase 1 — Authentication & Access Control

**Status:** ✅ COMPLETE

---

## What was built

### Backend

| Component | File | Description |
|---|---|---|
| User model | `backend/models/user.py` | Full user entity with Argon2 hashing, lockout, 2FA |
| RBAC service | `backend/services/rbac_service.py` | Permission matrix for Admin/Operator/Viewer |
| Auth service | `backend/services/auth_service.py` | Login, register, 2FA, password reset, logout |
| Auth API | `backend/api/__init__.py` | All `/api/auth/*` routes |
| Auth decorators | `backend/utils/decorators.py` | `@require_permission`, `@admin_only`, `@audit_log` |

### Frontend

| Component | File | Description |
|---|---|---|
| Login page | `frontend/templates/auth/login.html` | Holographic login with 2FA, password reset |
| Login CSS | `frontend/static/css/auth.css` | Holographic dark theme |
| Auth JS | `frontend/static/js/auth.js` | Login, 2FA setup/confirm, logout |

---

## Auth API Endpoints

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register` | Optional (admin-only in prod) | Create account |
| POST | `/api/auth/login` | None | Login — returns JWT |
| POST | `/api/auth/logout` | JWT | Audit logout |
| POST | `/api/auth/refresh` | Refresh token | Get new access token |
| POST | `/api/auth/2fa/setup` | JWT | Generate TOTP secret + QR code |
| POST | `/api/auth/2fa/confirm` | JWT | Confirm 2FA setup |
| POST | `/api/auth/2fa/disable` | JWT | Disable 2FA (requires password + code) |
| POST | `/api/auth/password/reset-request` | None | Request reset email |
| POST | `/api/auth/password/reset` | None | Reset with signed token |
| GET | `/api/auth/me` | JWT | Current user profile |
| GET | `/api/auth/permissions` | JWT | Current user's role + permissions |

---

## Role Permission Matrix

| Permission | Admin | Operator | Viewer |
|---|---|---|---|
| view_map | ✅ | ✅ | ✅ |
| manage_tracker | ✅ | ✅ | ❌ |
| create_zone | ✅ | ❌ | ❌ |
| acknowledge_alert | ✅ | ✅ | ❌ |
| manage_user | ✅ | ❌ | ❌ |
| view_audit | ✅ | ❌ | ❌ |
| edit_settings | ✅ | ❌ | ❌ |
| trigger_backup | ✅ | ❌ | ❌ |
| restore_backup | ✅ | ❌ | ❌ |
| manage_api_key | ✅ | ❌ | ❌ |

*(Full matrix in `backend/services/rbac_service.py`)*

---

## 2FA Flow

```
1. User calls POST /api/auth/2fa/setup
   ← Returns { qr_code: "data:image/png;base64,..." }

2. User scans QR with Google Authenticator / Authy

3. User calls POST /api/auth/2fa/confirm with code "123456"
   ← Enables 2FA on account

4. On next login, server returns { requires_2fa: true }
   Client prompts for TOTP code and re-posts /api/auth/login with totp_code
```

---

## Password Reset Flow (current stub)

```
1. User POSTs email to /api/auth/password/reset-request
   ← Server logs intent (email not yet sent — mail service not wired in Phase 1)

2. Server would send email with signed JWT reset token (not implemented in Phase 1)

3. User POSTs token + new_password to /api/auth/password/reset
   ← Validates signed JWT, updates password
```

**To implement email sending:** set `MAIL_ENABLED=1` and SMTP credentials in `.env`, then implement `send_password_reset_email()` in `auth_service.py` using `flask_mail.Mail`.

---

## Tests added

Run with:
```bash
pytest tests/test_auth.py -v
pytest tests/test_trackers.py -v   # includes RBAC permission tests
```

Tests cover:
- ✅ Register success / duplicate / short password
- ✅ Login by email and username
- ✅ Wrong password increments failed_attempts
- ✅ Lockout after 3 failed attempts
- ✅ JWT required for protected endpoints
- ✅ Viewer cannot create trackers (403)
- ✅ 2FA setup returns QR code
- ✅ Password reset hides email enumeration
- ✅ Full tracker CRUD

---

## What's missing (not in Phase 1 scope)

- **Email sending** — mail service wired but not used in Phase 1 (Phase 6)
- **Password reset email** — stub exists, needs `flask_mail` integration
- **Session management UI** — view/revoke active sessions (Phase 8)
- **MQTT** — not wired yet (Phase 3)
- **Positioning engine** — not wired yet (Phase 3)
- **SSE stream** — SSE endpoint in `dashboard.js` needs backend route (Phase 3)

---

## Next: Phase 2 — Core Tracking Data

- Tracker API (done as stub ✅)
- Node API (done as stub ✅)
- Zone + Section API (done as stub ✅)
- Search API (done ✅)
- Tag management page
- Zone editor page
- Position cache + SSE endpoint

---

## Notes for next agent

1. **Run `pytest tests/test_auth.py tests/test_trackers.py -v` first** — verify Phase 1 passes before touching anything.
2. The `@require_permission` decorator requires JWT auth on the route — it handles the 401/403 cases automatically.
3. The audit log is auto-populated by the `@audit_log` decorator on all API routes — no manual `AuditLog.log()` calls needed in route handlers.
4. All models use `datetime.now(timezone.utc)` for consistent UTC timestamps.
5. The `user.py` model uses a singleton `PasswordHasher` — safe to share across requests.
