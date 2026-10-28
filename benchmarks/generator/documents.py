"""S05 text documents: an Indian inter-office memorandum, plus Indian money/date formatting.

The memo follows the layout used across Indian corporate and government offices: a company
letterhead (name, registered office, CIN, GSTIN, telephone, e-mail and website, as Companies
Act 2013 s.12(3)(c) requires on letterheads), a centred "INTER-OFFICE MEMORANDUM" heading,
Ref. No. and Date on one line, To / From / Subject (and a reference to earlier correspondence),
numbered body paragraphs, a "Sd/-" signature block with name and designation, then Encl. and
"Copy to" lists. Sources are listed in benchmarks/generator/README.md.

Every page carries the diagonal vector watermark from ``pdf_style`` plus an extractable footer.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

from benchmarks.generator.pdf_style import (
    PAGE_H,
    PAGE_W,
    WATERMARK,
    DocumentStyle,
    escape,
    rgb,
    text_width,
    watermark_ops,
    wrap,
    write_pdf,
)

# --- Indian number, money and date conventions ----------------------------------------------
_ONES = (
    "Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen Fourteen "
    "Fifteen Sixteen Seventeen Eighteen Nineteen"
).split()
_TENS = "_ _ Twenty Thirty Forty Fifty Sixty Seventy Eighty Ninety".split()
MONTHS = (
    "January February March April May June July August September October November December"
).split()


def indian_group(value: str | Decimal, places: int = 2) -> str:
    """12345678.5 -> '1,23,45,678.50' (lakh/crore grouping)."""
    quantum = Decimal(1).scaleb(-places)
    number = Decimal(value).quantize(quantum, rounding=ROUND_HALF_EVEN)
    sign = "-" if number < 0 else ""
    whole, _, frac = f"{abs(number):f}".partition(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    grouped = ",".join([*groups, tail]) if groups else tail
    return sign + grouped + (f".{frac}" if places else "")


def _below_thousand(n: int) -> str:
    words = []
    if n >= 100:
        words += [_ONES[n // 100], "Hundred"]
        n %= 100
    if n >= 20:
        words.append(_TENS[n // 10] + (f"-{_ONES[n % 10]}" if n % 10 else ""))
    elif n or not words:
        words.append(_ONES[n])
    return " ".join(words)


def rupees_in_words(amount: str | Decimal) -> str:
    """'Indian Rupees Three Lakh Sixty Thousand Five Hundred Thirteen and Sixty Paise Only'."""
    value = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    rupees, paise = int(value), int((value - int(value)) * 100)
    parts = []
    for unit, size in (("Crore", 10**7), ("Lakh", 10**5), ("Thousand", 10**3)):
        if rupees >= size:
            parts.append(f"{_below_thousand(rupees // size)} {unit}")
            rupees %= size
    if rupees or not parts:
        parts.append(_below_thousand(rupees))
    text = "Indian Rupees " + " ".join(parts)
    if paise:
        text += f" and {_below_thousand(paise)} Paise"
    return text + " Only"


DATE_STYLES = ("dot", "slash", "dash", "ordinal", "long", "tally")


def indian_date(iso: str, style: str) -> str:
    d = date.fromisoformat(iso[:10])
    if style == "dot":
        return d.strftime("%d.%m.%Y")
    if style == "slash":
        return d.strftime("%d/%m/%Y")
    if style == "dash":
        return d.strftime("%d-%m-%Y")
    if style == "ordinal":
        suffix = "th" if 11 <= d.day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d.day % 10, "th")
        return f"{d.day}{suffix} {MONTHS[d.month - 1]}, {d.year}"
    if style == "long":
        return f"{d.day:02d} {MONTHS[d.month - 1]} {d.year}"
    if style == "tally":
        return f"{d.day:02d}-{MONTHS[d.month - 1][:3]}-{d.year}"
    raise ValueError(style)


# --- Memo model ------------------------------------------------------------------------------
@dataclass(frozen=True)
class Letterhead:
    name: str
    tagline: str
    registered_office: str
    corporate_label: str
    corporate_id: str
    gstin: str
    telephone: str
    email: str
    website: str


@dataclass(frozen=True)
class MemoTable:
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    widths: tuple[float, ...]  # fractions of the text column
    numeric: tuple[bool, ...]
    caption: str = ""


@dataclass(frozen=True)
class Memo:
    letterhead: Letterhead
    heading: str
    ref_no: str
    date_text: str
    to: str
    sender: str
    subject: str
    reference: str | None
    blocks: tuple  # str paragraphs (auto-numbered) and MemoTable items
    signatory: str
    designation: str
    department: str
    enclosures: tuple[str, ...] = ()
    copy_to: tuple[str, ...] = ()
    classification: str | None = None
    labels: tuple[str, str, str, str] = ("To", "From", "Subject", "Ref")
    letterhead_align: str = "centre"
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PageBreak:
    """Start the next block on a new page (annexures begin on their own page)."""


@dataclass(frozen=True)
class Heading:
    """An unnumbered bold line, e.g. an annexure title."""

    text: str


BOTTOM = 72.0  # Keep clear of the footer band.


class _Page:
    """A flowing A4 layout: ``need`` starts a continuation page instead of overflowing."""

    def __init__(self, style: DocumentStyle):
        self.st = style
        self.left, self.right = 62.0, PAGE_W - 62.0
        self.pages: list[list[str]] = []
        self.running = ""
        self.new_page()

    def new_page(self):
        self.ops = [rgb(self.st.paper) + f" 0 0 {PAGE_W:.2f} {PAGE_H:.2f} re f"]
        self.pages.append(self.ops)
        self.y = PAGE_H - 54.0
        if self.running:
            self.text(
                self.left, self.y, self.running, self.st.body_size - 1.5, colour=self.st.muted(0.3)
            )
            self.rule(self.y - 5, 0.4)
            self.y -= self.st.body_size + 16

    def font(self, bold: bool) -> tuple[str, str]:
        return ("/F2", self.st.bold_font) if bold else ("/F1", self.st.regular_font)

    def text(self, x, y, s, size, *, bold=False, colour=None):
        ref, _ = self.font(bold)
        self.ops.append(rgb(colour or self.st.ink))
        self.ops.append(f"BT {ref} {size:.2f} Tf {x:.2f} {y:.2f} Td ({escape(s)}) Tj ET")

    def width(self, s, size, bold=False) -> float:
        return text_width(s, self.font(bold)[1], size)

    def centred(self, y, s, size, **kw):
        self.text(
            (self.left + self.right) / 2 - self.width(s, size, kw.get("bold", False)) / 2,
            y,
            s,
            size,
            **kw,
        )

    def right_aligned(self, y, s, size, **kw):
        self.text(self.right - self.width(s, size, kw.get("bold", False)), y, s, size, **kw)

    def rule(self, y, weight=0.5, colour=None, x0=None, x1=None):
        self.ops.append(rgb(colour or self.st.muted(0.45), "RG") + f" {weight:.2f} w")
        x0 = self.left if x0 is None else x0
        x1 = self.right if x1 is None else x1
        self.ops.append(f"{x0:.2f} {y:.2f} m {x1:.2f} {y:.2f} l S")

    def need(self, height):
        if self.y - height < BOTTOM:
            if self.y > PAGE_H - 120:
                raise ValueError("memo block is taller than an A4 page")
            self.new_page()


def _letterhead(page: _Page, lh: Letterhead, align: str):
    st, size = page.st, page.st.body_size
    place = (
        page.centred
        if align == "centre"
        else (lambda y, s, z, **kw: page.text(page.left, y, s, z, **kw))
    )
    place(page.y, lh.name, size + 7, bold=True, colour=st.accent)
    page.y -= size + 4
    place(page.y, lh.tagline, size - 1.5, colour=st.muted(0.3))
    page.y -= size + 1
    for line in (
        f"Regd. Office: {lh.registered_office}",
        f"{lh.corporate_label}: {lh.corporate_id}  |  GSTIN: {lh.gstin}",
        f"Tel: {lh.telephone}  |  E-mail: {lh.email}  |  Web: {lh.website}",
    ):
        place(page.y, line, size - 2, colour=st.muted(0.25))
        page.y -= size - 0.5
    page.y -= 2
    page.rule(page.y, 1.6, st.accent)
    page.rule(page.y - 2.6, 0.5, st.accent)
    page.y -= 18


def _field(page: _Page, label: str, value: str, label_w: float):
    size = page.st.body_size
    page.need((size + 3) * 3)
    page.text(page.left, page.y, label, size, bold=True)
    page.text(page.left + label_w - 8, page.y, ":", size, bold=True)
    lines = wrap(value, page.st.regular_font, size, page.right - page.left - label_w)
    for i, line in enumerate(lines):
        page.text(page.left + label_w, page.y, line, size, bold=label.startswith("Sub"))
        if i < len(lines) - 1:
            page.y -= size + 3
    page.y -= size + 6


def _table(page: _Page, table: MemoTable):
    st = page.st
    span = page.right - page.left - 18
    x0 = page.left + 18
    cols = [w * span for w in table.widths]
    size = st.body_size - 1.5
    widest = max(
        [page.width(c, size, True) / (w - 8) for c, w in zip(table.columns, cols, strict=True)]
        + [
            page.width(v, size) / (w - 8)
            for row in table.rows
            for v, w in zip(row, cols, strict=True)
        ]
    )
    if widest > 1:
        size /= widest
    row_h = size + 7
    if table.caption:
        page.need(row_h)
        page.text(x0, page.y, table.caption, size + 0.5, bold=True)
        page.y -= size + 6
    page.need(row_h * (len(table.rows) + 1) + 6)
    top = page.y + size + 2
    tint = tuple(a + (p - a) * 0.86 for a, p in zip(st.accent, st.paper, strict=True))
    page.ops.append(rgb(tint) + f" {x0:.2f} {top - row_h:.2f} {span:.2f} {row_h:.2f} re f")
    for r, row in enumerate([table.columns, *table.rows]):
        baseline = top - row_h * r - row_h + 5
        x = x0
        for value, w, numeric in zip(row, cols, table.numeric, strict=True):
            bold = r == 0
            if numeric and r:
                page.text(x + w - 4 - page.width(value, size), baseline, value, size)
            else:
                page.text(x + 4, baseline, value, size, bold=bold)
            x += w
    bottom = top - row_h * (len(table.rows) + 1)
    line = st.muted(0.5)
    page.ops.append(rgb(line, "RG") + " 0.50 w")
    for r in range(len(table.rows) + 2):
        y = top - row_h * r
        page.ops.append(f"{x0:.2f} {y:.2f} m {x0 + span:.2f} {y:.2f} l S")
    x = x0
    for w in [0.0, *cols]:
        x += w
        page.ops.append(f"{x:.2f} {top:.2f} m {x:.2f} {bottom:.2f} l S")
    page.y = bottom - st.body_size - 5


def build_memo_pdf(
    path: Path | str, memo: Memo, style: DocumentStyle, page_losses: dict[int, str] | None = None
) -> int:
    """Write the memo; returns the page count stated in its footers.

    ``page_losses`` maps a 1-based page to ``TEXTLESS`` (the page keeps its graphics but has no
    text layer, as a flattened scan would) or ``MISSING`` (the page is absent from the file while
    the other pages still say "Page n of N").
    """
    page = _Page(style)
    size = style.body_size
    _letterhead(page, memo.letterhead, memo.letterhead_align)

    if memo.classification:
        page.right_aligned(
            page.y + 12, memo.classification, size - 2, bold=True, colour=style.accent
        )
    page.centred(page.y, memo.heading, size + 2.5, bold=True)
    w = page.width(memo.heading, size + 2.5, True)
    mid = (page.left + page.right) / 2
    page.rule(page.y - 3, 0.8, style.ink, mid - w / 2, mid + w / 2)
    page.y -= size + 12

    page.text(page.left, page.y, f"Ref. No.: {memo.ref_no}", size)
    page.running = f"Ref. No.: {memo.ref_no} dated {memo.date_text} (contd.)"
    page.right_aligned(page.y, f"Date: {memo.date_text}", size)
    page.y -= size + 12

    to_l, from_l, subject_l, ref_l = memo.labels
    label_w = max(page.width(x, size, True) for x in memo.labels) + 16
    _field(page, to_l, memo.to, label_w)
    _field(page, from_l, memo.sender, label_w)
    _field(page, subject_l, memo.subject, label_w)
    if memo.reference:
        _field(page, ref_l, memo.reference, label_w)
    page.rule(page.y + size - 2, 0.6)
    page.y -= 10

    def place(blocks, numbered=True):
        number = 0
        for block in blocks:
            if isinstance(block, MemoTable):
                _table(page, block)
                continue
            if isinstance(block, PageBreak):
                page.new_page()
                continue
            if isinstance(block, Heading):
                page.need((size + 3) * 2)
                page.text(page.left, page.y, block.text, size + 0.5, bold=True)
                page.y -= size + 9
                continue
            number += 1
            indent = 20 if numbered else 0
            lines = wrap(block, style.regular_font, size, page.right - page.left - indent)
            page.need((size + 3) * len(lines))
            if numbered:
                page.text(page.left, page.y, f"{number}.", size)
            for line in lines:
                page.text(page.left + indent, page.y, line, size)
                page.y -= size + 3
            page.y -= 4

    place(memo.blocks)

    page.need(size * 6)
    page.y -= 8
    x = page.right - max(
        page.width(s, size, bold)
        for s, bold in (
            ("Sd/-", False),
            (f"({memo.signatory})", True),
            (memo.designation, False),
            (memo.department, False),
        )
    )
    for s, bold in (
        ("Sd/-", False),
        (f"({memo.signatory})", True),
        (memo.designation, False),
        (memo.department, False),
    ):
        page.text(x, page.y, s, size, bold=bold)
        page.y -= size + 3
    page.y -= 8

    # Encl. and Copy to sit side by side under the signature, as on most office memos.
    lists = [
        (title, items)
        for title, items in (("Encl.", memo.enclosures), ("Copy to", memo.copy_to))
        if items
    ]
    if lists:
        rows = max(len(items) for _, items in lists) + 1
        page.need((size + 2) * rows)
        top = page.y
        for column, (title, items) in enumerate(lists):
            x = page.left + column * (page.right - page.left) / 2
            page.y = top
            page.text(x, page.y, f"{title}:", size - 0.5, bold=True)
            for i, item in enumerate(items, 1):
                page.y -= size + 2
                page.text(x + 14, page.y, f"{i}. {item}", size - 0.5)
        page.y = top - (size + 2) * rows

    # Annexures follow the signature and enclosure lists, each from its own page break.
    place(memo.extra.get("annexures", ()), numbered=False)

    count = len(page.pages)
    losses = {(n if n > 0 else count + n + 1): k for n, k in (page_losses or {}).items()}
    if any(n < 2 or n > count or k not in {"TEXTLESS", "MISSING"} for n, k in losses.items()):
        raise ValueError("a page loss must name a later page of the memo")
    foot, small = 40.0, max(size - 3, 6.5)
    for number, ops in enumerate(page.pages, 1):
        page.ops = ops
        if losses.get(number) == "TEXTLESS":
            # Keep paper, rules and table shading; drop every text object (no text layer).
            ops[:] = [op for op in ops if not op.startswith("BT ")]
            ops.extend(watermark_ops(style))
            continue
        page.rule(foot + 12, 0.4)
        page.text(
            page.left,
            foot,
            f"{memo.letterhead.name} - for internal circulation",
            small,
            colour=style.muted(0.3),
        )
        page.centred(foot - 10, WATERMARK, small, colour=style.muted(0.3))
        page.right_aligned(
            foot, f"Page {number} of {len(page.pages)}", small, colour=style.muted(0.3)
        )
        ops.extend(watermark_ops(style))
    stated = len(page.pages)
    write_pdf(
        path,
        [
            "\n".join(ops)
            for number, ops in enumerate(page.pages, 1)
            if losses.get(number) != "MISSING"
        ],
        fonts={"F1": style.regular_font, "F2": style.bold_font},
        alpha=style.watermark_alpha,
        info={
            "Title": f"{memo.heading} {memo.ref_no}",
            "Subject": WATERMARK,
            "Producer": "ReCycleGuard synthetic generator",
        },
    )
    return stated


__all__ = [
    "DATE_STYLES",
    "Heading",
    "Letterhead",
    "Memo",
    "MemoTable",
    "PageBreak",
    "build_memo_pdf",
    "indian_date",
    "indian_group",
    "rupees_in_words",
]
