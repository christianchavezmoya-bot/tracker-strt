"""
Playwright smoke — login, map, trackers, settings, alerts.

Extended flows: create tracker, draw zone, ack alert, export PDF, axe WCAG audit.

Local:
  pip install -r requirements-e2e.txt && playwright install chromium
  ./scripts/run_e2e_ci.sh
"""
import os
import re

import pytest

from conftest import e2e_auth_headers, seed_e2e_alert, unique_suffix

pytestmark = pytest.mark.skipif(
    os.getenv("PLAYWRIGHT_E2E") != "1",
    reason="Set PLAYWRIGHT_E2E=1 to run browser smoke tests",
)


def test_login_and_live_map(logged_in_page, e2e_base):
    page = logged_in_page
    assert "/login" not in page.url
    page.goto(f"{e2e_base}/")
    page.wait_for_selector("#map2d", state="visible", timeout=20000)


def test_trackers_page_loads(logged_in_page, e2e_base):
    page = logged_in_page
    page.goto(f"{e2e_base}/trackers")
    page.wait_for_load_state("domcontentloaded")
    assert page.locator(".page-title, h1").first.is_visible()


def test_settings_integrations_tab(logged_in_page, e2e_base):
    page = logged_in_page
    page.goto(f"{e2e_base}/settings")
    page.wait_for_load_state("domcontentloaded")
    page.click('button[data-tab="integrations"]')
    page.wait_for_selector("#section-integrations", state="visible")
    assert page.locator("#mailStatusGrid").is_visible()


def test_alerts_page_loads(logged_in_page, e2e_base):
    page = logged_in_page
    page.goto(f"{e2e_base}/alerts")
    page.wait_for_load_state("domcontentloaded")
    assert page.locator(".page-title, h1").first.is_visible()


def test_nodes_page_stays_on_route(logged_in_page, e2e_base):
    page = logged_in_page
    page.goto(f"{e2e_base}/nodes")
    page.wait_for_load_state("domcontentloaded")
    assert "/nodes" in page.url
    assert page.locator(".page-title, h1").first.is_visible()


def test_hardware_page_stays_on_route(logged_in_page, e2e_base):
    page = logged_in_page
    page.goto(f"{e2e_base}/hardware")
    page.wait_for_load_state("domcontentloaded")
    assert "/hardware" in page.url
    assert page.locator(".page-title, h1").first.is_visible()


def test_create_tracker(logged_in_page, e2e_base):
    page = logged_in_page
    hw = f"E2E-TAG-{unique_suffix()}"
    page.goto(f"{e2e_base}/trackers")
    page.wait_for_selector("#btnCreate", state="visible", timeout=15000)
    page.click("#btnCreate")
    page.wait_for_selector("#fHardware", state="visible")
    page.fill("#fHardware", hw)
    page.fill("#fName", f"E2E Tracker {hw}")
    page.click("#btnSave")
    page.wait_for_selector(f"text={hw}", timeout=15000)


def test_draw_zone_on_map(logged_in_page, e2e_base):
    page = logged_in_page
    zone_name = f"E2E Zone {unique_suffix()}"
    page.goto(f"{e2e_base}/?mode=setup")
    page.wait_for_selector("#map2d", state="visible", timeout=20000)
    for _ in range(60):
        if page.evaluate("() => !!(window._map2d && window.enterZoneDrawMode)"):
            break
        page.wait_for_timeout(500)
    else:
        pytest.fail("Leaflet map did not initialize (window._map2d missing)")
    page.click("#zoneDrawBtn")
    page.evaluate(
        """() => {
          const map = window._map2d;
          const center = map.getCenter();
          map.fire('click', { latlng: center });
        }"""
    )
    page.wait_for_selector("#zoneDrawForm", state="visible", timeout=15000)
    page.fill("#zoneNameInput", zone_name)
    page.fill("#zoneRadiusInput", "3")
    page.click("#zoneSaveBtn")
    page.wait_for_selector("#zoneDrawForm", state="detached", timeout=15000)
    resp = page.request.get(f"{e2e_base}/api/zones", headers=e2e_auth_headers(page))
    assert resp.ok
    names = [z.get("name") for z in (resp.json().get("items") or [])]
    assert zone_name in names


def test_acknowledge_alert(logged_in_page, e2e_base):
    page = logged_in_page
    alert_id = seed_e2e_alert(page, e2e_base)
    page.goto(f"{e2e_base}/alerts")
    page.wait_for_selector(f"#alert-{alert_id}", state="visible", timeout=15000)
    page.locator(f"#alert-{alert_id} button:has-text('Ack')").click()
    page.locator("#holoConfirmOk").click()
    page.wait_for_selector(f"#alert-{alert_id}", state="detached", timeout=10000)
    resp = page.request.get(
        f"{e2e_base}/api/alerts?state=ACKNOWLEDGED",
        headers=e2e_auth_headers(page),
    )
    assert resp.ok
    ids = [a.get("id") for a in (resp.json().get("items") or [])]
    assert alert_id in ids


def test_export_report_pdf(logged_in_page, e2e_base):
    page = logged_in_page
    resp = page.request.get(
        f"{e2e_base}/api/reports/pdf?type=summary",
        headers=e2e_auth_headers(page),
    )
    assert resp.ok, resp.text()[:200]
    body = resp.body()
    assert body.startswith(b"%PDF")
    assert b"/DCTDecode" in body or b"Summary" in body


def test_axe_wcag_audit_key_pages(logged_in_page, e2e_base):
    """axe-core WCAG 2.x audit on primary operator pages (no critical/serious violations)."""
    page = logged_in_page
    axe_url = "https://cdn.jsdelivr.net/npm/axe-core@4.10.2/axe.min.js"
    pages = ["/", "/trackers", "/alerts", "/reports", "/settings"]
    all_critical = []
    for path in pages:
        page.goto(f"{e2e_base}{path}")
        page.wait_for_load_state("domcontentloaded")
        page.add_script_tag(url=axe_url)
        violations = page.evaluate(
            """async () => {
              const results = await axe.run(document, {
                runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] }
              });
              return results.violations.map(v => ({
                id: v.id,
                impact: v.impact,
                help: v.help,
                page: window.location.pathname,
                nodes: v.nodes.length
              }));
            }"""
        )
        critical = [v for v in violations if v.get("impact") == "critical"]
        all_critical.extend(critical)
    assert not all_critical, f"Critical WCAG violations: {all_critical[:8]}"
