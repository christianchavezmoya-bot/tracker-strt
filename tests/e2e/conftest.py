"""Playwright E2E fixtures."""
import os
import pytest

BASE = os.getenv("HOLO_E2E_BASE", "http://127.0.0.1:8080")
ADMIN_EMAIL = os.getenv("HOLO_E2E_EMAIL", "admin@holo-rtls.local")
ADMIN_PASS = os.getenv("HOLO_E2E_PASSWORD", "ChangeMe123!")


@pytest.fixture(scope="session")
def e2e_base():
    return BASE


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


@pytest.fixture(scope="module")
def logged_in_page(browser_page, e2e_base):
    page = browser_page
    page.goto(f"{e2e_base}/login")
    page.wait_for_selector("#emailInput", state="visible", timeout=15000)
    page.fill("#emailInput", ADMIN_EMAIL)
    page.fill("#passwordInput", ADMIN_PASS)
    page.click("#loginBtn")
    page.wait_for_function(
        "() => !window.location.pathname.includes('/login')",
        timeout=25000,
    )
    return page
