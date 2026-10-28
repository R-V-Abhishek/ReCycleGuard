"""Control decisions remain inspectable when execution is cancelled or bounded."""

from dataclasses import replace

import pytest

from recycleguard.application import command_context
from recycleguard.contracts.workflow import (
    BudgetLimits,
    CancellationRequest,
    ObservationAssessment,
)
from tests.integration.test_a05_baseline import approved_foundation as approved_foundation
from tests.integration.test_a06_workflow import workflow as workflow
from tests.support.workflow import assess, plan


def test_cancellation_reason_is_retained_in_application_audit(workflow):
    with workflow([plan(), assess()]) as env:
        state = env.start()
        cancelled = env.runner.cancel(
            command_context(env.context.actor),
            state.run_id,
            state.version,
            "Operator needs a corrected dossier",
            capability=env.capability,
        )
        events = env.cases.kernel.list_stream_events(f"stream:{state.run_id}")
        event = next(e for e in events if e.event_type == "graph.cancellation_request.result")
        request = CancellationRequest.model_validate_json(
            env.cases.kernel.blob_store.get(event.payload_blob)
        )
        assert request.reason == "Operator needs a corrected dossier"
        assert request.run_id == state.run_id and request.expected_version == state.version
        assert cancelled.status == "CANCELLED" and not env.port.calls


def test_completed_tool_gets_unknown_assessment_when_model_budget_is_exhausted(workflow):
    with workflow([plan()], budgets=BudgetLimits(max_model_calls=1)) as env:
        state = env.drive(env.start())
        assert state.stop_reason == "BUDGET_EXHAUSTED"
        assert len(env.lookup.calls) == 1 and len(env.port.calls) == 1
        events = env.cases.kernel.list_stream_events(f"stream:{state.run_id}")
        event = next(e for e in events if e.event_type == "graph.assessment.result")
        assessment = ObservationAssessment.model_validate_json(
            env.cases.kernel.blob_store.get(event.payload_blob)
        )
        assert assessment.verdict == "UNKNOWN" and assessment.disposition == "ABSTAIN"
        assert assessment.next_check_or_stop == "BUDGET_EXHAUSTED"
        assert assessment.operation_ref == env.lookup.calls[0][0].operation_id
        assert assessment.assessment_id in state.assessment_refs


def test_exact_model_context_retains_the_actual_registry_and_result_references(workflow):
    with workflow([plan(), assess()]) as env:
        state = env.drive(env.start())
        request = env.port.calls[0][2]
        assert set(request["allowed_tools"]) == {"search_rules"}
        assert request["allowed_tools"]["search_rules"]["additionalProperties"] is False
        assert request["response_schema"]["required"] == ["plan", "action", "stop_reason"]
        assert request["prior_stage_result_refs"]
        assert len(state.result_refs) == 4  # Preflight, tool, draft and verification.
        for ref in state.result_refs:
            env.cases.kernel.blob_store.get(ref)


@pytest.mark.parametrize("reason", ["MANUAL_CLOSURE", "REVIEW_REJECTED", "RESOLVED_WITHIN_SCOPE"])
def test_model_cannot_generate_a_trusted_review_or_unsupported_resolution(workflow, reason):
    step = plan()
    output = {**step.output, "action": None, "stop_reason": reason}
    with workflow([replace(step, output=output), replace(step, output=output)]) as env:
        state = env.drive(env.start())
        assert state.status == "FAILED" and state.stop_reason == "PROVIDER_FAILURE"
        assert not env.lookup.calls and not state.resolved_finding_ids
        assert state.review_outcome == "NOT_REQUESTED"


def test_model_abstention_keeps_its_plan_and_leaves_finding_unresolved(workflow):
    step = plan()
    output = {**step.output, "action": None, "stop_reason": "NO_NEW_EVIDENCE"}
    with workflow([replace(step, output=output)]) as env:
        state = env.drive(env.start())
        assert state.status == "AWAITING_REVIEW" and state.review_outcome == "PENDING"
        assert state.stop_reason == "NO_NEW_EVIDENCE" and state.plan_refs
        assert state.abstained_finding_ids == ["finding:one"]
        assert not env.lookup.calls and not state.resolved_finding_ids
