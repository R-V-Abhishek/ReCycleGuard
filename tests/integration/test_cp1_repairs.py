"""Regression cases found while joining the CP1 workstreams."""

import pytest

from recycleguard.extraction import extract_csv, extract_json, extract_pdf_pages
from recycleguard.normalization.equivalence import EventEquivalenceEngine
from recycleguard.normalization.service import NormalizationService
from recycleguard.normalization.units import (
    NumericSafetyError,
    normalize_quantity,
    parse_strict_decimal,
)
from tests.unit.test_event_equivalence import make_test_observation
from tests.unit.test_normalization_service import make_obs


def test_csv_decimal_identifier_and_precision_remain_exact():
    obs, _, _ = extract_csv(b"quantity,identifier\n1.12345678,00123\n", "artifact:test", "ext:test")
    assert obs[0].parsed_fields == {"quantity": "1.12345678", "identifier": "00123"}
    assert normalize_quantity("1.12345678", "KG", "METAL_MASS", metal="CU").decimal == "1.12345678"
    with pytest.raises(NumericSafetyError):
        normalize_quantity("0.000000001", "KG", "METAL_MASS", metal="CU")
    with pytest.raises(NumericSafetyError):
        parse_strict_decimal("1,2,3")
    with pytest.raises(NumericSafetyError):
        parse_strict_decimal(True)


def test_same_day_distinct_partial_transfers_are_not_conflicts():
    first = make_test_observation(
        "obs:one", "cert:one", "25", event_time_str="2024-09-15T10:00:00Z"
    )
    second = make_test_observation(
        "obs:two", "cert:one", "30", event_time_str="2024-09-15T11:00:00Z"
    )
    engine = EventEquivalenceEngine(
        authoritative_artifact_ids=frozenset({first.artifact_revision_id})
    )
    result = engine.resolve_observations("case:001", [first, second])
    assert len(result.events) == 2 and not result.equivalences
    assert all(event.assertion_state == "SUPPORTED" for event in result.events)
    assert {event.event_time.value for event in result.events} == {
        first.event_time.value,
        second.event_time.value,
    }


def test_unreviewed_authority_and_coarse_time_cannot_deduplicate():
    first = make_test_observation("obs:one", "cert:one", "25")
    second = first.model_copy(update={"observation_id": "obs:two"})
    result = EventEquivalenceEngine().resolve_observations("case:001", [first, second])
    assert len(result.events) == 2 and not result.equivalences
    assert all(event.assertion_state == "PENDING" for event in result.events)
    coarse = first.event_time.model_copy(update={"value": "2024-09-15", "precision": "DATE"})
    first = first.model_copy(update={"event_time": coarse})
    second = second.model_copy(update={"event_time": coarse})
    engine = EventEquivalenceEngine(
        authoritative_artifact_ids=frozenset({first.artifact_revision_id})
    )
    result = engine.resolve_observations("case:001", [first, second])
    assert len(result.events) == 2 and not result.equivalences
    assert all(event.assertion_state == "PENDING" for event in result.events)


def test_missing_obligation_facts_and_unknown_types_are_quarantined():
    missing = make_obs("obs:one", "ObligationObservation", {"bucket_id": "bucket:one"})
    unknown = make_obs("obs:two", "UnsupportedObservation", {})
    output = NormalizationService().normalize("case:001", [missing, unknown])
    assert not output.records
    assert all(
        d.disposition == "QUARANTINED" and not d.derived_record_ids for d in output.dispositions
    )
    assert len(output.issues) == 2


def test_bad_pdf_is_failed_without_backend_fallback_or_invented_pages():
    observations, coverage, _, issues = extract_pdf_pages(b"not a pdf", "artifact:bad", "ext:bad")
    assert observations == [] and coverage == []
    assert issues[0].code == "EXTRACTION_FAILED"


def test_json_root_pointer_and_scalar_failure():
    observations, coverage, issues = extract_json(b'{"x":1}', "artifact:test", "ext:test")
    assert observations[0].locator.json_pointer == ""
    assert not issues
    observations, coverage, issues = extract_json(
        b"42", "artifact:test", "ext:test", is_jsonl=False
    )
    # Scalar JSONL is an extracted value, not a normalized transaction.
    assert len(coverage) == 1


def test_failed_acquisition_is_audited_without_a_fabricated_blob(tmp_path):
    from recycleguard.application import local_application
    from recycleguard.config import Settings
    from recycleguard.contracts.sources import SourceLead
    from recycleguard.intake import record_acquisition

    lead = SourceLead.model_validate(
        {
            "source_lead_id": "source_lead:missing",
            "aliases": ["missing"],
            "official_url": "https://example.test/missing.pdf",
            "discovery_evidence_refs": [],
            "source_class": "NOTICE_LEAD",
            "regime": "E_WASTE_2022",
            "state": "DISCOVERED",
            "acquired_artifact_revision_id": None,
            "rights_and_license": {
                "copyright_owner": "test",
                "statutory_exception_sec52": None,
                "asset_rights_seed": "REVIEW_REQUIRED",
                "redistribution_allowed": False,
                "attribution_text": "test",
            },
        }
    )
    with local_application(Settings(data_root=tmp_path)) as (cases, context, cap):
        args = {
            "body_bytes": None,
            "status_code": 404,
            "blob_store": cases.kernel.blob_store,
            "catalog": cases.snapshots.catalog,
            "kernel": cases.kernel,
            "capability": cap,
            "context": context,
        }
        result = record_acquisition(lead, **args)
        assert result.artifact_revision is None
        assert cases.snapshots.catalog.get_receipt(result.receipt.receipt_id) == result.receipt
        assert record_acquisition(lead, **args) == result
        assert cases.kernel.get_result(context.operation_id).status == "PARTIAL"


def test_intake_recursion_original_manifest_and_exact_replay(tmp_path):
    from recycleguard.application import local_application
    from recycleguard.config import Settings
    from recycleguard.intake import intake_batch

    root = tmp_path / "case"
    path = root / "documents/nested/file with spaces.txt"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"original bytes")
    with local_application(Settings(data_root=tmp_path / "runtime")) as (cases, context, cap):
        args = {
            "blob_store": cases.kernel.blob_store,
            "catalog": cases.snapshots.catalog,
            "kernel": cases.kernel,
            "capability": cap,
            "context": context,
        }
        first = intake_batch(root, **args)
        assert [r.supplied_path_or_url for r in first.receipts] == [
            "documents/nested/file with spaces.txt"
        ]
        path.write_bytes(b"changed on disk")
        assert intake_batch(root, **args) == first
        assert cases.kernel.blob_store.get(first.artifact_revisions[0].blob) == b"original bytes"


def test_h04_source_helper_rejects_fake_pdf_under_official_identity(tmp_path):
    from recycleguard.knowledge import register_reviewed_sources
    from recycleguard.storage import BlobStore

    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"%PDF-1.4 fabricated")
    with pytest.raises(ValueError, match="digest differs"):
        register_reviewed_sources(BlobStore(tmp_path / "blobs"), r02_path=fake, r08_path=fake)
