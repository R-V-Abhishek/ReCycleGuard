"""Vision-Language Model (VLM) PDF parser interface and adapter for RAG.

Owned by Sampreeth (H03 / H05).
Defines an optional injected parser boundary for scanned pages and tables.
No OCR/VLM engine, model gateway, or inference fallback is implemented here.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class VLMTable:
    """Structured table extracted by VLM."""

    table_id: str
    caption: str | None
    headers: list[str]
    rows: list[list[str]]
    footnotes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VLMPageExtraction:
    """Multimodal page representation extracted by VLM."""

    page_number: int
    raw_markdown: str
    clauses: list[dict[str, Any]] = field(default_factory=list)
    tables: list[VLMTable] = field(default_factory=list)
    visual_notes: list[str] = field(default_factory=list)
    model_name: str = "vlm-parser"
    confidence_score: float | None = None


class VLMPdfParser(Protocol):
    """Protocol for multimodal Vision-Language Model PDF page parsing."""

    def parse_page(
        self,
        page_bytes_or_text: bytes | str,
        page_number: int,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> VLMPageExtraction:
        """Extract one page from the original PDF bytes or supplied page text.

        PDF callers supply the entire immutable file and the requested 1-based page
        in metadata. An implementation must explicitly support that input or raise
        ValueError. No model gateway, OCR engine, or automatic fallback is selected.
        """
        ...


class DeterministicVLMPdfParser:
    """Text-only test double implementing the optional parser contract.

    Exercises table and clause preservation from supplied text. It does not perform
    OCR, image interpretation, or inference and cannot handle PDF/image bytes.
    """

    def __init__(self, model_name: str = "vlm-offline-test-double"):
        self.model_name = model_name

    def parse_page(
        self,
        page_bytes_or_text: bytes | str,
        page_number: int,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> VLMPageExtraction:
        if type(page_bytes_or_text) is not str:
            raise ValueError("Text-only test parser cannot extract a PDF or scanned image")
        text = page_bytes_or_text

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        clauses: list[dict[str, Any]] = []
        tables: list[VLMTable] = []
        current_clause: dict[str, Any] | None = None

        for line in lines:
            if (
                line.startswith("Rule ")
                or line.startswith("Section ")
                or line.startswith("Clause ")
            ):
                if current_clause:
                    clauses.append(current_clause)
                current_clause = {
                    "heading": line,
                    "text": line,
                    "page_number": page_number,
                }
            elif current_clause:
                current_clause["text"] += " " + line

            # Simple tabular detection for pipe-delimited or comma-separated rows
            if "|" in line:
                cells = [c.strip() for c in line.split("|") if c.strip()]
                if len(cells) >= 2:
                    if not tables:
                        tables.append(
                            VLMTable(
                                table_id=f"table_p{page_number}_1",
                                caption=f"Table on page {page_number}",
                                headers=cells,
                                rows=[],
                            )
                        )
                    else:
                        tables[-1].rows.append(cells)

        if current_clause:
            clauses.append(current_clause)

        return VLMPageExtraction(
            page_number=page_number,
            raw_markdown=text,
            clauses=clauses,
            tables=tables,
            model_name=self.model_name,
        )
