# HOLO-RTLS — Phase 3: Positioning Engine

> **Goal:** Real-time position data flows from hardware → DB → browser without manual intervention.
> **Status:** ✅ COMPLETE

---

## What Was Built

### Architecture

```
Physical Hardware (UWB, BLE, WiFi)
         │
         ▼
  HardwareBridgeManager
  ├─ SerialBridge      → UWBSerialReader (DWM1001, DW1000, etc.)
  ├─ MQTTSubscriber    → paho-mqtt (Sewio, custom MQTT)
  └─ MockBridge         → Simulated data (no hardware needed)
         │
         ▼ (event queue, thread-safe)
  IngestionLoop
  ├─ 1. Position calculation (PositioningService)
  │      • UWB trilateration + Kalman smoothing
  │      • BLE/WiFi RSSI → weighted centroid
  │      • Sewio direct x,y (no computation)
  ├─ 2. Tracker DB cache (auto-creates unknown tags)
  ├─ 3. Write to HistoryService (buffered batch → SQLite)
  ├─ 4. SSE broadcast → all connected browsers
  └─ 5. MQTT publish  → rtls/state_changes (multi-client sync)
         │
         ▼
  HistoryService (background flush every 5s)
  ├─ PositionSnapshot (latest position, one row per tracker)
  ├─ TrackingHistory  (full history, retention 30 days)
  └─ Velocity estimation (vx, vy, speed m/s)
```

---

## Services

| File | Role |
|---|---|
| `services/positioning_service.py` | UWB trilateration, Kalman, RSSI, velocity |
| `services/hardware_bridge.py` | Serial + MQTT + Mock bridges (background threads) |
| `services/floor_plan_mapper.py` | Affine transform: pixel ↔ real-world meters |
| `services/history_service.py` | Circular buffer + batch SQLite writes |
| `services/ingestion_loop.py` | Main pipeline: queue → position → DB → SSE → MQTT |
| `api/stream.py` | SSE endpoint + MQTT publisher |
| `api/positioning/` | REST API for history + calibration |

---

## Positioning Accuracy (from tests)

| Method | Expected Accuracy | Notes |
|---|---|---|
| UWB trilateration | 10–30 cm | With 4+ anchors, line-of-sight |
| BLE/WiFi RSSI | 3–10 m | Log-distance path loss model |
| Sewio direct | 1–5 cm | External IPS provides x,y directly |

All methods include Kalman smoothing (1D filter per axis, configurable variance).

---

## Configuration (Automatic)

The engine starts automatically when the Flask app starts:

```python
# backend/app.py — _init_positioning()
1. Loads anchors from WifiNode DB table (x, y, z per node)
2. Loads floor plan calibration from Setting table
3. Starts HistoryService (background flush thread)
4. Reads active HardwareConfig rows from DB
5. Starts bridge for each config (Serial or MQTT)
6. Starts IngestionLoop (consumes bridge queue)
7. Starts MQTT publisher (rtls/state_changes)
```

**No manual start required.** On restart, it reconnects to all active hardware configs.

---

## Mock Mode (No Hardware)

Add a "Mock / Simulator" hardware config. It generates Lissajous-curve movement
for configurable tag IDs, producing realistic-looking data every 0.5s.

```bash
# Activate mock from CLI (no DB needed):
# backend/services/hardware_bridge.py → MockBridge
```

---

## SSE Stream

Browser connects to `/api/stream/positions` and receives:

```json
{
  "type": "position_update",
  "tracker_id": 1,
  "hardware_id": "AA:BB:CC:DD:EE:FF",
  "x": 5.234, "y": 3.891, "z": 0.0,
  "accuracy": 0.12,
  "vx": 0.5, "vy": -0.3, "speed": 0.58,
  "source": "UWB",
  "timestamp": "2026-07-19T09:30:00+00:00"
}
```

Also sent on connect: `{"type": "snapshot", "positions": [...]}` with all current positions.

---

## API Endpoints (Phase 3)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/stream/positions` | SSE real-time stream |
| GET | `/api/stream/status` | Ingestion health + queue depth |
| GET | `/api/positioning/live` | All tracker positions (snapshot) |
| GET | `/api/positioning/live/<id>` | One tracker position |
| GET | `/api/positioning/history/<id>` | Position history |
| GET | `/api/positioning/history/<id>/export` | CSV export |
| GET | `/api/positioning/stats` | History service stats |
| POST | `/api/positioning/calibration` | Add calibration point |
| GET | `/api/positioning/calibration` | Calibration status |

---

## Unit Tests (18 passing)

```
tests/test_positioning.py
  TestTrilateration        4 tests
  TestKalmanSmoothing      1 test
  TestRSSIToDistance        4 tests
  TestRSSIPositioning       2 tests
  TestVelocityEstimation    3 tests
  TestMockDataGeneration    1 test
  TestMultiSourcePayload   3 tests
  ──────────────────────────────────
  Total                   18 passed
```

---

## Next: Phase 4 — Alerts Engine

After hardware positions are flowing:
1. AlertService evaluates zone restrictions + timeouts
2. Alert dispatch (in-app bell, email, SMS)
3. Alert panel page
4. Alert acknowledgement

See `docs/PHASE_4_TODO.md` (to be written).
