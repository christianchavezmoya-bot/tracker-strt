# Execution Report — Above-Market Continuation

**Branch:** `cursor/holo-rtls-execute-plan-af22` (not merged to `master`)  
**Date:** 2026-07-19  
**Tests:** `pytest` → **78 passed**

---

## This pass

### Shell migration (complete for admin ops pages)
- Migrated to `base.html`: **zones, backup, reports, nodes, hardware, settings**
- (Previously: trackers, muster, integrations, alerts, audit, users, search)

### Location Core retirement
- `/tracking` → redirects to `/?mode=setup` unless `?legacy=1` (or `HOLO_TRACKING_LEGACY_DEFAULT=1`)
- Nav/palette Scanner lab uses `/tracking?legacy=1`
- `GET /api/positioning/sources` — Location Core status + source list
- `/api/uwb` responses include `Deprecation` / `Link` successor headers
- Settings **Location Core** tab with live stats + deep links

### Anchors / coverage
- Node form: optional **coverage radius** → `metadata.coverage_radius_m`

---

## Still intentionally thin / later
- Live Map / tracking / login remain custom (intentional for full-bleed map & auth)
- Complete code removal of `/api/uwb` + `/tracking` templates
- Playwright / stress / a11y
- LLM / Unity / multi-tenant (non-goals)

Default login: `admin@holo-rtls.local` / `ChangeMe123!`
