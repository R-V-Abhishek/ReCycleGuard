"""V09 independent oracle validation and held-out access controls."""

import pytest

from benchmarks.evaluation.oracle import OracleBuilder
from benchmarks.evaluation.validation import (
    HeldOutAccessRecord,
    record_heldout_access,
    seal_oracles,
    validate_oracle,
    validate_oracle_against_world,
)
from benchmarks.generator.s05_cases import build_worlds


def test_case_001_oracle_validates_and_seals_as_reviewed():
    oracle = OracleBuilder.build_for_case_001()
    validation = validate_oracle(oracle)
    assert validation.valid
    seal = seal_oracles(
        {oracle.case_id: oracle}, dataset_version="case-001", reviewed_case_ids=[oracle.case_id]
    )
    assert seal.visible_reference_status == "HAND_REVIEWED"
    assert seal.reviewed_case_ids == [oracle.case_id]


def test_generated_projection_cannot_be_promoted_without_review():
    world = build_worlds()[0]
    oracle = OracleBuilder.build_for_world(world)
    assert validate_oracle_against_world(world, oracle).valid
    seal = seal_oracles({oracle.case_id: oracle}, dataset_version="pilot-0.1")
    assert seal.visible_reference_status == "UNVERIFIED_WORLD_PROJECTION"


def test_invalid_balance_is_rejected_before_sealing():
    oracle = OracleBuilder.build_for_case_001()
    balance = oracle.visible_evidence_balances[0] | {"signed_gap": "44.0000"}
    invalid = oracle.model_copy(update={"visible_evidence_balances": [balance]})
    assert not validate_oracle(invalid).valid
    with pytest.raises(ValueError, match="oracle validation failed"):
        seal_oracles({invalid.case_id: invalid}, dataset_version="case-001")


def test_heldout_access_requires_closed_run_and_matching_digests(tmp_path):
    oracle = OracleBuilder.build_for_case_001()
    seal = seal_oracles({oracle.case_id: oracle}, dataset_version="case-001")
    record = HeldOutAccessRecord(
        access_id="access:test",
        dataset_version="case-001",
        run_id="run:test",
        case_ids=[oracle.case_id],
        visible_input_digests={oracle.case_id: "0" * 64},
        oracle_digests={oracle.case_id: seal.oracle_digests[oracle.case_id]},
        purpose="closed trial scoring",
        recorded_at="2026-11-01T00:00:00Z",
        run_closed=True,
        oracle_loaded_after_close=True,
    )
    path = tmp_path / "heldout-access.jsonl"
    record_heldout_access(path, record, seal)
    assert path.read_text(encoding="utf-8").count("access:test") == 1
    with pytest.raises(ValueError, match="closed run"):
        record_heldout_access(path, record.model_copy(update={"run_closed": False}), seal)
