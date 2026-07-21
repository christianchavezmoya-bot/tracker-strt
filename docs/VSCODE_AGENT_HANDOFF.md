# VS Code Agent Handoff — HOLO-RTLS MQTT / STRATA

**Repo:** `tracker-strt`  
**Branch:** `master` (as of commit `5ff1130`)  
**Network example:** server `10.60.1.5`, subnet `10.60.1.0/24`, MQTT port `1883`

---

## What we are building

A **non-developer-friendly RTLS commissioning flow**:

1. Server embeds MQTT broker — admin turns it on in **Settings → Network & MQTT**
2. WiFi anchor units publish BLE scan data to the server
3. App **auto-detects nodes**, shows **raw MQTT traffic**, operator **acknowledges** and **places anchors** on map
4. After ≥3 anchors placed → **trilateration** → tags on Live Map via SSE

**Production path:** WiFi nodes → MQTT `:1883` → embedded broker → ingest → positioning → SSE → map  
**NOT production:** PC `HOLO-MQTT-Broker.exe` (commissioning/debug only), OpenWrt syslog at router `.1`

---

## What is DONE on master

### Waves A–D (commit `ad89599`)
- RTLS readiness checklist (dashboard + map banner)
- Admin MQTT broker toggle
- Node diagnostics API + `/nodes` Diagnostics tab
- WifiNode ↔ WifiAnchor sync, refresh-positions, 3D edit, multi-floor filter

### Raw traffic + auto-detection (commit `5ff1130`, PR #11)
- **`backend/services/mqtt_traffic_log.py`** — ring buffer of raw messages
- **`backend/services/mqtt_node_detect.py`** — detect node from STRATA topic/payload
- **`backend/services/mqtt_tag_ingest.py`** — logs all messages; registers nodes even when parse fails
- **UI:** Anchors → Diagnostics → **Incoming traffic** (auto-refresh 4s)
- **API:** `GET /api/nodes/mqtt-traffic`, `POST /api/nodes/:id/acknowledge`
- Setup cards say: set broker IP/port; topic/format varies — check Incoming traffic

---

## Real hardware format (confirmed from field)

**Topic:**
```
strata/v1/bluetooth/1/273983315172900
```

**Payload (JSON array):**
```
[1, 1750690877, 30, 273983315172900, 1, 828033288983, -95]
```

| Index | Field | Example | Notes |
|-------|--------|---------|-------|
| 0 | type | `1` | message type |
| 1 | timestamp | `1750690877` | Unix seconds |
| 2 | ? | `30` | unknown (scan interval?) |
| 3 | node_id | `273983315172900` | matches topic suffix; used as `STRATA:{id}` |
| 4 | ? | `1` | constant in samples |
| 5 | tag_id | `828033288983` | decimal → MAC `82:80:33:28:89:83` (12 digits) |
| 6 | rssi | `-95` | dBm |

**Parser status:** NOT implemented for tag ingest. CSV `rssi/data` and JSON objects work; numeric arrays return `[]`.

---

## What the VS Code agent should do NEXT

### Phase 1 — STRATA tag parser (priority)

**File:** `backend/services/mqtt_tag_parse.py`

Add branch in `parse_mqtt_payload()`:
- If JSON array of 7 numeric fields → extract tag MAC from field[5], RSSI from field[6]
- Set `anchor_mac` from field[3] / topic suffix → map to `STRATA:{node_id}` (same key as auto-detect)

**File:** `backend/services/mqtt_node_detect.py` (optional helper)
- Share `decimal_tag_id_to_mac(n: int) -> str` with parser

**Tests:** `tests/test_mqtt_tag_parse.py` + extend `tests/test_mqtt_traffic.py`:
```python
payload = "[1,1750690877,30,273983315172900,1,828033288983,-95]"
topic = "strata/v1/bluetooth/1/273983315172900"
# expect tag 82:80:33:28:89:83, rssi -95, anchor STRATA:273983315172900
```

**Integration test:** ingest STRATA message → DetectionEvent row → optional position fix if 3+ anchors placed.

### Phase 2 — Align setup UI

**Files:** `backend/services/mqtt_broker_manager.py`, `frontend/static/js/rtls-setup.js`, `node_reader/app.py`

Once parser works:
- Show STRATA topic/payload as primary example when Incoming traffic shows `strata_v1_array`
- Or dynamic: read last N messages from traffic log and display detected format

### Phase 3 — PC broker parity (optional)

**Files:** `node_reader/mqtt_parse.py`, `node_reader/app.py`

Mirror STRATA parsing in PC tool so "Parsed tags" table fills for STRATA messages (user screenshot showed `parsed_device_count: 0`).

---

## How to TEST (local)

### Unit / integration (always run)
```bash
cd /path/to/tracker-strt
python -m pytest tests/test_mqtt_traffic.py tests/test_mqtt_tag_parse.py \
  tests/test_mqtt_tag_ingest.py tests/test_mqtt_smoke_integration.py \
  tests/test_wave_c_diagnostics.py tests/test_wave_d.py tests/test_wave_ab_rtls.py -q
```

### Manual commissioning (real network)
1. Pull latest `master`, restart Flask/server
2. **Settings → Network & MQTT** → enable receiver
3. WiFi units → broker `10.60.1.5:1883`, keep factory STRATA topic
4. **Anchors → Diagnostics → Incoming traffic** — confirm messages, `Parsed: No` until Phase 1
5. **Discovered** tab — nodes like `STRATA-172900` appear
6. Acknowledge → place 3+ on map → enable parser → tags on Live Map

### PC broker (Windows, optional)
```bash
python -m node_reader
# or HOLO-MQTT-Broker.exe — same network 10.60.1.x
```

### Playwright E2E (CI)
```bash
PLAYWRIGHT_E2E=1 ./scripts/run_e2e_ci.sh
# tests/e2e/test_commissioning.py — readiness panel, diagnostics, Network tab
```

---

## Key files map

| Area | Path |
|------|------|
| MQTT parse | `backend/services/mqtt_tag_parse.py` |
| MQTT ingest | `backend/services/mqtt_tag_ingest.py` |
| Raw traffic log | `backend/services/mqtt_traffic_log.py` |
| Node auto-detect | `backend/services/mqtt_node_detect.py` |
| Broker manager | `backend/services/mqtt_broker_manager.py` |
| Nodes API | `backend/api/nodes/__init__.py` |
| Diagnostics UI | `frontend/templates/nodes/index.html` |
| Setup UI | `frontend/static/js/rtls-setup.js` |
| PC broker | `node_reader/app.py`, `node_reader/pc_broker.py` |

---

## Pitfalls (do not repeat)

1. **Do not hardcode `192.168.1.1`** — site uses `10.60.1.x`; broker address comes from server LAN IP / WiFi setup card
2. **Do not require `rssi/data` topic** — broker accepts any topic; STRATA uses `strata/v1/bluetooth/...`
3. **Do not assume parse = receive** — messages can arrive with `parsed: false`; check Incoming traffic
4. **Anchor key for STRATA** — use `STRATA:{node_id}` consistently in detect, parse, and DB
5. **Two anchor tables** — `WifiNode` (map) + `WifiAnchor` (trilateration); keep synced via `anchor_sync.py`
6. **Do not commit** `frontend/static/assets/floor-plans/` accidentals

---

## Git workflow

- Branch template: `cursor/<descriptive-name>-af22`
- Push: `git push -u origin <branch>`
- User often asks **"push to master"** — merge to `master` and push when tests pass

---

## Success criteria for next milestone

- [ ] STRATA payload parses to tag MAC + RSSI
- [ ] `Parsed: Yes` in Incoming traffic for STRATA messages
- [ ] DetectionEvent rows created for STRATA ingest
- [ ] Tags appear on Live Map after 3 placed anchors + live STRATA traffic
- [ ] All pytest above pass; no regression on CSV/JSON formats
