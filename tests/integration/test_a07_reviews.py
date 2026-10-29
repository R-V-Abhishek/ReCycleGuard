"""Real A07 services, authenticated synthetic review and recoverable projection."""

import shutil

import pytest

from recycleguard.application import command_context, local_application, local_review_application
from recycleguard.config import Settings
from recycleguard.contracts.artifacts import SnapshotRef
from recycleguard.contracts.review import ReviewDecision
from recycleguard.contracts.workflow import ActionDraft, AssessmentProposal, PlanDraft, PlanProposal
from recycleguard.investigation import InvestigationRequest, InvestigationService, ScriptedExchange
from recycleguard.local_session import initialize_reviewer
from tests.integration.test_a05_baseline import approved_foundation as approved_foundation

PASSWORD = "temporary-cp3-review-fixture"
RUN = "run:cp3_authenticated_review"


def request(cases):
    case = cases.snapshots.catalog.get_snapshot("snapshot:case_approved")
    corpus = cases.snapshots.catalog.get_snapshot("snapshot:corpus_approved")
    plan = PlanProposal(
        plan=PlanDraft(
            objective="Check the frozen allocation gap",
            hypotheses=["Credits require exact support"],
            proposed_checks=["Compute approved-case balances"],
            expected_evidence=["Deterministic calculation"],
            stopping_criteria=["Explicitly retain unresolved applicability"],
        ),
        action=ActionDraft(
            action_kind="CHECK",
            allowed_operation="compute_reconciliation",
            typed_arguments={"bucket_ids": []},
            finding_id="finding:cp3_review",
            concise_reason="Inspect exact supported quantities",
            evidence_refs=[],
        ),
        stop_reason=None,
    )
    assessment = AssessmentProposal(
        verdict="UNKNOWN",
        weak_result_or_mistake="Temporal applicability remains unknown",
        next_check_or_stop="Qualified report requires human review",
        disposition="ABSTAIN",
        revised_plan=None,
    )
    return InvestigationRequest(
        run_id=RUN,
        case_snapshot=SnapshotRef(
            snapshot_id=case.snapshot_id, membership_digest=case.membership_digest
        ),
        corpus_snapshot=SnapshotRef(
            snapshot_id=corpus.snapshot_id, membership_digest=corpus.membership_digest
        ),
        finding_ids=["finding:cp3_review"],
        scripted_exchanges=[
            ScriptedExchange(phase="PLAN", response=plan.model_dump(mode="json")),
            ScriptedExchange(phase="ASSESS", response=assessment.model_dump(mode="json")),
        ],
    )


@pytest.fixture
def prepared(tmp_path, approved_foundation):
    root = tmp_path / "evidence"
    shutil.copytree(approved_foundation, root, ignore=shutil.ignore_patterns("reviewer.json"))
    initialize_reviewer(root, "human:cp3_synthetic_review", PASSWORD)
    settings = Settings(data_root=root, mode="test", enable_test_adapters=True)
    with local_application(settings) as (cases, context, capability):
        service = InvestigationService(cases, settings, capability=capability)
        spec = service.prepare(context, request(cases))
        runner = service.runner(spec)
        try:
            state = runner.start_run(context, spec, capability=capability)
            for _ in range(12):
                if state.status == "AWAITING_REVIEW":
                    break
                assert state.status not in {"FAILED", "BLOCKED_INPUT", "BLOCKED_OUTPUT"}, state
                state = runner.advance(
                    command_context(context.actor), RUN, state.version, capability=capability
                )
            assert state.status == "AWAITING_REVIEW"
            packet = service.packet(context, spec)
        finally:
            runner.close()
    return settings, spec, packet


def submit(settings, spec, packet, kind):
    with local_review_application(settings, PASSWORD) as values:
        cases, context, capability, _, _ = values
        # Authenticated human capability is distinct from graph SERVICE authority.
        context = context.model_copy(
            update={"run_id": spec.run_id, "case_version_id": spec.case_snapshot.snapshot_id}
        )
        service = InvestigationService(cases, settings, capability=capability)
        decision = ReviewDecision(
            decision=kind,
            authenticated_reviewer_ref=context.actor,
            reason="Synthetic integration test review of exact qualified report.",
            recorded_at="2026-10-29T00:00:00Z",
        )
        result = service.review_service().submit_review(
            context,
            packet.packet_id,
            packet.review_dependency_digest,
            decision,
            capability=capability,
        )
        assert result.output.review_record.authenticated_reviewer_ref == context.actor
        assert result.output.review_record.input_snapshot_refs == [
            spec.case_snapshot,
            spec.corpus_snapshot,
        ]
        assert result.output.review_record.report_revision_id == packet.report_revision_id
        assert all(
            cases.kernel.get_event(identifier) is not None for identifier in result.audit_event_ids
        )
        return result


@pytest.mark.parametrize(
    "kind,status,outcome",
    [
        ("APPROVE", "COMPLETED", "APPROVED"),
        ("REJECT", "BLOCKED_OUTPUT", "REJECTED"),
        ("REQUEST_CHANGES", "DRAFTING", "CHANGES_REQUESTED"),
        ("ESCALATE", "AWAITING_REVIEW", "ESCALATED"),
    ],
)
def test_authenticated_decisions_project_after_restart(prepared, kind, status, outcome):
    settings, spec, packet = prepared
    result = submit(settings, spec, packet, kind)
    # Deliberate crash boundary: human review committed; no graph projection yet.
    with local_application(settings) as (cases, context, capability):
        service = InvestigationService(cases, settings, capability=capability)
        before = service.store.load(RUN)
        assert before.status == "AWAITING_REVIEW" and not before.review_record_refs
        state = service.recover_reviews(context, RUN)
        assert state.status == status and state.review_outcome == outcome
        assert state.review_record_refs == [result.output.review_record.review_id]
        assert service.recover_reviews(command_context(context.actor), RUN) == state
        assert service.review_service().get_packet(packet.packet_id) == packet
        assert service.review_service().get_decision(packet.packet_id) == result.output
        events = cases.kernel.list_stream_events(f"stream:{RUN}")
        assert any(event.event_type == "graph.review_projection.result" for event in events)


def test_requested_changes_requires_new_verified_report_and_new_packet(prepared):
    settings, spec, old = prepared
    submit(settings, spec, old, "REQUEST_CHANGES")
    with local_application(settings) as (cases, context, capability):
        service = InvestigationService(cases, settings, capability=capability)
        state = service.recover_reviews(context, RUN)
        assert state.status == "DRAFTING"
        runner = service.runner(spec)
        try:
            for _ in range(6):
                if state.status == "AWAITING_REVIEW":
                    break
                state = runner.advance(
                    command_context(context.actor), RUN, state.version, capability=capability
                )
            assert state.status == "AWAITING_REVIEW"
            updated = service.packet(context, spec)
            assert updated.packet_id != old.packet_id
            assert updated.report_revision_id != old.report_revision_id
            assert service.review_service().get_report(updated.packet_id).revision.run_id == RUN
        finally:
            runner.close()
    with local_review_application(settings, PASSWORD) as values:
        cases, context, capability, _, _ = values
        context = context.model_copy(
            update={"run_id": RUN, "case_version_id": spec.case_snapshot.snapshot_id}
        )
        service = InvestigationService(cases, settings, capability=capability)
        decision = ReviewDecision(
            decision="APPROVE",
            authenticated_reviewer_ref=context.actor,
            reason="Old report cannot be reused after requested changes.",
            recorded_at="2026-10-29T00:00:00Z",
        )
        with pytest.raises(ValueError, match="STALE_REVIEW"):
            service.review_service().submit_review(
                context,
                old.packet_id,
                old.review_dependency_digest,
                decision,
                capability=capability,
            )


def test_manual_closure_recovers_without_claiming_approval(prepared):
    settings, spec, packet = prepared
    with local_review_application(settings, PASSWORD) as values:
        cases, context, capability, _, _ = values
        context = context.model_copy(
            update={"run_id": RUN, "case_version_id": spec.case_snapshot.snapshot_id}
        )
        service = InvestigationService(cases, settings, capability=capability)
        result = service.review_service().close_without_decision(
            context,
            packet.packet_id,
            expected_dependency_digest=packet.review_dependency_digest,
            capability=capability,
            reason="Authorized synthetic closure without a decision",
        )
        expected_ref = "review_closure:" + context.operation_id.split(":", 1)[1]
        assert result.output.review_record is None
    with local_application(settings) as (cases, context, capability):
        service = InvestigationService(cases, settings, capability=capability)
        assert service.store.load(RUN).status == "AWAITING_REVIEW"
        state = service.recover_reviews(context, RUN)
        assert state.status == "COMPLETED"
        assert state.review_outcome == "CLOSED_WITHOUT_DECISION"
        assert state.stop_reason == "MANUAL_CLOSURE"
        assert state.review_record_refs == [expected_ref]
        assert service.recover_reviews(command_context(context.actor), RUN) == state
        assert service.review_service().get_decision(packet.packet_id) == result.output


def test_projection_rejects_changed_report_bytes_with_unchanged_revision_id(prepared, monkeypatch):
    settings, spec, packet = prepared
    submit(settings, spec, packet, "APPROVE")
    with local_application(settings) as (cases, context, capability):
        service = InvestigationService(cases, settings, capability=capability)
        before = service.store.load(RUN)
        original = service.latest_report(RUN)
        changed_report = original.report.model_copy(
            update={"rendered_markdown": original.report.rendered_markdown + "\nChanged content"}
        )
        assert changed_report.revision.report_revision_id == packet.report_revision_id
        changed = original.model_copy(update={"report": changed_report})
        monkeypatch.setattr(service, "latest_report", lambda _: changed)
        with pytest.raises(ValueError, match="exact current report bytes"):
            service.project_review(context, packet.packet_id)
        assert service.store.load(RUN) == before
        assert not any(
            event.event_type == "graph.review_projection.result"
            for event in cases.kernel.list_stream_events(f"stream:{RUN}")
        )
