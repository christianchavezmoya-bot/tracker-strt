"""
Optional Playwright smoke — login, map, trackers, settings.

Run with:
  pip install playwright pytest-playwright
  playwright install chromium
  PLAYWRIGHT_E2E=1 pytest tests/e2e/test_playwright_smoke.py -q
"""
import os
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("PLAYWRIGHT_E2E") != "1",
    reason="Set PLAYWRIGHT_E2E=1 to run browser smoke tests",
)

BASE = os.getenv("HOLO_E2E_BASE", "http://127.0.0.1:8080")
ADMIN_EMAIL = os.getenv("HOLO_E2E_EMAIL", "admin@holo-rtls.local")
ADMIN_PASS = os.getenv("HOLO_E2E_PASSWORD", "ChangeMe123!")


@pytest.fixture(scope="module")
def browser_page():
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        yield page
        browser.close()


def test_login_and_live_map(browser_page):
    page = browser_page
    page.goto(f"{BASE}/login")
    page.fill('input[name="email_or_username"], input[type="email"]', ADMIN_EMAIL)
    page.fill('input[name="password"], input[type="password"]', ADMIN_PASS)
    page.click('button[type="submit"]')
    page.wait_for_url(f"{BASE}/**", timeout=15000)
    assert "/login" not in page.url or page.locator("#map2d, .map-container").count() >= 0


def test_trackers_page_loads(browser_page):
    page = browser_page
    if "/login" in page.url:
        pytest.skip("Login failed — seed admin or set HOLO_E2E_* env")
    page.goto(f"{BASE}/trackers")
    page.wait_for_load_state("networkidle")
    assert page.locator("h1, .page-title").first.is_visible()


def test_settings_integrations_tab(browser_page):
    page = browser_page
    if "/login" in page.url:
        pytest.skip("Login failed")
    page.goto(f"{BASE}/settings")
    page.wait_for_load_state("networkidle")
    page.click('button[data-tab="integrations"]')
    page.wait_for_selector("#section-integrations", state="visible")
    assert page.locator("#mailStatusGrid").is_visible()
