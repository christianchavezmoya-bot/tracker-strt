# HOLO-RTLS — Current System (canonical)

> **This document describes the shipped web product.** Unity/C# notes in `architecture.md` and `roadmap.md` are R&D only unless marked otherwise.

## What it is

**HOLO-RTLS** is a Flask + Jinja **indoor RTLS operations console**: live map, asset registry, geofencing, alerts, reports, hardware commissioning, and admin tooling. One **Location Core** feeds Monitor, Setup, and Playback on the Live Map.

## Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.10+, Flask, SQLAlchemy, JWT |
| Database | SQLite (dev) / PostgreSQL (prod) — see `docs/POSTGRES.md` |
| Frontend | Jinja templates, vanilla JS, Leaflet 2D map, shared `base.html` shell |
| Real-time | SSE `/api/stream/positions`, optional MQTT |
| Edge | `scanner/` WiFi/BLE daemon, hardware bridges (mock/UWB/MQTT) |

## Primary surfaces

| URL | Purpose |
|-----|---------|
| `/` | Live Map — Monitor / Setup / Playback |
| `/trackers` | Asset registry |
| `/alerts` | Alert queue |
| `/reports` | Analytics + PDF/CSV export + schedules |
| `/settings` | Facility, thresholds, integrations, Web Push |
| `/integrations` | API keys + webhooks |
| `/muster` | Emergency muster board |
| `/tracking?legacy=1` | Scanner lab (deprecated path; redirects without `legacy=1`) |

## Auth

- Email/username + password; optional TOTP 2FA
- **Remember me**: tokens in `localStorage` (default) or `sessionStorage` when unchecked
- Roles: VIEWER, OPERATOR, ADMIN (`rbac_service`)

## Default demo login

`admin@holo-rtls.local` / `ChangeMe123!`

First boot seeds admin + mock hardware so tags move on the Live Map.

## Implementation plan

Active delivery plan: **`docs/MASTER_PLAN_ABOVE_MARKET.md`**  
Progress log: **`docs/EXECUTION_REPORT.md`**

## Tests

```bash
pytest tests/ -q --ignore=tests/e2e
```

Optional browser smoke: `PLAYWRIGHT_E2E=1 pytest tests/e2e/` with app on port 8080.
