"""V1 and finding proposals over the loopback fixture server. No weights, no quality claim."""

import json

import pytest

from recycleguard.application import command_context
from recycleguard.contracts.workflow import ActionProposal
from recycleguard.investigation import FixedPlan, evaluation_budgets
from recycleguard.local_model import LocalModelConfig, LocalModelPort
from tests.integration.test_a05_baseline import approved_foundation as approved_foundation
from tests.integration.test_model_investigation import native as native
from tests.support.workflow import assess, plan
from tests.unit.test_local_model import server as server

STOPPED = {"AWAITING_REVIEW", "FAILED", "BLOCKED_INPUT", "BLOCKED_OUTPUT"}


def run(native, monkeypatch, respond, *, fixed=True, frozen_limits=False):
    """``respond(payload)`` supplies the fixture text for each exact model request."""
    service, context, capability, request, config, backend = native
    if frozen_limits:
        config = config.model_copy(
            update={
                name: LocalModelConfig.model_fields[name].default
                for name in ("max_output_tokens", "max_total_tokens")
            }
        )
    request = request.model_copy(
        update={
            "local_model_config": config,
            "fixed_plan": FixedPlan(rule_queries=["allocation"]) if fixed else None,
            "budgets": evaluation_budgets(config),
        }
    )
    phases, original = [], LocalModelPort.invoke

    def invoke(port, ctx, model_request):
        payload = json.loads(port.blobs.get(model_request.exact_request_blob))
        phases.append(payload["phase"])
        backend.model_text = json.dumps(respond(payload))
        return original(port, ctx, model_request)

    monkeypatch.setattr(LocalModelPort, "invoke", invoke)
    spec = service.prepare(context, request)
    runner = service.runner(spec)
    try:
        state = runner.start_run(context, spec, capability=capability)
        for _ in range(16):
            if state.status in STOPPED:
                break
            state = runner.advance(
                command_context(context.actor), spec.run_id, state.version, capability=capability
            )
    finally:
        runner.close()
    actions = [
        ActionProposal.model_validate_json(service.blobs.get(event.payload_blob))
        for event in service.kernel.list_stream_events(f"stream:{spec.run_id}")
        if event.event_type == "graph.action.result"
    ]
    return spec, state, phases, [action.allowed_operation for action in actions]


def proposal(evidence_ref_ids, **changes):
    return {
        "issue_type": "F07_PAID_NO_TRANSFER",
        "advisory_status": "PENDING_VERIFICATION",
        "basis": "The allocation remains unsupported by a completed transfer.",
        "evidence_ref_ids": evidence_ref_ids,
        "next_action_kind": "REQUEST_EVIDENCE",
        "next_action_text": "Request the completed transfer record.",
    } | changes


def assess_with(payload_proposal):
    return assess(verdict="WEAK", disposition="CONTINUE").output | {
        "finding_proposal": payload_proposal
    }


def test_model_only_assesses_and_every_check_runs_despite_early_resolve(native, monkeypatch):
    resolve = assess(verdict="SUPPORTS", disposition="RESOLVE").output
    spec, state, phases, operations = run(native, monkeypatch, lambda _: resolve)
    assert spec.experiment_variant == "V1_FIXED_RETRIEVAL_REAL_MODEL"
    assert spec.execution_kind == "MODEL_BACKED"
    assert set(phases) == {"ASSESS"}
    assert operations[0] == "search_rules" and operations[1] == "compute_reconciliation"
    assert operations[-1] == "inspect_evidence"
    assert len(phases) == len(operations) == state.budget.tool_calls
    assert state.status == "AWAITING_REVIEW"
    assert state.resolved_finding_ids == ["finding:one"]


def test_final_continue_becomes_abstention_not_resolution(native, monkeypatch):
    keep_going = assess(verdict="UNKNOWN", disposition="CONTINUE").output
    _, state, phases, operations = run(native, monkeypatch, lambda _: keep_going)
    assert operations[-1] == "inspect_evidence" and len(phases) == len(operations)
    assert state.status == "AWAITING_REVIEW" and state.stop_reason == "NO_NEW_EVIDENCE"
    assert state.resolved_finding_ids == []
    assert state.abstained_finding_ids == ["finding:one"]


def test_reply_omitting_the_optional_proposal_does_not_fail_the_run(native, monkeypatch):
    omitted = assess(verdict="UNKNOWN", disposition="CONTINUE").output
    del omitted["finding_proposal"]
    _, state, _, _ = run(native, monkeypatch, lambda _: omitted)
    assert state.status == "AWAITING_REVIEW"


def test_assessment_prompt_carries_reference_ids_not_full_locators(native, monkeypatch):
    seen = []

    def respond(payload):
        seen.append(payload["observation"]["stage_output"])
        return assess(verdict="UNKNOWN", disposition="CONTINUE").output

    run(native, monkeypatch, respond)
    assert all("evidence_refs" not in stage for stage in seen)
    inspected = seen[-1]
    assert inspected["evidence_ref_ids"]
    assert inspected["evidence_refs_total"] == len(inspected["evidence_ref_ids"])


def test_gated_proposal_reaches_the_report_and_changes_it(native, monkeypatch):
    service = native[0]

    def respond(payload):
        stage = payload["observation"]["stage_output"]
        if stage["calculation_ids"]:
            return assess_with(proposal(stage["calculation_ids"]))
        return assess(verdict="UNKNOWN", disposition="CONTINUE").output

    spec, state, _, _ = run(native, monkeypatch, respond)
    assert state.status == "AWAITING_REVIEW"
    current = service.latest_report(spec.run_id)
    finding = next(f for f in current.findings if f.issue_type == "F07_PAID_NO_TRANSFER")
    assert finding.evidence_assessments == [{"source": "MODEL_PROPOSAL"}]
    assert current.verification.verdict == "QUALIFIED"
    assert not current.rejected_finding_proposals
    text = current.report.rendered_markdown
    assert "F07_PAID_NO_TRANSFER" in text and "passed the evidence gate" in text
    assert "dossier observations." in text


def test_report_without_a_proposal_has_no_model_finding(native, monkeypatch):
    service = native[0]
    keep_going = assess(verdict="UNKNOWN", disposition="CONTINUE").output
    spec, _, _, _ = run(native, monkeypatch, lambda _: keep_going)
    current = service.latest_report(spec.run_id)
    assert not any(
        f.evidence_assessments == [{"source": "MODEL_PROPOSAL"}] for f in current.findings
    )
    assert "No model-authored investigation steps" in current.report.rendered_markdown


def test_fabricated_citation_is_retained_as_a_rejection_not_a_finding(native, monkeypatch):
    service = native[0]
    fabricated = assess_with(proposal(["observation:invented"]))
    spec, state, _, _ = run(native, monkeypatch, lambda _: fabricated)
    assert state.status == "AWAITING_REVIEW"
    current = service.latest_report(spec.run_id)
    assert all(f.issue_type != "F07_PAID_NO_TRANSFER" for f in current.findings)
    assert {item.reason for item in current.rejected_finding_proposals} == {"UNKNOWN_EVIDENCE_REF"}


def test_adaptive_run_also_uses_the_gate(native, monkeypatch):
    service = native[0]
    check = plan(operation="compute_reconciliation").output
    check["action"]["typed_arguments"] = {"bucket_ids": []}

    def respond(payload):
        if payload["phase"] == "PLAN":
            return check
        stage = payload["observation"]["stage_output"]
        return assess(verdict="UNKNOWN", disposition="ABSTAIN").output | {
            "finding_proposal": proposal(stage["calculation_ids"])
        }

    spec, _, phases, _ = run(native, monkeypatch, respond, fixed=False)
    assert spec.experiment_variant == "V2_ADAPTIVE_REAL_MODEL" and "PLAN" in phases
    issue_types = {f.issue_type for f in service.latest_report(spec.run_id).findings}
    assert "F07_PAID_NO_TRANSFER" in issue_types


def inspect_plan(observation_ids):
    step = plan(operation="inspect_evidence").output
    step["action"]["typed_arguments"] = {"observation_ids": observation_ids}
    return step


def rejected_actions(service, spec):
    return [
        json.loads(service.blobs.get(event.payload_blob))
        for event in service.kernel.list_stream_events(f"stream:{spec.run_id}")
        if event.event_type == "graph.action_rejected.result"
    ]


def test_invented_observation_id_asks_the_model_again_and_never_dispatches(native, monkeypatch):
    keep_going = assess(verdict="UNKNOWN", disposition="ABSTAIN").output
    plans = []

    def respond(payload):
        if payload["phase"] == "ASSESS":
            return keep_going
        plans.append(payload)
        if len(plans) == 1:
            return inspect_plan(["obs:invented"])
        return inspect_plan(payload["inspectable_observation_ids"][:1])

    spec, state, _, operations = run(native, monkeypatch, respond, fixed=False)
    assert state.status == "AWAITING_REVIEW"
    assert "previous_rejection" not in plans[0] and plans[0]["inspectable_observation_ids"]
    assert "obs:invented" not in plans[1]["previous_rejection"]
    assert operations == ["inspect_evidence"]
    assert state.budget.tool_calls == 1 and state.budget.model_calls == 3
    assert [item["model_call"] for item in rejected_actions(native[0], spec)] == ["plan"]


def test_invented_id_after_the_repair_fails_without_correcting_the_model(native, monkeypatch):
    def respond(payload):
        return inspect_plan(["obs:invented"])

    spec, state, _, operations = run(native, monkeypatch, respond, fixed=False)
    assert state.status == "FAILED" and state.budget.tool_calls == 0 and not operations
    assert [item["model_call"] for item in rejected_actions(native[0], spec)] == [
        "plan",
        "plan_repair",
    ]


def test_clean_claim_is_rejected_while_credits_are_pending(native, monkeypatch):
    service = native[0]
    buckets = []

    def respond(payload):
        stage = payload["observation"]["stage_output"]
        if stage["calculation_ids"]:
            buckets.extend(stage["concise_decision"]["evidence_data"]["buckets"])
            return assess_with(
                proposal(
                    stage["calculation_ids"],
                    issue_type="F01_CLEAN_BASELINE",
                    advisory_status="RECONCILED_WITHIN_SCOPE",
                    next_action_kind="NO_FURTHER_ACTION",
                )
            )
        return assess(verdict="UNKNOWN", disposition="CONTINUE").output

    spec, _, _, _ = run(native, monkeypatch, respond)
    current = service.latest_report(spec.run_id)
    assert buckets and buckets[0]["pending"]["decimal"] != "0.0000"
    assert all(f.issue_type != "F01_CLEAN_BASELINE" for f in current.findings)
    assert {item.reason for item in current.rejected_finding_proposals} == {"CLEAN_NOT_ESTABLISHED"}


def test_plan_after_a_whole_dossier_inspection_stays_within_the_prompt_bound(native, monkeypatch):
    inspect = plan(operation="inspect_evidence").output
    inspect["action"]["typed_arguments"] = {"observation_ids": []}
    keep_going = assess(verdict="UNKNOWN", disposition="CONTINUE").output
    plans = []

    def respond(payload):
        if payload["phase"] == "ASSESS":
            return keep_going
        plans.append(payload)
        if len(plans) == 1:
            return inspect
        return {"plan": inspect["plan"], "action": None, "stop_reason": "NO_NEW_EVIDENCE"}

    _, state, _, _ = run(native, monkeypatch, respond, fixed=False, frozen_limits=True)
    assert state.status == "AWAITING_REVIEW" and len(plans) == 2
    prior = plans[1]["prior_stage_observations"][-1]
    assert "evidence_refs" not in prior and prior["evidence_refs_total"] > 0
    assessed = plans[1]["previous_assessments"][-1]
    assert "observation_refs" not in assessed and assessed["observation_refs_total"] > 0


def test_tampered_variant_is_rejected_and_evaluation_rejects_budget_overrides(native):
    service, context, _, request, config, _ = native
    spec = service.prepare(context, request)
    tampered = spec.model_copy(update={"experiment_variant": "V1_FIXED_RETRIEVAL_REAL_MODEL"})
    with pytest.raises(ValueError, match="experiment variant"):
        service.configuration(tampered)
    evaluation = service.settings.model_copy(update={"mode": "evaluation"})
    service.settings = evaluation
    with pytest.raises(ValueError, match="frozen budget"):
        service.prepare(context, request)
    frozen = request.model_copy(update={"budgets": evaluation_budgets(config)})
    assert service.prepare(context, frozen).budgets == evaluation_budgets(config)
