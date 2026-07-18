# HOLO-RTLS — Requirements Specification
## Parts, Software & Feature Registry

---

## 1. Hardware Requirements

### 1.1 Command PC (Minimum)

| Component | Minimum | Recommended | Justification |
|---|---|---|---|
| **CPU** | Intel i7-10th / AMD Ryzen 7 3700X | Intel i9-14th / AMD Ryzen 9 7900X | High single-thread performance for Unity game loop |
| **GPU** | NVIDIA RTX 3060 8GB | NVIDIA RTX 4070 Ti Super 16GB | URP rendering + local LLM VRAM |
| **RAM** | 32 GB DDR4 | 64 GB DDR5 | 300 device buffers + SQLite + Ollama in RAM |
| **Storage** | 512 GB NVMe SSD | 2 TB NVMe SSD | Fast scene loads, SQLite WAL, LLM model storage |
| **Network** | 1 Gbps Ethernet | 2.5 Gbps Ethernet | MQTT high-frequency telemetry ingestion |
| **OS** | Windows 11 Pro | Windows 11 Pro | Vulkan/DX12 URP compatibility |
| **Display** | 1920×1080 | 3840×2160 (4K Touch) | Holographic UI detail, touch interaction |

### 1.2 Edge Nodes (Raspberry Pi Network)

| Component | Recommended Model | Quantity | Notes |
|---|---|---|---|
| **Compute** | Raspberry Pi 5 (8GB) | 10–20 per facility | BLE 5.0 + WiFi 6 onboard |
| **Antenna** | High-gain BLE/WiFi external | 1 per Pi | Essential for RSSI accuracy |
| **Power** | PoE HAT for Pi 5 | 1 per Pi | Clean power, single cable |
| **Enclosure** | IP65 industrial box | 1 per Pi | Dust/moisture protection |
| **Storage** | 32GB SD Card (A2) | 1 per Pi | OS + scanning scripts |
| **Networking** | PoE Switch (managed, VLAN) | 1 per facility | Trunk to command PC |

### 1.3 Tracking Tags & Sensors

| Category | Device Type | Example Products | Quantity | Notes |
|---|---|---|---|---|
| **Personnel Badge** | BLE Wearable | Estimote Pro, Minew S1 | 50–200 | Panic button, LED, vibration |
| **Smartwatch** | Consumer BLE | Galaxy Watch, Apple Watch (via companion) | 20–50 | HR, SpO2 via BLE health profiles |
| **Machine Tag** | Rugged BLE Asset | Minew B8, Sensoro Alpha | 20–100 | Long battery life (5yr), IP67 |
| **Smartphone** | BYOD / Managed | Any BLE-enabled phone | Auto-detect | MAC address only, no vitals |
| **UWB Anchor** | Fixed Infrastructure | Pozyx Creator, Qorvo DecaWave | 4–8 per zone | cm-level accuracy for critical zones |
| **Gas Sensor** |固定式 BLE | Monnit B了一座, Sensirion SEN54 | 10–30 | CO, H₂S, LEL, temperature |
| **Temp/Humidity** | BLE Environmental | Sensirion STS40, Ruuvi Tag | 20–50 | Cold storage, server rooms |
| **Check-in Kiosk** | Edge Node + Display | Custom Pi + 7" touch | 2–10 | Triggers CheckIn/CheckOut status |

### 1.4 Networking Infrastructure

| Item | Specification | Purpose |
|---|---|---|
| **Managed Switch** | Cisco / Netgear / TP-Link (VLAN support) | VLAN isolation for IoT traffic |
| **MQTT Broker Server** | 4-core VM or NUC (dedicated) | Runs Mosquitto or EMQX |
| **NTP Server** | Facility time server | UTC sync for all Pis + command PC |
| **UPS** | APC Back-UPS 1500VA | Keep broker + command PC alive |

---

## 2. Software Stack

### 2.1 Unity & Development

| Software | Version | Purpose |
|---|---|---|
| **Unity Hub** | 2022.3 LTS or 2023.2+ | Project management |
| **Unity Editor** | 2022.3.f1 LTS | Primary development engine |
| **URP Template** | Built-in via Unity Hub | Rendering pipeline |
| **Visual Studio** | 2022 Community+ | C# IDE with Unity integration |
| **JetBrains Rider** | 2024.x (optional) | Alternative C# IDE |
| **NuGet for Unity** | 3.x | Package management (MQTTnet, SQLite) |
| **Git LFS** | Latest | Large CAD/mesh asset management |
| **GitHub Desktop** | Latest | Version control (optional) |

### 2.2 Backend & Networking

| Software | Version | Purpose |
|---|---|---|
| **MQTT Broker** | Mosquitto 2.x or EMQX 5.x | Message broker for telemetry |
| **Python** | 3.10+ | Edge node scanning scripts |
| **paho-mqtt** | 2.x | Python MQTT client library |
| **bluepy** | 1.3.x | BLE scanning on Raspberry Pi |
| **scapy** | 2.x | WiFi probe request analysis |
| **Node-RED** | 3.x (optional) | Intermediate data formatter |
| **Wireshark** | Latest | Network debugging |
| **MQTTX** | Latest | MQTT testing/validation |

### 2.3 Database

| Software | Version | Purpose |
|---|---|---|
| **SQLite** | 3.x (via System.Data.SQLite.Core) | Local persistence |
| **DB Browser for SQLite** | Latest | Manual DB inspection |
| **SQLite Studio** | Latest | Alternative DB GUI |

### 2.4 AI / LLM

| Software | Version | Purpose |
|---|---|---|
| **Ollama** | Latest | Local LLM runtime |
| **Llama 3** | 8B Instruct | Primary reasoning model |
| **Phi-3 Mini** | 3.8B | Lightweight fallback model |
| **LM Studio** | Latest (optional) | Alternative local LLM |

### 2.5 Reporting & Communication

| Software | Purpose |
|---|---|
| **SMTP Server** | Email delivery (corporate or Gmail App Password) |
| **wkhtmltopdf** (optional) | HTML → PDF for styled reports |
| **Excel / Google Sheets** | CSV report import |

---

## 3. Feature Registry

### 3.1 Core Tracking Features

| ID | Feature | Priority | Status | Notes |
|---|---|---|---|---|
| F-001 | 300+ simultaneous device tracking | Critical | Spec | DOD architecture required |
| F-002 | 2D floor plan view (orthographic) | Critical | Spec | CAD PNG/SVG background |
| F-003 | 3D tunnel / multi-level view | Critical | Spec | Y-offset per floor |
| F-004 | Real-time position interpolation (Lerp) | Critical | Spec | Frame-rate independent |
| F-005 | Kalman filter for mathematical smoothing | Critical | Spec | Must use filter output for reports |
| F-006 | RSSI-based triangulation | Critical | Spec | Via edge node network |
| F-007 | UWB anchor integration | High | Spec | For cm-accurate zones |
| F-008 | BLE beacon detection | High | Spec | Via Raspberry Pi nodes |
| F-009 | WiFi device detection (probe requests) | Medium | Spec | MAC address tracking |
| F-010 | Multi-level / Z-index filtering | High | Spec | 2D mode level dropdown |
| F-011 | Asset lifecycle management (Active/Offline/Maintenance/Decommissioned) | High | Spec | Prevents full arrays |

### 3.2 Visualization & Rendering

| ID | Feature | Priority | Status | Notes |
|---|---|---|---|---|
| F-101 | Holographic shader (Fresnel + scanlines) | Critical | Spec | URP Shader Graph |
| F-102 | 360° orbital camera (pan, zoom, rotate) | Critical | Spec | Right-click + scroll + middle-click |
| F-103 | GPU instancing (single draw call for 300 dots) | Critical | Spec | SRP Batcher approach |
| F-104 | Per-tag custom icons (pictures/symbols) | High | Spec | Sprite atlas + material swap |
| F-105 | Alert color states (cyan=normal, red=alert, yellow=warning) | High | Spec | Material property block |
| F-106 | Proximity lines (selected tag → nearby tags) | High | Spec | Dynamic LineRenderer |
| F-107 | Heatmap overlay (zone traffic density) | Medium | Spec | Compute shader or texture bake |
| F-108 | Zone ring visualization (POI, restricted, fuel) | High | Spec | Holographic ring meshes |
| F-109 | Section polygon visualization | High | Spec | Semi-transparent floor overlay |
| F-110 | "Follow Me" camera mode | Medium | Spec | Camera tracks selected tag |
| F-111 | Bloom post-processing | High | Spec | URP Volume + custom shader |
| F-112 | History trail rendering (LineRenderer) | High | Spec | For selected tag playback |

### 3.3 Map & Configuration

| ID | Feature | Priority | Status | Notes |
|---|---|---|---|---|
| F-201 | CAD image import (PNG/SVG → sprite) | Critical | Spec | Scale: pixels = real-world meters |
| F-202 | WiFi node drag-to-calibrate | Critical | Spec | Raycast → map collider |
| F-203 | WiFi node rename (in-app) | High | Spec | Save to SQLite |
| F-204 | WiFi node type assignment (Standard/CheckIn/CheckOut) | High | Spec | |
| F-205 | Map calibration points (skew correction matrix) | Medium | Spec | ≥2 reference points |
| F-206 | POI layer (add, edit, delete, move markers) | High | Spec | |
| F-207 | Safe zone layer (user-editable) | High | Spec | |
| F-208 | Fuel/exclusion zone layer | High | Spec | |
| F-209 | Restricted zone layer (geofence alerts) | Critical | Spec | Sphere + polygon types |
| F-210 | Section/area polygon drawing tool | Critical | Spec | Point-in-polygon detection |
| F-211 | Zone radius resizing (drag handles) | High | Spec | In 3D editor mode |
| F-212 | Layer visibility toggles (per-layer) | High | Spec | Eye icon per layer |
| F-213 | Import tunnel 3D mesh (FBX) | Medium | Spec | For 3D mode |

### 3.4 Alerts & Safety

| ID | Feature | Priority | Status | Notes |
|---|---|---|---|---|
| F-301 | No-signal alert (tag silent > X seconds) | Critical | Spec | Configurable timeout |
| F-302 | No-movement alert (stagflation / man-down) | Critical | Spec | Configurable distance + time |
| F-303 | Restricted zone entry alert | Critical | Spec | Geofence collision |
| F-304 | Low battery alert (configurable threshold) | High | Spec | Per-tag or global setting |
| F-305 | Critical vitals alert (HR / SpO2 thresholds) | High | Spec | Apple Health / BLE health profile |
| F-306 | Environmental hazard alert (gas / temp) | High | Spec | CO, H₂S, LEL thresholds |
| F-307 | WiFi node offline alert | High | Spec | Heartbeat timeout |
| F-308 | Audio alarm trigger | High | Spec | System beep / custom WAV |
| F-309 | Alert debouncing (prevent spam) | High | Spec | hasAlertedUI flag |
| F-310 | Alert acknowledgement | Medium | Spec | Mark as acknowledged |
| F-311 | Alert history log (searchable) | Medium | Spec | SQLite table |

### 3.5 Bi-Directional Control (Downlink)

| ID | Feature | Priority | Status | Notes |
|---|---|---|---|---|
| F-401 | Trigger alarm on tag (vibrate/buzzer) | Critical | Spec | MQTT → Pi → BLE write |
| F-402 | Send text message to tag/screen | High | Spec | For compatible devices |
| F-403 | Initiate call / notification | High | Spec | Via downlink command |
| F-404 | Mass alert (broadcast to all tags) | Medium | Spec | Emergency evacuation |
| F-405 | Selective alert (filtered subset) | Medium | Spec | Via LLM or manual selection |

### 3.6 Personnel & Tag Management

| ID | Feature | Priority | Status | Notes |
|---|---|---|---|---|
| F-501 | Assign name to tag | Critical | Spec | |
| F-502 | Assign type (Personnel / Machine) | Critical | Spec | |
| F-503 | Assign category (Tag / Smartphone / Sensor) | High | Spec | |
| F-504 | Assign custom icon / picture | High | Spec | |
| F-505 | Edit tag metadata (in side panel) | High | Spec | |
| F-506 | Decommission / reactivate tag | Medium | Spec | Sets assetState |
| F-507 | Search tags by name / ID | Critical | Spec | |
| F-508 | Filter by type (Personnel / Machine / Sensor) | Critical | Spec | |
| F-509 | Filter by section / zone | High | Spec | |
| F-510 | Filter by status (Alert / Normal / Offline) | High | Spec | |
| F-511 | Sort tag list (name / battery / signal) | Medium | Spec | |
| F-512 | Bulk tag operations (assign type to multiple) | Low | Spec | Multi-select |

### 3.7 Check-In / Check-Out

| ID | Feature | Priority | Status | Notes |
|---|---|---|---|---|
| F-601 | Check-in node placement | High | Spec | NodeType.CheckIn |
| F-602 | Check-out node placement | High | Spec | NodeType.CheckOut |
| F-603 | Automatic check-in detection (2m radius) | High | Spec | SqrMagnitude check |
| F-604 | Check-in / check-out log | High | Spec | SQLite + UI panel |
| F-605 | Personnel count per section | Medium | Spec | Real-time counter |
| F-606 | Muster report (all checked-in at evacuation) | Medium | Spec | Report generation |

### 3.8 History & Playback

| ID | Feature | Priority | Status | Notes |
|---|---|---|---|---|
| F-701 | View history for selected tag | Critical | Spec | Circular buffer (1 min live) |
| F-702 | History playback slider (scrub timeline) | High | Spec | Interpolate between points |
| F-703 | Timestamp display during playback | High | Spec | |
| F-704 | Long-term history query (SQLite) | Medium | Spec | Last 24h / 7d / custom |
| F-705 | Export history to CSV | Medium | Spec | |
| F-706 | History trail visualization | High | Spec | LineRenderer with timestamps |

### 3.9 AI / Natural Language

| ID | Feature | Priority | Status | Notes |
|---|---|---|---|---|
| F-801 | Natural language tag queries | High | Spec | "Find John in Sector 4" |
| F-802 | Filter commands via LLM | High | Spec | "Show all low battery" |
| F-803 | Alert explanation via LLM | Medium | Spec | "Why is this tag red?" |
| F-804 | Report generation via LLM | Low | Spec | "Generate today's summary" |
| F-805 | LLM chat interface (GUI) | High | Spec | Bottom-left chat panel |
| F-806 | LLM offline mode graceful degradation | Medium | Spec | Show "LLM unavailable" |

### 3.10 Security & Access Control

| ID | Feature | Priority | Status | Notes |
|---|---|---|---|---|
| F-901 | User login screen | Critical | Spec | |
| F-902 | Role-based UI (hide/disable features) | Critical | Spec | Admin / Security / Viewer |
| F-903 | Password hashing (BCrypt / Argon2) | Critical | Spec | |
| F-904 | JWT session tokens | High | Spec | 1h expiry |
| F-905 | Permission check before sensitive actions | Critical | Spec | |
| F-906 | Audit log (who did what) | Medium | Spec | SQLite |
| F-907 | Multi-operator simultaneous access | High | Spec | MQTT state sync |

### 3.11 Network & Integration

| ID | Feature | Priority | Status | Notes |
|---|---|---|---|---|
| F-A01 | Configurable MQTT broker IP + port | Critical | Spec | Settings panel |
| F-A02 | VLAN credential input | Critical | Spec | |
| F-A03 | TLS / SSL toggle for MQTT | High | Spec | |
| F-A04 | Auto-reconnect on MQTT disconnect | High | Spec | Exponential backoff |
| F-A05 | Network status indicator (connected/disconnected) | High | Spec | Top-right status light |
| F-A06 | NTP time sync (all components) | Medium | Spec | UTC timestamps |
| F-A07 | Webhook output (for external systems) | Low | Spec | HTTP POST on events |

### 3.12 Reporting & Statistics

| ID | Feature | Priority | Status | Notes |
|---|---|---|---|---|
| F-B01 | Daily summary report (CSV) | High | Spec | |
| F-B02 | Tag distance traveled | High | Spec | Kalman-filtered positions |
| F-B03 | Zone dwell time (time spent in each section) | High | Spec | Requires section detection |
| F-B04 | Battery level report | Medium | Spec | |
| F-B05 | Alert frequency report | Medium | Spec | |
| F-B06 | Email report delivery (SMTP) | High | Spec | Configurable recipient list |
| F-B07 | PDF report generation (optional) | Low | Spec | wkhtmltopdf |
| F-B08 | Custom date range reports | Medium | Spec | |
| F-B09 | Real-time statistics dashboard | High | Spec | Active count, alert count, etc. |
| F-B10 | Trend charts (movement patterns) | Low | Spec | Basic line charts |

---

## 4. Non-Functional Requirements

| Category | Requirement | Target |
|---|---|---|
| **Performance** | Frame rate (2D mode) | ≥60 FPS |
| **Performance** | Frame rate (3D mode, 300 tags) | ≥60 FPS |
| **Performance** | MQTT message processing latency | <1ms per message |
| **Performance** | Memory footprint (runtime) | <500 MB |
| **Scalability** | Max tracked devices | 500 (soft), 1000 (hard ceiling) |
| **Reliability** | Uptime (app without restart) | ≥7 days |
| **Accuracy** | Triangulation accuracy (BLE RSSI) | 1–3 meters typical |
| **Accuracy** | Triangulation accuracy (UWB) | 10–30 cm |
| **Accuracy** | Kalman-filter distance error | <5% vs ground truth |
| **Security** | MQTT transport encryption | TLS 1.3 |
| **Security** | Password storage | BCrypt / Argon2 |
| **Security** | Session token expiry | ≤4 hours |
| **Usability** | First-time map calibration | ≤15 minutes |
| **Usability** | Tag onboarding | ≤2 minutes per tag |
| **Compatibility** | Minimum Windows version | Windows 10 21H2 |
| **Compatibility** | Network protocol | MQTT 5.0 |

---

## 5. CAD & Asset Specifications

| Item | Specification |
|---|---|
| **CAD Export Format** | PNG (lossless) or SVG (vector) |
| **Minimum Resolution** | 300 DPI for print-quality; 72 DPI sufficient for display |
| **Real-World Dimensions** | User-provided (e.g., 50m × 30m) |
| **Scale Factor** | Configurable (default: 100 pixels = 1 meter) |
| **Background Color** | Dark (#1A1A2E or #0F0F1A) — matches holographic theme |
| **Tunnel Mesh Format** | FBX or OBJ with UV mapping |
| **Icon Sprite Atlas** | 512×512 PNG atlas, 16×16 individual icons minimum |
| **Shader Format** | URP Shader Graph (.shadergraph) |
| **Audio Assets** | WAV, 44.1kHz, <1 second for alert sounds |

---

*Part list last verified: 2026-07-17*
