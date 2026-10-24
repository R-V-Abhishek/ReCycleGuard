"""Dedicated B2B Invoice PDF generator with dynamic corporate color themes.

Replicates standard corporate B2B invoice layouts:
- Circular corporate logo badge with monogram
- Two-column party details ("BILL TO" / "SHIP TO")
- Itemized tabular grid with shaded header and formatted columns
- Split bottom: "Remarks / Payment Instructions" with EPR compliance notices and
  "Totals & Balance Due" summary block
- Dynamic theme palette with reproducible seed pinning
- Mandatory watermark: "SYNTHETIC - NOT A CPCB RECORD"
"""

import random
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class InvoiceTheme:
    """Color palette specification for an invoice theme."""

    name: str
    primary: tuple[float, float, float]  # Primary headers, accents, logo
    accent: tuple[float, float, float]  # Sub-headers, secondary lines
    light_fill: tuple[float, float, float]  # Box and table backgrounds
    border: tuple[float, float, float]  # Grid and box border lines


# 7 realistic corporate B2B color themes
INVOICE_THEMES: list[InvoiceTheme] = [
    InvoiceTheme(
        name="Navy Corporate",
        primary=(0.10, 0.21, 0.36),
        accent=(0.17, 0.42, 0.69),
        light_fill=(0.92, 0.97, 1.00),
        border=(0.75, 0.82, 0.90),
    ),
    InvoiceTheme(
        name="Emerald Eco",
        primary=(0.11, 0.27, 0.20),
        accent=(0.18, 0.52, 0.35),
        light_fill=(0.94, 1.00, 0.96),
        border=(0.76, 0.92, 0.82),
    ),
    InvoiceTheme(
        name="Charcoal Tech",
        primary=(0.18, 0.22, 0.28),
        accent=(0.30, 0.35, 0.42),
        light_fill=(0.96, 0.97, 0.98),
        border=(0.82, 0.85, 0.89),
    ),
    InvoiceTheme(
        name="Burgundy Metal",
        primary=(0.32, 0.11, 0.17),
        accent=(0.55, 0.16, 0.32),
        light_fill=(1.00, 0.96, 0.97),
        border=(0.93, 0.80, 0.85),
    ),
    InvoiceTheme(
        name="Teal Modern",
        primary=(0.11, 0.25, 0.27),
        accent=(0.16, 0.40, 0.41),
        light_fill=(0.90, 1.00, 0.98),
        border=(0.72, 0.91, 0.88),
    ),
    InvoiceTheme(
        name="Royal Purple",
        primary=(0.20, 0.15, 0.35),
        accent=(0.35, 0.25, 0.60),
        light_fill=(0.98, 0.96, 1.00),
        border=(0.88, 0.82, 0.96),
    ),
    InvoiceTheme(
        name="Amber Industrial",
        primary=(0.27, 0.16, 0.06),
        accent=(0.55, 0.33, 0.09),
        light_fill=(1.00, 0.98, 0.94),
        border=(0.94, 0.86, 0.74),
    ),
]


@dataclass
class InvoiceItem:
    description: str
    subtext: str = ""
    quantity: str = "0.0000"
    unit: str = "KG"
    unit_price: str = "0.0000"
    total: str = "0.0000"


@dataclass
class B2BInvoiceData:
    invoice_number: str
    invoice_date: str
    payment_terms: str
    seller_name: str
    seller_tagline: str
    seller_address: str
    seller_contact: str
    seller_gstin: str
    seller_reg_no: str
    buyer_name: str
    buyer_gstin: str
    buyer_address: str
    buyer_contact: str
    buyer_state: str
    ship_to_facility: str
    ship_to_address: str
    ship_to_eee_code: str
    ship_to_place: str
    items: list[InvoiceItem] = field(default_factory=list)
    subtotal: str = "0.0000"
    discount: str = "0.0000"
    subtotal_less_discount: str = "0.0000"
    tax_rate: str = "0.00%"
    total_tax: str = "0.0000"
    shipping_handling: str = "0.0000"
    total_amount: str = "0.0000"
    amount_paid: str = "0.0000"
    balance_due: str = "0.00"
    payment_remarks: list[str] = field(default_factory=list)
    watermark: str = "SYNTHETIC - NOT A CPCB RECORD"


def escape_pdf(text: str) -> str:
    """Escape text for literal PDF string."""
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def format_color(color: tuple[float, float, float]) -> str:
    """Return formatted RGB values with 2 decimals."""
    return f"{color[0]:.2f} {color[1]:.2f} {color[2]:.2f}"


def build_b2b_invoice_pdf(
    output_path: Path | str,
    data: B2BInvoiceData,
    seed: int | None = None,
) -> InvoiceTheme:
    """Render a B2B invoice PDF according to the corporate layout template.

    Returns the chosen InvoiceTheme.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if seed is not None:
        rng = random.Random(seed)
        theme = rng.choice(INVOICE_THEMES)
    else:
        theme = random.choice(INVOICE_THEMES)

    p_rgb = format_color(theme.primary)
    a_rgb = format_color(theme.accent)
    f_rgb = format_color(theme.light_fill)
    b_rgb = format_color(theme.border)

    s: list[str] = []

    # =========================================================================
    # 1. WATERMARK HEADER BANNER (Top)
    # =========================================================================
    s.append("0.75 0.12 0.12 rg")
    s.append("BT /F1 11 Tf 40 762 Td")
    s.append(f"({escape_pdf(data.watermark)}) Tj ET")

    # Separator rule under watermark
    s.append(f"{b_rgb} RG 0.5 w")
    s.append("40 754 m 572 754 l S")

    # =========================================================================
    # 2. HEADER: LOGO & SELLER DETAILS (Left) | INVOICE META BOX (Right)
    # =========================================================================
    # Circular Logo Badge at (68, 706), radius 22
    cx, cy, r = 68.0, 706.0, 22.0
    k = 0.5522847 * r
    s.append(f"{p_rgb} rg")
    s.append(f"{cx-r} {cy} m")
    s.append(f"{cx-r} {cy+k} {cx-k} {cy+r} {cx} {cy+r} c")
    s.append(f"{cx+k} {cy+r} {cx+r} {cy+k} {cx+r} {cy} c")
    s.append(f"{cx+r} {cy-k} {cx+k} {cy-r} {cx} {cy-r} c")
    s.append(f"{cx-k} {cy-r} {cx-r} {cy-k} {cx-r} {cy} c f")

    # White "LOGO" text inside circle
    s.append("1.0 1.0 1.0 rg")
    s.append(f"BT /F1 9 Tf {cx-14:.1f} {cy-3:.1f} Td (LOGO) Tj ET")

    # Seller Information
    s.append(f"{p_rgb} rg")
    s.append(f"BT /F1 13 Tf 100 722 Td ({escape_pdf(data.seller_name)}) Tj ET")

    s.append("0.35 0.35 0.35 rg")
    s.append(f"BT /F1 8 Tf 100 710 Td ({escape_pdf(data.seller_tagline)}) Tj ET")
    s.append(f"BT /F1 8 Tf 100 699 Td ({escape_pdf(data.seller_address)}) Tj ET")
    s.append(f"BT /F1 8 Tf 100 688 Td ({escape_pdf(data.seller_contact)}) Tj ET")

    s.append("0.15 0.15 0.15 rg")
    s.append(
        f"BT /F1 8 Tf 100 677 Td "
        f"({escape_pdf('GSTIN: ' + data.seller_gstin + '  |  ' + data.seller_reg_no)}) Tj ET"
    )

    # Invoice Meta Box (Right: 400 to 572, y 662 to 742, w=172, h=80)
    s.append(f"{f_rgb} rg {b_rgb} RG 0.75 w")
    s.append("400 662 172 80 re B")

    s.append(f"{p_rgb} rg")
    s.append("BT /F1 16 Tf 412 722 Td (INVOICE) Tj ET")

    s.append("0.2 0.2 0.2 rg")
    s.append(
        f"BT /F1 8.5 Tf 412 706 Td ({escape_pdf('INVOICE NO:  ' + data.invoice_number)}) Tj ET"
    )
    s.append(
        f"BT /F1 8.5 Tf 412 692 Td ({escape_pdf('DATE:        ' + data.invoice_date)}) Tj ET"
    )
    s.append(
        f"BT /F1 8.5 Tf 412 678 Td ({escape_pdf('TERMS:       ' + data.payment_terms)}) Tj ET"
    )

    # =========================================================================
    # 3. PARTY ADDRESS BLOCKS: BILL TO (Left) | SHIP TO (Right)
    # =========================================================================
    # Row y: 575 to 645 (w=256, h=70)
    # Box 1: BILL TO (x=40)
    s.append(f"{f_rgb} rg {b_rgb} RG 0.5 w")
    s.append("40 575 256 70 re B")
    # Header tab
    s.append(f"{a_rgb} rg")
    s.append("40 630 256 15 re f")
    s.append("1.0 1.0 1.0 rg")
    s.append("BT /F1 8.5 Tf 48 634 Td (BILL TO) Tj ET")

    s.append(f"{p_rgb} rg")
    s.append(f"BT /F1 8.5 Tf 48 616 Td ({escape_pdf(data.buyer_name)}) Tj ET")
    s.append("0.25 0.25 0.25 rg")
    s.append(
        f"BT /F1 7.5 Tf 48 604 Td ({escape_pdf('GSTIN: ' + data.buyer_gstin)}) Tj ET"
    )
    s.append(f"BT /F1 7.5 Tf 48 593 Td ({escape_pdf(data.buyer_address)}) Tj ET")
    s.append(
        f"BT /F1 7.5 Tf 48 582 Td ({escape_pdf(data.buyer_contact + ' | ' + data.buyer_state)}) Tj ET"
    )

    # Box 2: SHIP TO (x=316)
    s.append(f"{f_rgb} rg {b_rgb} RG 0.5 w")
    s.append("316 575 256 70 re B")
    # Header tab
    s.append(f"{a_rgb} rg")
    s.append("316 630 256 15 re f")
    s.append("1.0 1.0 1.0 rg")
    s.append("BT /F1 8.5 Tf 324 634 Td (SHIP TO / RECYCLING FACILITY) Tj ET")

    s.append(f"{p_rgb} rg")
    s.append(f"BT /F1 8.5 Tf 324 616 Td ({escape_pdf(data.ship_to_facility)}) Tj ET")
    s.append("0.25 0.25 0.25 rg")
    s.append(f"BT /F1 7.5 Tf 324 604 Td ({escape_pdf(data.ship_to_address)}) Tj ET")
    s.append(
        f"BT /F1 7.5 Tf 324 593 Td ({escape_pdf(data.ship_to_eee_code)}) Tj ET"
    )
    s.append(f"BT /F1 7.5 Tf 324 582 Td ({escape_pdf(data.ship_to_place)}) Tj ET")

    # =========================================================================
    # 4. ITEMIZED TRANSACTION TABLE
    # =========================================================================
    # Table bounds: x=40 to 572, top y=555, header height=20, rows down to 425
    table_top = 555
    header_h = 18

    # Table Header Background
    s.append(f"{p_rgb} rg")
    s.append(f"40 {table_top-header_h} 532 {header_h} re f")

    # Header Columns:
    # Description (40-300, w=260) | QTY (300-380, w=80) | UNIT PRICE (380-475, w=95) | TOTAL (475-572, w=97)
    s.append("1.0 1.0 1.0 rg")
    s.append(f"BT /F1 8.5 Tf 48 {table_top-13} Td (DESCRIPTION) Tj ET")
    s.append(f"BT /F1 8.5 Tf 320 {table_top-13} Td (QTY) Tj ET")
    s.append(f"BT /F1 8.5 Tf 400 {table_top-13} Td (UNIT PRICE (INR)) Tj ET")
    s.append(f"BT /F1 8.5 Tf 505 {table_top-13} Td (TOTAL (INR)) Tj ET")

    # Table Grid Outer Border
    table_bottom = 430
    s.append(f"{b_rgb} RG 0.5 w")
    s.append(
        f"40 {table_bottom} 532 {table_top-table_bottom} re s"
    )  # Outer box
    # Column dividers
    s.append(f"300 {table_bottom} m 300 {table_top} l S")
    s.append(f"385 {table_bottom} m 385 {table_top} l S")
    s.append(f"475 {table_bottom} m 475 {table_top} l S")

    # Render Table Line Items
    row_y = table_top - header_h - 18
    for item in data.items:
        # Description & subtext
        s.append("0.1 0.1 0.1 rg")
        s.append(
            f"BT /F1 8.5 Tf 48 {row_y} Td ({escape_pdf(item.description)}) Tj ET"
        )
        if item.subtext:
            s.append("0.4 0.4 0.4 rg")
            s.append(
                f"BT /F1 7.5 Tf 48 {row_y-11} Td ({escape_pdf(item.subtext)}) Tj ET"
            )

        # Quantity
        s.append("0.1 0.1 0.1 rg")
        s.append(
            f"BT /F1 8.5 Tf 315 {row_y} Td ({escape_pdf(item.quantity + ' ' + item.unit)}) Tj ET"
        )

        # Unit Price
        s.append(
            f"BT /F1 8.5 Tf 410 {row_y} Td ({escape_pdf(item.unit_price)}) Tj ET"
        )

        # Total
        s.append(
            f"BT /F1 8.5 Tf 505 {row_y} Td ({escape_pdf(item.total)}) Tj ET"
        )

        # Subtle row separator
        s.append(f"{b_rgb} RG 0.25 w")
        s.append(f"40 {row_y-16} m 572 {row_y-16} l S")
        row_y -= 30

    # Draw empty grid row lines to mimic invoice paper
    while row_y > table_bottom + 15:
        s.append(f"{b_rgb} RG 0.2 w")
        s.append(f"40 {row_y} m 572 {row_y} l S")
        row_y -= 22

    # =========================================================================
    # 5. BOTTOM SECTION: REMARKS (Left) | TOTALS / BALANCE DUE (Right)
    # =========================================================================
    bottom_y = 250
    bottom_h = 165

    # Left: Remarks / Payment Instructions Box (40 to 330, w=290, h=165)
    s.append(f"{f_rgb} rg {b_rgb} RG 0.5 w")
    s.append(f"40 {bottom_y} 290 {bottom_h} re B")

    # Remarks Header Tab
    s.append(f"{a_rgb} rg")
    s.append(f"40 {bottom_y+bottom_h-16} 290 16 re f")
    s.append("1.0 1.0 1.0 rg")
    s.append(
        f"BT /F1 8.5 Tf 48 {bottom_y+bottom_h-12} Td (Remarks / Payment Instructions:) Tj ET"
    )

    # Remarks Text
    rem_y = bottom_y + bottom_h - 30
    for rem in data.payment_remarks:
        if not rem.strip():
            rem_y -= 5
            continue
        if "CRITICAL" in rem or "PENDING" in rem or "WARNING" in rem:
            s.append("0.75 0.15 0.15 rg")  # Warning reddish
            s.append(f"BT /F1 7.5 Tf 48 {rem_y} Td ({escape_pdf(rem)}) Tj ET")
        elif "PAID" in rem or "NEFT" in rem:
            s.append("0.1 0.45 0.2 rg")  # Greenish
            s.append(f"BT /F1 7.5 Tf 48 {rem_y} Td ({escape_pdf(rem)}) Tj ET")
        else:
            s.append("0.25 0.25 0.25 rg")
            s.append(f"BT /F1 7.0 Tf 48 {rem_y} Td ({escape_pdf(rem)}) Tj ET")
        rem_y -= 11

    # Right: Calculations Box (345 to 572, w=227, h=165)
    s.append(f"{f_rgb} rg {b_rgb} RG 0.5 w")
    s.append(f"345 {bottom_y} 227 {bottom_h} re B")

    # Calculation Line Items
    calc_rows = [
        ("SUBTOTAL", data.subtotal),
        ("DISCOUNT", data.discount),
        ("SUBTOTAL LESS DISCOUNT", data.subtotal_less_discount),
        ("TAX RATE", data.tax_rate),
        ("TOTAL TAX", data.total_tax),
        ("SHIPPING/HANDLING", data.shipping_handling),
        ("TOTAL INVOICE VALUE", data.total_amount),
    ]

    cy_pos = bottom_y + bottom_h - 18
    for label, val in calc_rows:
        s.append("0.3 0.3 0.3 rg")
        s.append(f"BT /F1 7.5 Tf 355 {cy_pos} Td ({escape_pdf(label)}) Tj ET")
        s.append("0.1 0.1 0.1 rg")
        s.append(f"BT /F1 7.5 Tf 505 {cy_pos} Td ({escape_pdf(val)}) Tj ET")
        s.append(f"{b_rgb} RG 0.2 w")
        s.append(f"345 {cy_pos-4} m 572 {cy_pos-4} l S")
        cy_pos -= 16

    # Highlighted Balance Due Bar at bottom of totals box (height 28)
    s.append(f"{p_rgb} rg")
    s.append(f"345 {bottom_y} 227 28 re f")
    s.append("1.0 1.0 1.0 rg")
    s.append(f"BT /F1 9 Tf 355 {bottom_y+10} Td (Balance Due) Tj ET")
    s.append(
        f"BT /F1 10 Tf 485 {bottom_y+10} Td ({escape_pdf(data.balance_due + ' INR')}) Tj ET"
    )

    # =========================================================================
    # 6. FOOTER
    # =========================================================================
    s.append("0.45 0.45 0.45 rg")
    s.append(
        "BT /F1 7 Tf 120 220 Td (Registered under E-Waste \\(Management\\) Rules, 2022 | Central Pollution Control Board Compliance) Tj ET"
    )
    s.append(
        "BT /F1 6.5 Tf 165 210 Td (This document is synthetic and computer-generated for regulatory audit evaluation.) Tj ET"
    )

    # Build PDF Content
    content = "\n".join(s).encode("utf-8")
    content_len = len(content)

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {content_len} >>\nstream\n".encode("utf-8")
        + content
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = []
    curr = len(out[0])
    for i, obj in enumerate(objects, 1):
        offsets.append(curr)
        chunk = f"{i} 0 obj\n".encode("utf-8") + obj + b"\nendobj\n"
        out.append(chunk)
        curr += len(chunk)

    xref_offset = curr
    xref = [f"xref\n0 {len(objects) + 1}\n".encode("utf-8")]
    xref.append(b"0000000000 65535 f \n")
    for off in offsets:
        xref.append(f"{off:010d} 00000 n \n".encode("utf-8"))

    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("utf-8")

    out.extend(xref)
    out.append(trailer)

    with open(path, "wb") as f:
        f.write(b"".join(out))

    return theme
