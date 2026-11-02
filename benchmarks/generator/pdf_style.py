"""Shared text-PDF primitives for S05 documents: seeded paper/ink styling and a true watermark.

The watermark is drawn as vector stroke glyphs (paths, not text) on a rotated, translucent
layer tagged as a PDF watermark artifact. Text extractors therefore never interleave its
letters into document lines, while a reader always sees it across the page. A small
extractable footer still carries the mandatory "SYNTHETIC - NOT A CPCB RECORD" string.
"""

import random
from dataclasses import dataclass
from math import cos, radians, sin
from pathlib import Path

WATERMARK = "SYNTHETIC - NOT A CPCB RECORD"
PAGE_W, PAGE_H = 595.28, 841.89  # A4 portrait, the default paper size in Indian offices.

RGB = tuple[float, float, float]

# Office stationery seen in practice: bright white, ivory and cream bond, recycled stock.
PAPERS: dict[str, RGB] = {
    "white bond": (1.00, 1.00, 1.00),
    "ivory": (1.00, 0.99, 0.94),
    "cream": (0.99, 0.97, 0.91),
    "recycled beige": (0.97, 0.95, 0.89),
    "cool grey": (0.96, 0.96, 0.95),
    "blue-white": (0.95, 0.97, 1.00),
}
INKS: dict[str, RGB] = {
    "black": (0.00, 0.00, 0.00),
    "near black": (0.10, 0.10, 0.10),
    "charcoal": (0.18, 0.18, 0.20),
    "navy": (0.08, 0.12, 0.30),
    "blue-black": (0.05, 0.08, 0.20),
    "brown-black": (0.20, 0.13, 0.08),
    "green-black": (0.06, 0.18, 0.13),
}
ACCENTS: dict[str, RGB] = {
    "maroon": (0.48, 0.09, 0.14),
    "navy": (0.10, 0.21, 0.42),
    "forest": (0.09, 0.33, 0.20),
    "teal": (0.05, 0.33, 0.36),
    "indigo": (0.24, 0.18, 0.50),
    "saffron brown": (0.62, 0.30, 0.04),
    "slate": (0.22, 0.27, 0.33),
}
FAMILIES = {"sans": ("Helvetica", "Helvetica-Bold"), "serif": ("Times-Roman", "Times-Bold")}
MIN_CONTRAST = 7.0  # WCAG AAA for body ink on paper.
MIN_SECONDARY_CONTRAST = 4.5  # WCAG AA for headings and muted secondary text.


def _luminance(rgb: RGB) -> float:
    def channel(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = map(channel, rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: RGB, b: RGB) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@dataclass(frozen=True)
class DocumentStyle:
    """Visual choices only; a style never changes a quantity, identifier or date."""

    paper_name: str
    paper: RGB
    ink_name: str
    ink: RGB
    accent_name: str
    accent: RGB
    family: str
    body_size: float
    watermark_angle: float
    watermark_alpha: float
    watermark_gray: float

    @property
    def regular_font(self) -> str:
        return FAMILIES[self.family][0]

    @property
    def bold_font(self) -> str:
        return FAMILIES[self.family][1]

    def muted(self, weight: float = 0.35) -> RGB:
        """Ink blended toward the paper for secondary text, keeping readable contrast."""
        return tuple(i + (p - i) * weight for i, p in zip(self.ink, self.paper, strict=True))


def readable(style: DocumentStyle) -> bool:
    return (
        contrast(style.ink, style.paper) >= MIN_CONTRAST
        and min(contrast(style.accent, style.paper), contrast(style.muted(), style.paper))
        >= MIN_SECONDARY_CONTRAST
    )


def choose_style(rng: random.Random, *, body_sizes=(9.5, 10.0, 10.5, 11.0, 11.5)) -> DocumentStyle:
    """Seeded draw; combinations that fail the contrast floor are re-drawn, never used."""
    for _ in range(64):
        paper_name = rng.choice(sorted(PAPERS))
        ink_name = rng.choice(sorted(INKS))
        accent_name = rng.choice(sorted(ACCENTS))
        style = DocumentStyle(
            paper_name=paper_name,
            paper=PAPERS[paper_name],
            ink_name=ink_name,
            ink=INKS[ink_name],
            accent_name=accent_name,
            accent=ACCENTS[accent_name],
            family=rng.choice(sorted(FAMILIES)),
            body_size=rng.choice(body_sizes),
            watermark_angle=rng.choice((32.0, 36.0, 40.0, 44.0, 48.0, 52.0)),
            watermark_alpha=rng.choice((0.16, 0.18, 0.20, 0.22)),
            watermark_gray=rng.choice((0.35, 0.45, 0.55)),
        )
        if readable(style):
            return style
    raise ValueError("no readable style found")


def rgb(colour: RGB, op: str = "rg") -> str:
    return f"{colour[0]:.3f} {colour[1]:.3f} {colour[2]:.3f} {op}"


# --- Metrics (Adobe core-14 AFM widths, ASCII 32..126, 1/1000 em) -------------------------
_W = {
    "Helvetica": (
        "278 278 355 556 556 889 667 222 333 333 389 584 278 333 278 278 556 556 556 556 556 "
        "556 556 556 556 556 278 278 584 584 584 556 1015 667 667 722 722 667 611 778 722 278 "
        "500 667 556 833 722 778 667 778 722 667 611 722 667 944 667 667 611 278 278 278 469 "
        "556 222 556 556 500 556 556 278 556 556 222 222 500 222 833 556 556 556 556 333 500 "
        "278 556 500 722 500 500 500 334 260 334 584"
    ),
    "Helvetica-Bold": (
        "278 333 474 556 556 889 722 278 333 333 389 584 278 333 278 278 556 556 556 556 556 "
        "556 556 556 556 556 333 333 584 584 584 611 975 722 722 722 722 667 611 778 722 278 "
        "556 722 611 833 722 778 667 778 722 667 611 722 667 944 667 667 611 333 278 333 584 "
        "556 278 556 611 556 611 556 333 611 611 278 278 556 278 889 611 611 611 611 389 556 "
        "333 611 556 778 556 556 500 389 280 389 584"
    ),
    "Times-Roman": (
        "250 333 408 500 500 833 778 333 333 333 500 564 250 333 250 278 500 500 500 500 500 "
        "500 500 500 500 500 278 278 564 564 564 444 921 722 667 667 722 611 556 722 722 333 "
        "389 722 611 889 722 722 556 722 667 556 611 722 722 944 722 722 611 333 278 333 469 "
        "500 333 444 500 444 500 444 333 500 500 278 278 500 278 778 500 500 500 500 333 389 "
        "278 500 500 722 500 500 444 480 200 480 541"
    ),
    "Times-Bold": (
        "250 333 555 500 500 1000 833 333 333 333 500 570 250 333 250 278 500 500 500 500 500 "
        "500 500 500 500 500 333 333 570 570 570 500 930 722 667 722 722 667 611 778 778 389 "
        "500 778 667 944 722 778 611 778 722 556 667 722 722 1000 722 722 667 333 278 333 581 "
        "500 333 500 556 444 556 444 333 500 556 278 333 556 278 833 556 500 556 556 444 389 "
        "333 556 500 722 500 500 444 394 220 394 520"
    ),
}
WIDTHS = {font: [int(w) for w in table.split()] for font, table in _W.items()}


def text_width(text: str, font: str, size: float) -> float:
    table = WIDTHS[font]
    return sum(table[ord(ch) - 32] for ch in text) * size / 1000


def wrap(text: str, font: str, size: float, width: float) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if current and text_width(trial, font, size) > width:
            lines.append(current)
            current = word
        else:
            current = trial
    return lines + ([current] if current else [])


def escape(text: str) -> str:
    if not text.isascii():
        raise ValueError(f"core-14 PDF text must be ASCII: {text!r}")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


# --- Stroke font for the watermark: 4 x 6 grid polylines per glyph --------------------------
_P = "0,0 0,6 3,6 4,5 4,4 3,3 0,3"
GLYPHS: dict[str, list[str]] = {
    "S": ["4,6 1,6 0,5 0,4 1,3 3,3 4,2 4,1 3,0 0,0"],
    "Y": ["0,6 2,3 4,6", "2,3 2,0"],
    "N": ["0,0 0,6 4,0 4,6"],
    "T": ["0,6 4,6", "2,6 2,0"],
    "H": ["0,0 0,6", "4,0 4,6", "0,3 4,3"],
    "E": ["4,6 0,6 0,0 4,0", "0,3 3,3"],
    "I": ["1,6 3,6", "2,6 2,0", "1,0 3,0"],
    "C": ["4,5 3,6 1,6 0,5 0,1 1,0 3,0 4,1"],
    "-": ["1,3 3,3"],
    "O": ["1,0 0,1 0,5 1,6 3,6 4,5 4,1 3,0 1,0"],
    "A": ["0,0 0,4 2,6 4,4 4,0", "0,3 4,3"],
    "P": [_P],
    "B": [_P, "3,3 4,2 4,1 3,0 0,0"],
    "R": [_P, "2,3 4,0"],
    "D": ["0,0 0,6 3,6 4,5 4,1 3,0 0,0"],
    " ": [],
}
ADVANCE = 6.0


def watermark_ops(
    style: DocumentStyle, page: tuple[float, float] = (PAGE_W, PAGE_H), text: str = WATERMARK
) -> list[str]:
    """Diagonal translucent stroke-glyph watermark through the page centre."""
    theta = radians(style.watermark_angle)
    c, s = cos(theta), sin(theta)
    glyphs = len(text) * ADVANCE - (ADVANCE - 4)
    # Largest glyph unit whose rotated text box stays inside a 40pt page margin.
    unit = min(5.0, (page[0] - 80) / (glyphs * c + 6 * s), (page[1] - 80) / (glyphs * s + 6 * c))
    span = glyphs * unit
    # Centre the text box (span x 6 units) on the page centre after rotation.
    ox = page[0] / 2 - (c * span / 2 - s * 3 * unit)
    oy = page[1] / 2 - (s * span / 2 + c * 3 * unit)
    ops = [
        "/Artifact << /Type /Pagination /Subtype /Watermark >> BDC",
        "q /GSwm gs",
        f"{c:.5f} {s:.5f} {-s:.5f} {c:.5f} {ox:.2f} {oy:.2f} cm",
        rgb((style.watermark_gray,) * 3, "RG"),
        f"{unit * 0.8:.2f} w 1 J 1 j",
    ]
    for index, char in enumerate(text):
        x0 = index * ADVANCE
        for stroke in GLYPHS[char]:
            points = [tuple(map(float, p.split(","))) for p in stroke.split()]
            path = [
                f"{(x0 + x) * unit:.2f} {y * unit:.2f} {'m' if i == 0 else 'l'}"
                for i, (x, y) in enumerate(points)
            ]
            ops.append(" ".join(path) + " S")
    ops += ["Q", "EMC"]
    return ops


def write_pdf(
    path: Path | str,
    content: str | list[str],
    *,
    fonts: dict[str, str],
    alpha: float | None = None,
    media_box: tuple[float, float] = (PAGE_W, PAGE_H),
    info: dict[str, str] | None = None,
) -> None:
    """PDF 1.4 writer (one content stream per page) with deterministic bytes: no clock, no IDs."""
    pages = [content] if isinstance(content, str) else content
    font_refs, objects = [], []
    n = 3 + 2 * len(pages)
    for name, base in fonts.items():
        font_refs.append(f"/{name} {n} 0 R")
        objects.append(
            f"<< /Type /Font /Subtype /Type1 /BaseFont /{base} /Encoding /WinAnsiEncoding >>"
        )
        n += 1
    resources = f"/Font << {' '.join(font_refs)} >>"
    if alpha is not None:
        resources += f" /ExtGState << /GSwm {n} 0 R >>"
        objects.append(f"<< /Type /ExtGState /CA {alpha:.2f} /ca {alpha:.2f} >>")
        n += 1
    info_ref = ""
    if info:
        entries = " ".join(f"/{k} ({escape(v)})" for k, v in sorted(info.items()))
        objects.append(f"<< {entries} >>")
        info_ref = f" /Info {n} 0 R"
        n += 1
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    head = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
    ]
    for i, page in enumerate(pages):
        body = page.encode("ascii")
        head.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {media_box[0]:.2f} "
                f"{media_box[1]:.2f}] /Contents {4 + 2 * i} 0 R /Resources << {resources} >> >>"
            ).encode()
        )
        head.append(f"<< /Length {len(body)} >>\nstream\n".encode() + body + b"\nendstream")
    chunks = head + [o.encode() for o in objects]
    out = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets, cursor = [], len(out[0])
    for i, obj in enumerate(chunks, 1):
        offsets.append(cursor)
        chunk = f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
        out.append(chunk)
        cursor += len(chunk)
    xref = [f"xref\n0 {len(chunks) + 1}\n".encode(), b"0000000000 65535 f \n"]
    xref += [f"{off:010d} 00000 n \n".encode() for off in offsets]
    trailer = (
        f"trailer\n<< /Size {len(chunks) + 1} /Root 1 0 R{info_ref} >>\n"
        f"startxref\n{cursor}\n%%EOF\n"
    ).encode()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"".join(out + xref + [trailer]))


__all__ = [
    "WATERMARK",
    "PAGE_W",
    "PAGE_H",
    "DocumentStyle",
    "choose_style",
    "contrast",
    "readable",
    "escape",
    "rgb",
    "text_width",
    "watermark_ops",
    "wrap",
    "write_pdf",
]
