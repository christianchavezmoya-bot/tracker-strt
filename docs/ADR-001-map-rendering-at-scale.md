# ADR-001: Map Rendering Architecture at Scale (300 Trackers)

| Field | Value |
|-------|-------|
| **Status** | Accepted — Phase 0–2 implemented (2026-07-20) |
| **Date** | 2026-07-20 |
| **Deciders** | Product, Engineering, Operations |
| **Supersedes** | Unity-only delivery assumptions in `roadmap.md` (R&D retained, not primary path) |
| **Related** | `docs/MASTER_PLAN_ABOVE_MARKET.md`, `docs/CURRENT_SYSTEM.md`, `roadmap.md` |

---

## Context

HOLO-RTLS ships a **Flask web operations console** with:

- **2D mine map** — Leaflet + floor-plan PNG (metre CRS)
- **Regional map** — OpenStreetMap + Esri satellite tiles (WGS84)
- **3D preview** — Three.js WebGL (optional toggle)
- **Live data** — SSE `/api/stream/positions` from IngestionLoop

The product must support **~300 concurrent trackers**, **anchor/node placement**, and multiple view modes (indoor plan, site map, satellite). Stakeholders also want **game-like responsiveness** (smooth camera, interpolated motion) and a future **BIM-integrated walk-through** for training and commissioning.

**Current limits (reviewed 2026-07-20):**

| Area | Today | At 300 tags |
|------|-------|-------------|
| 2D trackers | One DOM `L.marker` per tag | Layout/paint bottleneck |
| 3D trackers | Two meshes per tag (~600 draw calls) | GPU + continuous RAF waste |
| Updates | Per-message layer scans (`eachLayer`) | CPU spike under load |
| Street View | OSM raster only — not 360° panorama | New integration required |
| BIM | Flat PNG plane in 3D | No tunnel/mesh geometry |
| Coordinates | 2D affine vs 3D raw coords | Views can disagree |

Master Plan principle **P1 — One product, one map** requires all view modes to share one positioning truth, not fork into separate apps.

---

## Decision

Adopt a **dual-layer rendering strategy**:

### Layer 1 — Primary ops console (web, always-on)

**Technology:** Evolve the existing Flask + Leaflet/Three.js stack.

| Component | Choice | Rationale |
|-----------|--------|-----------|
| 2D ops map | **Canvas/WebGL point layer** (MapLibre GL JS or Leaflet canvas renderer) | Single draw path for 300 tags; keeps browser-only deploy |
| 3D ops map | **Three.js InstancedMesh** + render-on-demand | Matches 300-tag / ≤10 draw-call target from Unity roadmap, without second client |
| Regional / satellite | **MapLibre** with OSM + satellite style layers | Unified geospatial stack; replaces dual Leaflet tile layers |
| Real-time transport | **SSE with batched updates** (50–100 ms coalesce) + fix event delivery | Lower message rate; reliable live updates |
| Motion | **Client interpolation** (lerp between samples); optional server Kalman | Game-like smoothness without Unity |
| Anchors (~10–50) | Rich DOM/SVG markers (unchanged pattern) | Low count, high interaction (drag, coverage rings) |

This layer is the **system of record for daily operations** — control room, tablets, RBAC, alerts, commissioning.

### Layer 2 — Immersive BIM walk-through (optional module, Phase 3)

**Technology:** **Unity 2022.3 LTS (URP)** as a read-mostly visualization client, OR **xeokit** for web-native IFC if Unity deployment is blocked.

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Geometry | **glTF 2.0** exported from IFC/Revit/Navisworks | Industry-standard; Draco-compressed for web/desktop |
| Data feed | Same **MQTT `rtls/state_changes`** or WebSocket batch stream Flask already publishes | No forked positioning logic |
| Scope | Training, executive demos, greenfield BIM sites | Not required for 12-hour shift operations |
| Business logic | Stays in **Flask API** — Unity/xeokit never owns auth, alerts, or persistence | Fail-closed, RBAC-honest (P7) |

Unity R&D in `roadmap.md` (GPU instancing, Kalman, 300-dot simulation) **remains valid** but applies to this optional module, not the primary delivery path.

### Explicitly not in scope for v1

- Replacing the web dashboard with Unity-only
- Google Street View as the main map canvas (licensing + wrong use case)
- CesiumJS as primary engine (overkill for underground metre-grid plans)

Street-level context (if needed later) = **side panel** via Mapillary, licensed Street View embed, or site 360° captures at gate/portal coordinates.

---

## Unified coordinate model (prerequisite)

All renderers consume positions from a single **CoordinateService**:

```
BIM local origin  ←→  mine metres (pos_x, pos_y, pos_z)
                   ←→  floor-plan pixels (affine calibration)
                   ←→  WGS84 (georef corner points)
```

**Floor/level model:** `MapSection.z_index` + elevation metres; trackers and zones filtered by active level in both 2D and 3D.

No view mode ships until it reads from this service — prevents satellite, mine, and BIM views from disagreeing.

---

## Real-time data architecture

```
Edge scanners → IngestionLoop → Location Core (optional Kalman)
                                      ↓
                              PositionSnapshot (DB)
                                      ↓
                    ┌─────────────────┴─────────────────┐
                    ▼                                   ▼
            SSE batcher (~20 Hz)                  MQTT rtls/state_changes
                    ↓                                   ↓
            Web ops clients                      Unity / xeokit viewer
```

| Rule | Detail |
|------|--------|
| Batch format | `{ "type": "batch", "updates": [{ tracker_id, x, y, z, … }] }` every 50 ms |
| SSE fix | Emit `event: position_update` line OR route all types through `onmessage` |
| Client registry | `Map<trackerId, renderHandle>` — O(1) updates, no `eachLayer` scans |
| Backpressure | Expose dropped-client count on `/api/stream/status` |

---

## Implementation phases

| Phase | Goal | Key deliverables | Blocks |
|-------|------|------------------|--------|
| **0 — Foundation** | Reliable live map for 100+ tags | CoordinateService; SSE fix + batching; tracker registry; 3D floor from same `image_url` as 2D | Everything else |
| **1 — Scale to 300** | Control-room grade performance | Instanced 2D canvas layer; Three.js InstancedMesh; render-on-demand; client lerp | Phase 0 |
| **2 — Multi-view** | Map + satellite + site context | MapLibre regional mode; 3D anchor rendering; floor filter for trackers; optional Mapillary panel | Phase 1 |
| **3 — BIM walk-through** | Immersive commissioning/training | glTF pipeline; Unity or xeokit embed from Live Map; shared tag inspector API | Phase 0 coords |
| **4 — Polish** | Above-market ops UX | Map-linked timeline replay; live dwell heatmap; tablet layout (map + alert sheet) | Phase 1 |

**Sign-off gate for Phase 1:** 300 simulated tags updating at 10 Hz, ≤16 ms frame time on reference hardware (mid-range GPU, Chrome), zero GC spikes in 5-minute soak.

---

## Consequences

### Positive

- Single web product for operations — aligns with Master Plan and market expectations (Sewio/Pozyx-class consoles)
- 300-tag performance achievable without forcing Unity on every operator workstation
- BIM walk-through becomes an **upsell module**, not a rewrite
- Unity roadmap R&D is preserved with a clear integration boundary
- Satellite and mine views share one geospatial stack after Phase 2

### Negative / trade-offs

- Two rendering codepaths to maintain (web instanced + optional Unity/xeokit)
- glTF/BIM pipeline requires CAD export discipline from customers
- MapLibre migration is non-trivial (regional view refactor)
- Street View remains a separate licensed integration, not a rendering-engine feature

### Risks

| Risk | Mitigation |
|------|------------|
| Unity module never ships | Phase 1 web 3D still delivers scaled ops map |
| BIM model drift vs as-built | Version BIM assets; display model date in UI |
| Team splits across JS + C# | Unity module owned by dedicated sub-team; strict API contract |
| "Game UI" conflicts with calm ops UX (P5) | Game-like = performance + camera, not particle overload |

---

## Alternatives considered

| Alternative | Rejected because |
|-------------|------------------|
| **Unity replaces web dashboard** | RBAC/SSO/deployment friction; market expects web ops console |
| **CesiumJS primary** | Poor fit for underground metre-grid; heavy for PNG-plan sites |
| **Keep DOM markers, optimize CSS** | Cannot reach 300 tags at 10 Hz — structural limit |
| **IFC.js only, no Unity** | Acceptable fallback for Phase 3 if Unity deployment blocked; lower visual fidelity for tunnels |
| **WebSocket-only, drop SSE** | SSE fine with batching; WebSocket added for Unity if needed |

---

## Acceptance criteria (stakeholder sign-off)

- [ ] **D1:** Web dashboard remains primary ops surface for all roles
- [ ] **D2:** Phase 1 targets 300 tags at 10 Hz with ≤16 ms frame time
- [ ] **D3:** All view modes consume CoordinateService — no forked transforms
- [ ] **D4:** BIM walk-through is optional Phase 3 module (Unity or xeokit), not v1 blocker
- [ ] **D5:** "Street view" scoped as 360° side panel integration, not OSM tiles alone
- [ ] **D6:** Unity `roadmap.md` items retained as R&D for Layer 2, not conflicting with Master Plan

---

## References

- Map review report (2026-07-20 conversation) — current-state analysis
- `frontend/static/js/visualization/map2d.js` — Leaflet mine/regional
- `frontend/static/js/visualization/map3d.js` — Three.js 3D
- `frontend/static/js/visualization/map-georef.js` — OSM + Esri satellite
- `backend/services/ingestion_loop.py` — SSE broadcast
- `roadmap.md` — Unity 300-dot instancing R&D (Phase 1–3 legacy plan)
- `docs/MASTER_PLAN_ABOVE_MARKET.md` — P1 One product, one map

---

*End of ADR-001*
