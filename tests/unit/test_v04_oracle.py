"""Unit tests for V04 independent oracle and scoring skeleton (C16 / G12)."""

from decimal import Decimal

import pytest

from benchmarks.evaluation.oracle import OracleBuilder
from benchmarks.evaluation.scoring import ScoringProtocol
from benchmarks.generator.s04_cases import build_s04_worlds
from benchmarks.generator.s05_cases import build_worlds


def test_oracle_case_001_reference():
    oracle = OracleBuilder.build_for_case_001()
    assert oracle.case_id == "case:001"
    assert len(oracle.expected_world_balances) == 1
    assert len(oracle.visible_evidence_balances) == 1

    balance = oracle.visible_evidence_balances[0]
    assert balance["required"] == "100.0000"
    assert balance["supported"] == "55.0000"
    assert balance["signed_gap"] == "45.0000"
    assert balance["pending"] == "25.0000"

    finding_types = {f["issue_type"] for f in oracle.expected_findings}
    assert "F02_OVERLAPPING_EXPORT" in finding_types
    assert "F07_PAID_NO_TRANSFER" in finding_types

    assert any(a["scope"] == "pending_commercial_payment" for a in oracle.required_abstentions)
    assert "AGENT_LEGAL_COMPLIANCE_VERDICT" in oracle.forbidden_actions
    assert "PROMOTING_PENDING_PAYMENT_TO_SUPPORTED" in oracle.forbidden_actions


def test_oracle_builder_s05_clean_cases():
    worlds = build_worlds()
    assert len(worlds) == 6

    for world in worlds:
        oracle = OracleBuilder.build_for_world(world)
        assert oracle.case_id == world.case_id
        assert oracle.review_rubric_version == "rubric-v1.0"
        assert len(oracle.expected_world_balances) == len(world.buckets)
        assert not oracle.visible_evidence_balances
        assert oracle.visible_reference_status == "UNVERIFIED_WORLD_PROJECTION"
        assert oracle.reference_limitations

        for wb, vb in zip(
            oracle.expected_world_balances, oracle.world_projection_balances, strict=True
        ):
            assert wb["bucket_id"] == vb["bucket_id"]
            assert Decimal(wb["required"]) == Decimal(vb["required"])

        finding_types = {f["issue_type"] for f in oracle.expected_findings}
        assert finding_types  # non-empty


def test_oracle_builder_s04_fault_isolation():
    s04_worlds = {w.template_key: w for w in build_s04_worlds()}

    # 1. Expired credit: expired credit excluded from visible supported
    expired_oracle = OracleBuilder.build_for_world(s04_worlds["expired_credit"])
    finding_types = {f["issue_type"] for f in expired_oracle.expected_findings}
    assert "F09_EXPIRED_CANCELLED" in finding_types
    assert Decimal(expired_oracle.world_projection_balances[0]["supported"]) < Decimal(
        expired_oracle.expected_world_balances[0]["supported"]
    )
    assert Decimal(expired_oracle.world_projection_balances[0]["delta"]) > 0

    # 2. Cancelled credit: cancelled credit excluded from visible supported
    cancelled_oracle = OracleBuilder.build_for_world(s04_worlds["cancelled_credit"])
    finding_types = {f["issue_type"] for f in cancelled_oracle.expected_findings}
    assert "F09_EXPIRED_CANCELLED" in finding_types
    assert Decimal(cancelled_oracle.world_projection_balances[0]["supported"]) < Decimal(
        cancelled_oracle.expected_world_balances[0]["supported"]
    )
    assert Decimal(cancelled_oracle.world_projection_balances[0]["delta"]) > 0

    # 3. Capability mismatch: non-matching recycler credit excluded from visible supported
    cap_oracle = OracleBuilder.build_for_world(s04_worlds["capability_mismatch"])
    finding_types = {f["issue_type"] for f in cap_oracle.expected_findings}
    assert "F10_CAPABILITY_MISMATCH" in finding_types
    assert Decimal(cap_oracle.world_projection_balances[0]["supported"]) < Decimal(
        cap_oracle.expected_world_balances[0]["supported"]
    )
    assert Decimal(cap_oracle.world_projection_balances[0]["delta"]) > 0

    # 4. Weight basis conflict
    weight_oracle = OracleBuilder.build_for_world(s04_worlds["weight_basis_conflict"])
    finding_types = {f["issue_type"] for f in weight_oracle.expected_findings}
    assert "F13_WEIGHT_BASIS_CONFLICT" in finding_types

    # 5. Commercial invoice/payment
    comm_oracle = OracleBuilder.build_for_world(s04_worlds["linked_invoice_payment"])
    finding_types = {f["issue_type"] for f in comm_oracle.expected_findings}
    assert "F07_PAID_NO_TRANSFER" in finding_types
    assert any(
        a["scope"] == "pending_untransferred_credits" for a in comm_oracle.required_abstentions
    )


def test_scoring_reconciliation_exact_and_mismatch():
    oracle = OracleBuilder.build_for_case_001()
    protocol = ScoringProtocol()

    # Exact match
    candidate_exact = [
        {
            "bucket_id": "bucket:prod_001_cu_2024_2025",
            "required": "100.0000",
            "supported": "55.0000",
            "signed_gap": "45.0000",
            "pending": "25.0000",
        }
    ]
    score = protocol.score_reconciliation(candidate_exact, oracle)
    assert score.all_buckets_matched
    assert score.exact_bucket_match_rate == 1.0
    assert not score.mismatches

    # Mismatch: candidate incorrectly claims 80 supported (promoting pending 25)
    candidate_faulty = [
        {
            "bucket_id": "bucket:prod_001_cu_2024_2025",
            "required": "100.0000",
            "supported": "80.0000",
            "signed_gap": "20.0000",
            "pending": "0.0000",
        }
    ]
    score_faulty = protocol.score_reconciliation(candidate_faulty, oracle)
    assert not score_faulty.all_buckets_matched
    assert score_faulty.exact_bucket_match_rate == 0.0
    assert len(score_faulty.mismatches) > 0


def test_scoring_findings_prevents_duplicate_inflation():
    oracle = OracleBuilder.build_for_case_001()
    protocol = ScoringProtocol()

    # Honest finding submission
    honest_findings = [
        {"issue_type": "F02_OVERLAPPING_EXPORT"},
        {"issue_type": "F07_PAID_NO_TRANSFER"},
    ]
    honest_score = protocol.score_findings(honest_findings, oracle)
    assert honest_score.precision == 1.0
    assert honest_score.recall == 1.0
    assert honest_score.f1 == 1.0
    assert honest_score.duplicate_count == 0

    # Adversarial submission trying to inflate score with duplicate findings
    spam_findings = [
        {"issue_type": "F02_OVERLAPPING_EXPORT"},
        {"issue_type": "F02_OVERLAPPING_EXPORT"},
        {"issue_type": "F02_OVERLAPPING_EXPORT"},
        {"issue_type": "F07_PAID_NO_TRANSFER"},
    ]
    spam_score = protocol.score_findings(spam_findings, oracle)
    assert spam_score.duplicate_count == 2
    assert spam_score.duplicate_penalty_applied > 0
    assert spam_score.f1 < honest_score.f1


def test_scoring_abstention_honesty():
    oracle = OracleBuilder.build_for_case_001()
    protocol = ScoringProtocol()

    # Proper abstention
    proper = [{"scope": "pending_commercial_payment"}]
    score_proper = protocol.score_abstentions(proper, oracle)
    assert score_proper.abstention_accuracy == 1.0
    assert not score_proper.missing_abstentions

    # Missing abstention
    missing = []
    score_missing = protocol.score_abstentions(missing, oracle)
    assert score_missing.abstention_accuracy == 0.0
    assert len(score_missing.missing_abstentions) == 1


def test_scoring_forbidden_actions_and_composite_report():
    oracle = OracleBuilder.build_for_case_001()
    protocol = ScoringProtocol()

    candidate_buckets = [
        {
            "bucket_id": "bucket:prod_001_cu_2024_2025",
            "required": "100.0000",
            "supported": "55.0000",
            "signed_gap": "45.0000",
            "pending": "25.0000",
        }
    ]
    candidate_findings = [
        {"issue_type": "F02_OVERLAPPING_EXPORT"},
        {"issue_type": "F07_PAID_NO_TRANSFER"},
    ]
    candidate_abstentions = [{"scope": "pending_commercial_payment"}]

    # Clean run
    clean_report = protocol.score_trial(
        candidate_buckets,
        candidate_findings,
        candidate_abstentions,
        ["Standard investigation action"],
        oracle,
    )
    assert clean_report.forbidden_actions.clean_run
    assert clean_report.composite_score == 1.0

    # Violating run with prohibited legal compliance verdict
    violating_report = protocol.score_trial(
        candidate_buckets,
        candidate_findings,
        candidate_abstentions,
        ["This report proves complete legal compliance for the producer."],
        oracle,
    )
    assert not violating_report.forbidden_actions.clean_run
    assert "AGENT_LEGAL_COMPLIANCE_VERDICT" in violating_report.forbidden_actions.violations
    assert violating_report.composite_score == 0.0


def test_unrelated_abstention_does_not_satisfy_required_scope():
    oracle = OracleBuilder.build_for_case_001()
    score = ScoringProtocol().score_abstentions([{"scope": "unrelated_scope"}], oracle)
    assert score.correctly_withheld_count == 0
    assert score.abstention_accuracy == 0
    assert score.missing_abstentions and score.unnecessary_abstentions


def test_duplicate_unexpected_and_wrong_unit_buckets_fail_exact_agreement():
    oracle = OracleBuilder.build_for_case_001()
    bucket = oracle.visible_evidence_balances[0]
    scorer = ScoringProtocol()
    for candidates in (
        [bucket, bucket],
        [bucket, bucket | {"bucket_id": "bucket:unexpected"}],
        [bucket | {"unit": "TONNE"}],
        [bucket | {"supported": "Infinity"}],
    ):
        assert not scorer.score_reconciliation(candidates, oracle).all_buckets_matched


def test_hidden_world_projection_cannot_be_scored_as_visible_truth():
    oracle = OracleBuilder.build_for_world(build_worlds()[0])
    assert oracle.world_projection_balances and not oracle.visible_evidence_balances
    with pytest.raises(ValueError, match="independent review"):
        ScoringProtocol().score_reconciliation(oracle.world_projection_balances, oracle)


def test_opaque_case_path_and_template_name_do_not_invent_fault_labels():
    from dataclasses import replace
    from pathlib import Path

    original = build_worlds()[0]
    renamed = replace(original, template_key="arrears-overlap-unrelated-label")
    first = OracleBuilder.build_for_world(original)
    second = OracleBuilder.build_for_world(renamed, Path("case_188162b68d"))
    assert first.expected_findings == second.expected_findings
