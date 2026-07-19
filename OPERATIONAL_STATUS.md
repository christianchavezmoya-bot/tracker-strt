# HOLO-RTLS — Operational Status & Gap Analysis

> **Author:** Claude Code · **Date:** 2026-07-19 · **Branch:** `master` @ `3bbfd5b`
> **Local:** `C:\Users\cchavez\Documents\Commtrac\Codex\Tracker-strt` · **Runtime:** Python 3.14 venv, Windows
> Reference docs analysed: `BUILD_PLAN.md`, `architecture.md`, `requirements.md`, `roadmap.md`, `implementation-manual.md`, `diagrams.md`.

---

## 0. Bottom Line

The app **is operational** as a Flask web service. After the fixes below, it boots, serves all pages, passes its full test suite, and every REST blueprint responds. **Live map auto-update is the one materially broken runtime feature** (SSE auth + a subsystem-integration gap). Roughly: **backend ~90% working; frontend loads and is API-wired but not fully live; the "vision" docs describe a different product that was never built.**

**Evidence collected this session:**
- `pytest tests` → **67 passed, 0 failed** (28 deprecation warnings only).
- Route probe: **14/14 pages = 200**, **38/39 API GETs = 200**; the one exception (`/api/uwb/position` = 503) is a *designed* "no data" response.
- End-to-end trilateration verified: simulated device solved to within expected error; live position served via `/api/scanner/positions/live`.

---

## 1. CRITICAL CONTEXT: the docs describe a *different* product

There are **two conflicting visions** in the repo, and it matters for reading every "what's implemented" claim:

| Document | Describes | Matches the code? |
|---|---|---|
| `architecture.md`, `implementation-manual.md`, `requirements.md`, `roadmap.md`, `diagrams.md` | A **Unity 3D / C# desktop app** (URP, DOD struct arrays, 300 devices @ 60 FPS, MQTTnet, **Ollama LLM**, holographic shaders, Raspberry-Pi MQTT edge nodes, downlink to hardware) | ❌ **No. None of this exists.** There is no Unity project, no C#, no LLM, no shaders, no MQTT edge-node fleet. |
| `BUILD_PLAN.md` | A **Python Flask + web (Leaflet/Three.js) + SQLite** app | ✅ **Yes — this is the real system.** |

**Treat only `BUILD_PLAN.md` as the roadmap of record.** The rest are aspirational design fiction. Any feature that appears *only* in the Unity docs (LLM assistant, 300-device GPU instancing, holographic shaders, bi-directional downlink, heatmap compute shader, MQTT-over-VLAN edge fleet) is **not implemented and not started.**

## 1a. There are also TWO positioning subsystems in the code (undocumented overlap)

Nothing in the docs explains this, but the code contains **two parallel, non-integrated positioning stacks**:

| | **Track A — Ingestion/UWB** (BUILD_PLAN Phase 3) | **Track B — WiFi/BLE Scanner** (added in commit `3bbfd5b`) |
|---|---|---|
| Positioning svc | `backend/services/positioning_service.py` | `backend/services/wifi_positioning.py` |
| Anchor model | `WifiNode` (`/api/nodes`) | `WifiAnchor` (`/api/scanner/anchors`) |
| Ingest path | hardware bridges → `IngestionLoop` → history → **SSE broadcast** | `POST /api/scanner/detections` → writes `TrackedDevice` |
| Live API | `/api/positioning/live`, SSE `/api/stream/positions` | `/api/scanner/positions/live` |
| Frontend | `/` (Command Center dashboard) | `/tracking` (Scanner map) |
| Scanner daemon | — | `scanner/` (mock / scapy / bleak) |

They duplicate concepts (two "anchor" tables, two "live position" endpoints, two map pages) and **do not share data**. This is the single biggest architectural cleanup item and the root of the live-update bug (§4, F-2).

---

## 2. What's WORKING (verified)

| Area | Status | Evidence / Notes |
|---|---|---|
| **Boot & serve** | ✅ | `python run.py` → serves on `:8080`; auto-seeds admin |
| **Auth & RBAC** (BUILD_PLAN Ph.1) | ✅ | JWT login/refresh, Argon2, 2FA (pyotp), lockout, roles; 14 auth tests pass |
| **Tracker CRUD** (Ph.2) | ✅ | `/api/trackers` all verbs; 9 tracker tests pass |
| **Nodes / Zones / Sections** (Ph.2) | ✅ | `/api/nodes`, `/api/zones`, `/api/zones/sections` → 200 |
| **Global search** (Ph.2) | ✅ | `/api/search?q=` → 200 |
| **Positioning engine** (Ph.3) | ✅ | Trilateration + Kalman verified end-to-end (both tracks); 18 positioning tests pass |
| **Alerts engine** (Ph.4) | ✅ | Full `/api/alerts/*` surface; 22 alert tests pass |
| **Reports** (Ph.6) | ✅ (API) | `/api/reports/{summary,daily,battery,distance,alert-breakdown,tracker-activity}` → 200 |
| **Settings + logo + floor-plans** (Ph.7) | ✅ | `/api/settings/*` → 200 |
| **Users / Audit** (Ph.8) | ✅ | `/api/users`, `/api/audit` → 200 |
| **Backup/restore** (Ph.9) | ✅ (API) | `/api/backup/*` → 200 |
| **Hardware config system** (Ph.3) | ✅ (API) | `/api/hardware/*` incl. profile catalog → 200 |
| **Swagger docs** (Ph.10) | ✅ | `/apidocs/index.html` served |
| **Scanner subsystem** (Track B) | ✅ | anchors/calibrate/detections/positions all work; daemon runs in `--mock` |
| **Frontend pages load** | ✅ | 14/14 routes → 200; `/` dashboard and `/tracking` render after fixes |
| **Test suite** | ✅ | **67/67 pass** |

---

## 3. What NEEDS IMPLEMENTATION / is INCOMPLETE

Against `BUILD_PLAN.md` (the accurate plan) and observed behaviour:

| Item | Plan ref | State | What's needed |
|---|---|---|---|
| **Live map auto-update** | Ph.2 S2.9 / Ph.5 S5.4 | 🔴 Broken | SSE returns 401 (see F-1) and scanner data isn't broadcast (F-2). This is *the* thing stopping "fully live." |
| **Frontend interactivity depth** | Ph.2/5 | 🟡 Unverified | Pages load and call the right APIs, but click-through flows (zone polygon drawing, node drag-place, history playback slider) were **not** QA'd headlessly. Needs manual/browser testing. |
| **3D view (Three.js)** | Ph.5 S5.3 | 🟡 Partial | Loads `three@0.160`; renders, but not verified with live data. Deprecated UMD build (warns; removed in r160). |
| **History playback slider** | Ph.5 S5.7 | 🟡 | Endpoint `/api/positioning/history/<id>` exists; UI/playback not verified. |
| **Reports UI + email delivery** | Ph.6 | 🟡 | Report **APIs** work; scheduled email (`APScheduler` + SMTP) and Reports **page** interactivity unverified; mail suppressed in dev. |
| **Long-term history persistence** | Ph.3 S3.6 | 🔴 Bug | History flush/prune threads crash (F-3) → DB history archive not written. |
| **Two-subsystem consolidation** | — (undocumented) | 🟡 Debt | Track A vs Track B should be merged or one deprecated (§1a). |
| **API-key auth** | Ph.10 | 🟡 | `ApiKey` model exists; no `/api/keys` route in the map — management UI/route not implemented. |
| **Unity-doc features** (LLM, downlink, heatmap, 300-dev GPU, edge fleet) | architecture.md | ⚪ Not started | Out of scope for the Flask app; ignore unless re-scoped. |

---

## 4. FINDINGS NOT IN THE DOCS (bugs)

### Already fixed this session (needed to boot/render)
| # | Bug | File | Fix |
|---|---|---|---|
| X-1 | `datetime.min(timezone.utc)` — value called like a function → `TypeError`, crashed startup | `backend/services/alert_service.py:96` | ✅ `datetime.min.replace(tzinfo=timezone.utc)` (code edit) |
| X-2 | `imghdr` removed in Python 3.13 → `ModuleNotFoundError` | `backend/api/settings/__init__.py:5` | ✅ installed `standard-imghdr` backport (env) |
| X-3 | `run.py` admin ✅-emoji print crashes on Windows cp1252 | `run.py:30` | ✅ `PYTHONUTF8=1` (env) — better: make the print ASCII |
| X-4 | CSP fix was **incomplete** — `unpkg` added to `script-src` but not `style-src` → Leaflet CSS blocked | `backend/security.py:31` | ✅ added `unpkg` to `style-src` (code edit) |
| X-5 | Landing dashboard never loaded `api.js` → `ReferenceError: API is not defined` (only page of 15 missing it) | `frontend/templates/dashboard/index.html` | ✅ added `<script src="/static/js/api.js">` (code edit) |

> (The four issues in your "already fixed" list — `hardware_bridge` syntax, `verify_jwt_in_request`, CSP-script-src, `.split()` on list — were indeed already patched in `3bbfd5b`. X-4 shows the CSP one was only *half* done.)

### Open bugs (not yet fixed)
| # | Severity | Bug | Where | Impact |
|---|---|---|---|---|
| **F-1** | 🔴 High | SSE stream uses `@jwt_required()` (header-only), but `/tracking` connects via `EventSource('/api/stream/positions?token=…')` (query param) → **401**, perpetual reconnect | `backend/api/stream.py:72-74` + `frontend/.../tracking.html:1411` | Live map never updates; indicator stuck on "reconnecting…" |
| **F-2** | 🔴 High | Scanner path writes `TrackedDevice` only; SSE snapshot reads `PositionSnapshot`; live deltas come from the **ingestion loop**, not the scanner → scanner devices never stream even if F-1 fixed | `wifi_positioning.py:_persist_fix` vs `stream.py:_snapshot_event` | `/tracking` can't show live scanner data via SSE |
| **F-3** | 🟠 Med | History flush/prune background threads run without app context → `RuntimeError: Working outside of application context` (logged repeatedly) | `backend/services/history_service.py` | Long-term history archive & retention pruning silently fail |
| **F-4** | 🟠 Med | `/` (Command Center) shows no live data out of the box — nothing feeds the ingestion loop until a `mock_data` **HardwareConfig** is created via `/api/hardware` | Track A activation | Empty dashboard misreads as "broken" |
| **F-5** | 🟡 Low | `requirements.txt` won't `pip install` on Windows/Py3.14 (numpy 1.26.4 pin; Linux-only `pybluez`/`bluepy`) | `requirements.txt` | Blocks setup; worked around with a relaxed venv |
| **F-6** | 🟡 Low | `Query.get()` legacy calls (SQLAlchemy 2.0 deprecation) throughout | multiple | Warnings now; breakage on a future SQLAlchemy 2.1 |
| **F-7** | 🟡 Low | `no `/api/keys` route despite `ApiKey` model + Ph.10 plan | — | API-key feature incomplete |
| **F-8** | 🟡 Low | Two parallel anchor/positioning subsystems (§1a) | — | Maintenance/UX confusion |

---

## 5. To reach "FULLY operational (live)"

1. **Fix F-1** — accept the SSE token from the query string. Either add `JWT_TOKEN_LOCATION=["headers","query_string"]` (+`JWT_QUERY_STRING_NAME="token"`) in config, or drop `@jwt_required()` on the stream and validate the `?token=` manually. *(~small)*
2. **Fix F-2** — decide the model: either (a) route scanner detections through the same `IngestionLoop`/SSE broadcast, or (b) add a short `setInterval` poll of `/api/scanner/positions/live` to `tracking.html` as a pragmatic fallback. *(a = medium, b = small)*
3. **Fix F-3** — wrap the history service's periodic flush/prune in `with app.app_context():`. *(~small)*
4. **Activate Track A** for the `/` dashboard demo — `POST /api/hardware` with the `mock_data` profile so the ingestion loop produces live trackers. *(config, not code)*
5. **Consolidate** Track A/B (F-8) and finish the interactivity QA of the editor pages. *(larger)*

Items 1–4 are small/contained and would make both maps genuinely live.

---

## 6. Setup recipe that works on this machine (for reproducibility)

- Python **3.11–3.12 recommended**; on the installed **3.14** use a venv with **relaxed** deps (latest numpy/Pillow/SQLAlchemy) and **skip** `pybluez`/`bluepy` (Linux-only) + `scapy` (only needed for real WiFi capture). Also `pip install standard-imghdr`.
- Required env: `SECRET_KEY`, `JWT_SECRET_KEY`; plus `PYTHONUTF8=1`, `FLASK_DEBUG=0`, `SCANNER_API_KEY` (must match the scanner node), `FLASK_MAIL_SUPPRESS_SEND=1`.
- Run `python run.py` → `http://localhost:8080`. Admin: `admin@holo-rtls.local` / `ChangeMe123!`.
- Scanner demo: `python scanner/main.py --mock` (no `--scan-interval` flag — it doesn't exist).

---

*Local code edits made this session (uncommitted): `backend/services/alert_service.py`, `backend/security.py`, `frontend/templates/dashboard/index.html`. New files: `.env`, `.venv/`, `REPO_REVIEW.md`, this file.*
