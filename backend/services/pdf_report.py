"""Branded PDF generator for HOLO-RTLS reports (no external PDF libs)."""
from __future__ import annotations
from datetime import datetime, timezone


def rows_to_pdf(title: str, rows: list, *, subtitle: str = None, site_name: str = None) -> bytes:
    """Build a multi-line PDF with HOLO-RTLS header + table-like text."""
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    brand = site_name or "HOLO-RTLS"
    lines = [
        "HOLO-RTLS",
        brand if brand != "HOLO-RTLS" else "Indoor Real-Time Location System",
        "",
        title,
        subtitle or "",
        f"Generated: {generated}",
        "=" * 72,
        "",
    ]
    if not rows:
        lines.append("No data for this report window.")
    else:
        keys = list(rows[0].keys())
        # Column header
        header = " | ".join(str(k) for k in keys)
        lines.append(header)
        lines.append("-" * min(72, max(len(header), 20)))
        for row in rows[:200]:
            lines.append(" | ".join(str(row.get(k, ""))[:48] for k in keys))
        if len(rows) > 200:
            lines.append("")
            lines.append(f"… {len(rows) - 200} additional rows omitted")
    lines.extend(["", "-" * 72, "Confidential — HOLO-RTLS operations report"])
    return _text_pdf("\n".join(lines), title=title)


def _text_pdf(text: str, title: str = "HOLO-RTLS Report") -> bytes:
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    # Multi-page: 52 lines per page at 14pt spacing from y=760
    raw_lines = safe.split("\n")
    pages = []
    page_lines = []
    y = 760
    for raw in raw_lines:
        if y < 50:
            pages.append(page_lines)
            page_lines = []
            y = 760
        # Title line uses larger font
        if not page_lines and raw == "HOLO-RTLS":
            page_lines.append(f"BT /F2 16 Tf 40 {y} Td ({raw[:90]}) Tj ET")
            y -= 22
        else:
            page_lines.append(f"BT /F1 9 Tf 40 {y} Td ({raw[:110]}) Tj ET")
            y -= 12
    if page_lines:
        pages.append(page_lines)
    if not pages:
        pages = [["BT /F1 10 Tf 40 760 Td (Empty report) Tj ET"]]

    objects = []
    # Catalog + Pages will be rebuilt with kids
    page_obj_nums = []
    content_obj_nums = []

    # We'll assemble: 1=Catalog, 2=Pages, 3=Font, 4=FontBold, then pairs of Page+Content
    # Simpler approach: rebuild with sequential numbering

    # Object 1: Catalog
    # Object 2: Pages
    # Object 3: Helvetica
    # Object 4: Helvetica-Bold
    # Then for each page i: page obj, content obj

    kids = []
    content_streams = []
    for i, cmds in enumerate(pages):
        stream = "\n".join(cmds).encode("latin-1", errors="replace")
        content_streams.append(stream)
        kids.append(i)

    # Build objects list dynamically
    objs: list[bytes] = []
    # placeholders indices
    # 1 catalog, 2 pages, 3 font, 4 font bold
    objs.append(b"")  # index 0 unused conceptually; we'll use 1-based in PDF

    def add_obj(data: bytes) -> int:
        objs.append(data)
        return len(objs) - 1

    # Reserve slots
    catalog_i = add_obj(b"")
    pages_i = add_obj(b"")
    font_i = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    bold_i = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

    page_refs = []
    for stream in content_streams:
        content_i = add_obj(
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )
        page_i = add_obj(
            (
                f"<< /Type /Page /Parent {pages_i} 0 R /MediaBox [0 0 612 792] "
                f"/Contents {content_i} 0 R "
                f"/Resources << /Font << /F1 {font_i} 0 R /F2 {bold_i} 0 R >> >> >>"
            ).encode()
        )
        page_refs.append(page_i)

    # Fill catalog + pages
    kids_str = " ".join(f"{n} 0 R" for n in page_refs)
    objs[pages_i] = f"<< /Type /Pages /Kids [{kids_str}] /Count {len(page_refs)} >>".encode()
    objs[catalog_i] = f"<< /Type /Catalog /Pages {pages_i} 0 R >>".encode()

    # Also set document info
    info_i = add_obj(
        f"<< /Title ({title[:80].replace('(', '').replace(')', '')}) "
        f"/Creator (HOLO-RTLS) /Producer (HOLO-RTLS PDF) >>".encode()
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i in range(1, len(objs)):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode())
        out.extend(objs[i])
        out.extend(b"\nendobj\n")
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objs)}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(
        (
            f"trailer<< /Size {len(objs)} /Root {catalog_i} 0 R /Info {info_i} 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        ).encode()
    )
    return bytes(out)
