"""
Playwright smoke — login, map, trackers, settings, alerts.

Local:
  pip install -r requirements-e2e.txt && playwright install chromium
  ./scripts/run_e2e_ci.sh

Or with a running app:
  PLAYWRIGHT_E2E=1 pytest tests/e2e/test_playwright_smoke.py -q
"""
import os
import pytest

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
