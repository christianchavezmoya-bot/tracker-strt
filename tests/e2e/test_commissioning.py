"""
Playwright E2E — RTLS commissioning UI (readiness checklist, diagnostics tab).

Local:
  PLAYWRIGHT_E2E=1 ./scripts/run_e2e_ci.sh
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("PLAYWRIGHT_E2E") != "1",
    reason="Set PLAYWRIGHT_E2E=1 to run browser smoke tests",
)


def test_dashboard_rtls_readiness_panel(logged_in_page, e2e_base):
    page = logged_in_page
    page.goto(f"{e2e_base}/")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_selector("#rtlsReadinessPanel", state="visible", timeout=20000)
    for _ in range(40):
        text = page.locator("#rtlsReadinessPanel").inner_text()
        if "SETUP PROGRESS" in text:
            break
        page.wait_for_timeout(500)
    assert "SETUP PROGRESS" in page.locator("#rtlsReadinessPanel").inner_text()


def test_nodes_diagnostics_tab(logged_in_page, e2e_base):
    page = logged_in_page
    page.goto(f"{e2e_base}/nodes")
    page.wait_for_load_state("domcontentloaded")
    page.click('button.node-tab[data-view="diagnostics"]')
    page.wait_for_selector("#diagnosticsTable", state="visible", timeout=15000)
    page.wait_for_selector("#diagBrokerSummary", state="visible", timeout=15000)
    broker_text = page.locator("#diagBrokerSummary").inner_text()
    assert "Broker" in broker_text or "Port" in broker_text


def test_settings_network_mqtt_tab(logged_in_page, e2e_base):
    page = logged_in_page
    page.goto(f"{e2e_base}/settings")
    page.wait_for_load_state("domcontentloaded")
    page.click('button[data-tab="network"]')
    page.wait_for_selector("#section-network", state="visible", timeout=15000)
    page.wait_for_selector("#mqttNetworkStatus", state="visible", timeout=15000)
    for _ in range(40):
        text = page.locator("#mqttNetworkStatus").inner_text()
        if "Status" in text or "Failed" in text:
            break
        page.wait_for_timeout(500)
    assert page.locator("#mqttBrokerToggle").is_visible()
