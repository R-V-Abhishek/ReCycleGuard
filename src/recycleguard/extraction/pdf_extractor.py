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
from typing import TYPE_CHECKING
from uuid import uuid4

from recycleguard.contracts.core import Issue, Locator, TemporalValue
from recycleguard.contracts.extraction import CoverageItem, Observation

if TYPE_CHECKING:
    from recycleguard.extraction.vlm_parser import VLMPdfParser


def _utc_now_rfc3339() -> str:
    return datetime.now(UTC).isoformat()


def extract_pdf_pages(
    pdf_bytes: bytes,
    artifact_revision_id: str,
    extraction_id: str,
    *,
    capture_time: TemporalValue | None = None,
    vlm_parser: VLMPdfParser | None = None,
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

    import pdfplumber
    from pdfminer.pdfdocument import PDFPasswordIncorrect
    from pdfminer.pdfparser import PDFSyntaxError
    from pdfminer.psparser import PSEOF
    from pdfplumber.utils.exceptions import PdfminerException

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                pages_data.append((i, page.extract_text() or ""))
    except (
        ValueError,
        OSError,
        PDFSyntaxError,
        PDFPasswordIncorrect,
        PSEOF,
        PdfminerException,
    ) as exc:
        issues.append(
            Issue(
                issue_id=f"issue:{uuid4().hex}",
                code="EXTRACTION_FAILED",
                severity="BLOCKING",
                message=f"PDF parsing failed: {exc}",
                field_path=None,
                evidence_refs=[],
                retryable=False,
            )
        )
        return [], [], "", issues

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
        extraction_method = "PDF_TEXT"
        vlm_tables = []

        if not stripped and vlm_parser is not None:
            try:
                vlm_page = vlm_parser.parse_page(page_text, page_idx)
                if vlm_page.raw_markdown.strip():
                    stripped = vlm_page.raw_markdown.strip()
                    extraction_method = "VLM_ASSISTED"
                    vlm_tables = [
                        {
                            "table_id": t.table_id,
                            "caption": t.caption,
                            "headers": t.headers,
                            "rows": t.rows,
                            "footnotes": t.footnotes,
                        }
                        for t in vlm_page.tables
                    ]
            except Exception:
                pass

        if stripped:
            obs_id = f"obs:{uuid4().hex[:12]}"
            parsed_fields: dict[str, object] = {"text": stripped}
            if vlm_tables:
                parsed_fields["vlm_tables"] = vlm_tables
            obs = Observation(
                observation_id=obs_id,
                extraction_id=extraction_id,
                artifact_revision_id=artifact_revision_id,
                locator=locator,
                observation_type="PDF_PAGE_TEXT",
                raw_fields={"page_number": page_idx, "character_count": len(stripped)},
                parsed_fields=parsed_fields,
                validation_state="VALID",
                extraction_method=extraction_method,
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
