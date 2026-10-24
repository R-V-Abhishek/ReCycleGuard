"""Contract tests for H01 source, extraction, coverage, and locator fixtures."""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from recycleguard.contracts import (
    BlobRef,
    CoverageItem,
    ExtractionResult,
    Locator,
    Observation,
    ProvisionVersion,
    SourceVersion,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures/visible/h01"


def test_source_version_r02_fixture():
    path = FIXTURES_DIR / "source_version_r02.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    sv = SourceVersion.model_validate(data)
    assert sv.source_version_id == "source_ver:r02_rules_2022_v1"
    assert sv.source_lead_id == "source_lead:r02"
    assert sv.notification_number == "G.S.R. 801(E)"
    assert sv.commencement.value == "2023-04-01"
    assert sv.review_state == "APPROVED"
    assert len(sv.commencement_basis_refs) == 1
    assert sv.commencement_basis_refs[0].locator.kind == "PDF_PAGE"
    assert sv.commencement_basis_refs[0].locator.page_index_1based == 1


def test_source_version_r08_fixture():
    path = FIXTURES_DIR / "source_version_r08.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    sv = SourceVersion.model_validate(data)
    assert sv.source_version_id == "source_ver:r08_cpcb_faq_20240123"
    assert sv.source_lead_id == "source_lead:r08"
    assert sv.notification_date.value == "2024-01-23"
    assert sv.completeness == "COMPLETE_TEXT"


def test_provision_version_r02_rule6_fixture():
    path = FIXTURES_DIR / "provision_version_r02_rule6.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    pv = ProvisionVersion.model_validate(data)
    assert pv.provision_version_id == "provision:r02_rule6_sub4"
    assert pv.role_scope == "SPECIFIC"
    assert pv.affected_roles == ["PRODUCER"]
    assert pv.locator.kind == "PDF_PAGE"
    assert pv.locator.page_index_1based == 8


def test_provision_version_r02_rule15_fixture():
    path = FIXTURES_DIR / "provision_version_r02_rule15.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    pv = ProvisionVersion.model_validate(data)
    assert pv.provision_version_id == "provision:r02_rule15_sub1_sub3"
    assert pv.role_scope == "GENERAL"
    assert set(pv.affected_roles) == {"PRODUCER", "RECYCLER"}
    assert pv.locator.page_index_1based == 14


def test_provision_version_r08_section_c_fixture():
    path = FIXTURES_DIR / "provision_version_r08_section_c.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    pv = ProvisionVersion.model_validate(data)
    assert pv.provision_version_id == "provision:r08_sec_c_recycler_capability"
    assert pv.locator.kind == "PDF_PAGE"
    assert pv.locator.page_index_1based == 9
    assert pv.applicability_assertion_id == "assertion:r08_metal_obligation_capability_independence"


def test_locator_examples_fixture():
    path = FIXTURES_DIR / "locator_examples.json"
    items = json.loads(path.read_text(encoding="utf-8"))
    assert len(items) == 5

    kinds = set()
    for item in items:
        loc = Locator.model_validate(item["locator"])
        kinds.add(loc.kind)

    assert kinds == {"PDF_PAGE", "PDF_CELL", "CSV_ROW", "JSON_POINTER", "TEXT_SPAN"}


def test_coverage_summary_fixture():
    path = FIXTURES_DIR / "coverage_summary.json"
    items = json.loads(path.read_text(encoding="utf-8"))
    assert len(items) >= 4

    dispositions = set()
    for item in items:
        ci = CoverageItem.model_validate(item)
        dispositions.add(ci.disposition)

    assert "PARSED" in dispositions
    assert "QUARANTINED" in dispositions
    assert "NOT_APPLICABLE" in dispositions


def test_extraction_result_fixture():
    path = FIXTURES_DIR / "extraction_result_sample.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    ext = ExtractionResult.model_validate(data)
    assert ext.status == "COMPLETE"
    assert ext.text_blob is not None
    assert len(ext.configuration_digest) == 64


def test_observation_sample_fixture():
    path = FIXTURES_DIR / "observation_sample.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    obs = Observation.model_validate(data)
    assert obs.observation_id == "obs:faq_sec_c_metal_obligation_capability"
    assert obs.extraction_method == "PDF_TEXT"
    assert obs.event_time.precision == "DATE"
    assert obs.source_capture_time.precision == "INSTANT"
    assert obs.ingestion_time.endswith("Z")


def test_acquired_original_faq_digest():
    pdf_path = FIXTURES_DIR / "acquired_originals/cpcb_faq_20240123.pdf"
    assert pdf_path.is_file()
    bytes_data = pdf_path.read_bytes()
    assert len(bytes_data) == 167964
    digest = hashlib.sha256(bytes_data).hexdigest()
    assert digest == "30f56238fb7db53dd82f69d198be9a92e31d98ea5b21d2724eb7397641a80d16"


def test_invalid_extraction_result_without_issues_rejected():
    blob = BlobRef(sha256="0" * 64, byte_length=100, media_type="text/plain")
    with pytest.raises(ValidationError, match="non-complete extraction requires explicit issues"):
        ExtractionResult(
            extraction_id="ext:fail01",
            artifact_revision_id="artifact_rev:some_doc",
            adapter_id="test_adapter",
            adapter_version="1.0",
            configuration_digest="0" * 64,
            text_blob=None,
            observations_blob=blob,
            coverage_blob=blob,
            status="FAILED",
            issues=[],
        )
