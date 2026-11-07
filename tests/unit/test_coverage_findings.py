"""Page loss is reported as F15 and withheld, never read as an empty page or a reason to stop."""

from pathlib import Path

from recycleguard.contracts.core import Issue
from recycleguard.contracts.extraction import ExtractionResult
from recycleguard.extraction.pdf_extractor import extract_pdf_pages
from recycleguard.reporting.coverage_findings import coverage_findings

DOCUMENTS = Path(__file__).resolve().parents[1] / "fixtures/visible/case_c42a634c48/documents"
CASE = "snapshot:coverage"


def extraction(revision, issues):
    return ExtractionResult.model_construct(artifact_revision_id=revision, issues=list(issues))


def issue(path, code="INCOMPLETE_COVERAGE"):
    return Issue(
        issue_id=f"issue:{path.replace(':', '_')}",
        code=code,
        severity="WARNING",
        message="test",
        field_path=path,
        evidence_refs=[],
        retryable=False,
    )


def test_a_textless_page_is_one_withheld_finding_citing_its_page():
    path = next(DOCUMENTS.glob("memo_*.pdf"))
    _, coverage, _, issues = extract_pdf_pages(path.read_bytes(), "artrev:memo", "ext:memo")
    (finding,) = coverage_findings(CASE, [(extraction("artrev:memo", issues), coverage)])
    assert finding.issue_type == "F15_EXTRACTION_PAGE_LOSS"
    assert finding.advisory_status == "REQUIRES_EXPERT_REVIEW"
    assert (finding.abstention_reason, finding.withheld_claim_scopes) == (
        "MISSING_EVIDENCE",
        ["lost_document_page"],
    )
    (ref,) = finding.fact_refs
    assert (ref.ref_kind, ref.ref_id) == ("ARTIFACT", "artrev:memo")
    assert ref.locator.kind == "PDF_PAGE" and ref.locator.page_index_1based == 2


def test_a_missing_printed_page_is_reported_without_a_page_locator():
    (finding,) = coverage_findings(CASE, [(extraction("artrev:memo", [issue("page:3")]), [])])
    assert finding.fact_refs[0].locator is None
    assert finding.next_action.kind == "REQUEST_EVIDENCE"


def test_row_problems_parser_failures_and_clean_documents_are_not_page_loss():
    others = [
        (extraction("artrev:ledger", [issue("row:4")]), []),
        (extraction("artrev:scan", [issue("page:1", code="EXTRACTION_FAILED")]), []),
        (extraction("artrev:invoice", []), []),
    ]
    assert coverage_findings(CASE, others) == []
