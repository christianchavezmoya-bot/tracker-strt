# HOLO-RTLS — System Architecture Diagrams

> Copy and paste any diagram block into [Mermaid Live Editor](https://mermaid.live) to render.
> All diagrams use Mermaid 10.x syntax.

---

## 1. High-Level System Architecture

```mermaid
flowchart TB
    subgraph PHYSICAL["🏭 Physical Layer"]
        TAG1["👤 Personnel Badge"]
        WATCH["⌚ Smartwatch"]
        PHONE["📱 Smartphone"]
        MACHINE["🔧 Machine Tag"]
        SENSOR["🌡️ Environmental Sensor"]
        UWB["📡 UWB Anchor"]
    end

    subgraph EDGE["⚡ Edge Compute Layer"]
        PI1["🍇 Pi Node 01"]
        PI2["🍇 Pi Node 02"]
        PI3["🍇 Pi Node N"]
        PI1 <--> |"BLE/WiFi"| PHYSICAL
        PI2 <--> |"BLE/WiFi"| PHYSICAL
        PI3 <--> |"BLE/WiFi"| PHYSICAL
    end

    subgraph TRANSPORT["🌐 Transport Layer"]
        BROKER["📡 MQTT Broker\n(Mosquitto / EMQX)\nTLS + ACL + VLAN"]
    end

    subgraph APP["🖥️ Application Layer — Unity 3D URP"]
        subgraph INGEST["Data Ingestion"]
            MQTT_CLIENT["MQTTnet Client"]
            PARSE["CSV Parser\n(Zero GC)"]
            DISPATCH["Thread Dispatcher"]
        end

        subgraph CORE["RTLS Core Engine"]
            KALMAN["Kalman Filter\n2D"]
            TRACK["Tracker Array\n[DOD Struct]"]
            ZONE["Geofence Engine\nSqrMagnitude"]
            ALERT["Alert Engine"]
            STATS["Statistics Engine"]
        end

        subgraph RENDER["Holographic Rendering"]
            CAM["Orbit Camera\n360°"]
            SHADER["URP Shader Graph\nFresnel + Scanlines"]
            BATCH["SRP Batcher\n≤10 Draw Calls"]
            PROX["Proximity Lines"]
            HEAT["Heatmap Layer"]
        end

        subgraph PERSIST["Persistence"]
            SQLITE["SQLite DB"]
            CFG["Config Manager"]
        end

        subgraph ENTERPRISE["Enterprise Features"]
            LLM["Local LLM Bridge\nOllama HTTP"]
            SMTP["Report Engine\nCSV + SMTP"]
            RBAC["Security Manager\nJWT + RBAC"]
            SYNC["Multi-Client Sync"]
        end
    end

    PHYSICAL --> |"BLE/WiFi"| EDGE
    EDGE --> |"MQTT\nrssi/data"| BROKER
    BROKER --> |"MQTT Subscribe"| MQTT_CLIENT
    MQTT_CLIENT --> PARSE
    PARSE --> DISPATCH
    DISPATCH --> KALMAN
    KALMAN --> TRACK
    TRACK --> ZONE
    ZONE --> ALERT
    TRACK --> STATS
    STATS --> SMTP
    MQTT_CLIENT --> SYNC
    SYNC --> |"Publish\nsystem/state"| BROKER
    LLM -.-> |"Filter Commands"| TRACK
    RBAC -.-> |"Permission Check"| ALERT
    TRACK --> RENDER
    CAM --> SHADER
    SHADER --> BATCH
    SQLITE --> CFG
    CFG -.-> |"Load State"| TRACK
```

---

## 2. Data Flow — Message Pipeline

```mermaid
sequenceDiagram
    participant TAG as 👤 Personnel Tag
    participant PI as 🍇 Pi Node
    participant BRK as 📡 MQTT Broker
    participant UNITY as Unity App
    participant KALMAN as 🎯 Kalman Filter
    participant DB as 🗄️ SQLite

    Note over TAG: BLE Advertisement<br/>MAC + RSSI + Battery

    TAG->>PI: BLE Scan (RSSI -72 dBm)
    Note over PI: scanner.py<br/>Parse MAC + RSSI

    PI->>BRK: Publish "Pi01_MAC,Tag_MAC,-72,98"
    Note over BRK: Topic: rssi/data<br/>QoS: ExactlyOnce

    BRK->>UNITY: MQTT Message Received
    Note over UNITY: Runs on MQTT Thread<br/>⚠️ No Unity API here

    UNITY->>UNITY: Parse CSV string<br/>nodeMac, tagMac, rssi, bat

    UNITY->>KALMAN: Push raw X, Y
    Note over KALMAN: Prediction + Update<br/>Returns smoothed position

    KALMAN->>UNITY: Smoothed X, Y

    UNITY->>UNITY: Update TrackerData[i]<br/>targetPosition = (X, Y, Z)

    Note over UNITY: UnityUpdate() Loop<br/>(16ms frame budget)

    UNITY->>UNITY: Lerp(current → target)<br/>RecordHistory(KalmanOutput)<br/>Check Geofences<br/>Evaluate Alerts<br/>Update SRP Batcher

    UNITY->>DB: Async Write (background thread)
    Note over DB: Node positions<br/>Tag metadata<br/>Alert log<br/>User changes

    UNITY->>BRK: Publish "node_moved,Node_01,15.2,10.5"
    Note over BRK: Topic: system/state_changes<br/>For multi-client sync

    BRK->>UNITY: Multi-client receives<br/>Updates hologramInstance.transform
```

---

## 3. Kalman Filter — Mathematical Flow

```mermaid
flowchart LR
    subgraph INPUT["Raw RSSI Measurement"]
        A["RSSI₁\n-72 dBm"]
        B["RSSI₂\n-68 dBm"]
        C["RSSI₃\n-75 dBm"]
    end

    subgraph TRI["Triangulation\n(Weighted Centroid)"]
        A --> T1["Dist₁\n= 2.1m"]
        B --> T2["Dist₂\n= 1.8m"]
        C --> T3["Dist₃\n= 3.2m"]
        T1 --> W1["W₁ = 1/2.1²\n= 0.227"]
        T2 --> W2["W₂ = 1/1.8²\n= 0.309"]
        T3 --> W3["W₃ = 1/3.2²\n= 0.098"]
        W1 --> SUM["Weighted Sum\nX = 2×0.227 + 4×0.309 + 1×0.098\nY = 3×0.227 + 5×0.309 + 2×0.098"]
    end

    subgraph KF["2D Kalman Filter"]
        SUM --> PRED["Prediction\nP = P + Q\nx = x (no change)"]
        PRED --> UP["Update\nK = P / (P + R)\nx = x + K(z - x)\nP = (1 - K)P"]
        PRED -.->|"error"| UP
    end

    subgraph OUTPUT["Filtered Position"]
        UP --> SMOOTH["Smoothed Position\n(12.4, 3.8)"]
        SMOOTH --> REPORT["targetPosition\n← Kalman Output"]
        SMOOTH --> VISUAL["currentPosition\n← Lerp(visual)"]
        SMOOTH --> HISTORY["RecordHistory()\n📍 Kalman Output (not Lerp)"]
    end

    style KF fill:#1a3a5c,color:#00e5ff,stroke:#00e5ff
    style INPUT fill:#1a2a1a,color:#69ff47,stroke:#69ff47
    style OUTPUT fill:#1a2a1a,color:#69ff47,stroke:#69ff47
```

---

## 4. Geofence Engine — Collision Detection

```mermaid
flowchart TD
    START["For each tracker i (0 → 299)"] --> ACTIVE{"IsActive?"}
    ACTIVE -->|"No"| SKIP["Continue"]
    ACTIVE -->|"Yes"| LEVEL{"Level matches\nfilter?"}
    LEVEL -->|"No"| SKIP2["Continue"]
    LEVEL -->|"Yes"| RESET["alertStatus = Normal"]

    RESET --> GEO1{"Is Point in\nPolygon?\n(Section Check)"}
    GEO1 -->|"Inside Section"| SEC["currentSection\n= section.name"]
    SEC -->|"isRestricted?"| REST["alertStatus =\nRestrictedZone"]
    REST -->|"Yes"| TRIG1["🔴 TRIGGER ALERT\n🔊 Audio Alarm"]
    GEO1 -->|"Outside"| OUTSIDE["currentSection\n= Unmapped"]

    OUTSIDE --> GEO2{"Inside Restricted\nSphere?\nSqrMagnitude < r²"}
    GEO2 -->|"Inside"| REST2["alertStatus =\nRestrictedZone"]
    REST2 --> TRIG1
    GEO2 -->|"Outside"| PROX{"Is tag\nselected?"}

    TRIG1 --> PROX

    PROX -->|"No tag selected"| NEXT["Next tracker\ni++"]
    PROX -->|"Tag j selected"| DIST["distSq = |pos_i - pos_j|²"]
    DIST -->|"distSq < 25m²"| NEAR["isNearby = true\nDraw proximity line"]
    DIST -->|"distSq ≥ 25m²"| FAR["isNearby = false"]
    NEAR --> NEXT
    FAR --> NEXT

    NEXT --> CHECK{"i < MAX?"}
    CHECK -->|"Yes"| LEVEL
    CHECK -->|"No"| RENDER["DrawMeshInstanced()\nSRP Batcher\nSingle draw call"]

    style TRIG1 fill:#3d0000,color:#ff4444,stroke:#ff4444
    style RENDER fill:#0a2a1a,color:#69ff47,stroke:#69ff47
```

---

## 5. Multi-Client State Synchronization

```mermaid
sequenceDiagram
    participant PC_A as 🖥️ Operator A<br/>(Admin)
    participant PC_B as 🖥️ Operator B<br/>(Security)
    participant PC_C as 🖥️ Operator C<br/>(Viewer)
    participant BRK as 📡 MQTT Broker

    Note over PC_A,PC_C: All clients subscribe to system/state_changes

    PC_A->>PC_A: User drags Node_01 to new position
    PC_A->>PC_A: Update local hologramInstance.transform
    PC_A->>PC_A: Update nodes[i].mapPosition in struct
    PC_A->>BRK: Publish "node_moved,Node_01,15.2,10.5"
    Note over BRK: Topic: system/state_changes<br/>FromClientID: PC_A

    BRK-->>PC_B: Deliver message
    BRK-->>PC_C: Deliver message
    BRK-->>PC_A: Deliver to self (echo)

    rect rgb(20, 40, 20)
        Note over PC_B: PC B receives node_moved
        PC_B->>PC_B: Parse: Node_01, 15.2, 10.5
        PC_B->>PC_B: Find nodes["Node_01"]
        PC_B->>PC_B: Update nodes[i].mapPosition
        PC_B->>PC_B: Update hologramInstance.transform
        Note over PC_B: ✅ Map instantly synced
    end

    rect rgb(20, 40, 20)
        Note over PC_C: PC C receives node_moved
        PC_C->>PC_C: Parse: Node_01, 15.2, 10.5
        PC_C->>PC_C: Update nodes[i].mapPosition
        PC_C->>PC_C: Update hologramInstance.transform
        Note over PC_C: ✅ Map instantly synced
    end
```

---

## 6. LLM Integration Flow

```mermaid
flowchart TB
    START["👤 User types in AI chat:\n'Show all low battery in Sector 4'"] --> SANITIZE

    subgraph SANITIZE["Input Sanitization"]
        S1["Strip code blocks\n``` → remove"]
        S2["Strip markdown links\n[text](url) → remove"]
        S3["Strip SQL injection chars\n'; DROP TABLE → sanitize"]
        S4["Strip prompt injection\n'Ignore previous' → block"]
    end
    SANITIZE --> VALID{"Sanitized?"}
    VALID -->|"Yes"| HTTP
    VALID -->|"No"| REJECT["❌ Discard input\nShow: 'Input not accepted'"]

    HTTP["Unity HTTP Client\nPOST localhost:11434/api/generate"]

    subgraph OLLAMA["Local Ollama Runtime"]
        O1["Load model into VRAM\n(Llama-3 8B or Phi-3)"]
        O2["System Prompt:\n'You are RTLS assistant.\nOutput JSON command only...'"]
        O3["User prompt injected\n'Filter low battery in Sector 4'"]
        O4["Model inference\n(~200ms on RTX 4070)"]
        O5["Raw response:\n{\"action\":\"filter\",\n\"battery\":\"low\",\n\"section\":\"Sector 4\"}"]
    end

    HTTP --> OLLAMA

    subgraph VALIDATE["Output Validation"]
        V1["Parse JSON\n(JsonUtility)"]
        V2{"Matches\nLlmCommand\nschema?"}
        V3["✅ Valid\nExtract action,\nfilters, params"]
        V4["❌ Invalid\nDiscard response\nLog to audit"]
    end

    O5 --> VALIDATE
    V1 --> V2
    V2 -->|"Match"| V3
    V2 -->|"No match"| V4

    V3 --> EXEC["Execute filtered command\nApply UI highlight\nZoom map to results"]
    V4 --> ERROR["Show: 'I couldn't\nunderstand that. Try:\nShow tags with...'"]
    EXEC --> DISPLAY["🤖 AI responds:\n'Filtered 12 tags with\nlow battery in Sector 4.\nMap has been updated.'"]

    style SANITIZE fill:#2a1a00,color:#ffb300,stroke:#ffb300
    style VALIDATE fill:#1a2a3a,color:#00e5ff,stroke:#00e5ff
    style OLLAMA fill:#1a2a1a,color:#69ff47,stroke:#69ff47
    style REJECT fill:#3d0000,color:#ff4444,stroke:#ff4444
```

---

## 7. RBAC — Role Permission Matrix

```mermaid
flowchart LR
    subgraph ROLES["User Roles"]
        ADMIN["👑 Admin\nFull Access"]
        SECOP["🛡️ Security Operator\nOperational Access"]
        VIEWER["👁️ Viewer\nRead-Only"]
    end

    subgraph PERMISSIONS["Permissions"]
        VIEW["View Map"]
        HIST["View History"]
        REPT["View Reports"]
        ALRM["Trigger Alarm"]
        MSG["Send Message"]
        TAG_ED["Edit Tag Names"]
        ZONE_CR["Create Zones"]
        NODE_ED["Edit Nodes"]
        THRESH["Change Thresholds"]
        USER_CR["Manage Users"]
        SYST["System Settings"]
        ZONE_DEL["Delete Zones"]
    end

    ROLES --> PERMISSIONS

    ADMIN -->|"✅ ✅ ✅ ✅ ✅ ✅ ✅ ✅ ✅ ✅ ✅ ✅ ✅"| PERMISSIONS
    SECOP -->|"✅ ✅ ✅ ✅ ❌ ❌ ❌ ❌ ❌ ❌ ❌ ❌ ❌"| PERMISSIONS
    VIEWER -->|"✅ ✅ ✅ ❌ ❌ ❌ ❌ ❌ ❌ ❌ ❌ ❌ ❌"| PERMISSIONS

    style ADMIN fill:#1a3a1a,color:#69ff47,stroke:#69ff47
    style SECOP fill:#1a2a1a,color:#00e5ff,stroke:#00e5ff
    style VIEWER fill:#1a1a1a,color:#888888,stroke:#888888
```

---

## 8. Alert State Machine

```mermaid
stateDiagram-v2
    [*] --> Normal : Tag active, reporting

    Normal --> NoSignal : No MQTT message<br/>for >timeoutSecs
    Normal --> NoMovement : Distance moved<br/>< threshold for<br/>>checkIntervalSecs
    Normal --> LowBattery : batteryLevel<br/>< threshold
    Normal --> CriticalVitals : HR>150 or<br/>HR<40 or SpO2<90
    Normal --> RestrictedZone : Entered restricted<br/>polygon or sphere
    Normal --> EnvHazard : gasPPM>threshold<br/>or temp>threshold
    Normal --> Offline : Asset state set<br/>to Decommissioned

    NoSignal --> Normal : Message received
    NoSignal --> [*] : Tag permanently<br/>decommissioned

    NoMovement --> Normal : Movement detected
    NoMovement --> CriticalVitals : Time extended<br/>without movement<br/>(possible man-down)

    LowBattery --> Normal : Battery recharged<br/>or replaced

    CriticalVitals --> Normal : Vitals return<br/>to normal range
    CriticalVitals --> NoSignal : Device dies

    RestrictedZone --> Normal : Tag exits zone
    RestrictedZone --> Escalated : Tag remains<br/>in zone > 60s

    EnvHazard --> Normal : Environment clears
    EnvHazard --> Escalated : Hazard persists<br/>> threshold duration

    Escalated --> Normal : Resolved
    Escalated --> [*] : Manual override<br/>by Admin

    Offline --> Active : Tag reactivated<br/>by Admin

    note right of Normal : ✅ Green dot
    note right of NoSignal : 🔴 Red dot + grayed
    note right of NoMovement : 🟡 Yellow pulsing
    note right of CriticalVitals : 🔴 Red + alarm +<br/>auto-downlink alarm
    note right of RestrictedZone : 🔴 Red dot +<br/>zone flashes red
    note right of Escalated : 🚨 Full audio alarm +<br/>alert logged to admin
```

---

## 9. Database Entity Relationship

```mermaid
erDiagram
    TRACKERS {
        int id PK
        string hardware_id UK
        string assigned_name
        int tag_type
        int category
        int icon_index
        int asset_state
    }

    WIFI_NODES {
        int id PK
        string mac_address UK
        string name
        float pos_x
        float pos_y
        float pos_z
        int node_type
    }

    MAP_SECTIONS {
        int id PK
        string name
        string polygon_json
        bool is_restricted
        string color_hex
    }

    TRACKING_HISTORY {
        int id PK
        int tracker_id FK
        float timestamp
        float pos_x
        float pos_y
        float pos_z
    }

    USERS {
        int id PK
        string username UK
        string password_hash
        int role
        string display_name
    }

    ALERT_LOG {
        int id PK
        int tracker_id FK
        int alert_type
        float timestamp
        bool acknowledged
    }

    TRACKERS ||--o{ TRACKING_HISTORY : "has"
    TRACKERS ||--o{ ALERT_LOG : "triggers"
    TRACKING_HISTORY ||--|| TRACKERS : "belongs to"
    ALERT_LOG ||--|| TRACKERS : "belongs to"
```

---

## 10. 2D vs 3D View Architecture

```mermaid
flowchart TB
    subgraph CAMERA_SETUP["Camera System"]
        ORBIT["Orbit Camera Controller\nHolographicOrbitCamera.cs"]
        ORBIT --> ORTHO["Orthographic Camera\n2D Floor Plan Mode"]
        ORBIT --> PERSP["Perspective Camera\n3D Tunnel Mode"]
    end

    subgraph 2D_MODE["2D Mode (Floor Plan)"]
        CAD_2D["CAD PNG\nAs Sprite Background"]
        LEVEL_FILTER["Level Dropdown\n(e.g., Floor 2)"]
        DOTS_2D["Tracking Dots\nRendered at Z=0"]
        POLY_2D["Section Polygons\nFlat 2D overlay"]
        ZONES_2D["Zone Rings\nFlat ring meshes"]
    end

    subgraph 3D_MODE["3D Mode (Tunnels / Multi-Level)"]
        CAD_3D["CAD → 3D Extrusion\n(ProBuilder walls)"]
        LEVEL_OFFSET["Y = Level × 5 units\n(Floor 1: Y=0, Floor 2: Y=5)"]
        DOTS_3D["Tracking Dots\nAt actual X,Y,Z position"]
        TUNNEL_MESH["Tunnel FBX Mesh\nDark walls with\nholographic shader"]
    end

    ORBIT --> |"is3DMode = false"| ORTHO
    ORBIT --> |"is3DMode = true"| PERSP

    ORTHO --> CAD_2D
    ORTHO --> DOTS_2D
    CAD_2D --> POLY_2D
    CAD_2D --> ZONES_2D
    CAD_2D --> LEVEL_FILTER

    PERSP --> CAD_3D
    CAD_3D --> LEVEL_OFFSET
    LEVEL_OFFSET --> DOTS_3D
    CAD_3D --> TUNNEL_MESH

    style ORTHO fill:#0a1a2a,color:#00e5ff,stroke:#00e5ff
    style PERSP fill:#0a2a1a,color:#69ff47,stroke:#69ff47
    style CAMERA_SETUP fill:#1a1a2a,color:#ffffff,stroke:#ffffff
```

---

## 11. History Circular Buffer

```mermaid
flowchart LR
    subgraph BUFFER["Fixed Circular Buffer\n[HistorySize = 600]"]
        direction TB
        H0["index 0\n(pos, t=0.0s)"]
        H1["index 1\n(pos, t=0.1s)"]
        H2["index 2\n(pos, t=0.2s)"]
        H299["index 299\n(pos, t=29.9s)"]
        H300["index 300\n(pos, t=30.0s) ← wrap!"]

        H0 --> H1 --> H2 --> H299 --> H300

        H300 -.->|"head = (head+1) % 600"| H0
    end

    subgraph OPERATIONS["Buffer Operations"]
        WRITE["On each RSSI update:\nhistory[head] = {position, timestamp}\nhead = (head + 1) % HistorySize"]
        READ["Read from head backwards\nfor playback: (head - 1, head - 2, ...) % HistorySize"]
        CLEAR["On app restart: reset head=0,\nall entries valid=false"]
    end

    OPERATIONS --> BUFFER

    style BUFFER fill:#1a2a1a,color:#69ff47,stroke:#69ff47
    style OPERATIONS fill:#1a1a2a,color:#00e5ff,stroke:#00e5ff
```

---

## 12. Network Topology — VLAN Isolation

```mermaid
flowchart TB
    subgraph CORP["🏢 Corporate Network (VLAN 1)\n10.0.1.0/24"]
        PC1["Admin Workstation"]
        PC2["Security Operator PC"]
        SERVER["File / AD Server"]
    end

    subgraph IOT["📡 IoT VLAN (VLAN 50)\n10.50.10.0/24"]
        PI1["🍇 Pi Node 01\n10.50.10.11"]
        PI2["🍇 Pi Node 02\n10.50.10.12"]
        PI3["🍇 Pi Node 03\n10.50.10.13"]
        PI_N["🍇 Pi Node N\n10.50.10.1N"]
        SWITCH["🔌 Managed PoE Switch\n(VLAN trunk)"]
    end

    subgraph RTLS_SERVER["RTLS Server (VLAN 50)\n10.50.10.5"]
        BROKER["📡 MQTT Broker\nMosquitto / EMQX\nPort 1883 / 8883"]
        NTP["⏰ NTP Server\nFacility time sync"]
    end

    subgraph COMMAND_PC["🖥️ Command PC\n(Trunk port)"]
        UNITY["Unity RTLS App\nHOLO-RTLS.exe"]
        OLLAMA["🤖 Ollama\nlocalhost:11434"]
        SQLITE["🗄️ SQLite DB\nLocal storage"]
    end

    PI1 --> SWITCH
    PI2 --> SWITCH
    PI3 --> SWITCH
    PI_N --> SWITCH
    SWITCH --> RTLS_SERVER
    RTLS_SERVER --> BROKER
    SWITCH -.->|"Trunk (tagged VLANs)"| COMMAND_PC

    CORP -->|"Management access\n(SSH/HTTPS)"| SWITCH
    CORP -.->|"MQTT client\nfor testing"| BROKER

    BROKER -->|"Subscribe\nrssi/data"| UNITY
    UNITY -->|"Publish\niot/command"| BROKER
    UNITY --> OLLAMA
    UNITY --> SQLITE

    style IOT fill:#1a0a2a,color:#bb86fc,stroke:#bb86fc
    style RTLS_SERVER fill:#1a0a2a,color:#bb86fc,stroke:#bb86fc
    style COMMAND_PC fill:#1a2a1a,color:#69ff47,stroke:#69ff47
```

---

## 13. Sprint / Phase Timeline (Gantt)

```mermaid
gantt
    title HOLO-RTLS Development Roadmap — 12 Weeks
    dateFormat  YYYY-MM-DD

    section Phase 0
    Pre-Dev Setup                    :done, p0_1, 2026-07-20, 7d
    Hardware Procurement             :done, p0_2, 2026-07-20, 14d

    section Phase 1
    Week 1: DOD Core + Rendering     :active, p1_1, 2026-07-27, 7d
    Week 2: Coord Mapping + 2D/3D     :p1_2, 2026-08-03, 7d

    section Phase 2
    Week 3: MQTT + Kalman             :p2_1, 2026-08-10, 7d
    Week 4: SQLite + Node Calib      :p2_2, 2026-08-17, 7d

    section Phase 3
    Week 5: Geofencing + Alerts       :p3_1, 2026-08-24, 7d
    Week 6: Downlink + Proximity      :p3_2, 2026-08-31, 7d

    section Phase 4
    Week 7: Enterprise UI             :p4_1, 2026-09-07, 7d
    Week 8: LLM + RBAC                :p4_2, 2026-09-14, 7d

    section Phase 5
    Week 9: History + Heatmaps        :p5_1, 2026-09-21, 7d
    Week 10: Reports + Email          :p5_2, 2026-09-28, 7d

    section Phase 6
    Week 11: Load Testing             :p6_1, 2026-10-05, 7d
    Week 12: Release + Docs           :p6_2, 2026-10-12, 7d

    section Milestones
    M1: Foundation                    :milestone, m1, 2026-08-10, 0d
    M2: Networked                     :milestone, m2, 2026-08-24, 0d
    M3: Intelligent                   :milestone, m3, 2026-09-07, 0d
    M4: Command Center                :milestone, m4, 2026-09-21, 0d
    M5: Analytics                     :milestone, m5, 2026-10-05, 0d
    M6: Production                     :milestone, m6, 2026-10-19, 0d
```

---

*Diagrams v1.0 — HOLO-RTLS — 2026-07-17*
*Render with Mermaid Live Editor: https://mermaid.live*
