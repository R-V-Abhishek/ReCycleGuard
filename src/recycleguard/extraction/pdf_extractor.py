"""Page-level text-PDF extractor and coverage tracker.

Owned by Sampreeth (H03 / C03).
Guarantees:
- Every physical PDF page (1-based index) receives a terminal disposition.
- Dispositions: PARSED (if text extracted), QUARANTINED (empty or unscannable scan).
- Verified page count equals coverage records count.
- Emits Observation records per page with PDF_PAGE locator and full extracted text.
- A file whose "Page X of N" footers state more pages than it holds is flagged
  INCOMPLETE_COVERAGE for each printed page that is absent (truncated file).
"""

import io
import re
from datetime import UTC, datetime
from uuid import uuid4

from recycleguard.contracts.core import Issue, Locator, TemporalValue
from recycleguard.contracts.extraction import CoverageItem, Observation

_PAGE_FOOTER = re.compile(r"\bPage\s+(\d+)\s+of\s+(\d+)\b", re.IGNORECASE)


def _utc_now_rfc3339() -> str:
    return datetime.now(UTC).isoformat()


def _missing_printed_pages(pages_data: list[tuple[int, str]]) -> tuple[int, list[int]]:
    """Printed page numbers a consistent "Page X of N" footer promises but the file lacks.

    Only one stated total across the file counts; mixed totals (merged documents) and
    footers that fit the physical count prove nothing and return no missing pages.
    """
    printed: set[int] = set()
    totals: set[int] = set()
    by_page: dict[int, int] = {}
    for page_idx, text in pages_data:
        for number, total in _PAGE_FOOTER.findall(text):
            printed.add(int(number))
            totals.add(int(total))
            by_page[page_idx] = int(number)
    if len(totals) != 1:
        return 0, []
    (stated,) = totals
    if stated <= len(pages_data) or any(n < 1 or n > stated for n in printed):
        return stated, []
    # A page without text is present (and quarantined above); infer its printed number
    # from a neighbouring footer so it is not reported a second time as absent.
    for page_idx, text in pages_data:
        if not text.strip():
            if page_idx - 1 in by_page:
                printed.add(by_page[page_idx - 1] + 1)
            elif page_idx + 1 in by_page:
                printed.add(by_page[page_idx + 1] - 1)
    return stated, [n for n in range(1, stated + 1) if n not in printed]


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

    # Coverage stays one item per physical page; an absent page has no locator of its own,
    # so the gap is reported against the printed page number.
    stated, missing = _missing_printed_pages(pages_data)
    for number in missing:
        issues.append(
            Issue(
                issue_id=f"issue:{uuid4().hex[:8]}",
                code="INCOMPLETE_COVERAGE",
                severity="WARNING",
                message=(
                    f"Footers state {stated} pages but the file holds {len(pages_data)}; "
                    f"printed page {number} is absent"
                ),
                field_path=f"page:{number}",
                evidence_refs=[],
                retryable=False,
            )
        )

    full_text = "\n".join(full_text_chunks)
    return observations, coverage_items, full_text, issues
