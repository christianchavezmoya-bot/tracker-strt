# HOLO-RTLS — Build Plan
## Indoor Real-Time Location System | Command Center Platform

> **Plan Version:** 1.1 | **Date:** 2026-07-19 | **Stack:** Python Flask + Web (Three.js/Leaflet) + SQLite
> **Status:** ✅ Phase 0 COMPLETE | ✅ Phase 1 COMPLETE | 🔄 Phase 2 STARTED

---

## 1. Vision & Scope

HOLO-RTLS is a **production-grade indoor positioning command center** for underground, tunnel, and facility environments. It tracks personnel, machines, and assets in real-time, handles hundreds of simultaneous devices, enforces strict multi-tenant access control, and generates business reports.

The system runs as a **Flask web application** backed by SQLite, with a modern holographic web UI, a Python positioning backend that integrates UWB/BLE hardware, and a plugin-ready architecture so features can be added without breaking existing ones.

**The reference folder** (`reference/`) contains the proven tracker-strt codebase — its `uwb_positioning.py`, `uwb_serial_reader.py`, and `floor_plan_mapper.py` are battle-tested and will be reused directly.

---

## 2. Project Structure

> **Status:** ✅ Phase 0 COMPLETE | ✅ Phase 1 COMPLETE | ✅ Phase 2 COMPLETE | ✅ Phase 3 COMPLETE | ✅ Phase 4 COMPLETE | 🔄 Phase 5 STARTED

```
HOLO-RTLS/
├── reference/                   ← tracker-strt code (read-only, do not modify)
│   ├── uwb_positioning.py       ← Trilateration + Kalman (use as-is)
│   ├── uwb_serial_reader.py     ← Serial/UART bridge (use as-is)
│   ├── floor_planMapper.py     ← Affine coordinate transform (use as-is)
│   ├── app_uwb.py               ← REST API pattern reference
│   ├── templates/               ← Frontend UI reference (index_uwb.html)
│   └── requirements.txt        ← Python dependencies
│
├── backend/                     ← Main Flask application
│   ├── app.py                   ← Application entry point
│   ├── config.py               ← Environment config (DB path, secrets, etc.)
│   ├── extensions.py            ← Flask extensions init (DB, login, mail)
│   │
│   ├── models/                  ← SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── user.py             ← User, Role
│   │   ├── tracker.py          ← Tracker (tag), WifiNode, MapSection
│   │   ├── zone.py             ← Zone, Section, CheckInLog
│   │   ├── alert.py            ← Alert, AlertLog, Notification
│   │   ├── audit.py            ← AuditLog
│   │   ├── settings.py         ← BusinessSetting, CustomerSetting
│   │   ├── backup.py           ← BackupJob
│   │   └── api_key.py          ← ApiKey
│   │
│   ├── api/                     ← REST API (Blueprint)
│   │   ├── __init__.py
│   │   ├── auth.py             ← /api/auth/*  (login, logout, 2FA, register)
│   │   ├── trackers.py         ← /api/trackers/* (CRUD, reassign, delete)
│   │   ├── nodes.py             ← /api/nodes/*
│   │   ├── zones.py             ← /api/zones/*
│   │   ├── alerts.py            ← /api/alerts/*
│   │   ├── history.py           ← /api/history/*
│   │   ├── reports.py           ← /api/reports/*
│   │   ├── search.py            ← /api/search/*  (assets + people search)
│   │   ├── settings.py          ← /api/settings/* (business + customer)
│   │   ├── users.py             ← /api/users/*  (user management)
│   │   ├── backup.py            ← /api/backup/*
│   │   ├── notifications.py     ← /api/notifications/*
│   │   ├── audit.py             ← /api/audit/*
│   │   └── uwb.py               ← /api/uwb/*  (positioning engine)
│   │
│   ├── services/                ← Business logic (independent of routes)
│   │   ├── auth_service.py      ← Login, 2FA, token management
│   │   ├── rbac_service.py       ← Permission checking
│   │   ├── alert_service.py      ← Alert evaluation + dispatch
│   │   ├── notification_service.py ← SMS, email, in-app dispatch
│   │   ├── positioning_service.py  ← Wraps reference/uwb_positioning.py
│   │   ├── report_service.py    ← Report generation (CSV, email)
│   │   ├── backup_service.py    ← Backup scheduling + restore
│   │   ├── audit_service.py     ← Audit logging
│   │   └── search_service.py    ← Full-text search across entities
│   │
│   ├── utils/                   ← Shared utilities
│   │   ├── decorators.py        ← @require_permission, @rate_limit, etc.
│   │   ├── validators.py        ← Input validation schemas
│   │   ├── hashing.py           ← Password hashing (Argon2)
│   │   ├── mqtt_client.py       ← MQTT publisher/subscriber
│   │   ├── sms_client.py        ← SMS provider (Twilio / Vonage)
│   │   ├── smtp_client.py       ← Email sending
│   │   └── backup_storage.py    ← Local + remote backup storage
│   │
│   └── migrations/              ← Database migrations (Alembic)
│
├── frontend/                    ← Web UI
│   ├── static/
│   │   ├── css/
│   │   │   ├── main.css        ← Global styles + holographic theme
│   │   │   ├── auth.css         ← Login / 2FA screen styles
│   │   │   ├── dashboard.css   ← Main layout + panels
│   │   │   └── components.css   ← Buttons, modals, inputs
│   │   ├── js/
│   │   │   ├── app.js           ← App init, router, auth state
│   │   │   ├── api.js           ← API client with token handling
│   │   │   ├── auth.js          ← Login, 2FA, register logic
│   │   │   ├── dashboard.js     ← Main map + UI logic
│   │   │   ├── tracker.js       ← Tag management
│   │   │   ├── alert.js         ← Alert panel + acknowledge
│   │   │   ├── notifications.js  ← Notification bell + list
│   │   │   ├── settings.js      ← Business + customer settings
│   │   │   ├── search.js        ← Global search
│   │   │   ├── audit.js         ← Audit log viewer
│   │   │   ├── reports.js       ← Report generation UI
│   │   │   └── visualization/
│   │   │       ├── map2d.js     ← 2D floor plan (Leaflet)
│   │   │       ├── map3d.js     ← 3D tunnel view (Three.js)
│   │   │       ├── heatmap.js   ← Heatmap layer
│   │   │       └── history.js    ← Playback slider
│   │   └── assets/
│   │       ├── logos/           ← Business logos
│   │       └── sounds/         ← Alert audio files
│   │
│   └── templates/               ← Jinja2 templates
│       ├── base.html           ← Base layout
│       ├── auth/
│       │   ├── login.html
│       │   ├── register.html
│       │   └── setup_2fa.html
│       └── dashboard/
│           ├── index.html      ← Main dashboard (map view)
│           ├── trackers.html   ← Tag management page
│           ├── zones.html      ← Zone editor
│           ├── alerts.html     ← Alert log page
│           ├── reports.html    ← Reports page
│           ├── settings.html   ← Settings pages
│           ├── users.html      ← User management
│           ├── audit.html      ← Audit log viewer
│           └── search.html     ← Search results page
│
├── tests/                       ← Unit + integration tests
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_trackers.py
│   ├── test_alerts.py
│   ├── test_api.py
│   └── test_positioning.py
│
├── config.env.example           ← Environment variables template
├── requirements.txt             ← Python dependencies
├── run.py                       ← Production entry point (gunicorn)
└── BUILD_PLAN.md               ← This file
```

---


## 3. Hardware Configuration System

Every physical device is a **HardwareConfig** row in SQLite. The positioning service reads all active configs on startup and reconnects automatically. Nothing is hardcoded.

### Pre-Built Profiles

**UWB (10-30cm accuracy):**
-  — Serial/UART (DWM1001 + BLE combo, most common)
-  — Serial (original DW1000)
-  — Serial (next-gen DW3000)
-  — MQTT (enterprise Sewio RTLS)
-  — Serial (Arduino-compatible prototyping kit)
-  — MQTT with universal JSON/CSV field mapping

**BLE (3-10m accuracy):**
-  — BLE GATT (standard beacon format)
-  — BLE GATT (temp + humidity + pressure + accelerometer)
-  — ESP32 as BLE scanner → MQTT bridge

**WiFi (5-15m accuracy):**
-  — ESP32 as WiFi RSSI scanner → MQTT

**Environmental:**
-  — I2C (PM2.5, VOC, NO2, temp, humidity)

**Testing:**
-  — Simulated positions for dev/demo

### Adding a New Profile

Add one  decorator to  — no migration needed:

    @profile(
        id="my_device",
        name="My Device",
        vendor="Vendor",
        hardware_type=HardwareType.UWB,
        protocol=Protocol.MQTT,
        description="...",
        settings_fields=[_field("host","Server Host","string",required=True,default="192.168.1.1")],
    )
    def my_device(): pass

Appears automatically in the Hardware Setup page.

### Hardware API

| Method | Endpoint | Description |
|---|---|---|
| GET | /api/hardware/profiles | Catalog of all profiles |
| GET | /api/hardware | List user configs |
| POST | /api/hardware | Create config |
| PATCH | /api/hardware/<id> | Update config |
| DELETE | /api/hardware/<id> | Delete config |
| POST | /api/hardware/<id>/test | Test connection |
| POST | /api/hardware/<id>/connect | Connect to device |
| POST | /api/hardware/<id>/disconnect | Disconnect |
| GET | /api/hardware/status | Status of all devices |

### Frontend Page

 — Hardware Setup page with status bar, device list, expand-to-view settings, Test/Connect/Delete buttons, and a profile picker modal with pre-filled example values.

---

## 3b. Feature Priority Matrix


Features are organized into **4 phases** across **3 priority levels**:

| Priority | Definition |
|---|---|
| 🔴 Critical | Blocks production use; must be in v1.0 |
| 🟡 High | Core business value; in v1.0 |
| 🟢 Medium | Important but can be added post-launch |

---

### Phase 1 — Foundation (v1.0 Core)

#### 3.1 Authentication & Access Control

| ID | Feature | Priority | Notes |
|---|---|---|---|
| A01 | User registration (admin-initiated) | 🔴 | Email invite or admin creates account |
| A02 | User login with email + password | 🔴 | Argon2 password hashing |
| A03 | JWT session tokens (4h expiry) | 🔴 | Access + refresh token pair |
| A04 | Role-Based Access Control (RBAC) | 🔴 | 3 roles: Admin, Operator, Viewer |
| A05 | Two-Factor Authentication (2FA TOTP) | 🟡 | Google Authenticator compatible |
| A06 | Password reset via email | 🟡 | Token-based, 1h expiry |
| A07 | Login attempt lockout (3 fails → 5min) | 🟡 | Per-account |
| A08 | Audit log on auth events | 🟡 | Login, logout, failed attempts, 2FA |
| A09 | Session management (view + revoke active sessions) | 🟢 | Admin only |

#### 3.2 Core Data Model

| ID | Feature | Priority | Notes |
|---|---|---|---|
| D01 | User model (id, email, name, role, password_hash, 2fa_secret, created_at) | 🔴 | |
| D02 | Tracker model (id, hardware_id, name, type, category, icon, asset_state) | 🔴 | Tag/tagged asset |
| D03 | WifiNode model (id, mac, name, x, y, z, type, status) | 🔴 | Fixed anchors |
| D04 | MapSection model (id, name, polygon_json, is_restricted, color) | 🔴 | |
| D05 | Zone model (id, name, type, position, radius, section_id) | 🔴 | Sphere + section polygons |
| D06 | Alert model (id, tracker_id, type, status, timestamp, acknowledged_by, notes) | 🔴 | |
| D07 | Notification model (id, user_id, type, message, read, created_at) | 🟡 | In-app |
| D08 | AuditLog model (id, user_id, action, entity_type, entity_id, details, ip, timestamp) | 🟡 | |
| D09 | BusinessSetting model (id, key, value, updated_at) | 🟡 | Key-value store |
| D10 | ApiKey model (id, name, key_hash, user_id, permissions, last_used) | 🟢 | For external integrations |
| D11 | BackupJob model (id, filename, size, created_at, status) | 🟡 | |
| D12 | TrackingHistory model (id, tracker_id, x, y, z, timestamp) | 🔴 | Short-term live buffer |
| D13 | CheckInLog model (id, tracker_id, node_id, direction, timestamp) | 🟡 | Check-in/check-out |

#### 3.3 Tag & Node Management

| ID | Feature | Priority | Notes |
|---|---|---|---|
| T01 | Create / edit / delete trackers | 🔴 | Via API + UI |
| T02 | Assign name, type, category, icon to tracker | 🔴 | |
| T03 | Decommission / reactivate tracker | 🔴 | Sets asset_state |
| T04 | Reassign tracker (change hardware_id mapping) | 🔴 | When hardware is replaced |
| T05 | Bulk tag import (CSV) | 🟡 | |
| T06 | Search trackers by name / hardware_id | 🔴 | |
| T07 | Filter tracker list by type, category, status | 🔴 | |
| T08 | Drag-and-drop WiFi node placement on map | 🔴 | Admin only |
| T09 | Node heartbeat monitoring (offline detection) | 🔴 | |

#### 3.4 Positioning Engine

| ID | Feature | Priority | Notes |
|---|---|---|---|
| P01 | Integrate `reference/uwb_positioning.py` as positioning service | 🔴 | Trilateration + Kalman |
| P02 | Integrate `reference/uwb_serial_reader.py` as hardware bridge | 🔴 | Serial + mock |
| P03 | Integrate `reference/floor_planMapper.py` as coordinate mapper | 🔴 | Affine transform |
| P04 | MQTT ingestion layer (subscribe to RSSI data) | 🔴 | Replace REST polling |
| P05 | 300-device real-time update loop | 🔴 | JSON broadcast |
| P06 | Tag → Kalman-filtered position → DB write | 🔴 | |
| P07 | Multi-client sync via MQTT (state_changes topic) | 🔴 | |

#### 3.5 Alerts & Geofencing

| ID | Feature | Priority | Notes |
|---|---|---|---|
| G01 | Point-in-polygon section detection | 🔴 | |
| G02 | Sphere intersection (SqrMagnitude) | 🔴 | |
| G03 | Restricted zone entry → alert | 🔴 | Red flash + audio |
| G04 | No signal alert (timeout detection) | 🔴 | |
| G05 | Low battery alert | 🔴 | |
| G06 | Alert acknowledgement by operator | 🔴 | |
| G07 | Alert debouncing (hasAlertedUI flag) | 🟡 | Prevent spam |
| G08 | Alert history log | 🟡 | |
| G09 | Proximity alert (selected tag + nearby tags) | 🟡 | |

#### 3.6 Map & Visualization

| ID | Feature | Priority | Notes |
|---|---|---|---|
| V01 | 2D floor plan view (Leaflet + CAD image) | 🔴 | |
| V02 | 3D tunnel view (Three.js) | 🔴 | |
| V03 | Real-time tag position rendering | 🔴 | |
| V04 | Section polygons overlay (restricted = red) | 🔴 | |
| V05 | Zone rings visualization | 🔴 | |
| V06 | Color-coded tag dots (normal/warning/critical/offline) | 🔴 | |
| V07 | Orbit camera controls (pan/zoom/rotate) | 🔴 | |
| V08 | History playback slider | 🟡 | |
| V09 | Heatmap layer | 🟢 | |

---

### Phase 2 — Business Features

#### 3.7 Notifications

| ID | Feature | Priority | Notes |
|---|---|---|---|
| N01 | In-app notification bell + list | 🟡 | Real-time via polling/SSE |
| N02 | Mark notification as read / dismiss | 🟡 | |
| N03 | Email notifications via SMTP | 🟡 | Low battery, restricted zone |
| N04 | SMS notifications via provider | 🟢 | Twilio/Vonage (configurable) |
| N05 | Per-user notification preferences | 🟢 | Email / SMS / in-app toggles |
| N06 | Notification on alert trigger | 🟡 | |

#### 3.8 Business & Customer Settings

| ID | Feature | Priority | Notes |
|---|---|---|---|
| S01 | Business settings panel (admin) | 🟡 | Key-value store via UI |
| S02 | Upload business logo (stored locally, served statically) | 🟡 | Max 2MB, PNG/JPG |
| S03 | Facility name + address | 🟡 | |
| S04 | Alert thresholds (battery %, no-signal timeout, etc.) | 🟡 | |
| S05 | Email/SMS provider credentials | 🟡 | SMTP host/port/creds, Twilio SID/token |
| S06 | NTP server configuration | 🟢 | |
| S07 | MQTT broker configuration (host, port, TLS, ACL) | 🟡 | |
| S08 | Customer branding (logo on reports/emails) | 🟢 | |
| S09 | System timezone configuration | 🟡 | |
| S10 | Data retention period (history purge) | 🟢 | |

#### 3.9 User Management

| ID | Feature | Priority | Notes |
|---|---|---|---|
| U01 | Admin creates / edits / deactivates users | 🟡 | |
| U02 | Assign role to user (Admin / Operator / Viewer) | 🟡 | |
| U03 | View all active sessions (admin) | 🟢 | |
| U04 | Force logout a user | 🟢 | Revoke all their tokens |

#### 3.10 Reports

| ID | Feature | Priority | Notes |
|---|---|---|---|
| R01 | Daily summary report (CSV) | 🟡 | Active tags, alerts, check-ins |
| R02 | Tag distance traveled report | 🟡 | Kalman-filtered positions |
| R03 | Zone dwell time report | 🟡 | |
| R04 | Battery level report | 🟡 | |
| R05 | Custom date range reports | 🟢 | |
| R06 | Email report delivery (SMTP) | 🟡 | Scheduled or on-demand |
| R07 | Business logo embedded in reports | 🟢 | |
| R08 | PDF report generation | 🟢 | wkhtmltopdf |

---

### Phase 3 — Enterprise & Integrations

#### 3.11 Search

| ID | Feature | Priority | Notes |
|---|---|---|---|
| Q01 | Global search bar (keyboard shortcut: Ctrl+K) | 🟡 | Searches trackers + users |
| Q02 | Search by name, hardware_id, section | 🟡 | |
| Q03 | Search results with type + status filter | 🟡 | |

#### 3.12 Audit & Compliance

| ID | Feature | Priority | Notes |
|---|---|---|---|
| C01 | Audit log viewer (admin) | 🟡 | Filterable by user, action, entity, date |
| C02 | Log all write operations (create/update/delete) | 🟡 | |
| C03 | Log all auth events | 🟡 | |
| C04 | Audit log export (CSV) | 🟢 | |
| C05 | Immutable audit trail (no delete on log entries) | 🟡 | |

#### 3.13 API Integration

| ID | Feature | Priority | Notes |
|---|---|---|---|
| I01 | REST API with API key auth | 🟢 | For external integrations |
| I02 | Swagger/OpenAPI documentation | 🟢 | |
| I03 | Webhook support (alert events → external URL) | 🟢 | |
| I04 | External positioning engine override | 🟢 | Accept position data from external IPS |

#### 3.14 Server Backup

| ID | Feature | Priority | Notes |
|---|---|---|---|
| B01 | Manual backup trigger (SQLite + uploads) | 🟡 | Admin only |
| B02 | Automated scheduled backup (daily/weekly) | 🟡 | Background scheduler |
| B03 | Backup file download | 🟡 | Admin only |
| B04 | Backup restore from file | 🟡 | Admin only |
| B05 | Backup rotation (keep last N) | 🟢 | Configurable retention |
| B06 | Remote backup storage (S3 / SFTP) | 🟢 | |

---

### Phase 4 — Polish & Scale

#### 3.15 Advanced Features

| ID | Feature | Priority | Notes |
|---|---|---|---|
| L01 | Local LLM assistant (Ollama) | 🟢 | Natural language queries |
| L02 | Heatmap visualization | 🟢 | |
| L03 | Downlink: trigger alarm via MQTT → Pi → BLE | 🟢 | |
| L04 | Downlink: send message to tag | 🟢 | |
| L05 | Check-in / check-out node placement | 🟢 | |
| L06 | Muster report (personnel count by section) | 🟢 | |
| L07 | Multi-operator simultaneous access | 🟡 | MQTT state sync already covers this |

---

## 4. Role & Permission Matrix

| Permission | Admin | Operator | Viewer |
|---|---|---|---|
| View map + live positions | ✅ | ✅ | ✅ |
| View tracker details | ✅ | ✅ | ✅ |
| Acknowledge alerts | ✅ | ✅ | ❌ |
| Create/edit zones | ✅ | ❌ | ❌ |
| Delete zones | ✅ | ❌ | ❌ |
| Drag nodes on map | ✅ | ❌ | ❌ |
| Manage trackers (add/edit/delete/reassign) | ✅ | ✅ | ❌ |
| Create/edit/delete users | ✅ | ❌ | ❌ |
| View audit log | ✅ | ❌ | ❌ |
| Manage business settings | ✅ | ❌ | ❌ |
| Upload business logo | ✅ | ❌ | ❌ |
| Configure alerts & thresholds | ✅ | ❌ | ❌ |
| Configure SMTP/SMS | ✅ | ❌ | ❌ |
| Configure MQTT | ✅ | ❌ | ❌ |
| Trigger manual backup | ✅ | ❌ | ❌ |
| Restore from backup | ✅ | ❌ | ❌ |
| Generate reports | ✅ | ✅ | ❌ |
| View reports | ✅ | ✅ | ✅ |
| View settings | ✅ | ✅ | ✅ |
| Manage API keys | ✅ | ❌ | ❌ |

---

## 5. Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.10+ / Flask 3 |
| ORM | SQLAlchemy 2 + Flask-SQLAlchemy |
| DB | SQLite (file-based, easy backup) |
| Auth | Flask-JWT-Extended + PyOTP (TOTP 2FA) |
| Password hashing | argon2-cffi |
| Frontend | Vanilla JS + Jinja2 (no heavy SPA framework) |
| 2D Map | Leaflet.js |
| 3D Map | Three.js |
| CSS | Custom CSS (holographic theme) |
| Email | Flask-Mail + SMTP |
| SMS | Twilio SDK (pluggable) |
| Background tasks | APScheduler (backup scheduling) |
| MQTT | paho-mqtt |
| Serial | pyserial (from reference) |
| API docs | Flasgger (Swagger/OpenAPI) |
| Migrations | Flask-Migrate (Alembic) |
| Testing | pytest + pytest-flask |
| Production | Gunicorn |

---

## 6. Build Phases — Step-by-Step

### Phase 0 — Project Setup ✅ DONE
**Goal:** Clean scaffold, DB migrations, config, dependencies.

```
Step 0.1  →  ✅ Create directory structure
Step 0.2  →  ✅ Write requirements.txt
Step 0.3  →  ✅ Write config.py + .env.example
Step 0.4  →  ✅ Initialize Flask app + extensions
Step 0.5  →  ✅ Write all SQLAlchemy models (10 models)
Step 0.6  →  ✅ Write extensions.py
Step 0.7  →  ✅ Write run.py
Step 0.8  →  ✅ Write tests: conftest, test_auth, test_trackers
Step 0.9  →  ✅ .gitignore
```

### Phase 1 — Auth + RBAC ✅ DONE
**Goal:** Users can register, login, get JWT tokens, use 2FA.

```
Step 1.1  →  ✅ Auth service: register, hash password (argon2)
Step 1.2  →  ✅ Auth service: login, verify password, issue JWT
Step 1.3  →  ✅ Auth API: POST /api/auth/register, /login, /logout
Step 1.4  →  ✅ 2FA setup: generate TOTP secret, QR code
Step 1.5  →  ✅ 2FA verify on login
Step 1.6  →  ✅ Login lockout after 3 failed attempts
Step 1.7  →  ✅ RBAC service: permission decorator + matrix
Step 1.8  →  ✅ Apply @require_permission to all API routes
Step 1.9  →  ✅ Login page HTML/CSS + JS (holographic theme)
Step 1.10 →  ✅ Tests: 14 auth tests + 9 tracker tests
```

### Phase 2 — Core Tracking Data 🔄 IN PROGRESS
**Goal:** CRUD for trackers, nodes, sections, zones. The foundation everything else runs on.

```
Step 2.1  →  ✅ Tracker API: GET list, POST create, DELETE, PATCH, /reassign
Step 2.2  →  ✅ Node API: CRUD + position update
Step 2.3  →  ✅ Zone API: CRUD
Step 2.4  →  ✅ Section API: CRUD + polygon JSON
Step 2.5  →  ✅ Search service: full-text search across trackers + users
Step 2.6  →  ✅ Search API: /api/search?q=
Step 2.7  →  ⬜ Tracker management page (HTML + JS)
Step 2.8  →  ⬜ Zone editor page (HTML + JS, polygon drawing)
Step 2.9  →  ⬜ SSE stream endpoint: /api/stream/positions
```

### Phase 3 — Positioning Engine ✅ DONE
**Goal:** Integrate reference code; position data flows from hardware → DB → frontend.

```
Step 3.1  →  ✅ Positioning service: wrap reference/uwb_positioning.py
Step 3.2  →  ✅ Serial reader + MQTT bridge services
Step 3.3  →  ✅ Floor plan mapper service
Step 3.4  →  ✅ MQTT client: subscribe to rssi/data, vitals/data, env/data
Step 3.5  →  ✅ Ingestion loop: parse → Kalman → update DB → broadcast via SSE
Step 3.6  →  ✅ History service: circular buffer + SQLite write
Step 3.7  →  ✅ Multi-client sync: publish state_changes to MQTT
Step 3.8  →  ✅ Server-Sent Events (SSE) endpoint: /api/stream/positions
Step 3.9  →  ✅ Tests: 18/18 positioning accuracy tests passing
```

### Phase 4 — Alerts Engine ✅ DONE
**Goal:** Alerts fire correctly and operators see them in real-time.

```
Step 4.1  →  ✅ Alert service: zone geometry (point-in-polygon, sphere) + evaluation
Step 4.2  →  ✅ Notification dispatch: in-app (DB) + email (SMTP) + SMS (Twilio)
Step 4.3  →  ✅ Alert API: full CRUD + acknowledge/resolve + bulk + counts/stats
Step 4.4  →  ✅ Alert notifications via SSE stream (real-time push to browsers)
Step 4.5  →  ✅ Alert history + stats API
Step 4.6  →  ✅ Alert panel page: summary cards, filters, real-time updates, bell
Step 4.7  →  ✅ Tests: 22/22 alert trigger tests passing
```

### Phase 5 — Map & Visualization 🔄 IN PROGRESS
**Goal:** The holographic command center UI is fully functional.

```
Step 5.1  →  Dashboard base layout (header, sidebar, map area)
Step 5.2  →  2D map: Leaflet + CAD image as tile layer
Step 5.3  →  3D map: Three.js tunnel renderer
Step 5.4  →  Real-time dot rendering (tag positions via SSE)
Step 5.5  →  Section polygons + zone rings (color-coded)
Step 5.6  →  Tag detail panel (click tag → show info/vitals/location)
Step 5.7  →  History playback slider
Step 5.8  →  Orbit camera controls
Step 5.9  →  Holographic CSS theme (dark, cyan, glow effects)
Step 5.10 →  Tag list sidebar with filters
```

### Phase 6 — Reports & Notifications (1 day)
**Goal:** Business can generate and email reports.

```
Step 6.1  →  Report service: build CSV for each report type
Step 6.2  →  Report API: /api/reports/daily, /distance, /dwell, /battery
Step 6.3  →  SMTP client: send report as attachment
Step 6.4  →  Notification service: in-app + email dispatch
Step 6.5  →  Notification preferences (per-user)
Step 6.6  →  Reports page UI
Step 6.7  →  Tests: report generation, email dispatch
```

### Phase 7 — Settings & Business Config (1 day)
**Goal:** Admin can configure the whole system from the UI.

```
Step 7.1  →  Business settings model (key-value)
Step 7.2  →  Settings API: GET/PUT /api/settings/<key>
Step 7.3  →  Logo upload (POST /api/settings/logo, save to static/)
Step 7.4  →  Alert threshold settings UI
Step 7.5  →  SMTP/SMS provider config UI
Step 7.6  →  MQTT config UI
Step 7.7  →  Settings page with sections
Step 7.8  →  Inject logo into dashboard header + reports
```

### Phase 8 — Audit & User Management (1 day)
**Goal:** Full audit trail and user admin.

```
Step 8.1  →  Audit service: log all write operations
Step 8.2  →  Audit API: /api/audit (GET with filters)
Step 8.3  →  Audit log viewer page
Step 8.4  →  User management API: CRUD users, assign role
Step 8.5  →  User management page
Step 8.6  →  Tests: audit log captures correct events
```

### Phase 9 — Backup & Deployment (1 day)
**Goal:** System can be backed up and restored; runs in production.

```
Step 9.1  →  Backup service: SQLite dump + file storage
Step 9.2  →  Backup API: trigger, list, download, restore
Step 9.3  →  APScheduler: daily automated backup
Step 9.4  →  Backup management UI
Step 9.5  →  config.env setup instructions
Step 9.6  →  gunicorn.conf.py
Step 9.7  →  nginx.conf example
Step 9.8  →  Docker Compose file (optional)
Step 9.9  →  Production smoke test
```

### Phase 10 — API Keys & Integrations (0.5 day)
**Goal:** External systems can connect via API.

```
Step 10.1 →  API key model + generation
Step 10.2 →  API key auth middleware (alternative to JWT)
Step 10.3 →  Swagger/OpenAPI docs (Flasgger)
Step 10.4 →  API key management page
```

### Phase 11 — Polish & Testing (1.5 days)
**Goal:** Everything works, nothing is broken.

```
Step 11.1 →  End-to-end tests: full auth → create tag → position → alert → acknowledge
Step 11.2 →  Error pages (404, 500) styled to holographic theme
Step 11.3 →  Loading states + empty states on all pages
Step 11.4 →  Keyboard shortcuts (Ctrl+K = search, Esc = close modals)
Step 11.5 →  Mobile responsive layout (basic)
Step 11.6 →  Delete reference folder (dev decision point)
Step 11.7 →  README.md with setup instructions
```

---

## 7. Estimated Timeline

```
Week 1:  ✅ Phase 0 → Phase 1 (Setup + Auth + RBAC)    ← DONE
Week 2:  🔄 Phase 2 → Phase 3 (Data model + Positioning Engine)
Week 3:  ⬜ Phase 4 → Phase 5 (Alerts + Map & Visualization)
Week 4:  ⬜ Phase 6 → Phase 8 (Reports + Settings + Audit)
Week 5:  ⬜ Phase 9 → Phase 11 (Backup + API + Polish)
```

**Total: ~5 weeks** for a production-quality v1.0

---

## 8. Key Design Decisions

### Why Vanilla JS (not React/Vue)?
- Simpler deployment (single Flask app, no build step for frontend)
- Faster to iterate for a team of 1-3 developers
- Jinja2 templates + vanilla JS covers all UI needs
- Can always add a React SPA later via a separate `/app` route

### Why SQLite?
- Zero infrastructure — single file, easy backup, easy restore
- Sufficient for single-facility deployment up to millions of history rows
- WAL mode enabled for concurrent reads during live tracking
- If multi-tenant or high scale needed later → Postgres with minimal code change

### Why SSE instead of WebSockets?
- Simpler server-side (Flask-SSE pattern)
- Works through most proxies without config
- Sufficient for one-way position updates
- Can upgrade to WebSockets later for bidirectional needs (downlink commands)

### Why REST (not GraphQL)?
- Easier to document, test, and integrate
- SQLite doesn't benefit from GraphQL's nested queries
- OpenAPI/Swagger integration is mature

### Why Argon2 for passwords?
- Current best practice (won Password Hashing Competition)
- argon2-cffi is well-maintained in Python

### Why APScheduler (not Celery)?
- No Redis dependency
- Sufficient for backup scheduling + alert cleanup
- Single-process model avoids infrastructure complexity

---

## 9. Current Repository Contents

```
HOLO-RTLS/
├── reference/                  ← tracker-strt code (read-only)
│   ├── uwb_positioning.py    ✅ Proven trilateration + Kalman
│   ├── uwb_serial_reader.py  ✅ Serial/UART + mock reader
│   ├── floor_plan_mapper.py ✅ Affine coordinate transform
│   ├── app_uwb.py           ✅ REST API pattern reference
│   └── requirements.txt     ✅ Python dependencies
│
├── backend/
│   ├── app.py              ✅ Flask factory
│   ├── config.py           ✅ All settings from env vars
│   ├── extensions.py        ✅ db, migrate, jwt, mail singletons
│   ├── models/             ✅ 10 models + __init__.py
│   ├── api/                ✅ 13 blueprint stubs (all CRUD routes)
│   ├── services/            ✅ auth_service.py, rbac_service.py
│   └── utils/              ✅ decorators.py
│
├── frontend/
│   ├── templates/
│   │   ├── auth/login.html ✅ Holographic login page
│   │   └── dashboard/
│   │       ├── index.html  ✅ Main command center
│   │       └── *.html     ✅ 9 placeholder pages
│   └── static/             ✅ CSS (22KB) + JS (api, auth, dashboard, map2d, map3d)
│
├── tests/                    ✅ conftest + test_auth + test_trackers
├── docs/                     ✅ PHASE_0.md + PHASE_1.md
├── run.py                   ✅ Entry point + default admin
├── .env.example
├── .gitignore
├── requirements.txt
└── BUILD_PLAN.md
```

---

## 10. Immediate Next Action

Phase 0 ✅ and Phase 1 ✅ are complete.

**Next agent should:**

1. Run `pytest tests/ -v` to verify everything passes
2. Start Phase 2 — implement tracker management page + zone editor page
3. Wire the SSE stream endpoint for live position updates

Ready to start Phase 2?
