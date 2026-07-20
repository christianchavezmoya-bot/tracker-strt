#!/usr/bin/env python3
"""Capture screenshots + CSS theme tokens across HOLO-RTLS pages."""
import json
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.getenv("HOLO_E2E_BASE", "http://127.0.0.1:8080")
EMAIL = os.getenv("HOLO_E2E_EMAIL", "admin@holo-rtls.local")
PASSWORD = os.getenv("HOLO_E2E_PASSWORD", "ChangeMe123!")
OUT = Path("/opt/cursor/artifacts/theme-smoke")
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    ("live-map", "/"),
    ("map-setup", "/?mode=setup"),
    ("anchors", "/nodes"),
    ("hardware", "/hardware"),
    ("zones", "/zones"),
    ("trackers", "/trackers"),
    ("settings", "/settings"),
    ("alerts", "/alerts"),
]

THEME_JS = """() => {
  const root = getComputedStyle(document.documentElement);
  const body = getComputedStyle(document.body);
  const topbar = document.querySelector('.topbar, .shell-topbar');
  const tb = topbar ? getComputedStyle(topbar) : null;
  const stylesheets = [...document.styleSheets]
    .map(s => { try { return s.href || '[inline]'; } catch(e) { return '[blocked]'; } })
    .filter(Boolean);
  return {
    url: location.href,
    pathname: location.pathname + location.search,
    title: document.title,
    bodyClass: document.body.className,
    stylesheets,
    cssVars: {
      bgPrimary: root.getPropertyValue('--bg-primary').trim(),
      accent: root.getPropertyValue('--accent').trim(),
      cyan: root.getPropertyValue('--cyan').trim(),
      textPrimary: root.getPropertyValue('--text-primary').trim(),
      topbarH: root.getPropertyValue('--topbar-h').trim(),
      fontUi: root.getPropertyValue('--font-ui').trim(),
    },
    computed: {
      bodyBg: body.backgroundColor,
      bodyColor: body.color,
      bodyFont: body.fontFamily.slice(0, 80),
      topbarBg: tb ? tb.backgroundColor : null,
      topbarHeight: tb ? tb.height : null,
    },
    layout: {
      hasShellMain: !!document.querySelector('.shell-main'),
      hasAnalyticsRow: !!document.getElementById('analyticsRow'),
      hasMap2d: !!document.getElementById('map2d'),
      hasNavToggle: !!document.querySelector('.holonav-toggle'),
      hasBrandSub: !!document.querySelector('.brand-sub'),
      pageTitle: document.querySelector('.page-title')?.textContent?.trim() || null,
    },
    errors: window.__themeSmokeErrors || [],
  };
}"""


def main():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        page.wait_for_selector("#emailInput", timeout=15000)
        page.fill("#emailInput", EMAIL)
        page.fill("#passwordInput", PASSWORD)
        page.click("#loginBtn")
        page.wait_for_url(re.compile(r".*(?<!/login)$"), timeout=25000)

        for slug, path in PAGES:
            console_errors.clear()
            page.goto(f"{BASE}{path}", wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            if path == "/" or path.startswith("/?"):
                try:
                    page.wait_for_selector("#map2d", state="visible", timeout=12000)
                except Exception:
                    pass
            else:
                try:
                    page.wait_for_selector(".page-title, h1, .shell-main", timeout=8000)
                except Exception:
                    pass

            shot = OUT / f"{slug}.png"
            page.screenshot(path=str(shot), full_page=False)
            data = page.evaluate(THEME_JS)
            data["slug"] = slug
            data["finalUrl"] = page.url
            data["redirected"] = not page.url.rstrip("/").endswith(path.rstrip("/").split("?")[0]) and "mode=setup" not in page.url if "mode=setup" in path else page.url != f"{BASE}{path}"
            if "mode=setup" in path:
                data["redirected"] = "mode=setup" not in page.url
            elif path not in ("/",):
                data["redirected"] = path.split("?")[0] not in page.url
            data["consoleErrors"] = console_errors[:8]
            results.append(data)
            print(f"OK {slug}: {page.url} -> {shot.name}")

        browser.close()

    report = {"pages": results}
    (OUT / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
