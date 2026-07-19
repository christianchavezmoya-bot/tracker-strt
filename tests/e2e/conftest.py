"""Playwright E2E fixtures."""
import os
import re
import time

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
    page.wait_for_url(re.compile(r".*(?<!/login)$"), timeout=25000)
    return page


def e2e_auth_headers(page) -> dict:
    token = page.evaluate(
        "() => localStorage.getItem('holo_access_token') || localStorage.getItem('access_token')"
    )
    return {"Authorization": f"Bearer {token}"}


def seed_e2e_alert(page, e2e_base) -> int:
    resp = page.request.post(
        f"{e2e_base}/api/e2e/seed-alert",
        headers=e2e_auth_headers(page),
    )
    assert resp.ok, resp.text()
    return resp.json()["alert"]["id"]


def unique_suffix() -> str:
    return str(int(time.time() * 1000) % 1000000)
