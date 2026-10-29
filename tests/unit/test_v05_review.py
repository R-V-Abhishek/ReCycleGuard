"""Trusted review uses real enrolled sessions and durable audit-backed packets."""

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from recycleguard.application import command_context, local_application, local_review_application
from recycleguard.baseline import BaselineService
from recycleguard.config import Settings
from recycleguard.contracts.artifacts import SnapshotRef
from recycleguard.contracts.review import ReviewDecision
from recycleguard.local_session import initialize_reviewer
from recycleguard.reporting import BaselineReportBuilder, ReportVerifier
from recycleguard.reporting.repair import ReportRepairService
from recycleguard.review import ReviewService
from recycleguard.storage.authority import AuthorizationError, Capability
from tests.integration.test_a05_baseline import approved_foundation as approved_foundation
from tests.integration.test_a05_baseline import baseline_request
from tests.support.c08 import clean_case, run

PASSWORD = "temporary-review-fixture-password"
RUN = "run:review_service_test"


@dataclass
class Head:
    run_id: str = RUN
    status: str = "AWAITING_REVIEW"


@pytest.fixture
def review(tmp_path, approved_foundation):
    root = tmp_path / "data"
    shutil.copytree(approved_foundation, root, ignore=shutil.ignore_patterns("reviewer.json"))
    initialize_reviewer(root, "human:review_fixture", PASSWORD)
    settings = Settings(data_root=root)
    head = Head()
    reports = {}
    with local_application(settings) as (cases, context, cap):
        case = cases.snapshots.catalog.get_snapshot("snapshot:case_approved")
        corpus = cases.snapshots.catalog.get_snapshot("snapshot:corpus_approved")
        calculated = BaselineService(cases).run(
            context, baseline_request(cases, case), capability=cap
        )
        report = BaselineReportBuilder().build(calculated.output.calculation, run_id=RUN)
        reports[RUN] = report
        service = ReviewService(cases, run_state=lambda _: head, current_report=reports.__getitem__)
        context = command_context(context.actor).model_copy(
            update={"run_id": RUN, "case_version_id": case.snapshot_id}
        )
        packet = service.create_review_packet(
            context,
            report,
            authoritative_calculations=report.calculations,
            input_snapshots=[
                SnapshotRef(snapshot_id=s.snapshot_id, membership_digest=s.membership_digest)
                for s in (case, corpus)
            ],
            capability=cap,
        )
    with local_review_application(settings, PASSWORD) as values:
        cases, context, cap, service_actor, service_cap = values
        context = context.model_copy(update={"run_id": RUN, "case_version_id": case.snapshot_id})
        service = ReviewService(cases, run_state=lambda _: head, current_report=reports.__getitem__)
        yield service, context, cap, packet, report, head, reports


def decision(context, kind="APPROVE"):
    return ReviewDecision(
        decision=kind,
        authenticated_reviewer_ref=context.actor,
        reason="Reviewed this exact qualified synthetic report.",
        recorded_at=datetime.now(UTC).isoformat(),
    )


@pytest.mark.parametrize(
    "kind,status,outcome",
    [
        ("APPROVE", "COMPLETED", "APPROVED"),
        ("REJECT", "BLOCKED_OUTPUT", "REJECTED"),
        ("REQUEST_CHANGES", "DRAFTING", "CHANGES_REQUESTED"),
        ("ESCALATE", "AWAITING_REVIEW", "ESCALATED"),
    ],
)
def test_review_transitions_are_durable_and_bound_to_report(review, kind, status, outcome):
    service, context, cap, packet, report, _, _ = review
    proposed = decision(context, kind)
    result = service.submit_review(
        context, packet.packet_id, packet.review_dependency_digest, proposed, capability=cap
    )
    assert result.output.new_run_status == status
    assert result.output.new_review_outcome == outcome
    record = result.output.review_record
    assert record.run_id == RUN and record.report_revision_id == report.revision.report_revision_id
    assert record.input_snapshot_refs == packet.input_snapshot_refs
    assert service.get_decision(packet.packet_id) == result.output
    assert service.get_packet(packet.packet_id) == packet
    assert service.get_report(packet.packet_id) == report
    assert result.audit_event_ids == [f"event:result_{context.operation_id}"]
    assert all(
        service.kernel.get_event(identifier) is not None for identifier in result.audit_event_ids
    )
    assert (
        service.submit_review(
            context, packet.packet_id, packet.review_dependency_digest, proposed, capability=cap
        )
        == result
    )
    fresh = command_context(context.actor).model_copy(
        update={"run_id": RUN, "case_version_id": context.case_version_id}
    )
    with pytest.raises(ValueError, match="STALE_REVIEW"):
        service.submit_review(
            fresh,
            packet.packet_id,
            packet.review_dependency_digest,
            decision(fresh, kind),
            capability=cap,
        )


@pytest.mark.parametrize("change", ["session", "actor", "service", "capability"])
def test_spoofs_fail_without_decision_or_packet_mutation(review, change):
    service, context, cap, packet, _, _, _ = review
    proposed = decision(context)
    if change == "session":
        proposed = proposed.model_copy(
            update={
                "authenticated_reviewer_ref": context.actor.model_copy(
                    update={"authenticated_session_ref": "session:forged"}
                )
            }
        )
    elif change == "actor":
        proposed = proposed.model_copy(
            update={
                "authenticated_reviewer_ref": context.actor.model_copy(
                    update={"actor_id": "human:other"}
                )
            }
        )
    elif change == "service":
        context = context.model_copy(
            update={"actor": context.actor.model_copy(update={"actor_kind": "MODEL_PROPOSAL"})}
        )
    else:
        cap = Capability()
    with pytest.raises(AuthorizationError):
        service.submit_review(
            context, packet.packet_id, packet.review_dependency_digest, proposed, capability=cap
        )
    assert service.get_decision(packet.packet_id) is None
    assert service.get_packet(packet.packet_id) == packet


@pytest.mark.parametrize("stale", ["digest", "report", "run"])
def test_stale_packet_uses_server_state_not_caller_claims(review, stale):
    service, context, cap, packet, report, head, reports = review
    digest = packet.review_dependency_digest
    if stale == "digest":
        digest = "0" * 64
    elif stale == "report":
        reports[RUN] = report.model_copy(
            update={"rendered_markdown": "changed after packet creation"}
        )
    else:
        head.status = "COMPLETED"
    with pytest.raises(ValueError, match="STALE_REVIEW"):
        service.submit_review(context, packet.packet_id, digest, decision(context), capability=cap)
    assert service.get_decision(packet.packet_id) is None


def test_failed_audit_rolls_back_packet_decision_atomically(review):
    service, context, cap, packet, _, _, _ = review
    service.connection.execute("""CREATE TRIGGER fail_review BEFORE INSERT ON audit_events
      WHEN NEW.event_json LIKE '%review.report.result%'
      BEGIN SELECT RAISE(ABORT,'review audit unavailable'); END""")
    proposed = decision(context)
    with pytest.raises(sqlite3.Error):
        service.submit_review(
            context, packet.packet_id, packet.review_dependency_digest, proposed, capability=cap
        )
    assert service.get_decision(packet.packet_id) is None
    assert service.kernel.get_result(context.operation_id) is None
    service.connection.execute("DROP TRIGGER fail_review")
    result = service.submit_review(
        context, packet.packet_id, packet.review_dependency_digest, proposed, capability=cap
    )
    assert result.status == "SUCCESS"


def test_restart_loads_packets_and_decisions_from_audited_storage(review):
    service, context, cap, packet, _, _, _ = review
    result = service.submit_review(
        context,
        packet.packet_id,
        packet.review_dependency_digest,
        decision(context),
        capability=cap,
    )
    restored = ReviewService(
        service.cases, run_state=service.run_state, current_report=service.current_report
    )
    assert restored.get_packet(packet.packet_id) == packet
    assert restored.get_decision(packet.packet_id) == result.output


def test_new_authorized_packet_supersedes_old_open_packet(review):
    service, context, cap, packet, report, _, _ = review
    with local_application(Settings(data_root=service.blobs.root)) as (cases, root, service_cap):
        creator = command_context(root.actor).model_copy(
            update={
                "run_id": RUN,
                "case_version_id": context.case_version_id,
            }
        )
        publisher = ReviewService(
            cases, run_state=service.run_state, current_report=service.current_report
        )
        newer = publisher.create_review_packet(
            creator,
            report,
            input_snapshots=packet.input_snapshot_refs,
            authoritative_calculations=report.calculations,
            capability=service_cap,
        )
    assert newer.packet_id != packet.packet_id
    with pytest.raises(ValueError, match="STALE_REVIEW"):
        service.submit_review(
            context,
            packet.packet_id,
            packet.review_dependency_digest,
            decision(context),
            capability=cap,
        )
    assert service.get_decision(packet.packet_id) is None


def test_catalog_pointer_cannot_substitute_an_unaudited_packet(review):
    service, context, cap, packet, _, _, _ = review
    tampered = packet.model_copy(update={"review_dependency_digest": "f" * 64})
    blob = service.blobs.put(tampered.model_dump_json().encode(), "application/json")
    service.connection.execute(
        "UPDATE report_review_packets SET packet_blob=? WHERE packet_id=?",
        (blob.model_dump_json(), packet.packet_id),
    )
    service.connection.commit()
    with pytest.raises(ValueError, match="audit result"):
        service.submit_review(
            context, packet.packet_id, "f" * 64, decision(context), capability=cap
        )
    assert service.get_decision(packet.packet_id) is None


def test_manual_closure_never_approves(review):
    service, context, cap, packet, _, _, _ = review
    result = service.close_without_decision(
        context,
        packet.packet_id,
        expected_dependency_digest=packet.review_dependency_digest,
        capability=cap,
        reason="Authorized fixture closure",
    )
    assert result.output.new_review_outcome == "CLOSED_WITHOUT_DECISION"
    assert result.output.stop_reason == "MANUAL_CLOSURE"


@pytest.mark.parametrize("tamper", ["template", "prohibited", "rendering", "uncited"])
def test_report_repair_rebuilds_only_from_authoritative_calculation(tmp_path, tamper):
    calculation = run(tmp_path, clean_case()).output
    report = BaselineReportBuilder().build(calculation)
    claims = list(report.claims)
    if tamper == "template":
        index = next(i for i, c in enumerate(claims) if c.kind == "NUMERIC")
        claims[index] = claims[index].model_copy(update={"template_or_text": "{value} {value}"})
    elif tamper == "prohibited":
        claims[0] = claims[0].model_copy(
            update={"template_or_text": "This proves legal compliance"}
        )
    elif tamper == "uncited":
        claims[0] = claims[0].model_copy(update={"evidence_refs": []})
    bad = report.model_copy(update={"claims": claims, "rendered_markdown": "tampered"})
    verifier = ReportVerifier()
    verified = verifier.verify(bad, authoritative_calculations=[calculation])
    result = ReportRepairService().repair(bad, verified, authoritative_calculations=[calculation])
    assert result.repair_attempts == 1 and result.status == "SUCCESS"
    assert result.repaired_report == report
    assert (
        ReportRepairService(max_repairs=0)
        .repair(bad, verified, authoritative_calculations=[calculation])
        .status
        == "BLOCKED_OUTPUT"
    )


def test_repair_cannot_expand_server_limit_or_trust_supplied_verification(tmp_path):
    calculation = run(tmp_path, clean_case()).output
    report = BaselineReportBuilder().build(calculation)
    verified = ReportVerifier().verify(report, authoritative_calculations=[calculation])
    bad = report.model_copy(update={"rendered_markdown": "fraud"})
    result = ReportRepairService().repair(bad, verified, authoritative_calculations=[calculation])
    assert result.repair_attempts == 1 and result.repaired_report == report
    with pytest.raises(ValueError):
        ReportRepairService(max_repairs=9)
    with pytest.raises(TypeError):
        ReportRepairService().repair(
            bad, verified, authoritative_calculations=[calculation], max_repairs=99
        )
