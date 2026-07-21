# Node / Anchor Master Plan — Detection, Maps, MQTT Broker

> **Context:** WiFi nodes publish BLE tag data via **MQTT port 1883**. The **HOLO-RTLS server** becomes the MQTT broker (replacing the PC `node_reader` broker for production). Anchors must work on **2D and 3D** Live Maps.  
> **Repo state:** `master` / `main` @ MQTT broker app + dual anchor models (`WifiNode` + `WifiAnchor`).

---

## 1. Current state (review)

### What works today

| Area | Implementation | UI / API |
|------|----------------|----------|
| **Register anchor** | `WifiNode` model | `POST /api/nodes`, `/nodes` page |
| **Rename** | `assigned_name` | `PATCH /api/nodes/:id` |
| **Edit location** | `pos_x/y/z` metres | Map Setup drag, placement mode, `PATCH` |
| **Delete** | Hard delete + audit | `DELETE /api/nodes/:id` |
| **2D map** | Leaflet — markers, drag, coverage rings | `map2d.js`, `/?mode=setup` |
| **3D map** | Three.js — anchor cylinders, floor plane | `map3d.js` |
| **Tag ingest (HTTP)** | `POST /api/scanner/detections` | Pi / scanner daemon |
| **Tag positioning** | RSSI trilateration (≥3 anchors) | `WifiPositioningService` |
| **History / playback** | `TrackingHistory`, map playback mode | `/api/positioning/history` |
| **Tracker assignment** | Discovery → acknowledge | `/trackers` page |
| **Hardware test** | MQTT/serial connect test | `/hardware` page |

### Critical gaps

| Gap | Impact |
|-----|--------|
| **Server is not MQTT broker** | WiFi nodes cannot publish to server `:1883` today; only PC `node_reader` embeds `amqtt` |
| **Server MQTT expects JSON** | WiFi CSV `NodeMAC,TagMAC,RSSI,Battery` parsed only in `node_reader/mqtt_parse.py` |
| **Two anchor tables** | `WifiNode` (Location Core) vs `WifiAnchor` (scanner) — not synced |
| **`load_anchors_from_db` bug** | Uses `node.mac`, `node.x`, `status == "active"` — wrong fields; **0 anchors load** |
| **Unplaced-node filter bug** | `map2d.js` filters `n.pos_x` but API returns `position.x` |
| **No node heartbeat ingest** | `last_heartbeat` column never updated |
| **No network diagnostics page** | Per-node MQTT stats, packet rate, last seen |
| **No scanner anchor DELETE** | Stale `WifiAnchor` rows accumulate |
| **PC broker ≠ production path** | Tags stop on PC; no uplink to server map |

---

## 2. Target architecture

```mermaid
flowchart TB
    subgraph nodes [WiFi nodes same LAN]
        N1[Node A MAC ..4B:18]
        N2[Node B]
        N3[Node C]
    end

    subgraph server [HOLO-RTLS Server]
        BRK[Embedded MQTT Broker :1883]
        ING[MqttTagIngestService]
        SYNC[AnchorSyncService]
        POS[WifiPositioningService]
        HIST[HistoryService]
        SSE[SSE /api/stream/positions]
        API["/api/nodes · /api/nodes/:id/diagnostics"]
    end

    subgraph ui [Web UI]
        MAP2D[2D Live Map]
        MAP3D[3D Live Map]
        NODES[/nodes admin]
        DIAG[Network diagnostics]
    end

    N1 & N2 & N3 -->|MQTT publish rssi/data CSV| BRK
    BRK --> ING
    ING -->|anchor_mac + detections| POS
    ING -->|update last_seen| SYNC
    POS --> HIST --> SSE
    SSE --> MAP2D & MAP3D
    API --> NODES & DIAG
    SYNC -->|WifiNode status ONLINE| API
```

### Design principles

1. **Single anchor source of truth:** `WifiNode` — scanner `WifiAnchor` becomes a view/sync layer or is merged.
2. **Server = broker** for production; PC broker remains a **commissioning tool** only.
3. **Same coordinates** for 2D and 3D: metres `(pos_x, pos_y, pos_z)` from `WifiNode`.
4. **MQTT topic contract:** `rssi/data` CSV + optional JSON on `ble/rssi`, `wifi/rssi`.

---

## 3. Feature specification

### 3.1 Node detection

| Step | Behaviour |
|------|-----------|
| Auto-detect on MQTT connect | First publish from unknown `NodeMAC` → create **provisional** `WifiNode` (`status=CALIBRATING`, position unset) |
| LAN scan (optional) | Subnet scan for `:1883`, `:80` — suggest IPs in commissioning wizard |
| Discovery list | `/nodes` tab **Discovered** — nodes with MQTT traffic but no map position |

### 3.2 Assignment

| Object | Assignment |
|--------|------------|
| **Node → map** | Admin picks node → clicks 2D/3D map → saves `pos_x/y/z` |
| **Node → section/floor** | `metadata.floor_id` or link to `MapSection` |
| **Tag → tracker** | Existing `/trackers` acknowledge flow (unchanged) |
| **Tag → nearest node** | `Tracker.nearest_node` from positioning output |

### 3.3 Location (2D + 3D)

| Map | Anchor rendering | Interaction |
|-----|------------------|-------------|
| **2D** | Leaflet marker + coverage circle | Drag → `PATCH` position; Setup placement mode |
| **3D** | Cylinder at `(x,y,z)` on floor plane | Click → edit panel; sync camera floor to `pos_z` |
| **Multi-floor** | Filter nodes where `pos_z` ≈ active floor `z_index` | Floor selector drives both maps |

**Coordinate rule:** Store **metres** in DB. 2D uses calibration + floor plan affine; 3D uses same `(x,y)` and `z` as height above floor.

### 3.4 CRUD + rename

| Action | API | UI |
|--------|-----|-----|
| Create | `POST /api/nodes` | Add modal on `/nodes` |
| Read | `GET /api/nodes`, `GET /api/nodes/:id` | Table + map popup |
| Update / rename | `PATCH /api/nodes/:id` | Inline edit + map form |
| Delete | `DELETE /api/nodes/:id` | Confirm dialog; remove markers |

### 3.5 History & statistics

| Metric | Source | API (new) |
|--------|--------|-----------|
| Tag positions over time | `TrackingHistory` | Existing `/api/positioning/history/:id` |
| **Per-node RSSI stats** | Aggregate `DetectionEvent` by anchor MAC | `GET /api/nodes/:id/stats?since=24h` |
| **Messages / hour** | MQTT ingest counter | `GET /api/nodes/:id/diagnostics` |
| **Uptime / heartbeat** | `last_heartbeat`, MQTT last_seen | Diagnostics panel |
| Playback | Map playback mode | Existing — ensure anchors visible in 2D/3D during playback |

### 3.6 Network diagnostics

New page: **`/nodes/diagnostics`** (or tab on `/nodes`)

| Field | Description |
|-------|-------------|
| Broker status | Server MQTT broker up, port 1883, bind IP |
| Node online | Last MQTT message &lt; 60s |
| Msg rate | Publishes/min per node |
| Last payload | Sample CSV/JSON (truncated) |
| Avg RSSI heard | From recent detections |
| Actions | Test publish, ping broker, copy `mqtt://SERVER:1883` |

---

## 4. Server MQTT broker implementation

### 4.1 Reuse PC broker code on server

Move/adapt from `node_reader/`:

| Module | Server path |
|--------|-------------|
| `pc_broker.py` | `backend/services/mqtt_broker.py` |
| `capture_plugin.py` | `backend/services/mqtt_capture_plugin.py` |
| `mqtt_parse.py` | `backend/services/mqtt_tag_parse.py` |

### 4.2 Ingest pipeline

```python
# On MQTT message (topic, payload):
devices = parse_mqtt_payload(payload, topic)
for batch in group_by_anchor(devices):
    wifi_positioning.process_scan_batch(anchor_mac, detections)
    update_node_last_seen(anchor_mac)
ingestion_loop.notify_sse()  # existing path
```

### 4.3 Config (`.env`)

```env
MQTT_BROKER_ENABLED=true
MQTT_BROKER_BIND=0.0.0.0
MQTT_BROKER_PORT=1883
MQTT_BROKER_ALLOW_ANONYMOUS=true
# Existing outbound publish uses same broker via localhost
MQTT_BROKER_HOST=127.0.0.1
```

### 4.4 WiFi node configuration (example PC `10.60.1.5` → server)

| Setting | Value |
|---------|-------|
| Broker host | Server LAN IP (e.g. `10.60.1.5`) |
| Port | `1883` |
| Topic | `rssi/data` |
| Payload | `NodeMAC,TagMAC,RSSI,Battery` |

---

## 5. Unify anchor models (Phase 2)

**Problem:** `WifiNode` and `WifiAnchor` duplicate MAC, name, position.

**Recommended approach:**

1. **`WifiNode` = canonical** (already used by 2D/3D map).
2. On `POST /api/scanner/anchors`, **upsert** matching `WifiNode` by MAC.
3. On `PATCH /api/nodes/:id`, **sync** to `WifiAnchor` if row exists (migration period).
4. Long-term: drop `WifiAnchor` table; migrate `DetectionEvent.anchor_id` → `wifi_node_id`.

---

## 6. Implementation phases

### Phase 0 — Quick fixes (1–2 days)

| Task | File |
|------|------|
| Fix `load_anchors_from_db` | `backend/services/positioning_service.py` |
| Fix unplaced-node filter | `frontend/static/js/visualization/map2d.js` |
| Fix MQTT env var names in `app.py` | `backend/app.py` |
| Add `DELETE /api/scanner/anchors/:id` | `backend/api/scanner/__init__.py` |

### Phase 1 — Server MQTT broker + ingest (core)

| Task | File |
|------|------|
| Embedded broker service | `backend/services/mqtt_broker.py` |
| CSV parse + batch ingest | `backend/services/mqtt_tag_ingest.py` |
| Start broker in app factory | `backend/app.py` |
| Auto-update `last_heartbeat` / `last_seen` | `backend/services/node_presence.py` |
| Tests | `tests/test_mqtt_tag_ingest.py` |

### Phase 2 — Anchor UX + 2D/3D parity

| Task | File |
|------|------|
| Unplaced nodes banner (fixed filter) | `map2d.js` |
| 3D click-to-select anchor + edit | `map3d.js` |
| Floor filter by `pos_z` | `map2d.js`, `map3d.js`, `dashboard.js` |
| Node popup: rename inline | `map2d.js` |
| Sync `WifiNode` ↔ `WifiAnchor` | `backend/services/anchor_sync.py` |

### Phase 3 — Diagnostics, history, statistics

| Task | File |
|------|------|
| `GET /api/nodes/:id/diagnostics` | `backend/api/nodes/__init__.py` |
| `GET /api/nodes/:id/stats` | `backend/api/nodes/__init__.py` |
| Diagnostics UI tab | `frontend/templates/nodes/diagnostics.html` |
| Broker status chip on dashboard | `settings.html` / `dashboard.js` |

### Phase 4 — Auto-discovery & commissioning

| Task | Description |
|------|-------------|
| MQTT auto-register | Unknown anchor MAC → provisional node |
| Commissioning wizard | Broker URL copy, firewall hint, test publish |
| Node Reader uplink mode | Optional: PC broker → forward to server (dev only) |

---

## 7. API additions (summary)

```
GET    /api/nodes/:id/diagnostics     → online, msg_rate, last_payload, broker_reachable
GET    /api/nodes/:id/stats           → avg_rssi, detection_count, tags_seen (since=)
GET    /api/nodes/discovered          → MQTT seen, not yet placed
POST   /api/nodes/:id/heartbeat       → optional explicit heartbeat (MQTT preferred)
DELETE /api/scanner/anchors/:id       → remove scanner duplicate
GET    /api/system/mqtt-broker        → broker status, bind, port, clients_connected
```

---

## 8. 2D / 3D map checklist

| Requirement | 2D | 3D |
|-------------|----|----|
| Load anchors from `/api/nodes` | ✅ | ✅ |
| Show unplaced nodes | Fix filter | Add list panel |
| Drag reposition | ✅ | ⬜ Phase 2 |
| Coverage radius | ✅ metadata | ⬜ Phase 2 |
| Multi-floor (`pos_z`) | Partial | Partial |
| Playback shows anchors | ✅ | ✅ |
| SSE tag positions | ✅ | ✅ |

---

## 9. Dependencies

```
# backend/requirements.txt (add)
amqtt>=0.11.0
```

Firewall: **inbound TCP 1883** on server host.

---

## 10. Success criteria

1. WiFi node publishes to **`mqtt://SERVER:1883`** → tags appear on **Live Map (2D & 3D)** within 2s.
2. Admin can **create, rename, move, delete** anchors on map and `/nodes` page.
3. **Diagnostics** shows each node online/offline and message rate.
4. **History playback** shows tag paths with anchors visible.
5. **≥3 placed anchors** → RSSI trilateration produces stable positions.

---

## 11. Related files

| Path | Role |
|------|------|
| `backend/models/tracker.py` | `WifiNode` |
| `backend/models/detection.py` | `WifiAnchor`, `DetectionEvent` |
| `backend/api/nodes/` | Node CRUD |
| `backend/api/scanner/` | Detection ingest |
| `backend/services/wifi_positioning.py` | Trilateration |
| `backend/services/hardware_bridge.py` | Legacy JSON MQTT subscriber |
| `frontend/static/js/visualization/map2d.js` | 2D anchors |
| `frontend/static/js/visualization/map3d.js` | 3D anchors |
| `node_reader/pc_broker.py` | Reference broker impl |
| `node_reader/mqtt_parse.py` | CSV parse reference |

---

## 12. Recommended next PR

**Title:** Phase 0 + Phase 1 — Server MQTT broker and anchor bug fixes

1. Fix positioning anchor load + map unplaced filter  
2. Port `mqtt_parse` + embedded broker to `backend/services/`  
3. Wire ingest → `WifiPositioningService` → SSE  
4. Document `.env` and firewall for port 1883  
