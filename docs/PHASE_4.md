# HOLO-RTLS — Phase 4: Alert Engine

> **Goal:** Alerts fire automatically and operators see them in real-time.
> **Status:** ✅ COMPLETE

---

## What Was Built

### Alert Types

| Type | Trigger | Response |
|---|---|---|
| `NO_SIGNAL` | Tag offline > 2min | In-app + email |
| `RESTRICTED_ZONE` | Tag enters restricted zone | In-app + email + SSE flash |
| `LOW_BATTERY` | Battery < 20% or < 10% | In-app |
| `ENV_HAZARD` | VOC > 500ppb or temp > 40°C | In-app + email |
| `NODE_OFFLINE` | Anchor node offline | In-app |
| `MANUAL` | Operator-triggered | In-app |

### Architecture

```
IngestionLoop
    │
    ├── position update (x, y, z)
    │
    ▼
AlertService.evaluate_position()
    │
    ├── Zone violations (sphere intersection)
    ├── Section violations (point-in-polygon, ray-casting)
    ├── Low battery check
    └── Environmental hazard check
    │
    ▼
AlertService._fire_alert()
    │
    ├── Write Alert row to DB (ACTIVE state)
    ├── SSE broadcast → all browsers (alert event)
    └── NotificationService.notify_alert()
              │
              ├── In-app notification (Notification table)
              ├── Email (SMTP via Flask-Mail)
              └── SMS (Twilio, if configured)
```

---

## Alert Debouncing

Each (tracker_id, alert_type) pair has a **60-second debounce window**.
If the same alert fires again within 60s, it is suppressed.
This prevents alert storms from continuous zone violations.

```python
_should_fire(tracker_id, alert_type)
  → last fired < 60s ago? → SUPPRESSED
  → otherwise → FIRED
```

---

## Zone Geometry

**Sphere zones** (most common): use `point_in_sphere()` — fast, O(1).

**Section polygons**: use `point_in_polygon()` — ray-casting algorithm.
Supports GeoJSON `coordinates` format or simple list of `[x, y]` pairs.
The mining map sections (MapSection with `is_restricted=True`) use polygon geometry.

---

## Real-Time Notifications

Alerts push to browsers via the existing SSE stream — no polling needed.

```javascript
const es = new EventSource('/api/stream/positions');
es.addEventListener('alert', e => {
  const alert = JSON.parse(e.data).alert;
  // alert = { id, tracker_id, alert_type, state, message, position, ... }
  showAlertToast(alert);
});
```

---

## Alert API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/alerts` | List alerts (filterable by state, type, tracker, since |
| GET | `/api/alerts/active` | All unacknowledged alerts |
| GET | `/api/alerts/counts` | Counts by type and state |
| GET | `/api/alerts/stats` | Summary: total, active, today, avg resolution time |
| GET | `/api/alerts/<id>` | Single alert |
| POST | `/api/alerts/<id>/acknowledge` | Acknowledge (requires permission) |
| POST | `/api/alerts/<id>/resolve` | Resolve (requires permission) |
| POST | `/api/alerts/acknowledge-all` | Bulk acknowledge all active |
| GET | `/api/alerts/notifications` | Current user's in-app notifications |
| POST | `/api/alerts/notifications/<id>/read` | Mark as read |
| POST | `/api/alerts/notifications/read-all` | Mark all as read |

---

## Notification Channels

| Channel | Status | Config |
|---|---|---|
| In-app | ✅ Active | Always on |
| Email | ✅ Configured | `MAIL_SERVER` in backend/config.py |
| SMS | ⚙️ Optional | Twilio credentials via settings |

---

## Alert Panel Page (`/alerts`)

- Summary cards: total, active, today, fired, suppressed, avg resolution time
- Filter by state: All / Active / Acknowledged / Resolved
- Filter by type: All / No Signal / Low Battery / Restricted Zone / Env Hazard
- Acknowledge individual or bulk
- Resolve individual
- SSE real-time: new alerts flash in with toast notification
- Floating notification bell with unread badge
- Alert row shows: icon, type, message, position, section, timestamp, acknowledgement status

---

## Unit Tests (22 passing)

```
TestPointInPolygon       6 tests  — ray-casting, concave, edge cases
TestPointInSphere        4 tests  — 3D intersection
TestAlertServiceLogic   12 tests  — zone violation, battery, env, debounce
─────────────────────────────────────────────────────────────
Total                  22 passed
```

---

## Next: Phase 5 — Map & Visualization

After alerts, build the map visualization using the uploaded mining PNG:
1. Map upload + storage (CAD image as section background)
2. Calibration: click image → real-world coordinates
3. 2D view: Leaflet + CRS.Simple image overlay
4. 3D view: Three.js texture plane
5. Real-time tag dots via SSE
6. Zone rings and section polygons overlay
7. Tag detail panel (click → info/vitals/location)
8. History playback slider

See `docs/PHASE_5_TODO.md` (to be written).
