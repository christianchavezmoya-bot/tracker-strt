# Pre-Merge Smoke Report — HOLO-RTLS

**Date:** 2026-07-19 (updated after gap fixes)  
**Branch:** `cursor/holo-rtls-execute-plan-af22`  
**PR:** [#2](https://github.com/christianchavezmoya-bot/tracker-strt/pull/2)

---

## Verdict: **READY for stakeholder merge review**

| Gate | Status |
|------|--------|
| pytest (105 tests) | **PASS** |
| Playwright E2E (9 tests) | **PASS** |
| SSE soak (CI short + 8h script) | **PASS** / script provided |
| axe-core WCAG (critical) | **PASS** |
| GitHub CI | Expected green on push |
| Push to `master` | **Not performed** |

---

## Gap fixes implemented (this pass)

| Gap | Fix |
|-----|-----|
| SSE 8h soak | `tests/test_sse_soak.py` (CI ~45s) + `scripts/sse_soak.sh` / `scripts/sse_soak_runner.py` (default 8h) |
| E2E flows | Added create tracker, draw zone, ack alert, export PDF + axe audit |
| axe-core WCAG | E2E `test_axe_wcag_audit_key_pages` + aria-label fixes on filters/reports |
| `proximity_meters` 404 | Seeded defaults + GET fallback via `settings_defaults.py` |
| Branded PDF charts | Pillow JPEG bar chart embedded in PDF (`/DCTDecode`) |
| Legacy `/tracking` | Template removed; route redirects to `/?mode=setup` |

---

## Test commands

```bash
pytest tests/ -q --ignore=tests/e2e          # 105 passed
./scripts/run_e2e_ci.sh                      # 9 passed
SSE_SOAK_SECONDS=45 pytest tests/test_sse_soak.py -q
./scripts/sse_soak.sh                          # 8h ops soak (app must be running)
```

Default login: `admin@holo-rtls.local` / `ChangeMe123!`

---

*No merge to `master` without explicit approval.*
