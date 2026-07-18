# Phase 0 — Project Setup

**Goal:** Clean scaffold, DB initialized, config wired, ready to run.

---

## What was built

```
HOLO-RTLS/
├── backend/
│   ├── app.py              ← Flask factory (create_app)
│   ├── config.py           ← All settings from env vars
│   ├── extensions.py       ← db, migrate, jwt, mail (singleton instances)
│   ├── models/
│   │   ├── __init__.py     ← Re-exports all models
│   │   ├── user.py         ← User, UserRole, Argon2 passwords, lockout
│   │   ├── tracker.py      ← Tracker, WifiNode, MapSection, Zone
│   │   ├── alert.py        ← Alert, Notification
│   │   ├── audit.py        ← AuditLog (immutable)
│   │   ├── settings.py     ← Setting (KV store), BusinessLogo
│   │   └── backup.py       ← BackupJob, TrackingHistory, CheckInLog, ApiKey
│   ├── api/                ← All REST API blueprints
│   │   ├── __init__.py     ← Auth routes
│   │   ├── trackers/
│   │   ├── nodes/
│   │   ├── zones/
│   │   ├── alerts/
│   │   ├── search/
│   │   ├── settings/
│   │   ├── users/
│   │   ├── audit/
│   │   ├── notifications/
│   │   ├── reports/
│   │   ├── backup/
│   │   └── uwb/            ← Integrates reference/uwb_positioning.py
│   ├── services/
│   │   ├── auth_service.py ← Login, 2FA, password reset (all business logic)
│   │   └── rbac_service.py ← Role permission matrix + checks
│   └── utils/
│       └── decorators.py   ← @require_permission, @admin_only, @audit_log
│
├── frontend/
│   ├── templates/
│   │   ├── auth/login.html ← Holographic login page
│   │   └── dashboard/index.html ← Main command center (2D/3D map UI)
│   ├── static/
│   │   ├── css/
│   │   │   ├── main.css    ← Holographic theme (20KB)
│   │   │   ├── auth.css    ← Login page styles
│   │   │   └── dashboard.css ← Map-specific styles
│   │   └── js/
│   │       ├── api.js      ← JWT-aware fetch client
│   │       ├── auth.js     ← Login, 2FA, logout logic
│   │       ├── dashboard.js ← Main UI: tag list, alerts, SSE, search
│   │       └── visualization/
│   │           ├── map2d.js ← Leaflet 2D floor plan
│   │           └── map3d.js ← Three.js 3D tunnel view
│
├── tests/
│   ├── conftest.py         ← pytest fixtures: app, client, db, auth_headers
│   ├── test_auth.py        ← 14 auth tests
│   └── test_trackers.py    ← 9 tracker CRUD tests
│
├── run.py                  ← Entry point (creates default admin)
├── .env.example            ← All env vars documented
├── .gitignore
├── requirements.txt
└── BUILD_PLAN.md          ← Master plan (this file)
```

---

## To start the project

```bash
# 1. Create .env from example
cp .env.example .env
# Edit .env and set SECRET_KEY + JWT_SECRET_KEY

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run — creates SQLite DB + default admin automatically
python run.py
```

Default admin: `admin@holo-rtls.local` / `ChangeMe123!`

---

## Key design decisions

- **SQLAlchemy 2 + Flask-SQLAlchemy** — modern ORM, type-safe
- **Argon2** for passwords (via argon2-cffi) — winner of Password Hashing Competition
- **JWT via Flask-JWT-Extended** — access tokens (4h) + refresh tokens (7d)
- **PyOTP + qrcode** — TOTP 2FA (Google Authenticator compatible)
- **Argon2 login lockout** — per-account, 3 fails → 5min lock
- **Reference code imported from `../reference/`** — sys.path manipulation in uwb/__init__.py

---

## Next: Phase 1

Phase 1 builds on this scaffold to add:
- Complete Auth API (done in Phase 1 scope)
- All remaining API stubs (Phase 2-4 scope — already done as stubs)
- Positioning engine (Phase 3)
- Alert engine (Phase 4)
- Full map visualization (Phase 5)

The scaffold is complete. Next agent should run `pytest` to verify everything passes.
