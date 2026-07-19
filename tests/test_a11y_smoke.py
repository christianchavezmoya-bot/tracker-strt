"""Accessibility smoke checks (static HTML/JS/CSS)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_base_has_skip_link():
    html = (ROOT / "frontend/templates/base.html").read_text()
    assert 'class="skip-link"' in html
    assert 'href="#main-content"' in html


def test_api_has_holo_confirm_and_aria_live():
    js = (ROOT / "frontend/static/js/api.js").read_text()
    assert "window.holoConfirm" in js
    assert "aria-live" in js
    assert "alertdialog" in js


def test_shell_reduced_motion():
    css = (ROOT / "frontend/static/css/shell.css").read_text()
    assert "prefers-reduced-motion" in css


def test_no_native_confirm_in_admin_ui():
    bare = []
    for p in (ROOT / "frontend").rglob("*"):
        if p.suffix not in (".html", ".js") or "tracking.html" in str(p):
            continue
        for i, line in enumerate(p.read_text().splitlines(), 1):
            if "confirm(" in line and "holoConfirm" not in line:
                bare.append(f"{p.relative_to(ROOT)}:{i}")
    assert not bare, f"native confirm() still used: {bare[:10]}"
