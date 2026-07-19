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
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        yield page
        context.close()
        browser.close()


def _login(page):
    page.goto(f"{BASE}/login")
    page.wait_for_selector("#emailInput", state="visible")
    page.fill("#emailInput", ADMIN_EMAIL)
    page.fill("#passwordInput", ADMIN_PASS)
    page.click("#loginBtn")
    page.wait_for_function("() => !window.location.pathname.includes('/login')", timeout=20000)


def test_login_and_live_map(browser_page):
    page = browser_page
    _login(page)
    assert "/login" not in page.url
    page.wait_for_selector("#map2d", state="visible", timeout=15000)


def test_trackers_page_loads(browser_page):
    page = browser_page
    if "/login" in page.url:
        _login(page)
    page.goto(f"{BASE}/trackers")
    page.wait_for_load_state("domcontentloaded")
    assert page.locator(".page-title, h1").first.is_visible()


def test_settings_integrations_tab(browser_page):
    page = browser_page
    if "/login" in page.url:
        _login(page)
    page.goto(f"{BASE}/settings")
    page.wait_for_load_state("domcontentloaded")
    page.click('button[data-tab="integrations"]')
    page.wait_for_selector("#section-integrations", state="visible")
    assert page.locator("#mailStatusGrid").is_visible()


def test_alerts_page_loads(browser_page):
    page = browser_page
    if "/login" in page.url:
        _login(page)
    page.goto(f"{BASE}/alerts")
    page.wait_for_load_state("domcontentloaded")
    assert page.locator(".page-title, h1").first.is_visible()
