"""Unit tests for V05 trusted review transitions, report repair and forbidden-claim checks."""

from datetime import UTC, datetime

import pytest

from recycleguard.contracts.artifacts import SnapshotRef
from recycleguard.contracts.core import ActorRef, CommandContext
from recycleguard.contracts.review import ReviewDecision
from recycleguard.reporting.baseline import BaselineReportBuilder, ReportVerifier
from recycleguard.reporting.repair import ReportRepairService
from recycleguard.review.service import ReviewService
from recycleguard.storage.authority import AuthorizationError, LocalAuthority, TrustedPrincipal
from tests.support.c08 import clean_case, run


def dummy_context(actor_id="human:alice", actor_kind="HUMAN", session_ref="session:valid"):
    actor = ActorRef(
        actor_id=actor_id,
        actor_kind=actor_kind,
        authenticated_session_ref=session_ref,
    )
    return CommandContext(
        contract_version="1.1",
        command_id="command:review_test",
        operation_id="operation:review_test",
        attempt_id="attempt:1",
        idempotency_key="idem:review_test",
        actor=actor,
        case_version_id=None,
        run_id=None,
        turn_id=None,
        correlation_id="corr:review_test",
        parent_operation_id=None,
    )


def build_test_report(tmp_path):
    calc = run(tmp_path, clean_case()).output
    return BaselineReportBuilder().build(calc)


def test_review_packet_creation(tmp_path):
    report = build_test_report(tmp_path)
    service = ReviewService()

    snapshot_ref = SnapshotRef(snapshot_id="snapshot:case_1", membership_digest="0" * 64)
    packet = service.create_review_packet(report, input_snapshots=[snapshot_ref])

    assert packet.packet_id.startswith("packet:")
    assert packet.report_revision_id == report.revision.report_revision_id
    assert packet.review_dependency_digest == report.revision.review_dependency_digest
    assert len(packet.input_snapshot_refs) == 1
    assert set(packet.permitted_decisions) == {"APPROVE", "REJECT", "REQUEST_CHANGES", "ESCALATE"}


def test_trusted_review_transitions_all_decisions(tmp_path):
    report = build_test_report(tmp_path)
    service = ReviewService()
    ctx = dummy_context()
    authority = LocalAuthority({"human": TrustedPrincipal(ctx.actor, frozenset(["review."]))})
    cap = authority.issue("human")

    # 1. APPROVE
    packet_app = service.create_review_packet(report)
    dec_app = ReviewDecision(
        decision="APPROVE",
        authenticated_reviewer_ref=ctx.actor,
        reason="Verified working paper and supporting evidence.",
        recorded_at=datetime.now(UTC).isoformat(),
    )
    res_app = service.submit_review(
        ctx, packet_app.packet_id, packet_app.review_dependency_digest, dec_app, capability=cap
    )
    assert res_app.status == "SUCCESS"
    assert res_app.output.new_run_status == "COMPLETED"
    assert res_app.output.new_review_outcome == "APPROVED"
    assert res_app.output.stop_reason == "RESOLVED_WITHIN_SCOPE"

    # 2. REJECT
    packet_rej = service.create_review_packet(report)
    dec_rej = ReviewDecision(
        decision="REJECT",
        authenticated_reviewer_ref=ctx.actor,
        reason="Rejected due to unverifiable claims.",
        recorded_at=datetime.now(UTC).isoformat(),
    )
    res_rej = service.submit_review(
        ctx, packet_rej.packet_id, packet_rej.review_dependency_digest, dec_rej, capability=cap
    )
    assert res_rej.status == "SUCCESS"
    assert res_rej.output.new_run_status == "BLOCKED_OUTPUT"
    assert res_rej.output.new_review_outcome == "REJECTED"
    assert res_rej.output.stop_reason == "REVIEW_REJECTED"

    # 3. REQUEST_CHANGES
    packet_chg = service.create_review_packet(report)
    dec_chg = ReviewDecision(
        decision="REQUEST_CHANGES",
        authenticated_reviewer_ref=ctx.actor,
        reason="Additional observation citations requested.",
        recorded_at=datetime.now(UTC).isoformat(),
    )
    res_chg = service.submit_review(
        ctx, packet_chg.packet_id, packet_chg.review_dependency_digest, dec_chg, capability=cap
    )
    assert res_chg.status == "SUCCESS"
    assert res_chg.output.new_run_status == "BLOCKED_OUTPUT"
    assert res_chg.output.new_review_outcome == "CHANGES_REQUESTED"
    assert res_chg.output.stop_reason == "CHANGES_REQUESTED"

    # 4. ESCALATE
    packet_esc = service.create_review_packet(report)
    dec_esc = ReviewDecision(
        decision="ESCALATE",
        authenticated_reviewer_ref=ctx.actor,
        reason="Escalated to senior domain reviewer.",
        recorded_at=datetime.now(UTC).isoformat(),
    )
    res_esc = service.submit_review(
        ctx, packet_esc.packet_id, packet_esc.review_dependency_digest, dec_esc, capability=cap
    )
    assert res_esc.status == "SUCCESS"
    assert res_esc.output.new_run_status == "AWAITING_REVIEW"
    assert res_esc.output.new_review_outcome == "ESCALATED"
    assert res_esc.output.stop_reason == "EXPERT_REVIEW_REQUIRED"


def test_authorized_manual_closure_never_approved(tmp_path):
    report = build_test_report(tmp_path)
    service = ReviewService()
    ctx = dummy_context()
    authority = LocalAuthority({"human": TrustedPrincipal(ctx.actor, frozenset(["review."]))})
    cap = authority.issue("human")

    packet = service.create_review_packet(report)
    res = service.close_without_decision(
        ctx, packet.packet_id, capability=cap, reason="Time budget expired"
    )

    assert res.status == "SUCCESS"
    assert res.output.new_run_status == "COMPLETED"
    assert res.output.new_review_outcome == "CLOSED_WITHOUT_DECISION"
    assert res.output.stop_reason == "MANUAL_CLOSURE"
    assert res.output.new_review_outcome != "APPROVED"


def test_stale_packet_rejection(tmp_path):
    report = build_test_report(tmp_path)
    service = ReviewService()
    ctx = dummy_context()
    authority = LocalAuthority({"human": TrustedPrincipal(ctx.actor, frozenset(["review."]))})
    cap = authority.issue("human")

    packet = service.create_review_packet(report)
    dec = ReviewDecision(
        decision="APPROVE",
        authenticated_reviewer_ref=ctx.actor,
        reason="OK",
        recorded_at=datetime.now(UTC).isoformat(),
    )

    # 1. Dependency digest mismatch
    with pytest.raises(ValueError, match="STALE_REVIEW.*mismatch"):
        service.submit_review(ctx, packet.packet_id, "wrong_digest_" * 4, dec, capability=cap)

    # 2. First submission succeeds
    service.submit_review(
        ctx, packet.packet_id, packet.review_dependency_digest, dec, capability=cap
    )

    # 3. Resubmission on already decided packet fails
    with pytest.raises(ValueError, match="STALE_REVIEW.*already been decided"):
        service.submit_review(
            ctx, packet.packet_id, packet.review_dependency_digest, dec, capability=cap
        )


def test_spoofed_reviewer_rejection(tmp_path):
    report = build_test_report(tmp_path)
    service = ReviewService()
    ctx = dummy_context(actor_id="human:alice")
    authority = LocalAuthority({"human": TrustedPrincipal(ctx.actor, frozenset(["review."]))})
    cap = authority.issue("human")

    packet = service.create_review_packet(report)

    # Spoofed actor in decision
    spoofed_actor = ActorRef(
        actor_id="human:bob", actor_kind="HUMAN", authenticated_session_ref="session:bob"
    )
    spoofed_dec = ReviewDecision(
        decision="APPROVE",
        authenticated_reviewer_ref=spoofed_actor,
        reason="Attempting to forge Bob's approval",
        recorded_at=datetime.now(UTC).isoformat(),
    )

    with pytest.raises(AuthorizationError, match="spoofed reviewer identity rejected"):
        service.submit_review(
            ctx, packet.packet_id, packet.review_dependency_digest, spoofed_dec, capability=cap
        )


def test_terminal_runs_do_not_resume_silently(tmp_path):
    report = build_test_report(tmp_path)
    service = ReviewService()
    ctx = dummy_context()
    authority = LocalAuthority({"human": TrustedPrincipal(ctx.actor, frozenset(["review."]))})
    cap = authority.issue("human")

    packet = service.create_review_packet(report)
    dec = ReviewDecision(
        decision="APPROVE",
        authenticated_reviewer_ref=ctx.actor,
        reason="OK",
        recorded_at=datetime.now(UTC).isoformat(),
    )

    with pytest.raises(ValueError, match="terminal runs do not resume silently"):
        service.submit_review(
            ctx,
            packet.packet_id,
            packet.review_dependency_digest,
            dec,
            capability=cap,
            current_run_status="COMPLETED",
        )


def test_filing_acknowledgment_attachment(tmp_path):
    service = ReviewService()
    ctx = dummy_context()
    authority = LocalAuthority({"human": TrustedPrincipal(ctx.actor, frozenset(["review."]))})
    cap = authority.issue("human")

    ack = service.attach_acknowledgment(
        ctx,
        artifact_revision_id="art:cpcb_upload_receipt",
        linked_case_version_id="case:v1",
        claimed_external_reference="CPCB-EPR-2024-99881",
        validation_state="VALID",
        capability=cap,
    )
    assert ack.status == "SUCCESS"
    assert ack.output.claimed_external_reference == "CPCB-EPR-2024-99881"
    assert ack.output.validation_state == "VALID"


def test_report_repair_service_malformed_template(tmp_path):
    report = build_test_report(tmp_path)
    # Inject malformed template into a numeric claim
    claims = list(report.claims)
    index = next(i for i, c in enumerate(claims) if c.kind == "NUMERIC")
    claims[index] = claims[index].model_copy(
        update={"template_or_text": "Required: {value} and {value}."}
    )
    invalid_report = report.model_copy(update={"claims": claims})

    verifier = ReportVerifier()
    failed_verification = verifier.verify(
        invalid_report, authoritative_calculations=report.calculations
    )
    assert failed_verification.verdict == "BLOCKED"

    # Repair
    repair_service = ReportRepairService(verifier=verifier, max_repairs=1)
    repair_result = repair_service.repair(
        invalid_report,
        failed_verification,
        authoritative_calculations=report.calculations,
    )

    assert repair_result.status in {"SUCCESS", "QUALIFIED"}
    assert repair_result.repair_attempts == 1
    assert repair_result.verification.verdict in {"PASS", "QUALIFIED"}
    assert "{value}" in repair_result.repaired_report.claims[index].template_or_text
    assert repair_result.repaired_report.claims[index].template_or_text.count("{value}") == 1


def test_report_repair_service_prohibited_verdict(tmp_path):
    report = build_test_report(tmp_path)
    claims = list(report.claims)
    # Inject prohibited legal compliance claim
    claims[0] = claims[0].model_copy(
        update={"template_or_text": "This confirms legal compliance for the firm."}
    )
    invalid_report = report.model_copy(update={"claims": claims})

    verifier = ReportVerifier()
    failed_verification = verifier.verify(
        invalid_report, authoritative_calculations=report.calculations
    )
    assert failed_verification.verdict == "BLOCKED"
    assert any(i.code == "PROHIBITED_VERDICT" for i in failed_verification.issues)

    repair_service = ReportRepairService(verifier=verifier, max_repairs=1)
    repair_result = repair_service.repair(
        invalid_report,
        failed_verification,
        authoritative_calculations=report.calculations,
    )

    assert repair_result.status in {"SUCCESS", "QUALIFIED"}
    assert repair_result.verification.verdict in {"PASS", "QUALIFIED"}
    assert not any(i.code == "PROHIBITED_VERDICT" for i in repair_result.verification.issues)


def test_report_repair_exhausted_budget(tmp_path):
    report = build_test_report(tmp_path)
    claims = list(report.claims)
    claims[0] = claims[0].model_copy(update={"template_or_text": "This confirms legal compliance."})
    invalid_report = report.model_copy(update={"claims": claims})

    verifier = ReportVerifier()
    failed_verification = verifier.verify(
        invalid_report, authoritative_calculations=report.calculations
    )

    repair_service = ReportRepairService(verifier=verifier, max_repairs=0)
    repair_result = repair_service.repair(
        invalid_report,
        failed_verification,
        authoritative_calculations=report.calculations,
    )

    assert repair_result.status == "BLOCKED_OUTPUT"
    assert repair_result.repair_attempts == 0
