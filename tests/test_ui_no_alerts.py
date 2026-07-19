def test_no_alert_calls_in_admin_templates():
    """Phase B UX: admin templates should use showToast, not alert()."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "frontend"
    offenders = []
    for p in root.rglob("*.html"):
        text = p.read_text()
        if "alert(" in text:
            offenders.append(str(p.relative_to(root.parent)))
    assert not offenders, f"alert() still used in: {offenders}"
