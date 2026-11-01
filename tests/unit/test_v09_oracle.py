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
        {oracle.case_id: oracle},
        dataset_version="case-001",
        reviewed_case_ids=[oracle.case_id],
        review_records={oracle.case_id: review_record(oracle)},
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


def review_record(oracle):
    from benchmarks.evaluation.validation import VisibleReferenceReview, oracle_digest

    return VisibleReferenceReview(
        reviewer_ref="human:synthetic_test_reviewer",
        oracle_digest=oracle_digest(oracle),
        visible_input_digest="1" * 64,
        evidence_refs=["artifact:synthetic_test_original"],
        reference_calculation_refs=oracle.reference_calculation_refs,
        recorded_at="2026-11-01T00:00:00Z",
    )


def test_reviewed_ids_cannot_promote_an_unreviewed_projection():
    oracle = OracleBuilder.build_for_world(build_worlds()[0])
    with pytest.raises(ValueError, match="cannot be promoted"):
        seal_oracles(
            {oracle.case_id: oracle},
            dataset_version="test",
            reviewed_case_ids=[oracle.case_id],
            review_records={oracle.case_id: review_record(oracle)},
        )


def test_review_requires_exact_oracle_and_calculation_evidence():
    oracle = OracleBuilder.build_for_case_001()
    kwargs = dict(dataset_version="test", reviewed_case_ids=[oracle.case_id])
    with pytest.raises(ValueError, match="independent review records"):
        seal_oracles({oracle.case_id: oracle}, **kwargs)
    review = review_record(oracle)
    with pytest.raises(ValueError, match="oracle digest"):
        seal_oracles(
            {oracle.case_id: oracle},
            **kwargs,
            review_records={oracle.case_id: review.model_copy(update={"oracle_digest": "0" * 64})},
        )
    with pytest.raises(ValueError, match="calculation references"):
        seal_oracles(
            {oracle.case_id: oracle},
            **kwargs,
            review_records={
                oracle.case_id: review.model_copy(
                    update={"reference_calculation_refs": ["calc:unrelated"]}
                )
            },
        )


@pytest.mark.parametrize("value", [55.0, 55, "5.5e1", "055", "NaN", "1.123456789"])
def test_oracle_rejects_noncanonical_quantities(value):
    oracle = OracleBuilder.build_for_case_001()
    balance = oracle.expected_world_balances[0] | {"supported": value}
    assert not validate_oracle(
        oracle.model_copy(update={"expected_world_balances": [balance]})
    ).valid


@pytest.mark.parametrize(
    "field,value",
    [
        ("metal", "CU_OTHER"),
        ("unit", "TONNE"),
        ("liability_year", "2024-2026"),
        ("bucket_id", None),
        ("required", "-1"),
        ("supported", "-1"),
    ],
)
def test_oracle_rejects_invalid_dimensions_and_negative_values(field, value):
    oracle = OracleBuilder.build_for_case_001()
    balance = oracle.expected_world_balances[0] | {field: value}
    assert not validate_oracle(
        oracle.model_copy(update={"expected_world_balances": [balance]})
    ).valid


def test_oracle_rejects_missing_duplicate_or_dimension_shifted_buckets():
    oracle = OracleBuilder.build_for_case_001()
    first = oracle.expected_world_balances[0]
    second = first | {"bucket_id": "bucket:second"}
    for balances in ([], [first, first], [first, second]):
        assert not validate_oracle(
            oracle.model_copy(update={"expected_world_balances": balances})
        ).valid
    shifted = oracle.visible_evidence_balances[0] | {"metal": "AU"}
    assert not validate_oracle(
        oracle.model_copy(update={"visible_evidence_balances": [shifted]})
    ).valid


def test_world_validation_rejects_wrong_case_and_dimensions():
    world = build_worlds()[0]
    oracle = OracleBuilder.build_for_world(world)
    assert not validate_oracle_against_world(
        world, oracle.model_copy(update={"case_id": "case:unrelated"})
    ).valid
    changed = [
        balance | {"metal": "AU" if balance["metal"] != "AU" else "CU"}
        for balance in oracle.expected_world_balances
    ]
    assert not validate_oracle_against_world(
        world, oracle.model_copy(update={"expected_world_balances": changed})
    ).valid


def test_seal_rejects_wrong_mapping_identity_or_mixed_rubric():
    oracle = OracleBuilder.build_for_case_001()
    with pytest.raises(ValueError, match="mapping key"):
        seal_oracles({"case:wrong": oracle}, dataset_version="test")
    other = oracle.model_copy(update={"case_id": "case:other", "review_rubric_version": "other"})
    with pytest.raises(ValueError, match="one rubric"):
        seal_oracles({oracle.case_id: oracle, other.case_id: other}, dataset_version="test")


def test_full_pilot_world_arithmetic_validates_without_claiming_visible_review():
    from benchmarks.generator.pilot_cases import build_pilot_cases

    cases = build_pilot_cases()
    assert len(cases) == 48
    records = {}
    for case in cases:
        oracle = OracleBuilder.build_for_world(case.world)
        result = validate_oracle_against_world(case.world, oracle)
        assert result.valid, (result.numeric_errors, result.rubric_errors)
        records[oracle.case_id] = oracle
    assert len(records) == 48
    seal = seal_oracles(records, dataset_version="pilot-0.1")
    assert seal.reviewed_case_ids == []
    assert seal.visible_reference_status == "UNVERIFIED_WORLD_PROJECTION"
