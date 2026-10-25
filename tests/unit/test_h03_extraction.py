"""Unit and regression tests for H03 extraction and page/row coverage.

Verifies:
- CSV row-level extraction guarantees terminal dispositions for every row.
- validate_row_coverage_consistency checks row bounds and continuity.
- JSON / JSONL extraction with JSON_POINTER locators.
- PDF page-level extraction verifies physical page count equals coverage records.
- Complete ExtractionResult conforms to CONTRACTS §3.3.
"""

from __future__ import annotations

from pathlib import Path

from recycleguard.contracts.artifacts import ArtifactRevision
from recycleguard.contracts.core import TemporalValue
from recycleguard.extraction import (
    extract_artifact,
    extract_csv,
    extract_json,
    extract_pdf_pages,
    validate_row_coverage_consistency,
)
from recycleguard.storage import BlobStore

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
CASE_001_DIR = FIXTURES_DIR / "visible/case_001"
H01_FIXTURES_DIR = FIXTURES_DIR / "visible/h01"


def test_extract_real_case_001_csv():
    csv_path = CASE_001_DIR / "documents/doc_ledger_export.csv"
    assert csv_path.is_file()
    bytes_data = csv_path.read_bytes()

    obs, cov, issues = extract_csv(bytes_data, "artifact_rev:test_csv", "ext:test_csv")

    assert len(obs) == 2
    assert len(cov) == 2
    assert not issues

    # Verify coverage consistency
    assert validate_row_coverage_consistency(2, cov)

    # Check locator kind and 1-based indexing
    assert [c.locator.row_index_1based for c in cov] == [1, 2]
    assert all(c.locator.kind == "CSV_ROW" for c in cov)
    assert all(c.disposition == "PARSED" for c in cov)


def test_extract_csv_quarantine_malformed_rows():
    malformed_csv = b"col1,col2,col3\nval1,val2,val3\nbad_row_only_one_col\nvalA,valB,valC\n"
    obs, cov, issues = extract_csv(malformed_csv, "artifact_rev:test_bad_csv", "ext:test_bad_csv")

    assert len(obs) == 2  # 2 parsed rows
    assert len(cov) == 3  # 3 total data rows

    assert cov[0].disposition == "PARSED"
    assert cov[1].disposition == "QUARANTINED"
    assert cov[1].reason_code == "CSV_COLUMN_COUNT_MISMATCH"
    assert cov[2].disposition == "PARSED"

    # All 3 rows accounted for
    assert validate_row_coverage_consistency(3, cov)
    assert len(issues) == 1
    assert issues[0].code == "INCOMPLETE_COVERAGE"


def test_extract_real_case_001_json():
    json_path = CASE_001_DIR / "documents/doc_source_records.json"
    assert json_path.is_file()
    bytes_data = json_path.read_bytes()

    obs, cov, issues = extract_json(bytes_data, "artifact_rev:test_json", "ext:test_json")

    assert len(obs) > 0
    assert len(cov) > 0
    assert not issues
    assert all(c.locator.kind == "JSON_POINTER" for c in cov)
    assert all(c.disposition == "PARSED" for c in cov)


def test_extract_real_pdf_faq_pages():
    pdf_path = H01_FIXTURES_DIR / "acquired_originals/cpcb_faq_20240123.pdf"
    assert pdf_path.is_file()
    bytes_data = pdf_path.read_bytes()

    obs, cov, text, issues = extract_pdf_pages(bytes_data, "artifact_rev:test_pdf", "ext:test_pdf")

    # 13 physical pages in the authentic FAQ PDF
    assert len(cov) == 13
    assert len(obs) == 13
    assert not issues

    page_numbers = [c.locator.page_index_1based for c in cov]
    assert page_numbers == list(range(1, 14))
    assert all(c.locator.kind == "PDF_PAGE" for c in cov)
    assert all(c.disposition == "PARSED" for c in cov)

    # Text contains meaningful CPCB content
    assert "Central Pollution Control Board" in text or "E-Waste" in text or "CPCB" in text


def test_extract_artifact_service_end_to_end(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    pdf_path = CASE_001_DIR / "documents/doc_invoice_payment.pdf"
    raw_bytes = pdf_path.read_bytes()

    blob_ref = store.put(raw_bytes, "application/pdf")
    revision = ArtifactRevision(
        artifact_id="artifact:invoice",
        artifact_revision_id="artifact_rev:invoice_001",
        blob=blob_ref,
        original_filename="doc_invoice_payment.pdf",
        source_kind="COMPANY_RECORD",
        doc_type="GST_INVOICE",
        establishes=["PAYMENT"],
        does_not_establish=["LIABILITY_ALLOCATION"],
        source_url=None,
        fetch_attempt_id=None,
        captured_at=TemporalValue(
            raw=None,
            value="2024-10-01",
            precision="DATE",
            timezone=None,
            interpretation_status="PARSED",
        ),
        ingested_at="2026-10-25T00:00:00Z",
        access_policy_id="policy:standard",
        rights_decision_id="decision:allow",
        synthetic=True,
        derived_from=[],
    )

    result, observations, coverage = extract_artifact(revision, store)

    assert result.artifact_revision_id == revision.artifact_revision_id
    assert result.status in {"COMPLETE", "PARTIAL"}
    assert result.text_blob is not None

    # Verify blobs stored
    obs_bytes = store.get(result.observations_blob)
    assert len(obs_bytes) > 0
    cov_bytes = store.get(result.coverage_blob)
    assert len(cov_bytes) > 0
