# HOLO-RTLS — Indoor Real-Time Location System
## Architecture Documentation

> **Canonical product (this repo):** Flask + Jinja web RTLS — see `docs/MASTER_PLAN_ABOVE_MARKET.md` and `docs/EXECUTION_REPORT.md`.  
> **Below:** Historical / aspirational Unity holographic R&D notes. Treat Unity claims as **not** the current shipping stack.

> **Version:** 1.0 | **Engine (aspirational):** Unity 3D (URP) | **Target (R&D):** 300+ Devices @ 60 FPS

---

## 1. Project Overview

### 1.1 What This System Does

HOLO-RTLS is a high-performance, AI-augmented indoor positioning platform that transforms raw BLE/WiFi/UWB telemetry into a real-time holographic command center. It replaces slow, generic SCADA dashboards with a gaming-engine-grade visual experience capable of tracking hundreds of assets simultaneously — personnel, machines, smartphones, wearables, and environmental sensors — across multi-level tunnels, buildings, and open facilities.

### 1.2 Design Philosophy

Three principles govern every architectural decision:

| Principle | Why It Matters |
|---|---|
| **Data-Oriented Design (DOD)** | 300+ entities at 60 FPS is impossible with standard OOP GameObjects. Struct arrays and flat memory layouts eliminate GC pauses and maximize CPU cache efficiency. |
| **Zero-Trust Hardware** | Unity never talks directly to BLE/WiFi hardware. Edge nodes (Raspberry Pis) bridge the physical layer. MQTT is the single source of truth. |
| **Mathematical Fidelity** | Visual smoothness is cosmetic. Reports, alerts, and dwell-time calculations must be based on Kalman-filter-corrected coordinates — not interpolated lerp positions. |

### 1.3 Core Goals

- [x] Track 300 simultaneous devices at ≥60 FPS
- [x] Render in 2D (floor plan) and 3D (tunnels, multi-level)
- [x] Holographic UI aesthetic matching reference imagery
- [x] 360° orbital camera with smooth pan/zoom
- [x] Real-time geofencing and proximity alerts
- [x] BLE/WiFi/UWB triangulation via edge node network
- [x] Vital sign monitoring (HR, SpO2) from wearables
- [x] Environmental sensor integration (gas, temperature)
- [x] Bi-directional downlink (alarm, message, call)
- [x] Local LLM assistant for natural language queries
- [x] Role-Based Access Control (RBAC)
- [x] Persistent SQLite database (no data loss on restart)
- [x] VLAN-aware MQTT transport
- [x] Automated email reports
- [x] Heatmap, history playback, statistics
- [x] User-editable POI, zones, sections, WiFi node positions

---

## 2. System Architecture

### 2.1 Layer Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     APPLICATION LAYER                        │
│                   Unity 3D — URP + C# DOD                    │
│  ┌─────────────┐ ┌──────────────┐ ┌────────────────────┐   │
│  │ Holographic │ │ Orbit Camera │ │    UI Toolkit     │   │
│  │   Renderer  │ │  Controller  │ │  (Canvas/Panel)   │   │
│  └─────────────┘ └──────────────┘ └────────────────────┘   │
│  ┌─────────────┐ ┌──────────────┐ ┌────────────────────┐   │
│  │ RTLS Engine │ │ Kalman Filter│ │  Alert & Geofence  │   │
│  │ (DOD Array) │ │   (Math)     │ │     Engine         │   │
│  └─────────────┘ └──────────────┘ └────────────────────┘   │
│  ┌─────────────┐ ┌──────────────┐ ┌────────────────────┐   │
│  │ MQTT Client │ │  LLM Bridge  │ │  Report Engine    │   │
│  │  (MQTTnet)  │ │  (Ollama)     │ │  (CSV + SMTP)      │   │
│  └─────────────┘ └──────────────┘ └────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           SQLite Database (Persistence Layer)       │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │ MQTT over VLAN (TLS + ACLs)
┌──────────────────────────▼──────────────────────────────────┐
│                    TRANSPORT LAYER                           │
│            MQTT Broker (Mosquitto / EMQX)                   │
│         VLAN-isolated | TLS encrypted | ACL-controlled      │
└──────────────────────────┬──────────────────────────────────┘
                           │ MQTT Subscribe / Publish
┌──────────────────────────▼──────────────────────────────────┐
│                  EDGE COMPUTE LAYER                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Pi Node 01  │  │  Pi Node 02  │  │   Pi Node N      │  │
│  │  (Python 3)  │  │  (Python 3)  │  │   (Python 3)     │  │
│  │  BLE Scan    │  │  BLE Scan    │  │   BLE Scan       │  │
│  │  WiFi Probe  │  │  WiFi Probe  │  │   WiFi Probe     │  │
│  │  Triangulate │  │  Triangulate │  │   Triangulate    │  │
│  │  MQTT Pub    │  │  MQTT Pub    │  │   MQTT Pub       │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │ BLE / WiFi / UWB Radio
┌──────────────────────────▼──────────────────────────────────┐
│                    PHYSICAL LAYER                            │
│  ┌─────────┐ ┌──────────┐ ┌─────────────┐ ┌──────────────┐  │
│  │Personnel│ │ Smart-   │ │   BLE/      │ │ Environmental│  │
│  │ Tags /  │ │ phones / │ │   UWB       │ │   Sensors    │  │
│  │ Badges  │ │ Watches  │ │   Anchors   │ │ (Gas/Temp)   │  │
│  └─────────┘ └──────────┘ └─────────────┘ └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
BLE/WiFi Radio Waves
        │
        ▼
┌──────────────────┐
│  Edge Node Pi    │
│  ───────────────│
│  1. Scan for     │
│     MAC addrs    │
│  2. Read RSSI    │
│  3. Triangulate  │
│  4. Format CSV   │
└────────┬─────────┘
         │ MQTT Publish: `rssi/data` → "Pi01_MAC,Tag_MAC,-72,98"
         ▼
┌──────────────────┐
│  MQTT Broker     │
│  (TLS + ACLs)    │
└────────┬─────────┘
         │ MQTT Subscribe
         ▼
┌──────────────────────────────────────────────────────────┐
│  Unity — RTLSKernel (Main Thread)                        │
│  ──────────────────────────────────────────────────────│
│                                                          │
│  1. Parse CSV string (zero allocation)                  │
│  2. Push to Kalman Filter → smoothed X, Y               │
│  3. Update TrackerData[i].targetPosition                 │
│                                                          │
│  ── Per-Frame Update Loop ─────────────────────────────│
│  4. Lerp(current → target) for visual smoothness         │
│  5. Record history to circular buffer                   │
│  6. Check geofences (SqrMagnitude, O(n×m))              │
│  7. Check proximity (selected tag vs all)                │
│  8. Evaluate IoT alerts (vitals, gas, battery)         │
│  9. Draw instanced mesh (single GPU draw call)          │
│  10. Update UI via UnityMainThreadDispatcher            │
│                                                          │
│  ── Persisted to SQLite ──────────────────────────────│
│  • Node positions (calibration)                         │
│  • Tag metadata (names, icons, types)                   │
│  • Map sections (polygons)                              │
│  • User accounts + roles                               │
│  • Alert history                                        │
└──────────────────────────────────────────────────────────┘
         │
         ├──► UI Canvas (Holographic panels)
         ├──► 3D Holographic Map (URP shaders)
         ├──► LLM Bridge → Ollama (HTTP POST)
         └──► Report Engine → SMTP Email
```

---

## 3. Core Data Structures

### 3.1 TrackerData (Primary Entity)

```csharp
public enum DeviceCategory { PersonnelTag, MachineTag, Smartphone, Smartwatch, EnvSensor }
public enum TagType        { Personnel, Machine }
public enum CheckInStatus  { Unchecked, CheckedIn, CheckedOut }
public enum AlertStatus    { Normal, NoMovement, NoSignal, RestrictedZone, LowBattery, CriticalVitals }
public enum AssetState     { Active, Offline, Maintenance, Decommissioned }
public enum UserRole       { Admin, SecurityOperator, Viewer }

public struct TrackerData
{
    // Identity
    public string  hardwareId;
    public string  assignedName;
    public TagType tagType;
    public DeviceCategory category;
    public int     iconIndex;           // Sprite atlas index
    public AssetState assetState;

    // Position & Movement
    public Vector3 currentPosition;     // Lerp'd visual position
    public Vector3 targetPosition;     // Kalman-filtered true position
    public Vector3 positionAtLastCheck;
    public float    totalDistanceTraveled;
    public float    lastReportTime;
    public float    lastMovementCheckTime;
    public int      levelOrZIndex;      // For 3D / multi-level

    // IoT Telemetry
    public float    batteryLevel;       // 0.0 – 1.0
    public bool     isBatteryCritical;
    public float    heartRate;          // -1 = N/A
    public float    spO2;               // -1 = N/A
    public bool     isVitalsCritical;
    public float    temperature;        // Environmental
    public float    gasPPM;             // Environmental
    public bool     isEnvCritical;

    // State
    public AlertStatus   currentAlert;
    public CheckInStatus checkStatus;
    public string       currentSectionName;
    public bool         isSelected;
    public bool         isNearby;        // Proximity flag
    public bool         hasAlertedUI;   // Debounce flag

    // History (Fixed circular buffer — zero GC)
    public const int HistorySize = 600; // 1 minute @ 10Hz
    public int historyHead;
    public HistoryPoint[] history;

    public void Initialize()
    {
        history = new HistoryPoint[HistorySize];
        historyHead = 0;
    }

    public void RecordHistory(Vector3 pos, float timestamp)
    {
        history[historyHead] = new HistoryPoint { timestamp = timestamp, position = pos };
        historyHead = (historyHead + 1) % HistorySize;
    }
}

public struct HistoryPoint
{
    public float timestamp;
    public Vector3 position;
}
```

### 3.2 WifiNodeData (Edge Node Anchor)

```csharp
public enum NodeType  { Standard, CheckIn, CheckOut }
public enum NodeStatus { Active, Calibrating, Offline }

public struct WifiNodeData
{
    public string     macAddress;
    public string     assignedName;
    public Vector3    mapPosition;        // User-dragged position in Unity units
    public NodeType   nodeType;
    public NodeStatus status;
    public float      lastHeartbeat;
    public GameObject hologramInstance;   // Visual anchor on map
}
```

### 3.3 MapSection (User-Drawn Zones)

```csharp
public struct MapSection
{
    public string      sectionName;
    public List<Vector2> polygonPoints;   // 2D polygon vertices
    public bool        isRestricted;
    public bool        isVisible;
    public string      assignedColorHex;
    public GameObject  meshRepresentation; // Holographic floor overlay
}
```

### 3.4 UserData (RBAC)

```csharp
public struct UserData
{
    public string   username;
    public string   passwordHash;         // BCrypt or Argon2 in production
    public UserRole role;
    public string   displayName;
    public DateTime lastLogin;
}
```

---

## 4. Subsystem Specifications

### 4.1 MQTT Ingestion Layer

**Broker:** EMQX (recommended for enterprise) or Mosquitto (lightweight)
**Port:** 8883 (TLS) or 1883 (local VLAN only)
**Protocol:** MQTT 5.0

| Topic | Direction | Payload Format | Purpose |
|---|---|---|---|
| `rssi/data` | Pi → Unity | `PiMAC,TagMAC,RSSI,Battery` | RSSI telemetry |
| `vitals/data` | Pi → Unity | `TagMAC,HR,SpO2,Temp` | Wearable vitals |
| `env/data` | Pi → Unity | `SensorMAC,Temp,GasPPM` | Environmental |
| `node/heartbeat` | Pi → Unity | `PiMAC,IP,Name` | Node online status |
| `node/position` | Pi → Unity | `PiMAC,X,Y` | Auto-placed nodes |
| `iot/command/downlink` | Unity → Pi | `{"cmd":"alarm","mac":"..."}` | Downlink commands |
| `system/state_changes` | Unity → All | `action,id,param...` | Multi-client sync |

**Performance Rule:** Never parse JSON in the hot path. Edge nodes send delimited strings. Unity uses `string.Split(',')` and `float.TryParse()` — no reflection, no Newtonsoft, zero allocations in the parse step.

### 4.2 Kalman Filter Module

Raw RSSI values are noisy. A simple 2D Kalman filter corrects trajectory before the data reaches `targetPosition`.

```csharp
public class KalmanFilter2D
{
    private float q;        // Process noise (sensor uncertainty)
    private float r;        // Measurement noise (environment)
    private float x;        // State estimate
    private float p;        // Estimate error covariance
    private float k;        // Kalman gain

    public KalmanFilter2D(float processNoise = 0.1f, float measurementNoise = 1.0f)
    {
        q = processNoise; r = measurementNoise;
        x = 0; p = 1; k = 0;
    }

    public Vector2 Update(Vector2 measurement)
    {
        // Prediction
        p = p + q;

        // Update
        k = p / (p + r);
        x = x + k * (measurement.x - x);
        p = (1 - k) * p;

        return new Vector2(x, measurement.y); // Return smoothed X, raw Y for demo
    }
}
```

**Integration:**
```
MQTT Message (raw RSSI) → Triangulation Math → KalmanFilter2D.Update() → targetPosition
                                                                           │
                                                                   Vector3.Lerp() ← visual smoothing only
                                                                           │
                                                                   currentPosition (what renderer uses)
                                                                           │
                                                                   historyRecord() ← records TRUE position (not lerp'd)
```

### 4.3 Rendering Pipeline

**Strategy:** Hybrid SRP Batcher + Graphics.DrawMeshInstanced

- Each unique icon/material = one SRP batch group (≤ 1ms CPU per frame for 300 objects)
- Tags are `GameObject` entities with `MeshRenderer` — not pure struct rendering
- All tags share the same URP holographic shader with per-material color/alpha overrides

**Holographic Shader (Shader Graph):**
- Fresnel rim glow (cyan default, red for alerts)
- Animated scanlines (Time node × frequency)
- Semi-transparency (alpha blend)
- Emissive boost for glow in dark environments
- Bloom post-processing via URP Volume

### 4.4 Geofence & Proximity Engine

```csharp
void EvaluateGeofences(int trackerIdx)
{
    ref var tracker = ref trackers[trackerIdx];
    if (!tracker.isActive || tracker.assetState != AssetState.Active) return;

    tracker.currentAlert = AlertStatus.Normal;

    // ── Point-in-Polygon: Section Detection ──
    Vector2 tag2D = new Vector2(tracker.currentPosition.x, tracker.currentPosition.z);
    tracker.currentSectionName = "Unmapped";

    for (int s = 0; s < mapSections.Length; s++)
    {
        if (!mapSections[s].isVisible) continue;
        if (IsPointInPolygon(tag2D, mapSections[s].polygonPoints))
        {
            tracker.currentSectionName = mapSections[s].sectionName;
            if (mapSections[s].isRestricted)
                tracker.currentAlert = AlertStatus.RestrictedZone;
            break;
        }
    }

    // ── SqrMagnitude: Restricted Zone Spheres ──
    for (int z = 0; z < zones.Length; z++)
    {
        if (zones[z].type != ZoneType.Restricted || !zones[z].isVisible) continue;
        float distSq = (tracker.currentPosition - zones[z].position).sqrMagnitude;
        if (distSq < zones[z].radius * zones[z].radius)
        {
            tracker.currentAlert = AlertStatus.RestrictedZone;
            break;
        }
    }

    // ── Proximity Check (selected tag only) ──
    tracker.isNearby = false;
    if (selectedTrackerIndex != -1 && selectedTrackerIndex != trackerIdx)
    {
        float proxDistSq = (tracker.currentPosition - trackers[selectedTrackerIndex].currentPosition).sqrMagnitude;
        tracker.isNearby = proxDistSq < 25f; // 5m radius squared
    }
}
```

### 4.5 Alert Engine

| Alert Type | Trigger Condition | Action |
|---|---|---|
| NoSignal | `Time.time - lastReportTime > noSignalTimeoutSecs` | UI notification + log |
| NoMovement | Distance < 0.5m for `noMovementCheckIntervalSecs` | UI notification |
| RestrictedZone | Point-in-polygon or sphere intersection | Red flash + audio alarm |
| LowBattery | `batteryLevel < criticalBatteryThreshold` | UI badge + email |
| CriticalVitals | `HR > 150 || HR < 40 || spO2 < 90` | Audio alarm + auto-alarm downlink |
| EnvHazard | `gasPPM > 500 \|\| temp > 60°C` | Area lockdown alert + email |
| NodeOffline | `Time.time - node.lastHeartbeat > 10s` | UI node health panel |

### 4.6 LLM Integration (Ollama)

**Architecture:** Unity HTTP client → Ollama REST API → JSON command → Unity action

```
User: "Trigger alarm on everyone with low battery in Sector 4"
         │
         ▼
Unity ──HTTP POST──► Ollama (localhost:11434)
                              │
                              ▼ (Local LLM: Llama-3 / Phi-3)
                         "{"action":"filter","filters":{"battery":"low","section":"Sector 4"}}"
                              │
                              ▼
Unity parses JSON command → applies UI filter → highlights targets
```

**Safety:** Ollama system prompt is hardcoded. LLM output must match `LlmCommand` JSON schema or it is discarded. Input is pre-sanitized (no markdown injection).

### 4.7 Database Schema (SQLite)

```sql
-- Asset Registry
CREATE TABLE trackers (
    id           INTEGER PRIMARY KEY,
    hardware_id  TEXT UNIQUE NOT NULL,
    assigned_name TEXT,
    tag_type     INTEGER,
    category     INTEGER,
    icon_index   INTEGER,
    asset_state  INTEGER DEFAULT 0
);

-- Calibration Nodes
CREATE TABLE wifi_nodes (
    id          INTEGER PRIMARY KEY,
    mac_address TEXT UNIQUE NOT NULL,
    name        TEXT,
    pos_x       REAL,
    pos_y       REAL,
    pos_z       REAL,
    node_type   INTEGER
);

-- Map Sections
CREATE TABLE map_sections (
    id             INTEGER PRIMARY KEY,
    name           TEXT,
    polygon_json   TEXT,  -- JSON array of Vector2
    is_restricted  INTEGER,
    color_hex      TEXT
);

-- History (long-term archive)
CREATE TABLE tracking_history (
    id          INTEGER PRIMARY KEY,
    tracker_id  INTEGER,
    timestamp   REAL,
    pos_x       REAL,
    pos_y       REAL,
    pos_z       REAL,
    FOREIGN KEY(tracker_id) REFERENCES trackers(id)
);

-- Users & RBAC
CREATE TABLE users (
    id           INTEGER PRIMARY KEY,
    username     TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role         INTEGER,
    display_name TEXT
);

-- Alert Log
CREATE TABLE alert_log (
    id          INTEGER PRIMARY KEY,
    tracker_id  INTEGER,
    alert_type  INTEGER,
    timestamp   REAL,
    acknowledged INTEGER DEFAULT 0
);
```

---

## 5. Coordinate System

```
Real-World          →  Unity Engine Units          →  Visual
50m × 30m room      →  1 meter = 100 units         →  5000 × 3000 px sprite
(0,0) bottom-left   →  Origin at sprite center     →  Centered in scene
Z = floor index     →  Y offset per level (5 units/level)  →  3D tunnel extrusion
```

**Calibration Points:** Users place ≥2 known reference points on the CAD image and enter real-world coordinates. A transformation matrix corrects for skew, rotation, and scale.

---

## 6. Security Architecture

### 6.1 Network Security

| Layer | Mechanism |
|---|---|
| Transport | MQTT over TLS 1.3 (port 8883) |
| Authentication | MQTT username + password |
| Authorization | ACLs: Pis can only publish to `rssi/`, `vitals/`, `env/`, `node/`. Unity can only publish to `iot/command/`, `system/state_changes/`. |
| VLAN | IoT nodes on isolated VLAN (e.g., `10.50.10.0/24`). Command PC has trunk port access. |
| Firewall | Broker only accepts connections from VLAN subnet |

### 6.2 Application Security

- **Authentication:** BCrypt-hashed passwords stored in SQLite. JWT tokens issued on login (1h expiry).
- **RBAC Enforcement:** Every sensitive UI action calls `SecurityManager.HasPermission(requiredRole)` before execution.
- **LLM Sandboxing:** Strict system prompt + JSON schema validation on output.
- **Input Sanitization:** All MQTT payloads validated against expected format before processing.

---

## 7. Multi-Client State Synchronization

When one operator drags a WiFi node, all connected Unity clients must update instantly:

```
Unity Client A drags Node_01 → Publish: "node_moved,Node_01,15.2,10.5" → system/state_changes
                                                              │
                                                              ▼
MQTT Broker ──► Unity Client B ──► Parse topic ──► Update nodes[idx].mapPosition
                                                              │
                                                              ▼
                                                     Update hologramInstance.transform.position
```

This ensures all operators see a consistent, live-updated map.

---

## 8. View Modes

### 8.1 2D Mode (Floor Plan)
- **Camera:** Orthographic, looking straight down (-Z axis)
- **CAD Image:** High-res PNG as background sprite
- **Z-axis:** Used for level filtering dropdown (e.g., "Floor 2")
- **3D Objects:** Flat discs for tags, 2D polygons for sections

### 8.2 3D Mode (Tunnels / Multi-Level)
- **Camera:** Perspective, full orbital control (azimuth + elevation)
- **CAD Map:** Extruded walls (ProBuilder or imported FBX) at Y offsets per level
- **Tags:** 3D spheres at actual Y/Z coordinates
- **Use Case:** Underground tunnels, mine shafts, multi-story parking

---

## 9. Performance Budget

| Metric | Target | Mechanism |
|---|---|---|
| Frame Rate | ≥60 FPS | SRP Batching + flat struct arrays |
| Frame Time | ≤16ms | No GC allocations in hot path |
| Tracker Update | O(n×m) ≤0.1ms | SqrMagnitude (no sqrt) |
| MQTT Parse | ≤0.01ms per msg | Delimited string, not JSON |
| Memory (Trackers) | ~50MB | Fixed struct arrays, no heap |
| Memory (History) | ~100MB | Fixed circular buffers |
| Draw Calls | ≤10 | SRP Batching groups |
| GPU Instancing | 1 draw call | All 300 dots in one call |

---

## 10. Directory Structure

```
HOLO-RTLS/
├── Architecture/
│   └── architecture.md
├── Docs/
│   ├── user-manual.md
│   ├── implementation-manual.md
│   ├── roadmap.md
│   └── requirements.md
├── Diagrams/
│   └── diagrams.md
├── Assets/
│   ├── Scripts/
│   │   ├── Core/
│   │   │   ├── RTLSKernel.cs          # Main manager, DOD arrays
│   │   │   ├── KalmanFilter2D.cs      # Mathematical smoothing
│   │   │   │   ├── Ingestion/
│   │   │   │   ├── MQTTClient.cs      # MQTTnet integration
│   │   │   │   └── MessageDispatcher.cs
│   │   │   ├── Rendering/
│   │   │   │   ├── HolographicOrbitCamera.cs
│   │   │   │   ├── TrackerEntity.cs   # Per-tag visual controller
│   │   │   │   └── ProximityLineRenderer.cs
│   │   │   ├── Alerts/
│   │   │   │   ├── AlertEngine.cs
│   │   │   │   ├── GeofenceEngine.cs
│   │   │   │   └── DownlinkCommander.cs
│   │   │   ├── Persistence/
│   │   │   │   ├── DatabaseManager.cs
│   │   │   │   └── ConfigManager.cs
│   │   │   ├── AI/
│   │   │   │   └── LocalLLMBridge.cs
│   │   │   ├── Security/
│   │   │   │   ├── SecurityManager.cs
│   │   │   │   └── JWTManager.cs
│   │   │   ├── Reporting/
│   │   │   │   ├── ReportEngine.cs
│   │   │   │   └── HistoryPlaybackController.cs
│   │   │   └── Editor/
│   │   │       ├── NodeDragController.cs
│   │   │       ├── PolygonDrawTool.cs
│   │   │       └── MapCalibrationTool.cs
│   │   ├── Data/
│   │   │   ├── DataModels.cs
│   │   │   └── NetworkConfig.cs
│   │   └── Utilities/
│   │       ├── UnityMainThreadDispatcher.cs
│   │       └── CircularBuffer.cs
│   ├── Shaders/
│   │   ├── HolographicShader.shadergraph
│   │   ├── AlertPulseShader.shadergraph
│   │   └── HeatmapComputeShader.compute
│   ├── Prefabs/
│   │   ├── TrackingDot.prefab
│   │   ├── WifiNode.prefab
│   │   ├── ZoneRing.prefab
│   │   └── SectionPlane.prefab
│   └── Materials/
│       ├── HolographicCyan.mat
│       ├── HolographicRed.mat
│       └── HolographicBlue.mat
├── Backend/
│   ├── edge-node/
│   │   ├── scanner.py          # BLE/WiFi scanning
│   │   ├── triangulator.py     # RSSI triangulation
│   │   └── mqtt_publisher.py   # MQTT uplink
│   └── mqtt-broker/
│       └── mosquitto.conf
├── Database/
│   └── schema.sql
└── HOLO-RTLS.sln
```

---

## 11. Glossary

| Term | Definition |
|---|---|
| **DOD** | Data-Oriented Design — structuring data in flat arrays for cache efficiency |
| **RTLS** | Real-Time Location System — indoor positioning infrastructure |
| **IPS** | Indoor Positioning System — generic term for indoor geo-location |
| **UWB** | Ultra-Wideband — radio technology for centimeter-level positioning |
| **RSSI** | Received Signal Strength Indicator — signal power measurement |
| **Geofence** | Virtual perimeter around a real-world geographic area |
| **SRP Batcher** | Scriptable Render Pipeline Batcher — Unity GPU batching system |
| **Kalman Filter** | Mathematical algorithm for estimating true position from noisy measurements |
| **Triangulation** | Locating a point using distances from multiple known anchors |
| **Downlink** | Bi-directional command path from server/app to end device |
| **RBAC** | Role-Based Access Control — permission model |
| **JWT** | JSON Web Token — stateless authentication credential |
| **Ollama** | Local LLM runtime with REST API |
| **EMQX / Mosquitto** | MQTT message brokers |

---

*Last updated: 2026-07-17 | Architecture v1.0*
