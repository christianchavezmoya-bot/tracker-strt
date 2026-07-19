"""Branded PDF generator for HOLO-RTLS reports (Pillow chart + hand-built PDF)."""
from __future__ import annotations

import io
import struct
from datetime import datetime, timezone


def rows_to_pdf(title: str, rows: list, *, subtitle: str = None, site_name: str = None) -> bytes:
    """Build a PDF with HOLO-RTLS header, optional bar chart graphic, and table."""
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
    metrics = _summary_metrics(rows)
    chart_jpeg = _render_summary_chart_jpeg(metrics, title=title) if metrics else None
    chart_lines = _summary_bar_chart_lines(rows)
    if chart_lines:
        lines.extend(chart_lines)
    if not rows:
        lines.append("No data for this report window.")
    else:
        keys = list(rows[0].keys())
        header = " | ".join(str(k) for k in keys)
        lines.append(header)
        lines.append("-" * min(72, max(len(header), 20)))
        for row in rows[:200]:
            lines.append(" | ".join(str(row.get(k, ""))[:48] for k in keys))
        if len(rows) > 200:
            lines.append("")
            lines.append(f"… {len(rows) - 200} additional rows omitted")
    lines.extend(["", "-" * 72, "Confidential — HOLO-RTLS operations report"])
    return _build_pdf("\n".join(lines), title=title, chart_jpeg=chart_jpeg)


def _summary_metrics(rows: list) -> list[tuple[str, float]]:
    if not rows or "metric" not in rows[0]:
        return []
    numeric = []
    for row in rows:
        metric = row.get("metric")
        if not metric or metric == "generated_at":
            continue
        try:
            numeric.append((str(metric), float(row.get("value", 0))))
        except (TypeError, ValueError):
            continue
    return numeric if len(numeric) >= 2 else []


def _render_summary_chart_jpeg(metrics: list[tuple[str, float]], *, title: str = "Summary") -> bytes:
    """Render a branded horizontal bar chart as JPEG bytes."""
    from PIL import Image, ImageDraw, ImageFont

    width, height = 720, 320
    img = Image.new("RGB", (width, height), (8, 15, 30))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    except OSError:
        font = font_sm = font_title = ImageFont.load_default()

    draw.text((24, 18), "HOLO-RTLS", fill=(0, 229, 255), font=font_title)
    draw.text((24, 44), title[:48], fill=(200, 220, 230), font=font_sm)

    max_v = max(v for _, v in metrics) or 1.0
    bar_left, bar_top = 160, 78
    bar_max_w = width - bar_left - 80
    row_h = 28
    colors = [(0, 229, 255), (105, 255, 71), (255, 221, 87), (255, 68, 68), (147, 112, 219)]

    for i, (label, val) in enumerate(metrics[:8]):
        y = bar_top + i * row_h
        label_txt = label.replace("_", " ")[:18]
        draw.text((24, y + 4), label_txt, fill=(148, 163, 184), font=font_sm)
        bw = max(4, int(bar_max_w * val / max_v))
        color = colors[i % len(colors)]
        draw.rounded_rectangle(
            [bar_left, y + 2, bar_left + bw, y + row_h - 6],
            radius=4,
            fill=color,
        )
        disp = str(int(val)) if val == int(val) else f"{val:.1f}"
        draw.text((bar_left + bw + 8, y + 4), disp, fill=(226, 232, 240), font=font)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88, optimize=True)
    return buf.getvalue()


def _summary_bar_chart_lines(rows: list) -> list:
    """ASCII bar chart for summary metric rows (metric + numeric value)."""
    metrics = _summary_metrics(rows)
    if not metrics:
        return []
    max_v = max(v for _, v in metrics) or 1.0
    out = ["Summary chart", ""]
    for label, val in metrics:
        bar_len = max(1, int(36 * val / max_v))
        disp = str(int(val)) if val == int(val) else f"{val:.1f}"
        out.append(f"{label.replace('_', ' ')[:22]:22} |{'#' * bar_len}| {disp}")
    out.append("")
    return out


def _jpeg_dimensions(jpeg_bytes: bytes) -> tuple[int, int]:
    """Read width/height from JPEG SOF marker without Pillow."""
    i = 2
    while i < len(jpeg_bytes) - 8:
        if jpeg_bytes[i] != 0xFF:
            i += 1
            continue
        marker = jpeg_bytes[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            h = struct.unpack(">H", jpeg_bytes[i + 5 : i + 7])[0]
            w = struct.unpack(">H", jpeg_bytes[i + 7 : i + 9])[0]
            return w, h
        length = struct.unpack(">H", jpeg_bytes[i + 2 : i + 4])[0]
        i += 2 + length
    from PIL import Image
    with Image.open(io.BytesIO(jpeg_bytes)) as im:
        return im.size


def _build_pdf(text: str, title: str = "HOLO-RTLS Report", chart_jpeg: bytes | None = None) -> bytes:
    pages: list[list[str]] = []

    if chart_jpeg:
        w, h = _jpeg_dimensions(chart_jpeg)
        scale = min(532 / w, 400 / h)
        disp_w, disp_h = w * scale, h * scale
        x, y = 40, 792 - disp_h - 40
        pages.append([f"__JPEG__:{x:.1f}:{y:.1f}:{disp_w:.1f}:{disp_h:.1f}"])

    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    raw_lines = safe.split("\n")
    page_lines: list[str] = []
    y = 760
    for raw in raw_lines:
        if y < 50:
            pages.append(page_lines)
            page_lines = []
            y = 760
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

    objs: list[bytes] = []

    def add_obj(data: bytes) -> int:
        objs.append(data)
        return len(objs) - 1

    catalog_i = add_obj(b"")
    pages_i = add_obj(b"")
    font_i = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    bold_i = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

    image_i = None
    if chart_jpeg:
        image_i = add_obj(
            (
                f"<< /Type /XObject /Subtype /Image /Width {_jpeg_dimensions(chart_jpeg)[0]} "
                f"/Height {_jpeg_dimensions(chart_jpeg)[1]} /ColorSpace /DeviceRGB "
                f"/BitsPerComponent 8 /Filter /DCTDecode /Length {len(chart_jpeg)} >>"
            ).encode()
            + b"\nstream\n"
            + chart_jpeg
            + b"\nendstream"
        )

    page_refs = []
    for cmds in pages:
        stream_parts: list[str] = []
        for cmd in cmds:
            if cmd.startswith("__JPEG__:") and image_i is not None:
                _, xs, ys, ws, hs = cmd.split(":")
                stream_parts.append(
                    f"q {ws} 0 0 {hs} {xs} {ys} cm /Im1 Do Q"
                )
            else:
                stream_parts.append(cmd)
        stream = "\n".join(stream_parts).encode("latin-1", errors="replace")
        resources = f"/Font << /F1 {font_i} 0 R /F2 {bold_i} 0 R >>"
        if image_i is not None:
            resources += f" /XObject << /Im1 {image_i} 0 R >>"
        content_i = add_obj(
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )
        page_i = add_obj(
            (
                f"<< /Type /Page /Parent {pages_i} 0 R /MediaBox [0 0 612 792] "
                f"/Contents {content_i} 0 R /Resources << {resources} >> >>"
            ).encode()
        )
        page_refs.append(page_i)

    kids_str = " ".join(f"{n} 0 R" for n in page_refs)
    objs[pages_i] = f"<< /Type /Pages /Kids [{kids_str}] /Count {len(page_refs)} >>".encode()
    objs[catalog_i] = f"<< /Type /Catalog /Pages {pages_i} 0 R >>".encode()
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
