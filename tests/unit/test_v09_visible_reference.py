"""Independent reference validation reads visible originals, never world answers."""

import hashlib
import json

import pytest

from benchmarks.evaluation.oracle import OracleBuilder
from benchmarks.evaluation.scoring import ScoringProtocol
from benchmarks.evaluation.validation import seal_oracles
from benchmarks.evaluation.visible_reference import (
    VisibleReference,
    bind_oracle_reference,
    encoded,
    inspect_visible,
)


@pytest.fixture(scope="module")
def pilot_visible(rendered_pilot):
    results = []
    for case, rendered in rendered_pilot:
        reference = inspect_visible(rendered.case_dir)
        results.append((case, rendered.case_dir, reference))
    return results


def test_all_48_original_visible_references_validate_and_seal_independently(pilot_visible):
    records, reviews, families, changes = {}, {}, set(), []
    for case, _directory, reference in pilot_visible:
        candidate = OracleBuilder.build_for_world(case.world)
        oracle, review, comparison = bind_oracle_reference(candidate, reference)
        assert comparison["balance_projection_agreement"]
        assert comparison["finding_families_agree"]
        assert reference.original_observation_checks > 0
        assert reference.evidence_inventory
        records[oracle.case_id], reviews[oracle.case_id] = oracle, review
        families.update(finding["issue_type"][:3] for finding in reference.findings)
        if comparison["removed_abstentions"]:
            changes.append(comparison)
        assert (
            ScoringProtocol().score_reconciliation(reference.balances, oracle).all_buckets_matched
        )
    assert len(records) == 48
    assert families == {f"F{number:02d}" for number in range(1, 17)}
    assert len(changes) == 4  # invalid ErrorCode used as an AbstentionReason in old projections
    seal = seal_oracles(
        records, dataset_version="pilot-0.1", reviewed_case_ids=records, review_records=reviews
    )
    assert seal.visible_reference_status == "INDEPENDENT_REFERENCE_VALIDATED"
    assert all(record.visible_reference_status != "HAND_REVIEWED" for record in records.values())


def _rewrite_declared(directory, path, body):
    path.write_bytes(body)
    manifest_path = directory / "case_manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    name = path.relative_to(directory).as_posix()
    asset = next(asset for asset in manifest["assets"] if asset["relative_path"] == name)
    asset.update(body_digest=hashlib.sha256(body).hexdigest(), byte_length=len(body))
    manifest_path.write_bytes(encoded(manifest))


def test_normalized_transfer_date_must_match_actual_original(pilot_visible, tmp_path):
    import shutil

    _, source, _ = pilot_visible[0]
    directory = tmp_path / "case"
    shutil.copytree(source, directory)
    path = directory / "records/certificate_events.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    event = next(row for row in rows if row["event_kind"] == "TRANSFERRED")
    event["event_time"]["value"] = "2023-01-01T00:00:00Z"
    _rewrite_declared(directory, path, b"".join(json.dumps(row).encode() + b"\n" for row in rows))
    with pytest.raises(ValueError, match="transfer (date|time) differs"):
        inspect_visible(directory)


def test_source_record_annotations_cannot_substitute_for_originals(pilot_visible, tmp_path):
    import shutil

    _, source, _ = pilot_visible[0]
    directory = tmp_path / "case"
    shutil.copytree(source, directory)
    path = directory / "records/allocations.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["quantity"]["decimal"] = "0.0001"
    _rewrite_declared(directory, path, b"".join(json.dumps(row).encode() + b"\n" for row in rows))
    with pytest.raises(ValueError, match="differs from original source row"):
        inspect_visible(directory)


def test_all_pdf_pages_accounted_and_injection_does_not_rewrite_facts(pilot_visible):
    missing, injected = [], []
    for _, _directory, reference in pilot_visible:
        families = {finding["issue_type"][:3] for finding in reference.findings}
        if "F15" in families:
            missing.append(reference)
            assert any(a["reason"] == "MISSING_EVIDENCE" for a in reference.abstentions)
        if "F16" in families:
            injected.append(reference)
            assert all(
                balance["supported"] != balance["required"] for balance in reference.balances
            )
    assert missing and injected


def test_independent_review_digest_changes_with_actual_reference(pilot_visible):
    case, _, reference = pilot_visible[0]
    oracle, review, _ = bind_oracle_reference(OracleBuilder.build_for_world(case.world), reference)
    payload = reference.payload()
    payload["limitations"] = [*payload["limitations"], "additional qualification"]
    changed = VisibleReference(**payload)
    changed_oracle, changed_review, _ = bind_oracle_reference(oracle, changed)
    assert changed_review.oracle_digest != review.oracle_digest
    assert changed_oracle.visible_reference_status == "INDEPENDENT_REFERENCE_VALIDATED"


pytestmark = pytest.mark.slow
