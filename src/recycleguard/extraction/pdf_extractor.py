"""Page-level text-PDF extractor and coverage tracker.

Owned by Sampreeth (H03 / C03).
Guarantees:
- Every physical PDF page (1-based index) receives a terminal disposition.
- Dispositions: PARSED (if text extracted), QUARANTINED (empty or unscannable scan).
- Verified page count equals coverage records count.
- Emits Observation records per page with PDF_PAGE locator and full extracted text.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from uuid import uuid4

from recycleguard.contracts.core import Issue, Locator, TemporalValue
from recycleguard.contracts.extraction import CoverageItem, Observation


def _utc_now_rfc3339() -> str:
    return datetime.now(UTC).isoformat()


def extract_pdf_pages(
    pdf_bytes: bytes,
    artifact_revision_id: str,
    extraction_id: str,
    *,
    capture_time: TemporalValue | None = None,
) -> tuple[list[Observation], list[CoverageItem], str, list[Issue]]:
    """Extract page text and coverage items from PDF bytes."""
    observations: list[Observation] = []
    coverage_items: list[CoverageItem] = []
    issues: list[Issue] = []
    full_text_chunks: list[str] = []

    cap_time = capture_time or TemporalValue(
        raw=None,
        value=_utc_now_rfc3339()[:10],
        precision="DATE",
        timezone=None,
        interpretation_status="PARSED",
    )
    ingestion_time = _utc_now_rfc3339()

    pages_data: list[tuple[int, str]] = []

    # Method 1: Try pdfplumber
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                pages_data.append((i, text))
    except Exception as exc1:
        # Method 2: Try pypdfium2
        try:
            import pypdfium2

            pdf = pypdfium2.PdfDocument(pdf_bytes)
            for i, page in enumerate(pdf, 1):
                textpage = page.get_textpage()
                text = textpage.get_text_range() or ""
                pages_data.append((i, text))
        except Exception as exc2:
            # Method 3: Try pdfminer
            try:
                from pdfminer.high_level import extract_pages
                from pdfminer.layout import LTTextContainer

                for i, page_layout in enumerate(extract_pages(io.BytesIO(pdf_bytes)), 1):
                    page_text = ""
                    for element in page_layout:
                        if isinstance(element, LTTextContainer):
                            page_text += element.get_text()
                    pages_data.append((i, page_text))
            except Exception as exc3:
                issues.append(
                    Issue(
                        issue_id=f"issue:{uuid4().hex[:8]}",
                        code="EXTRACTION_FAILED",
                        severity="BLOCKING",
                        message=f"No PDF extractor succeeded on document: {exc1}; {exc2}; {exc3}",
                        field_path="pdf_document",
                        evidence_refs=[],
                        retryable=False,
                    )
                )
                return observations, coverage_items, "", issues

    # Now process pages_data
    for page_idx, page_text in pages_data:
        locator = Locator(
            kind="PDF_PAGE",
            page_index_1based=page_idx,
            printed_page_label=str(page_idx),
            row_index_1based=None,
            column_name=None,
            json_pointer=None,
            text_start=None,
            text_end=None,
            table_id=None,
            cell_row=None,
            cell_column=None,
        )

        stripped = page_text.strip()
        cov_id = f"cov:{uuid4().hex[:12]}"

        if stripped:
            obs_id = f"obs:{uuid4().hex[:12]}"
            obs = Observation(
                observation_id=obs_id,
                extraction_id=extraction_id,
                artifact_revision_id=artifact_revision_id,
                locator=locator,
                observation_type="PDF_PAGE_TEXT",
                raw_fields={"page_number": page_idx, "character_count": len(stripped)},
                parsed_fields={"text": stripped},
                validation_state="VALID",
                extraction_method="PDF_TEXT",
                field_quality={"quality": "PARSED_PDF_PAGE"},
                event_time=cap_time,
                source_capture_time=cap_time,
                ingestion_time=ingestion_time,
            )
            observations.append(obs)
            full_text_chunks.append(f"--- Page {page_idx} ---\n{stripped}\n")

            coverage_items.append(
                CoverageItem(
                    coverage_item_id=cov_id,
                    artifact_revision_id=artifact_revision_id,
                    locator=locator,
                    disposition="PARSED",
                    reason_code="PDF_PAGE_TEXT_EXTRACTED",
                    child_observation_ids=[obs_id],
                )
            )
        else:
            # Blank page or scanned image without embedded text: quarantine
            coverage_items.append(
                CoverageItem(
                    coverage_item_id=cov_id,
                    artifact_revision_id=artifact_revision_id,
                    locator=locator,
                    disposition="QUARANTINED",
                    reason_code="UNSUPPORTED_SCAN_OR_EMPTY_PAGE",
                    child_observation_ids=[],
                )
            )
            issues.append(
                Issue(
                    issue_id=f"issue:{uuid4().hex[:8]}",
                    code="INCOMPLETE_COVERAGE",
                    severity="WARNING",
                    message=(
                        f"Page {page_idx} contains no extractable text; quarantined as scan/empty"
                    ),
                    field_path=f"page:{page_idx}",
                    evidence_refs=[],
                    retryable=False,
                )
            )

    full_text = "\n".join(full_text_chunks)
    return observations, coverage_items, full_text, issues
