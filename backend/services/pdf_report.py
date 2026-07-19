"""Minimal PDF generator (no external PDF libs)."""
from __future__ import annotations


def rows_to_pdf(title: str, rows: list) -> bytes:
    """Build a simple single-page PDF with title + table-like text lines."""
    lines = [title, "=" * min(60, max(len(title), 20)), ""]
    if not rows:
        lines.append("No data for this report.")
    else:
        keys = list(rows[0].keys())
        lines.append(" | ".join(str(k) for k in keys))
        lines.append("-" * 60)
        for row in rows[:80]:
            lines.append(" | ".join(str(row.get(k, ""))[:40] for k in keys))
    content = "\n".join(lines)
    return _text_pdf(content)


def _text_pdf(text: str) -> bytes:
    # Escape PDF special chars
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    # Split into lines for Tj operators
    pdf_lines = []
    y = 780
    for raw in safe.split("\n"):
        if y < 40:
            break
        pdf_lines.append(f"BT /F1 10 Tf 40 {y} Td ({raw[:110]}) Tj ET")
        y -= 14
    stream = "\n".join(pdf_lines).encode("latin-1", errors="replace")
    objects = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    objects.append(
        f"4 0 obj<< /Length {len(stream)} >>stream\n".encode() + stream + b"\nendstream\nendobj\n"
    )
    objects.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return bytes(out)
