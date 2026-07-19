# HOLO-RTLS — Master Plan: 100% Functional & Above-Market

> **Status:** Planning only — **no application code changes in this document’s delivery**  
> **Branch:** `cursor/holo-rtls-master-plan-af22`  
> **Baseline:** `master` @ `3ce9b37` (reviewed + smoke-tested 2026-07-19)  
> **Canonical roadmap:** This document supersedes conflicting Unity-era claims in `architecture.md` / `roadmap.md` for *implementation*. Keep those files as aspirational R&D notes only.

---

## 0. Executive summary

HOLO-RTLS today is a **working Flask + Jinja indoor RTLS MVP**: authentication, most REST APIs, fourteen pages, trilateration engines, alerts, reports, hardware profiles, and a scanner daemon all exist. It is **not** yet a coherent, day-to-day operations product.

This plan brings the product to:

1. **100% functional** — every shipped page and API works end-to-end without 500s, placeholders, or dead ends.  
2. **100% operational** — first boot shows live data; maps update reliably; backups, notifications, and history actually persist.  
3. **Above market** — clearer UX than typical mid-market RTLS consoles (Sewio Sensmap, Pozyx, Quuppa, Kontakt.io-class), with a **professional, attractive, operator-friendly UI**, stronger commissioning wizards, unified positioning, and deeper analytics/compliance than the MVP.

**North-star user promise**

> In under 15 minutes, an admin can upload a floor plan, place anchors, register tags, see people and assets move live, draw safety zones, get alerts, and export a report — on a UI that feels like a modern industrial product, not a prototype dashboard.

---

## 1. Product principles (non-negotiable)

| # | Principle | Meaning |
|---|---|---|
| P1 | **One product, one map** | Ops map and commissioning tools share one positioning truth. Modes change; data does not fork. |
| P2 | **Never a dead end** | Every nav item is a finished workflow. Placeholders are forbidden in production nav. |
| P3 | **Map-native editing** | Zones, sections, anchors, and tags are created/edited on the floor plan first; forms are secondary. |
| P4 | **First-run success** | Fresh install auto-seeds demo (or guided wizard) so Command Center is never empty. |
| P5 | **Calm professional UI** | Attractive, high-contrast, restrained motion. No emoji-primary nav, no glow-spam, no Inter-only “AI dashboard” look. |
| P6 | **Fail closed, explain loudly** | Bad input → 400 with clear message. System health always visible. |
| P7 | **Role-honest UI** | Viewers see map + alerts; operators act; admins configure. Hide what you cannot use. |
| P8 | **Leave nothing behind** | Every model, API, BUILD_PLAN ID, and orphan template is either finished, merged, or explicitly retired. |

---

## 2. Target experience & UI system (frontend-first)

### 2.1 Visual direction (above-market)

**Goal:** Control-room clarity for 8–12 hour shifts, with enough craft to feel premium.

| Token | Direction |
|---|---|
| **Brand** | “HOLO-RTLS” as a persistent product mark in the shell (wordmark + simple geometric mark). Not only nav text. |
| **Typography** | Distinctive pairing: **display** = modern geometric sans or condensed industrial (e.g. *Space Grotesk* / *IBM Plex Sans* for UI; *IBM Plex Mono* for coordinates/IDs). **Avoid** Inter/Roboto/Arial as primary. |
| **Color** | Deep slate/graphite base (`#0B1220`–`#121A2B`), **single primary accent** (electric teal or safety amber — pick one), semantic status greens/ambers/reds. Avoid purple-indigo gradients and cream/terracotta tropes. |
| **Surfaces** | Subtle layered panels with light borders; soft depth — not neon glow stacks. Background: quiet grid or very soft radial atmosphere, not flat black. |
| **Density** | Ops map = spacious. Admin tables = compact but readable (14–15px, generous row height). |
| **Motion** | 2–3 intentional motions: shell entrance, live tag pulse, alert toast slide. No endless glow pulses. |
| **Icons** | Consistent SVG icon set (Lucide/Heroicons-style). **No emoji in primary navigation.** |
| **Cards** | Default: no cards on the live map. Cards only for interactive lists/modals. |
| **Responsive** | Desktop command center + **tablet live view** (map + alert queue). Phone = limited acknowledge/search. |

### 2.2 Application shell (shared layout)

**Today:** Every page reinvents chrome; hamburger drawer with emoji; CSS duplicated.

**Proposed `base.html` shell**

```
┌─────────────────────────────────────────────────────────────┐
│ TOPBAR: Brand · Facility · Live status · Search · Alerts · User │
├──────────┬──────────────────────────────────────────────────┤
│ SIDE NAV │  PAGE CONTENT (map full-bleed OR admin workspace) │
│ (icons + │                                                   │
│  labels) │                                                   │
└──────────┴──────────────────────────────────────────────────┘
```

**Nav information architecture**

| Group | Items | Who |
|---|---|---|
| **Operate** | Live Map, Alerts, Search | All |
| **Assets** | Trackers (tags), Devices (scanner registrations) | Op+ |
| **Site** | Floor Plans, Anchors & Nodes, Zones, Hardware | Op+/Admin |
| **Insights** | Reports, History playback (deep link) | Op+ |
| **Admin** | Users, Audit, Backup, Integrations (API keys/webhooks), Settings | Admin |

**Modes on Live Map (not separate products)**

- **Monitor** — situational awareness (default)  
- **Setup** — place/calibrate anchors, upload plans, draw zones  
- **Playback** — history scrubber  

### 2.3 UI quality bar (acceptance)

Every page must meet:

- [ ] Shared shell, consistent spacing scale (4/8/12/16/24/32)  
- [ ] Empty states with **one clear CTA**  
- [ ] Loading skeletons (not blank panels)  
- [ ] Inline validation errors  
- [ ] Keyboard: `/` or Ctrl+K search; Esc closes overlays  
- [ ] Accessible contrast (WCAG AA for text)  
- [ ] No orphan placeholder routes in nav  

---

## 3. Architecture goals (enable the UX)

### 3.1 Unify positioning (Track A + Track B + `/api/uwb`)

**Today:** Three parallel concepts (ingestion/UWB, scanner WiFi/BLE, in-memory UWB demo).

**Goal:** One **Location Core**

| Concept | Single model |
|---|---|
| Anchor | `Anchor` (protocol: UWB / BLE / WiFi / MOCK) |
| Trackable | `Tracker` (personnel/machine/sensor/asset) |
| Floor plan | `FloorPlan` + calibration transform |
| Live position | `PositionSnapshot` + SSE `/api/stream/positions` |
| History | `TrackingHistory` (flush/prune with app context) |

Scanner daemon becomes an **ingest adapter** that writes detections → Location Core → same SSE the Live Map consumes.

`/api/uwb` demo either becomes a profile behind Hardware or is retired from public API.

### 3.2 Reliability platform

- Auto-load `.env` at startup  
- Absolute default SQLite path; Postgres path documented  
- Mock hardware **auto-starts in development** (or first-run wizard)  
- History worker runs inside app context  
- Input validation layer (Marshmallow/Pydantic) on all mutating APIs  
- Contract + smoke tests in CI for every page + critical flows  

---

## 4. Feature-by-feature plan

For each feature: **What it is (user POV)** → **How it works today** → **Goals & proposed changes**.

---

### 4.1 Authentication & identity

#### 4.1.1 Login

**User POV:** Operator opens the app, signs in with email/username + password, optionally enters a 2FA code, lands on Live Map.

**How today:** `/login` + `/api/auth/login` (`email_or_username`, password, optional `totp_code`). JWT access + refresh in `localStorage`. Styled auth card exists.

**Goals / changes**
- Polish login as a **brand-first** screen (facility logo optional, HOLO-RTLS hero mark, calm atmospheric background).  
- “Remember me” must either work (longer refresh) or be removed.  
- Replace `alert()` password-reset feedback with in-UI toasts.  
- Load Font Awesome (or replace with SVG) so icons never break.  
- Post-login redirect to last page or Live Map; clear error copy for lockout.

#### 4.1.2 Registration

**User POV:** Admins create accounts (or invite users). Public self-signup is off in production.

**How today:** `POST /api/auth/register`; gated by module `DEBUG` (env), not app config — tests break when `FLASK_DEBUG=0`. No dedicated register page.

**Goals / changes**
- Admin-only registration in production via JWT + role (use `current_app.config`).  
- Optional invite-by-email flow later.  
- Users page remains the primary create path (see §4.12).

#### 4.1.3 JWT refresh & logout

**User POV:** Session stays alive during a shift; logout clears access everywhere on this browser.

**How today:** Refresh endpoint + client refresh in `api.js`; logout audits.

**Goals / changes**
- Silent refresh before expiry; on failure → login with reason.  
- Clear all `holo_*` keys consistently.  
- Optional: server-side token blocklist for logout/revoke.

#### 4.1.4 Two-factor authentication (TOTP)

**User POV:** Admin enables 2FA, scans QR, confirms code; later logins ask for code. Can disable with password + code.

**How today:** API setup/confirm/disable; QR in login flow; tests cover core paths.

**Goals / changes**
- Dedicated Settings → Security section for profile 2FA (not only login-time).  
- Recovery codes download (above-market).  
- Enforce 2FA for Admin role (policy toggle).

#### 4.1.5 Login lockout

**User POV:** After too many bad passwords, account temporarily locked with clear wait time.

**How today:** Configurable attempts/seconds; works.

**Goals / changes**
- Surface remaining lock time in API error payload + UI.  
- Audit lockout events (already partially covered).

#### 4.1.6 Password reset

**User POV:** “Forgot password” → email with link → set new password.

**How today:** Request always returns success message; **email send is stub**; reset token handling incomplete.

**Goals / changes**
- Real signed tokens (itsdangerous/JWT) + SMTP send when mail enabled.  
- Reset page UI (`/reset-password?token=`).  
- Dev mode: show reset link in UI/logs when `FLASK_MAIL_SUPPRESS_SEND=1`.

#### 4.1.7 Sessions (missing — BUILD_PLAN A09/U03/U04)

**User POV:** “Where am I logged in?” List devices/sessions; revoke one or all; admin force-logout.

**How today:** Not implemented.

**Goals / changes**
- `UserSession` model (jti, ip, user-agent, created, last_seen).  
- Profile → Sessions UI; Admin → force revoke on user detail.  
- Above-market: suspicious login alerts.

#### 4.1.8 RBAC (roles & permissions)

**User POV:** Viewers watch; operators manage day-to-day; admins configure site and users.

**How today:** VIEWER / OPERATOR / ADMIN matrix in `rbac_service`; `@require_permission` on APIs; nav partially gates admin items.

**Goals / changes**
- Align UI visibility with permissions everywhere.  
- Resolve plan vs code: node manage for Operator is OK if intentional — document it.  
- Add permission: `manage_hardware`, `manage_integrations`.  
- Viewer: read-only map + alerts (no setup tools).

---

### 4.2 Live Map / Command Center (`/`)

**User POV:** The home screen. See who/what is where on the floor plan (2D) or in a 3D facility view; filter assets; open a tag; ack alerts; play back history.

**How today:** Rich template + Leaflet/Three.js; KPIs; filters; layers; calibration wizard; tag card (vitals fields); heatmap; playback bar. **Live SSE on `/` opens without `?token=`** → live updates fail. Empty until hardware feeds Track A. DOM/JS ID mismatches break some controls. Edit tag → `/trackers` placeholder.

**Goals / changes**
- **Reliable live updates** (SSE with query token or cookie; reconnect indicator truthful).  
- First-run: auto mock feed or “Start demo” CTA.  
- Fix template↔JS wiring (search, notifications, playback, status).  
- Full-bleed map as the visual plane; side panel is a slim inspector, not a dashboard collage of competing widgets.  
- Hero budget for Monitor mode: brand (shell) + map + one inspector + alert toast stream.  
- Tag actions: locate, history, alarm, edit (opens finished Trackers drawer/modal).  
- 3D: non-deprecated Three build; floors from data not hardcoded 0–2 only.  
- Heatmap: dwell/time-based option (above-market), not only soft blobs.  
- Tablet layout: map + bottom alert sheet.

---

### 4.3 Live Tracking / Scanner map (`/tracking`)

**User POV today:** Separate “WiFi/BLE scanner” app for anchors, devices, floor plans.

**How today:** Canvas map; poll live positions; SSE with token; admin tabs. Parallel to Command Center (Track B).

**Goals / changes**
- **Fold into Live Map → Setup mode** (or rename to “Commissioning” under Site).  
- Keep powerful tools: place anchor, calibrate, upload floor plan, device registry.  
- Feed Location Core so Monitor mode shows the same devices.  
- UI: match shell; replace one-off inline CSS with design system.  
- Retire duplicate mental model (“which map is real?”).

---

### 4.4 Trackers / Tags (`/trackers`) — CRITICAL

**User POV:** Asset registry — assign tags to people/machines, see battery, status, last seen, category; create/edit/decommission; bulk import.

**How today:** **Placeholder page** (“Phase 2+”). Full CRUD API exists (`/api/trackers`) including reassign. Dashboard edit links die here. Create API rejects/coerces poorly (`hardware_id` int → 500).

**Goals / changes**
- **Ship a complete Trackers UI** (highest product priority after live map reliability).  
- Table + filters (type, status, battery, section, assignee) + search.  
- Detail drawer: identity, hardware binding, vitals last values, position deep-link to map, alert history.  
- Create/edit forms with validated enums; MAC normalization.  
- Bulk CSV import/export (BUILD_PLAN T05).  
- Decommission / archive (soft delete).  
- QR/barcode label print sheet (above-market nice-to-have).  
- Fix API type coercion + OpenAPI examples.

---

### 4.5 Anchors & Nodes (`/nodes` + scanner anchors)

**User POV:** Place fixed infrastructure that hears tags. See online/offline; edit coordinates; calibrate TX power.

**How today:** Nodes page for Track A `WifiNode`; scanner anchors separate; click-to-place unplaced nodes on map; no drag of existing markers; node offline alerting partial.

**Goals / changes**
- Unified **Anchors** page + map Setup tools.  
- Drag existing anchors on map; snap-to-grid optional.  
- Heartbeat / last_seen; offline badge + alert.  
- Calibration assistant (distance test, RSSI → meters preview).  
- Coverage quality visualization (above-market): rough trilateration confidence heat.

---

### 4.6 Zones & Sections (`/zones`)

**User POV:** Draw facility sections (polygons) and safety/operational zones (restricted, check-in, danger). Alerts fire when tags enter/leave/dwell.

**How today:** Form UI; sections paste JSON polygons; zones are spheres (x/y/z/radius). Creating `zone_type` as string `"RESTRICTED"` corrupts list (`GET /api/zones` → 500). Not map-native.

**Goals / changes**
- **Map-native editors** on Live Map Setup: draw polygon, resize circle, assign type/color.  
- Strict enum validation (ints or named enums with coercion).  
- Advanced zone rules (above-market / Sewio-like): enter, exit, dwell max, debounce UI.  
- Zone groups / visibility layers.  
- Repair path for bad historical rows.  
- Keep table view as secondary “list all zones”.

---

### 4.7 Alerts (`/alerts`)

**User POV:** See what needs attention; acknowledge; resolve; jump to the tag on the map.

**How today:** Strong page: filters, ack/resolve/ack-all, stats. Engine covers geo, restricted, battery, no-signal, etc. Proximity alerts missing. Some SSE token key inconsistency historically on pages.

**Goals / changes**
- Map deep-link from every alert (“Show on map”).  
- Owner / severity / notes on ack.  
- Proximity alert rules (tag-to-tag or tag-to-anchor distance).  
- Sound + desktop notification opt-in.  
- Consistent shell; remove floating-only chrome.  
- Incident timeline (above-market).

---

### 4.8 Notifications (in-app / email / SMS)

**User POV:** Bell icon for in-app events; optional email/SMS for critical alerts per preference.

**How today:** In-app notifications API; email/SMS code paths exist but mail suppressed; SMS needs phone field (missing on User); no per-user prefs.

**Goals / changes**
- User profile: email on/off, SMS on/off, severity threshold, quiet hours.  
- Add `User.phone` (E.164).  
- Settings → Integrations: SMTP + Twilio test buttons.  
- Digest email option (hourly/daily).  
- Never block alert creation if notify channel fails — log + show channel error in health.

---

### 4.9 Reports & analytics (`/reports`)

**User POV:** Answer “who was where?”, battery risk, alert mix; download CSV; later PDF/email schedule.

**How today:** Summary, activity, breakdown, daily/battery/distance CSV, full-export. No dwell report, PDF, scheduled email, or logo branding in exports.

**Goals / changes**
- Zone **dwell time** report (R03).  
- PDF export with facility logo (R07/R08).  
- Schedule report emails (R06) via APScheduler.  
- Trajectory / spaghetti preview for a tag+time range (above-market).  
- UI: clearer report cards, date-range picker, “Run” vs “Download”, empty-state guidance.  
- Embed charts that match design system (not a third theme).

---

### 4.10 Global search (`/search` + Ctrl+K)

**User POV:** Type a name/MAC/zone → jump there instantly.

**How today:** `/api/search` + search page; Command Center overlay partially broken (ID drift). Search can 500 if zones serialization breaks.

**Goals / changes**
- Shell-level command palette (Ctrl+K) on every page.  
- Ranked results with icons + “Open on map” actions.  
- Recent searches.  
- Hardened against bad related-entity serialization.

---

### 4.11 Hardware setup (`/hardware`)

**User POV:** Connect the physical world — pick a profile (DWM1001, Pozyx, mock…), configure port/MQTT, test, connect, see status.

**How today:** Rich UI + profile catalog. `POST .../test` works; **`.../connect` broken** (`get_config` called instead of `get_profile` → 404). Mock profile exists but not auto-started. Orphan template `dashboard/hardware.html`.

**Goals / changes**
- Fix connect path; status LEDs truthful.  
- Dev: one-click **Start mock simulation**.  
- Wizard: choose profile → connection → verify packets → bind anchors.  
- Delete orphan template.  
- Health panel: packets/sec, last error, reconnect.

---

### 4.12 Users (`/users`)

**User POV:** Admins manage who can access the system and at what role.

**How today:** List/create/edit/deactivate/reset password — solid.

**Goals / changes**
- Invite email; last login; 2FA status badge; sessions link.  
- Phone field for SMS.  
- UI polish to design system; avoid copy-pasted admin CSS.

---

### 4.13 Audit log (`/audit`)

**User POV:** Compliance — who changed what, when.

**How today:** Filterable viewer; client-side CSV.

**Goals / changes**
- Server-side export API (large logs).  
- Immutable retention policy setting.  
- Deep links to affected entities.  
- Tamper-evident hash chain optional (above-market / regulated sites).

---

### 4.14 Backup & restore (`/backup`)

**User POV:** Snapshot the database; download; restore after disaster.

**How today:** Manual trigger/list/download/restore works in smoke test. `BackupJob.trigger=scheduled` unused; no S3/remote; retention count env-only.

**Goals / changes**
- Scheduled backups (daily/weekly) via APScheduler.  
- Retention UI + enforcement.  
- Optional remote storage (S3-compatible).  
- Pre-restore warning + automatic safety snapshot.  
- Backup encryption at rest (above-market).

---

### 4.15 Settings (`/settings`)

**User POV:** Facility name, thresholds, appearance/logo, floor plans, system knobs.

**How today:** Tabs work; settings update via `PUT /api/settings/<key>` (bulk PATCH 405). Floor plans partially duplicated with scanner. SMTP/SMS mostly env. NTP missing.

**Goals / changes**
- Single settings API shape documented; UI uses per-key PUT or a real bulk endpoint.  
- Integrations tab: MQTT (TLS options), SMTP, Twilio, Scanner API key rotate.  
- Appearance: logo, accent color, login wallpaper.  
- Alert thresholds with live preview copy (“Battery critical at 15%”).  
- Timezone + NTP status (S06).  
- Unify floor-plan management here **and** map Setup (one API).

---

### 4.16 Floor plans & calibration

**User POV:** Upload building plan; click two known points; map pixels ↔ meters; tags appear in the right place.

**How today:** Calibration wizard on Command Center; settings floor plans; scanner floor plans — **two systems**.

**Goals / changes**
- One Floor Plan entity; multi-building / multi-floor tree.  
- Guided calibration with accuracy estimate.  
- Opacity/scale tools; plan versioning.  
- Above-market: CAD/PDF import assist (phase later).

---

### 4.17 Positioning engine (trilateration + Kalman)

**User POV:** Tags move smoothly and accurately enough for safety/ops (meters for BLE/WiFi; cm when UWB hardware connected).

**How today:** Two engines (`positioning_service`, `wifi_positioning`) + unit tests; scanner needs `mac_address` key and `real_x/real_y` on anchors or positions stay empty.

**Goals / changes**
- Single engine interface; adapters per signal type.  
- Document accuracy expectations by mode.  
- Outlier rejection + confidence score shown in UI.  
- Sensor fusion when UWB + BLE both present (above-market / Pozyx-like narrative).

---

### 4.18 Live stream (SSE) & MQTT

**User POV:** Map updates without refresh; optional plant systems get MQTT events.

**How today:** SSE works with `?token=` (verified); Command Center must pass token. MQTT connect fails gracefully if broker down. Publisher for state changes exists.

**Goals / changes**
- All EventSource clients use token (or httpOnly cookie auth).  
- Heartbeat events so UI can show “Live” vs “Reconnecting”.  
- MQTT settings UI + connection badge.  
- Topic documentation for integrators.

---

### 4.19 History & playback

**User POV:** Scrub time to see where someone was; export trail CSV.

**How today:** API + UI bar; history flush/prune may fail outside app context (F-3); playback wiring fragile.

**Goals / changes**
- Fix persistence workers.  
- Robust scrubber: range pick, speed, trail polyline, export.  
- Compare two tags (above-market).  
- Retention settings honored.

---

### 4.20 Scanner daemon (`scanner/`)

**User POV (edge tech):** Raspberry Pi / PC listens for WiFi/BLE, posts batches to the server.

**How today:** WiFi/BLE/mock; systemd unit; API key; default URL may point at wrong port; detection field names must match server.

**Goals / changes**
- Align payload schema + OpenAPI.  
- Default `BACKEND_URL=http://host:8080`.  
- Health endpoint; auto-register anchor with coordinates workflow.  
- Docs: mock demo in 2 commands.  
- No downlink yet — see §4.26.

---

### 4.21 UWB / hardware bridges

**User POV:** Plug supported hardware; tags appear with better accuracy.

**How today:** Profiles + serial/MQTT bridges; mock; `/api/uwb` demo separate.

**Goals / changes**
- Merge demo into mock/hardware path.  
- Connection doctor (permissions on `/dev/ttyUSB*`, baud, sample packet decode).  
- Per-profile setup illustrations in UI.

---

### 4.22 Check-in / muster (model only today)

**User POV:** Kiosk or zone marks personnel checked-in; emergency muster board shows who is missing.

**How today:** `CheckInLog` / `CheckInStatus` model fields — **no API/UI**.

**Goals / changes**
- Check-in/out zones + API events.  
- Muster mode on Live Map (big missing list — above-market for mines/tunnels).  
- Kiosk display page (fullscreen, simple).

---

### 4.23 API keys & developer integrations

**User POV (integrator):** Create a key for scanner/MES; revoke; see last used.

**How today:** `ApiKey` model + `MANAGE_API_KEY` permission — **no routes/UI/middleware**. Swagger exists. Nav “API Docs” OK.

**Goals / changes**
- `/api/keys` CRUD + hashed storage.  
- Admin Integrations page.  
- Middleware accepting `X-API-Key` on selected routes.  
- Webhooks for alert.created / zone.enter (I03).  
- External position inject endpoint (I04) for hybrid IPS.

---

### 4.24 Vitals & environmental sensors

**User POV:** See HR/SpO2/gas on a person or area sensor; alert on critical vitals / ENV_HAZARD.

**How today:** Fields on tracker + dashboard card; depends on MQTT vitals; no history API.

**Goals / changes**
- Vitals time-series API + mini charts.  
- Thresholds in settings.  
- Hide vitals UI when no vital-capable tags (progressive disclosure).

---

### 4.25 PWA / mobile

**User POV:** Install on tablet; get alert push; use outdoors in facility.

**How today:** manifest + service worker cache; push handler placeholder.

**Goals / changes**
- Tablet Live View layout.  
- Web push subscriptions (optional).  
- Offline shell with “reconnecting” for map.

---

### 4.26 Downlink / tag alarm (L03–L04)

**User POV:** Operator presses “Alarm” on a tag → tag buzzes/LED (hardware permitting).

**How today:** UI trigger / MQTT stub-ish; not reliable hardware downlink.

**Goals / changes**
- Hardware capability flag per profile.  
- Queue + ack from device.  
- Clear UI when hardware cannot downlink.

---

### 4.27 Proximity, LLM, multi-tenant (later / optional)

| Feature | User POV | Plan |
|---|---|---|
| Proximity alerts | Warn when two tags too close / too far | Phase C rules engine |
| LLM assistant | Natural language “who is in Zone B?” | **Out of scope** until core RTLS is excellent; keep as R&D doc only |
| Multi-facility tenancy | One deploy, many sites | Facility switcher after single-site excellence |
| Unity holographic client | Gaming-engine 3D | Separate product track — not this web app |

---

## 5. Page-by-page UI redesign goals

| Page | Attractive / professional / friendly goals |
|---|---|
| **Login** | Brand-first composition; atmospheric background; single clear form; excellent errors |
| **Live Map** | Full-bleed plan; slim inspector; restrained accents; live badge; empty→wizard |
| **Trackers** | Clean data table; status chips; drawer details; bulk actions |
| **Anchors** | Split view: table + mini-map; online dots |
| **Zones** | Prefer map editor; list secondary; color legend |
| **Alerts** | Severity rail; one-click ack; map jump; calm typography |
| **Reports** | Gallery of report types; preview; export buttons grouped |
| **Search** | Command palette aesthetic |
| **Hardware** | Stepper wizard; profile cards with real photos/diagrams if available |
| **Settings** | Segmented tabs; save bar sticky; test-connection buttons |
| **Users / Audit / Backup** | Same admin density language; helpful empty states |
| **Nav** | Icon + label; active state; collapse to icons; no emoji |

**Design deliverables (before heavy coding)**
1. Token sheet (CSS variables)  
2. Shell wireframe (desktop + tablet)  
3. Live Map Monitor mock  
4. Trackers list/detail mock  
5. Zone draw interaction spec  

---

## 6. Implementation program (phased)

> Calendar estimates intentionally omitted. Phases are dependency-ordered work packages.

### Phase A — Stabilize (“it always works”)
- Fix zones enum / list 500  
- Fix tracker `hardware_id` coercion  
- Fix hardware `connect`  
- Align scanner detection schema + anchor coordinates  
- SSE token on Command Center  
- History worker app context  
- Auto mock / first-run demo  
- `load_dotenv` + absolute DB default  
- Smoke + contract tests for above  

**Exit criteria:** Fresh clone → login → see moving tags within minutes; no 500 on normal flows.

### Phase B — Unify & finish core product
- Location Core merge (A/B)  
- Finish Trackers UI  
- Shared `base.html` shell + design tokens (UI system)  
- Map-native zone/anchor editing  
- Alerts map deep-link + proximity v1  
- Settings integrations tab  
- Password reset real path  

**Exit criteria:** One map product; no placeholders in nav; operators can run a shift.

### Phase C — Above-market differentiators
- Dwell reports + PDF + scheduled email  
- Muster / check-in  
- API keys + webhooks  
- Sessions revoke  
- Coverage confidence viz  
- Trajectory analytics  
- Tablet PWA live view  
- Scheduled encrypted backups + remote store  
- Advanced zone dwell rules  

**Exit criteria:** Feature set meets or exceeds mid-market RTLS software *software* expectations (hardware accuracy still depends on deployed radios).

### Phase D — Harden & scale
- Postgres default for production  
- Horizontal concerns: rate limits, audit export, retention jobs  
- Performance: 300+ tags stress test  
- Accessibility pass  
- Documentation rewrite (retire Unity-as-current)  
- Remove orphans (`dashboard/hardware.html`, unused UWB demo if merged)  

---

## 7. BUILD_PLAN ID coverage matrix

| ID | Feature | Plan target phase |
|---|---|---|
| A01–A05, A07–A08 | Auth core | Done → polish A/B |
| A06 | Password reset email | B |
| A09 | Sessions | C |
| D10 | ApiKey | C |
| D13 | CheckInLog | C |
| T01–T04, T06–T07 | Tracker API + **UI** | B |
| T05 | Bulk CSV | B |
| T08 | Drag nodes | B |
| T09 | Node offline | B |
| P01–P07 | Positioning / MQTT | A–B unify |
| G01–G08 | Alerts | Polish B |
| G09 | Proximity | C |
| V01–V09 | Visualization / playback / heatmap | A fix, C enhance |
| N01–N06 | Notifications + prefs | B/C |
| S01–S10 | Settings / SMTP / NTP / branding | B/C |
| U01–U04 | Users / force logout | B/C |
| R01–R08 | Reports / dwell / PDF / email | C |
| Q/C/I/B | Search, audit, API, backup schedule | B/C |
| L01 | LLM | Deferred R&D |
| L03–L06 | Downlink / muster | C |
| L02 | Heatmap enhance | C |

---

## 8. Testing & operational acceptance

### Automated
- Keep 67 unit tests green; expand for zones/scanner/hardware connect/settings.  
- New `tests/test_smoke_api.py` mirroring live smoke script.  
- Frontend: Playwright smoke — login, map loads, create tracker, draw zone, ack alert, export report.

### Manual UAT scripts (per role)
1. **Viewer:** login → map → search → view alert (cannot ack if policy says so).  
2. **Operator:** create tracker, ack alert, run report, place anchor.  
3. **Admin:** hardware mock, users, backup/restore, settings, API key.

### Operational “above market” checklist
- [ ] Time-to-first-live-tag < 15 minutes on demo hardware profile  
- [ ] Live badge accuracy  
- [ ] 8-hour soak without SSE death  
- [ ] Backup restore drill documented  
- [ ] Alert email received in staging  

---

## 9. Explicit non-goals (for this web product track)

- Rebuilding as Unity / C# DOD client  
- Shipping a local LLM assistant before core RTLS excellence  
- Matching UWB **physical accuracy** of Sewio/Pozyx without equivalent anchor hardware  
- Multi-tenant SaaS billing  

---

## 10. Success definition — “100% functional & above market”

The product is done when:

1. **Every nav destination is a finished workflow.**  
2. **One Location Core** powers Monitor, Setup, and Playback.  
3. **Fresh install** yields live motion without tribal knowledge.  
4. **No class of bug** like enum/string 500s remains on validated APIs.  
5. **UI** passes the brand/shell/contrast/motion bar in §2.  
6. **Feature set** covers registry, map-native geofence, alerts+notify, dwell analytics, muster, API keys, scheduled backup — i.e. mid-market RTLS *software* parity or better.  
7. **Docs** describe the system that actually exists.

---

## 11. Suggested delivery order (first coding milestones)

When implementation is authorized (separate change sets):

1. Phase A reliability PR  
2. Design-system + `base.html` shell PR (UI foundation)  
3. Trackers page PR  
4. Location Core unification PR  
5. Map-native zones/anchors PR  
6. Phase C differentiators in thin vertical slices  

---

*End of master plan. No application source code was modified to produce this document.*
