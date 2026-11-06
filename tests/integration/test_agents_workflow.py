"""MG2 Reader and Analyst through the real runner over the loopback fixture server.

No weights and no quality claim: the replies are fixtures, so this checks plumbing, audit and
the gate, not whether a model reads well.
"""

import json
from pathlib import Path

from recycleguard.agents.models import AgentRecord
from recycleguard.application import command_context
from recycleguard.investigation import evaluation_budgets
from recycleguard.local_model import LocalModelConfig, LocalModelPort, PromptText
from tests.integration.test_a05_baseline import approved_foundation as approved_foundation
from tests.integration.test_model_investigation import native as native
from tests.unit.test_local_model import server as server

PROMPT = Path(__file__).parents[2] / "docs/checkpoints/mg2/prompts/mg2_reader_analyst_v1.json"
STOPPED = {"AWAITING_REVIEW", "FAILED", "BLOCKED_INPUT", "BLOCKED_OUTPUT"}


def run(native, monkeypatch, respond, *, agents="READER_ANALYST"):
    """``respond(payload)`` supplies the fixture reply for each exact model request."""
    service, context, capability, request, config, backend = native
    text = PromptText.model_validate_json(PROMPT.read_bytes())
    config = LocalModelConfig.model_validate(
        config.model_dump()
        | {
            "prompt": text,
            "prompt_version": text.prompt_version,
            "prompt_template_id": f"prompt:u01_qwen_{text.prompt_version}",
        }
    )
    request = request.model_copy(
        update={
            "local_model_config": config,
            "agents": agents,
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
    records = [
        AgentRecord.model_validate_json(service.blobs.get(event.payload_blob))
        for event in service.kernel.list_stream_events(f"stream:{spec.run_id}")
        if event.event_type == "graph.agent.result"
    ]
    return spec, state, phases, records, service


def reply(payload):
    if payload["phase"] == "READ":
        return {"claims": []}
    return {"findings": []}


def test_the_agents_replace_the_plan_and_assess_loop(native, monkeypatch):
    spec, state, phases, records, _ = run(native, monkeypatch, reply)
    assert spec.experiment_variant == "V3_READER_ANALYST_REAL_MODEL"
    assert set(phases) <= {"READ", "ANALYZE"} and phases[-1] == "ANALYZE"
    assert phases.count("ANALYZE") == 1
    assert state.status == "AWAITING_REVIEW"
    assert len(records) == 1 and records[0].architecture == "READER_ANALYST"
    assert state.pending_finding_ids == [] and state.resolved_finding_ids == ["finding:one"]


def test_the_analyst_only_arm_never_calls_the_reader(native, monkeypatch):
    spec, state, phases, records, _ = run(native, monkeypatch, reply, agents="ANALYST_ONLY")
    assert spec.experiment_variant == "V3_ANALYST_ONLY_REAL_MODEL"
    assert phases == ["ANALYZE"] and state.status == "AWAITING_REVIEW"
    assert records[0].coverage is None


def test_an_invalid_analyst_reply_still_drafts_the_report(native, monkeypatch):
    def invalid(payload):
        return {"claims": []} if payload["phase"] == "READ" else {"findings": "none"}

    _, state, phases, records, _ = run(native, monkeypatch, invalid, agents="ANALYST_ONLY")
    assert state.status == "AWAITING_REVIEW" and state.stop_reason == "NO_NEW_EVIDENCE"
    assert records[0].analyst_stopped_because == "INVALID_OUTPUT"
    assert state.abstained_finding_ids == ["finding:one"]


MEMO = "The recycler named on the transfer trades under another name than its registration"


def with_memo(monkeypatch):
    """The dossier plus one prose observation, as a memo would arrive."""
    from recycleguard.investigation import InvestigationService
    from tests.unit.test_agents import observation

    original = InvestigationService._observations

    def observations(self, spec):
        return [*original(self, spec), observation("obs:memo", note=MEMO)]

    monkeypatch.setattr(InvestigationService, "_observations", observations)


def alias_replies(payload):
    if payload["phase"] == "READ":
        assert "obs:memo" in [p["observation_id"] for p in payload["passages"]]
        return {
            "claims": [
                {
                    "kind": "ENTITY_ALIAS_STATEMENT",
                    "observation_id": "obs:memo",
                    "quote": "trades under another name",
                }
            ]
        }
    assert payload["verified_claims"][0]["family"] == "F05_WRONG_ENTITY_ALIAS"
    assert "another name" not in json.dumps(payload["verified_claims"])
    finding = {
        "advisory_status": "REQUIRES_EXPERT_REVIEW",
        "basis": "A passage addresses an automated reader.",
        "abstention_reason": None,
        "withheld_claim_scopes": [],
        "next_action_kind": "INVESTIGATE",
        "next_action_text": "A reviewer reads the passage.",
    }
    return {
        "findings": [
            finding | {"issue_type": "F05_WRONG_ENTITY_ALIAS", "evidence_ref_ids": ["obs:memo"]},
            finding | {"issue_type": "F12_UNSEEN_NOTICE_LEAD", "evidence_ref_ids": ["obs:memo"]},
        ]
    }


def test_a_verified_claim_becomes_a_gated_finding_and_an_unbacked_family_is_rejected(
    native, monkeypatch
):
    with_memo(monkeypatch)
    spec, state, phases, records, service = run(native, monkeypatch, alias_replies)
    assert phases == ["READ", "ANALYZE"] and state.status == "AWAITING_REVIEW"
    assert records[0].verified_claims[0].observation_id == "obs:memo"
    report = service.latest_report(spec.run_id)
    assert [f.issue_type for f in report.findings if f.issue_type.startswith("F05")] == [
        "F05_WRONG_ENTITY_ALIAS"
    ]
    assert [(r.proposal.issue_type, r.reason) for r in report.rejected_finding_proposals] == [
        ("F12_UNSEEN_NOTICE_LEAD", "NO_VERIFIED_CLAIM")
    ]
    assert MEMO not in report.model_dump_json()
