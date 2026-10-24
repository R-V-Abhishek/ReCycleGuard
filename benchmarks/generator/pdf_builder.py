"""Minimal, pure-Python PDF builder for generating synthetic test documents.

Emits clean, standard PDF 1.4 documents containing text, tables, and the mandatory
watermark header required by ReCycleGuard specifications.
"""

from pathlib import Path


def escape_pdf_text(text: str) -> str:
    """Escape special characters in PDF literal text strings."""
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_synthetic_pdf(
    output_path: Path | str,
    title: str,
    lines: list[str],
    watermark: str = "SYNTHETIC - NOT A CPCB RECORD",
) -> None:
    """Generate a valid, single-page PDF 1.4 document with text and watermark."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    stream_lines = []

    # Watermark banner at the top
    stream_lines.append("0.7 0.1 0.1 rg")  # Dark red/maroon color
    stream_lines.append("BT")
    stream_lines.append("/F1 14 Tf")
    stream_lines.append("50 745 Td")
    stream_lines.append(f"({escape_pdf_text(watermark)}) Tj")
    stream_lines.append("ET")

    # Document title
    stream_lines.append("0 0 0 rg")  # Black
    stream_lines.append("BT")
    stream_lines.append("/F1 16 Tf")
    stream_lines.append("50 710 Td")
    stream_lines.append(f"({escape_pdf_text(title)}) Tj")
    stream_lines.append("ET")

    # Separator line
    stream_lines.append("0.5 0.5 0.5 RG")
    stream_lines.append("50 695 m 560 695 l S")

    # Body lines
    y = 675
    line_height = 16
    stream_lines.append("0.1 0.1 0.1 rg")
    for line in lines:
        if not line.strip():
            y -= line_height // 2
            continue
        stream_lines.append("BT")
        if line.startswith("===") or line.startswith("---"):
            stream_lines.append("/F1 10 Tf")
            stream_lines.append(f"50 {y} Td")
            stream_lines.append(f"({escape_pdf_text(line)}) Tj")
        elif ":" in line and not line.startswith(" "):
            # Section header or key-value
            stream_lines.append("/F1 11 Tf")
            stream_lines.append(f"50 {y} Td")
            stream_lines.append(f"({escape_pdf_text(line)}) Tj")
        else:
            stream_lines.append("/F1 10 Tf")
            stream_lines.append(f"50 {y} Td")
            stream_lines.append(f"({escape_pdf_text(line)}) Tj")
        stream_lines.append("ET")
        y -= line_height

    content = "\n".join(stream_lines).encode("utf-8")
    content_len = len(content)

    # Construct PDF objects
    objects = []
    # 1: Catalog
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    # 2: Pages
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    # 3: Page
    objects.append(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
    )
    # 4: Contents stream
    stream_obj = (
        f"<< /Length {content_len} >>\nstream\n".encode("utf-8")
        + content
        + b"\nendstream"
    )
    objects.append(stream_obj)
    # 5: Font
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    # Build file layout
    out = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = []
    current_offset = len(out[0])

    for i, obj in enumerate(objects, 1):
        offsets.append(current_offset)
        header = f"{i} 0 obj\n".encode("utf-8")
        footer = b"\nendobj\n"
        chunk = header + obj + footer
        out.append(chunk)
        current_offset += len(chunk)

    xref_offset = current_offset
    xref = [f"xref\n0 {len(objects) + 1}\n".encode("utf-8")]
    xref.append(b"0000000000 65535 f \n")
    for offset in offsets:
        xref.append(f"{offset:010d} 00000 n \n".encode("utf-8"))

    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("utf-8")

    out.extend(xref)
    out.append(trailer)

    with open(path, "wb") as f:
        f.write(b"".join(out))
