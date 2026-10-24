import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from recycleguard.contracts.artifacts import ArtifactRevision, AssetReceipt
from recycleguard.contracts.core import TemporalValue, utc_timestamp
from recycleguard.contracts.domain import RECORD_ADAPTER, Allocation
from recycleguard.contracts.dossier import CaseManifest
from recycleguard.contracts.extraction import CoverageItem, Observation
from recycleguard.extraction import validate_row_coverage_consistency

CASE = Path(__file__).parents[1] / "fixtures/visible/case_001"
RECORD_FILES = [
    "entities",
    "registrations",
    "obligations",
    "certificates",
    "certificate_events",
    "allocations",
    "commercial_records",
    "account_balances",
]


@pytest.mark.parametrize("name", RECORD_FILES)
def test_s01_producer_uses_shared_domain_consumer(name):
    for line in (CASE / f"records/{name}.jsonl").read_text().splitlines():
        value = RECORD_ADAPTER.validate_json(line)
        assert RECORD_ADAPTER.validate_json(value.model_dump_json()) == value


@pytest.mark.parametrize(
    "name,model",
    [
        ("certificate_observations", Observation),
        ("observations", Observation),
        ("artifacts", ArtifactRevision),
        ("receipts", AssetReceipt),
    ],
)
def test_s01_producer_uses_h01_and_storage_consumers(name, model):
    for line in (CASE / f"records/{name}.jsonl").read_text().splitlines():
        value = model.model_validate_json(line)
        assert model.model_validate_json(value.model_dump_json()) == value


def test_manifest_is_not_an_approved_snapshot():
    manifest = CaseManifest.model_validate_json((CASE / "case_manifest.json").read_bytes())
    assert manifest.status == "DRAFT"
    assert len(manifest.assets) == 16
    assert manifest.adapter_versions


@pytest.mark.parametrize(
    "path",
    [
        "../expected/answers.json",
        "/tmp/hidden.json",
        "records/../../secret",
        "benchmarks/truth.json",
        "documents\\..\\secret",
    ],
)
def test_manifest_traversal_rejected(path):
    data = json.loads((CASE / "case_manifest.json").read_text())
    data["assets"][0]["relative_path"] = path
    with pytest.raises(ValidationError):
        CaseManifest.model_validate_json(json.dumps(data))


@pytest.mark.parametrize(
    "value", ["2025-04-31T00:00:00Z", "2025-04-02T00:00:00", "2025-04-02T00:00:00+05:30"]
)
def test_ingestion_runtime_clock_requires_real_utc(value):
    with pytest.raises(ValueError):
        utc_timestamp(value)


def test_missing_s01_ingestion_clock_cannot_pass_h01():
    data = json.loads((CASE / "records/certificate_observations.jsonl").read_text().splitlines()[0])
    del data["ingestion_time"]
    with pytest.raises(ValidationError):
        Observation.model_validate(data)


def test_negative_allocation_rejected():
    data = json.loads((CASE / "records/allocations.jsonl").read_text())
    data["quantity"]["decimal"] = "-1"
    with pytest.raises(ValidationError):
        Allocation.model_validate(data)


def test_row_coverage_requires_distinct_data_rows_not_just_count():
    base = json.loads((CASE / "records/certificate_observations.jsonl").read_text().splitlines()[0])

    def item(row):
        return CoverageItem(
            coverage_item_id=f"coverage:{row}",
            artifact_revision_id="art:csv",
            locator={**base["locator"], "row_index_1based": row},
            disposition="PARSED",
            reason_code="OK",
            child_observation_ids=[],
        )

    assert validate_row_coverage_consistency(2, [item(1), item(2)])
    assert not validate_row_coverage_consistency(2, [item(1), item(1)])
    assert not validate_row_coverage_consistency(2, [item(2), item(3)])
    assert not validate_row_coverage_consistency(-1, [])


def test_source_date_cannot_invent_instant_precision():
    with pytest.raises(ValidationError):
        TemporalValue(
            raw="2024-04-01",
            value="2024-04-01T00:00:00Z",
            precision="DATE",
            timezone="UTC",
            interpretation_status="PARSED",
        )


@pytest.mark.parametrize("event_kind", ["EXPIRED", "CANCELLED", "STATUS_OBSERVED"])
def test_shared_certificate_id_does_not_erase_distinct_lifecycle_events(event_kind):
    from recycleguard.contracts.domain import CertificateEvent

    source = json.loads((CASE / "records/certificate_events.jsonl").read_text())
    original = CertificateEvent.model_validate(source)
    changed = {
        **source,
        "event_id": "evt:other",
        "record_id": "evt:other",
        "record_revision_id": "rev:other",
        "event_kind": event_kind,
        "external_event_ref": "TXN-2024-999",
    }
    event = CertificateEvent.model_validate(changed)
    assert event.certificate_id == original.certificate_id
    assert event.credit_lot_id == original.credit_lot_id
    assert event.event_id != original.event_id
    assert event.event_kind != original.event_kind


def test_qualified_calculation_and_explicit_abstention_interchange():
    from recycleguard.contracts import ServiceResult
    from recycleguard.contracts.results import CalculationResult, FindingRecord

    root = CASE.parents[1] / "expected"
    calculation = CalculationResult.model_validate_json(
        (root / "cp0_calculation.json").read_bytes()
    )
    finding = FindingRecord.model_validate_json((root / "cp0_finding.json").read_bytes())
    result = ServiceResult[CalculationResult](
        contract_version="1.1",
        operation_id="operation:cp0",
        attempt_id="attempt:cp0",
        status="PARTIAL",
        output=calculation,
        output_blob=None,
        issues=calculation.issues,
        dependencies=[],
        audit_event_ids=[],
    )
    assert ServiceResult[CalculationResult].model_validate_json(result.model_dump_json()) == result
    assert finding.ledger_supported_value_ref.calculation_id == calculation.calculation_id
    assert finding.abstention_reason == "MISSING_EVIDENCE"
    bad = json.loads(finding.model_dump_json())
    bad["advisory_status"] = "RECONCILED_WITHIN_SCOPE"
    with pytest.raises(ValidationError):
        FindingRecord.model_validate(bad)


@pytest.mark.parametrize(
    "status,artifact,reason",
    [
        ("RECEIVED", None, None),
        ("DECLARED_MISSING", "art:invented", "missing"),
        ("FETCH_FAILED", None, None),
    ],
)
def test_receipt_cannot_invent_success_or_missing_artifacts(status, artifact, reason):
    data = json.loads((CASE / "records/receipts.jsonl").read_text().splitlines()[0])
    data.update(intake_status=status, artifact_revision_id=artifact, reason=reason)
    with pytest.raises(ValidationError):
        AssetReceipt.model_validate(data)


def test_calculation_result_rejects_mixed_metal_output():
    from recycleguard.contracts.results import CalculationResult

    data = json.loads((CASE.parents[1] / "expected/cp0_calculation.json").read_text())
    data["bucket_results"][0]["signed_gap"]["metal"] = "AU"
    with pytest.raises(ValidationError, match="share dimension, metal and unit"):
        CalculationResult.model_validate(data)
