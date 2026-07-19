# HOLO-RTLS — Development Roadmap
## 12-Week Phased Plan

> **Status:** Legacy Unity-era roadmap. The **shipping product** is the Flask web app.  
> For current priorities use `docs/MASTER_PLAN_ABOVE_MARKET.md`. Unity / Ollama items below are R&D, not current delivery criteria.

> **Team Size:** 3–4 developers | **Sprints:** 2 weeks each | **Total Duration:** 12 weeks

---

## Phase 0: Pre-Development (Week 0)

**Goal:** Environment setup, architecture sign-off, team alignment

### Week 0 Tasks

| Task | Owner | Deliverable | Acceptance Criteria |
|---|---|---|---|
| Finalize architecture document | Architect | `architecture.md` approved | All stakeholders sign off |
| Set up Git repository + branching strategy | DevOps | Git repo with `main`, `dev`, `feature/*` branches | CI pipeline configured |
| Procure hardware (2× Pi 5, tags, switch) | Hardware Eng | Hardware in hand | Can flash Pi, connect to network |
| Set up MQTT broker (Mosquitto on local PC) | Dev | Broker running on `localhost:1883` | `mqttx` client can pub/sub |
| Install Unity Hub + license | All devs | Unity 2022.3 LTS installed | New URP project creates successfully |
| Install Ollama + download Llama-3 8B | AI Dev | Ollama running at `localhost:11434` | `curl localhost:11434/api/tags` returns models |
| Define MQTT topic schema | Architect | Shared `TOPICS.md` document | All devs agree on pub/sub format |
| Set up SQLite schema | Backend Dev | `schema.sql` file | DB creates with all tables, foreign keys pass |

### Phase 0 Exit Criteria
- [ ] Unity project builds without errors
- [ ] MQTT broker accepts connections from test client
- [ ] Ollama responds to API requests
- [ ] Git repo has initial commit with folder structure
- [ ] All team members can run the dev environment

---

## Phase 1: Core Engine & Performance Foundation (Weeks 1–2)

**Goal:** 300 dots moving at 60 FPS on a dark grid — no UI, no network, just raw DOD performance

### Week 1: DOD Core + Rendering

**Focus:** Get the Data-Oriented Design tracking engine working with the holographic visual system

| Task | Owner | Deliverable | Acceptance Criteria |
|---|---|---|---|
| Create URP 3D project with dark theme settings | Unity Dev | Fresh URP project | Dark background, bloom enabled, HDR |
| Implement `TrackerData` struct arrays (MAX = 300) | Unity Dev | `RTLSKernel.cs` with fixed arrays | No `new` allocations after Start() |
| Implement `KalmanFilter2D` class | Math Dev | `KalmanFilter2D.cs` | Pass unit tests: noisy input → smooth output |
| Create holographic shader (Fresnel + scanlines) | Shader Dev | `HolographicShader.shadergraph` | Cyan glow, animated scanlines, semi-transparent |
| Build `HolographicOrbitCamera` | Unity Dev | Orbit camera with pan/zoom/rotate | Smooth 60 FPS camera movement |
| Create tracking dot prefab (sphere + hologram material) | Unity Dev | `TrackingDot.prefab` | Glowing cyan sphere visible in scene |
| Implement GPU instancing / SRP batching | Unity Dev | `TrackerEntity.cs` + material groups | Unity Profiler shows ≤10 draw calls for 300 dots |
| Write 300-device simulation in Unity (no MQTT) | Unity Dev | `Simulator.cs` — generates fake positions | All 300 dots visible, moving smoothly |

**Week 1 Exit Criteria:**
- [ ] 300 tracking dots rendered at ≥60 FPS
- [ ] Camera orbits 360° without stutter
- [ ] Profiler shows <16ms frame time
- [ ] Kalman filter visually smooths noisy input
- [ ] No GC.Alloc calls in Update() loop

### Week 2: Coordinate Mapping + 2D/3D Views

**Focus:** Wire up real-world scale, switch between 2D and 3D views

| Task | Owner | Deliverable | Acceptance Criteria |
|---|---|---|---|
| CAD image import pipeline (PNG → Sprite) | Unity Dev | Map loader script | Image appears as background in scene |
| Coordinate mapping: pixels ↔ meters ↔ Unity units | Unity Dev | `CoordinateMapper.cs` | Click on map → correct real-world coordinate printed |
| 2D orthographic camera mode | Unity Dev | Toggle in camera controller | Flat overhead view, correct scale |
| 3D perspective camera mode (tunnels) | Unity Dev | Y-offset per level system | Dots appear at correct height in 3D view |
| Level filter UI (dropdown: Floor 1, Floor 2) | Unity Dev | Level selector in canvas | Only dots on selected level visible |
| Circle movement simulation (path tracing) | Unity Dev | Dots follow configurable paths | Demonstrates smooth 60 FPS with motion |
| Unit test coordinate mapping | Math Dev | Test suite | Expected: 5000 units = 50m at 100px/m |

**Phase 1 Exit Criteria:**
- [ ] 300 dots render at 60 FPS in both 2D and 3D views
- [ ] Camera smoothly switches between ortho/perspective
- [ ] CAD map loads and scales correctly to real-world dimensions
- [ ] Level filtering works without frame drops
- [ ] Unity Profiler confirmed: no GC spikes, <16ms frame time

---

## Phase 2: Network Layer & Persistence (Weeks 3–4)

**Goal:** MQTT ingestion, SQLite persistence, real device data replacing simulation

### Week 3: MQTT Ingestion + Kalman Integration

**Focus:** Connect real edge nodes, feed telemetry into the tracking engine

| Task | Owner | Deliverable | Acceptance Criteria |
|---|---|---|---|
| Integrate MQTTnet (NuGet) | Unity Dev | `MQTTClient.cs` | Connects to broker, subscribes to topics |
| CSV parse engine (no JSON in hot path) | Unity Dev | `MessageDispatcher.cs` | Processes 3000 messages/sec without GC |
| Kalman filter integrated into tracking loop | Math Dev | Filter applied before `targetPosition` | Visible smoothness improvement over raw |
| UnityMainThreadDispatcher (thread-safe dispatch) | Unity Dev | Queue-based dispatcher | MQTT callbacks safely update Unity objects |
| Edge node Pi: BLE scanner script | IoT Dev | `scanner.py` on Pi | Publishes `PiMAC,TagMAC,RSSI,Battery` every 100ms |
| Edge node Pi: MQTT publisher | IoT Dev | `mqtt_publisher.py` | Confirmed message arrives at Unity |
| Multi-device simulation script (Python) | IoT Dev | `simulator.py` | Sends 300 fake tags moving in patterns via MQTT |
| Alert when MQTT disconnects | Unity Dev | Red banner UI | Reconnects automatically within 10s |

**Week 3 Exit Criteria:**
- [ ] MQTT broker receives and relays messages from Python simulator
- [ ] Unity receives and processes ≥1000 messages/second without dropping
- [ ] Kalman-filtered positions visibly smoother than raw RSSI positions
- [ ] No frame drops during high-message-volume burst test
- [ ] Auto-reconnect works when broker restarts

### Week 4: Persistence & Node Calibration

**Focus:** Nothing is lost on restart. Map calibration is drag-and-drop

| Task | Owner | Deliverable | Acceptance Criteria |
|---|---|---|---|
| SQLite database integration | Backend Dev | `DatabaseManager.cs` | CRUD operations on all tables |
| Persist node positions to DB on drag | Unity Dev | Save triggers on drag end | Reboot app, nodes stay in place |
| Persist tag metadata (name, type, icon) | Unity Dev | Auto-save on edit | Reboot app, names persist |
| Persist map sections (polygons) | Unity Dev | Save on polygon close | Reboot app, zones visible |
| Load all persisted state on app start | Unity Dev | `RTLSKernel.Awake()` loads from DB | Full state restored in <2 seconds |
| WiFi node drag-to-calibrate system | Unity Dev | `NodeDragController.cs` | User drags sphere to correct location on map |
| Node rename in-app | Unity Dev | Right-click context menu | Name saved to SQLite |
| Node heartbeat monitoring | Unity Dev | Node offline alert after 10s silence | UI indicator per node (green/yellow/red) |
| Edge node discovery (auto-register new nodes) | Unity Dev | New Pi appears at center on connect | Drag it to calibrate |

**Phase 2 Exit Criteria:**
- [ ] App restart restores full state (nodes, tags, sections) from SQLite
- [ ] User can drag a WiFi node to a new position and it saves automatically
- [ ] MQTT disconnection triggers visible alert with auto-reconnect
- [ ] 300 simulated tags update in real-time from Python script
- [ ] Kalman filter output (not raw RSSI) is used for position updates

---

## Phase 3: Enterprise Features — Zones, Alerts & Bi-Directional (Weeks 5–6)

**Goal:** Geofencing, alert engine, and downlink command system

### Week 5: Geofencing + Alert Engine

**Focus:** Zones, sections, and the alert system that makes this mission-critical

| Task | Owner | Deliverable | Acceptance Criteria |
|---|---|---|---|
| Point-in-polygon section drawing tool | Unity Dev | `PolygonDrawTool.cs` | User clicks points, closes polygon, names section |
| Section persistence (polygon points → SQLite) | Unity Dev | Save on close, load on start | Sections survive app restart |
| Geofence collision engine (SqrMagnitude) | Unity Dev | `GeofenceEngine.cs` | Restricted zone entry triggers alert |
| Section membership detection (point-in-polygon) | Math Dev | `IsPointInPolygon()` | Correct for convex and concave polygons |
| Alert UI system (notifications panel) | Unity Dev | `AlertEngine.cs` + canvas panel | Alerts appear, stack, auto-dismiss normal alerts |
| Alert types: NoSignal, NoMovement, RestrictedZone, LowBattery | Unity Dev | Per-alert color + sound | Each has distinct visual indicator |
| Configurable alert thresholds (inspector) | Unity Dev | Public fields in RTLSKernel | Admin can change timeouts without code |
| Alert acknowledgement (click to dismiss) | Unity Dev | `hasAlertedUI` debounce | Prevents alert spam |
| Alert history log in UI | Unity Dev | Searchable list panel | Filter by type, tag, time range |
| Audio alarm on critical alerts | Unity Dev | System audio playback | Can be muted in settings |

**Week 5 Exit Criteria:**
- [ ] User can draw a polygon section on the map and mark it restricted
- [ ] Walking a simulated tag into a restricted zone triggers immediate alert
- [ ] All 5 alert types fire correctly under test conditions
- [ ] Alert panel shows correct count and details
- [ ] Audio alarm plays for RestrictedZone and CriticalVitals alerts

### Week 6: Bi-Directional Control + Proximity

**Focus:** Send commands back to the physical world

| Task | Owner | Deliverable | Acceptance Criteria |
|---|---|---|---|
| Downlink command publisher (Unity → MQTT) | Unity Dev | `DeviceCommander.cs` | Publishes to `iot/command/downlink` |
| Pi subscriber (receives downlink, executes BLE write) | IoT Dev | `downlink_listener.py` | Tag vibrates when command received |
| Trigger alarm on tag (UI button) | Unity Dev | Button in tag detail panel | Connected tag vibrates within 2 seconds |
| Send message to tag (text display) | Unity Dev | Message dialog in UI | Supported tags display text |
| Initiate call / notification | Unity Dev | Call button | Tag rings/vibrates |
| Mass alert (all tags in area) | Unity Dev | Broadcast command | All tags in section alarm |
| Proximity detection (selected tag → nearby tags) | Unity Dev | `isNearby` flag per tracker | Nearby dots highlighted |
| Proximity line rendering | Unity Dev | `ProximityLineRenderer.cs` | Glowing lines connect selected tag to nearby tags |
| Check-in node logic (2m radius trigger) | Unity Dev | CheckIn/CheckOut status on tag | Tag auto-checks in when near node |
| Check-in log panel | Unity Dev | List of all check-in events | Shows who, where, when |

**Phase 3 Exit Criteria:**
- [ ] Alert enters restricted zone → alarm triggers → audio fires → UI notification appears
- [ ] Click "Trigger Alarm" → MQTT message → tag hardware vibrates
- [ ] Select a tag → nearby tags are highlighted with proximity lines
- [ ] Tag walks near Check-In node → status changes to CheckedIn in UI
- [ ] All alert types fire correctly under test conditions

---

## Phase 4: Enterprise UI, AI & Security (Weeks 7–8)

**Goal:** Full UI suite, LLM integration, and role-based access control

### Week 7: UI Suite + Statistics

**Focus:** The holographic command center aesthetic and data panels

| Task | Owner | Deliverable | Acceptance Criteria |
|---|---|---|---|
| Holographic UI theme (dark panels, cyan borders, scanline overlays) | UI Dev | Canvas styled to holographic spec | Matches reference imagery |
| Tag detail side panel (name, type, battery, vitals, section) | UI Dev | Click tag → panel opens | All fields populated from struct |
| Tag search bar (real-time filter as you type) | UI Dev | `OnSearchValueChanged()` | Results filter instantly |
| Tag type filter (All / Personnel / Machine / Sensor) | UI Dev | Dropdown + checkbox filters | Both map dots and list items filtered |
| Tag list panel (scrollable, shows all active tags) | UI Dev | Virtualized list for 300 items | No frame drops when scrolling |
| Real-time statistics bar (active count, alerts, checked-in) | UI Dev | Top stats strip | Updates every second |
| Battery level bar per tag (color-coded) | UI Dev | Green → Yellow → Red | Reflects actual batteryLevel float |
| Section/tag statistics (dwell time, distance traveled) | UI Dev | Stats panel for selected tag | |
| VLAN settings panel (broker IP, port, TLS toggle) | UI Dev | `NetworkConfig.cs` + UI | Connects to any VLAN broker |
| Settings persistence (PlayerPrefs → SQLite) | Unity Dev | Settings survive restart | |

**Week 7 Exit Criteria:**
- [ ] UI looks like a holographic command center (not a standard Unity canvas)
- [ ] Search filters tags in <100ms as user types
- [ ] Tag type filter affects both map dots and list simultaneously
- [ ] Statistics panel shows accurate data derived from Kalman-filtered positions
- [ ] Settings panel connects to a new MQTT broker on VLAN and works

### Week 8: LLM Integration + RBAC

**Focus:** Natural language AI assistant and secure multi-user access

| Task | Owner | Deliverable | Acceptance Criteria |
|---|---|---|---|
| Ollama HTTP client integration | AI Dev | `LocalLLMBridge.cs` | `curl localhost:11434/api/tags` works |
| System prompt + JSON command schema | AI Dev | Defined prompt with examples | LLM returns valid `LlmCommand` JSON |
| Natural language filter queries | AI Dev | Chat input → filter action | "Show low battery in Sector 4" → correct filter |
| LLM chat display panel (bottom-left) | UI Dev | Chat history with responses | Scrollable, shows user + AI messages |
| LLM output validation (JSON schema check) | AI Dev | Reject non-JSON output | Invalid responses logged and discarded |
| Login screen UI | Security Dev | Username + password fields | Login attempt validates against DB |
| RBAC enforcement on all sensitive buttons | Security Dev | `SecurityManager.HasPermission()` | Viewer cannot trigger alarms |
| Password hashing (BCrypt) | Security Dev | `PasswordHash` utility | Hashes match, rainbow tables useless |
| JWT session tokens (issue + validate) | Security Dev | `JWTManager.cs` | Expired tokens rejected |
| Role-specific UI hiding | UI Dev | Viewer sees read-only UI | Admin sees all controls |
| User management panel (Admin only: add/edit/delete users) | UI Dev | CRUD panel | Changes persist to SQLite |
| Audit log (who triggered which alarm) | Security Dev | `alert_log` table | |

**Phase 4 Exit Criteria:**
- [ ] "Show me all personnel with low battery" → AI → correct filter applied → relevant tags highlighted
- [ ] Viewer role cannot see the "Trigger Alarm" button
- [ ] Login required before any UI is accessible
- [ ] Admin can add a new user with Security role
- [ ] All sensitive actions are logged with username and timestamp

---

## Phase 5: Reporting & Polish (Weeks 9–10)

**Goal:** Reports, history playback, heatmaps, and visual polish

### Week 9: History Playback + Heatmaps

**Focus:** Time travel through tracking data and traffic density visualization

| Task | Owner | Deliverable | Acceptance Criteria |
|---|---|---|---|
| History circular buffer (600-entry per tag) | Unity Dev | `TrackerData.history[]` | Records every position update |
| History playback slider (selected tag) | Unity Dev | `HistoryPlaybackController.cs` | Scrubbing slider moves dot through past path |
| Timestamp display during playback | UI Dev | HH:MM:SS label | Updates as slider moves |
| LineRenderer trail (history path) | Unity Dev | Drawn for selected tag | Shows actual path taken |
| Long-term history query (SQLite) | Backend Dev | Query by date range | Loads 24h+ history from DB |
| History export to CSV | Unity Dev | Export button | Opens save dialog, downloads CSV |
| Heatmap compute shader | Shader Dev | `HeatmapComputeShader.compute` | Grid cells glow red/yellow/blue by traffic |
| Heatmap toggle (on/off) | UI Dev | Toolbar button | Toggles heatmap layer on/off |
| Performance profiler integration (frame time display) | Unity Dev | FPS counter in corner | Shows locked 60 FPS |

**Week 9 Exit Criteria:**
- [ ] Select tag → click "History" → slider allows scrubbing through last 60 seconds
- [ ] LineRenderer shows accurate path including timestamps
- [ ] Heatmap glows brighter in high-traffic zones
- [ ] CSV export contains timestamp, x, y, section for selected date range
- [ ] Frame rate counter shows 60 FPS throughout

### Week 10: Report Engine + Email

**Focus:** Automated reporting that runs off the main thread

| Task | Owner | Deliverable | Acceptance Criteria |
|---|---|---|---|
| Daily summary report template | Backend Dev | CSV format | Contains all required columns |
| Statistics engine (dwell time, distance, alert count) | Backend Dev | `ReportEngine.cs` | Calculations match Kalman-filtered positions |
| SMTP email integration | Backend Dev | `SendReportEmail()` | PDF/CSV sent to configured address |
| Scheduled report trigger (daily at set time) | Unity Dev | Cron-style scheduler in Unity | Email fires without manual trigger |
| Report configuration UI (recipients, schedule) | UI Dev | Settings → Reports panel | Persists to SQLite |
| Muster report (evacuation check-in status) | Unity Dev | One-click report | Lists all checked-in personnel with location |
| Multi-client state sync (MQTT) | Unity Dev | `system/state_changes` topic | Drag node on PC A → updates on PC B |
| Graceful degradation (LLM offline) | AI Dev | Fallback message | UI shows "AI unavailable" if Ollama down |
| Asset state management UI (Decommissioned filter) | UI Dev | Tag list filter | Decommissioned tags hidden by default |

**Phase 5 Exit Criteria:**
- [ ] "Generate Report" → CSV produced → email sent to recipient
- [ ] Report contains accurate dwell times and distances from Kalman data
- [ ] Multi-client sync: two Unity instances see same node positions after drag
- [ ] Heatmap visible and togglable
- [ ] History playback works smoothly without affecting live tracking

---

## Phase 6: Hardening & Release (Weeks 11–12)

**Goal:** Bug fixes, load testing, security audit, and documentation

### Week 11: Load Testing & Bug Fixes

**Focus:** Prove the system handles 300 devices at full throttle

| Task | Owner | Deliverable | Acceptance Criteria |
|---|---|---|---|
| 300-device sustained load test (Python simulator) | QA | 10-minute run at 10Hz each | 0 dropped messages, 0 frame drops |
| 500-device burst test | QA | Sudden 500-device spike | System degrades gracefully (no crash) |
| Kalman filter accuracy test | QA | Compare filter output vs ground truth | <5% distance error |
| Memory leak test (72-hour run) | QA | Unity Profiler memory snapshot | Memory stable (no growth) |
| MQTT TLS security test | Security | Test with Wireshark | Payload encrypted on wire |
| RBAC penetration test | Security | Viewer tries sensitive actions | All blocked, all logged |
| LLM prompt injection test | Security | Inject "ignore previous" into chat | Rejected by sanitization |
| Bug triage and fix sprint | All Devs | Jira/Trello board cleared | P0 and P1 bugs resolved |

### Week 12: Documentation + Release

**Focus:** Handoff package is complete

| Task | Owner | Deliverable | Acceptance Criteria |
|---|---|---|---|
| Final user manual | Tech Writer | `user-manual.md` | Covers all features with screenshots |
| Final implementation manual | Dev team | `implementation-manual.md` | Setup, coding standards, git flow |
| Architecture diagram | Architect | `diagrams.md` | Full system diagram with legends |
| README.md (project landing page) | DevOps | `README.md` | Quick start, screenshots, requirements |
| API documentation (internal events) | Architect | `API.md` | All public C# events and methods documented |
| Release build (Windows executable) | DevOps | `.exe` installer | Runs on clean Windows 10 machine |
| Deployment guide (edge nodes + broker) | IoT Dev | `DEPLOY.md` | Step-by-step Pi setup instructions |
| Stakeholder demo | All | Live demo with real hardware | 300 simulated tags + 2 real tags |

**Phase 6 Exit Criteria:**
- [ ] Release build runs standalone on clean Windows PC
- [ ] All P0/P1 bugs from load testing resolved
- [ ] User manual covers every feature
- [ ] Architecture diagrams are accurate and current
- [ ] Stakeholder demo successfully shows all Phase 1–5 features

---

## Milestone Summary

| Milestone | Target | Key Deliverable |
|---|---|---|
| **M1: Foundation** | End of Week 2 | 300 dots at 60 FPS, 2D/3D views |
| **M2: Networked** | End of Week 4 | MQTT ingestion + SQLite persistence + node calibration |
| **M3: Intelligent** | End of Week 6 | Geofencing, alerts, downlink control |
| **M4: Command Center** | End of Week 8 | Full holographic UI + LLM + RBAC |
| **M5: Analytics** | End of Week 10 | History playback, heatmaps, reports |
| **M6: Production** | End of Week 12 | Release build, documentation, stakeholder demo |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Kalman filter tuning is harder than expected | Medium | High | Pre-build filter with known good hyperparameters |
| 300 MQTT messages/sec causes frame drops | Low | High | Profile early in Week 1; if needed, batch messages |
| BLE scanning on Pi is unreliable (RF interference) | High | Medium | Use high-gain antennas + UWB for critical zones |
| LLM hallucinations produce invalid commands | Medium | Medium | Strict JSON schema validation; discard invalid output |
| Multi-client MQTT sync causes race conditions | Low | Medium | Last-write-wins with timestamp; no complex merging |
| Unity URP + 300 objects exceed VRAM budget | Low | High | Use simple sphere meshes (<1KB each); LOD if needed |
| SQL injection in report queries | Low | Critical | Use parameterized queries exclusively |

---

*Roadmap last updated: 2026-07-17*
