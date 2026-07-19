# Execution Report — Above-Market Continuation

**Branch:** `cursor/holo-rtls-execute-plan-af22` (not merged to `master`)  
**Date:** 2026-07-19  
**Tests:** `pytest` → see latest commit  
**Smoke:** zones+rules, section polygon, UWB deprecated flag, backup list

---

## This pass

### Map Setup (Location Core)
- Circle **zone draw form** (no `prompt()`): type, radius, dwell-max / on-enter / on-exit rules
- **Section polygon** draw mode (click vertices → Finish → form with restricted + color)
- Toolbar: separate zone (circle) vs section (polygon) buttons; viewer RBAC hides both

### Zones / Alerts
- `Zone.rules_json` + API create/update `rules`
- AlertService: session-safe section polygon snaps; **dwell_max_seconds** evaluation
- SQLite schema patch for `rules_json`

### Location Core / UWB
- `/api/uwb/*` marked `deprecated: true` with successor pointers
- `/tracking` top banner → Live Map as primary surface

### Backup / Prod
- Optional Fernet encryption (`BACKUP_ENCRYPT_KEY` + `cryptography`)
- Pre-restore safety snapshot; decrypt-on-restore for `.enc`
- Schedule API reports `encryption_enabled`
- `docs/POSTGRES.md` + `psycopg2-binary` in requirements

### Shell
- `muster.html` + `trackers.html` extend `base.html`

---

## Still intentionally thin / later
- Full `base.html` migration of remaining pages (settings, hardware, zones list, etc.)
- Confidence-based coverage heat (still fixed rings)
- Fully retire `/tracking` + `/api/uwb` (routes kept for lab compat)
- Remote/offsite backup targets; Postgres as enforced prod default
- 300+ stress / Playwright / a11y suite
- LLM / Unity / multi-tenant (plan non-goals)

Default login: `admin@holo-rtls.local` / `ChangeMe123!`
