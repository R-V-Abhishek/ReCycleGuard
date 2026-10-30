"""Native HTTP boundary wired to real A07 services; loopback fixtures load no weights."""

import json
import shutil

import pytest
from pydantic import ValidationError

from recycleguard.application import command_context, local_application
from recycleguard.baseline import BaselineOutput
from recycleguard.config import Settings
from recycleguard.contracts.artifacts import SnapshotRef
from recycleguard.contracts.workflow import BudgetLimits
from recycleguard.investigation import InvestigationRequest, InvestigationService, ScriptedExchange
from recycleguard.local_model import LocalModelPort
from recycleguard.workflow.runner import CallRecord
from tests.integration.test_a05_baseline import approved_foundation as approved_foundation
from tests.support.workflow import assess, plan
from tests.unit.test_local_model import configuration
from tests.unit.test_local_model import server as server


@pytest.fixture
def native(tmp_path, approved_foundation, server):
    root = tmp_path / "runtime"
    shutil.copytree(approved_foundation, root, ignore=shutil.ignore_patterns("reviewer.json"))
    settings = Settings(data_root=root)
    config = configuration(server, tmp_path)
    with local_application(settings) as (cases, context, capability):
        case = cases.snapshots.catalog.get_snapshot("snapshot:case_approved")
        corpus = cases.snapshots.catalog.get_snapshot("snapshot:corpus_approved")
        request = InvestigationRequest(
            run_id="run:native_a07_loopback_fixture",
            case_snapshot=SnapshotRef(
                snapshot_id=case.snapshot_id, membership_digest=case.membership_digest
            ),
            corpus_snapshot=SnapshotRef(
                snapshot_id=corpus.snapshot_id, membership_digest=corpus.membership_digest
            ),
            finding_ids=["finding:one"],
            local_model_config=config,
            budgets=BudgetLimits(tokens_per_model_call=16384),
        )
        service = InvestigationService(cases, settings, capability=capability)
        yield service, context, capability, request, config, server[0]


def test_request_must_select_exactly_one_backend(native):
    _, _, _, request, _, _ = native
    body = request.model_dump(mode="json")
    with pytest.raises(ValidationError, match="exactly one"):
        InvestigationRequest.model_validate_json(json.dumps(body | {"local_model_config": None}))
    exchange = ScriptedExchange(phase="PLAN", response=plan().output).model_dump(mode="json")
    with pytest.raises(ValidationError, match="exactly one"):
        InvestigationRequest.model_validate_json(
            json.dumps(body | {"scripted_exchanges": [exchange]})
        )


def test_runtime_native_port_executes_actual_tools_without_support_promotion(native, monkeypatch):
    service, context, capability, request, config, backend = native
    # A fixture HTTP server supplies known JSON to exercise transport/composition;
    # this test makes no claim about model inference or held-out quality.
    check = plan(operation="compute_reconciliation").output
    check["action"]["typed_arguments"] = {"bucket_ids": []}
    assessment = assess(verdict="UNKNOWN", disposition="ABSTAIN").output
    original_invoke = LocalModelPort.invoke
    assessment_payloads = []

    def fixture_response(port, ctx, model_request):
        assert ctx.run_id == request.run_id
        assert ctx.case_version_id == request.case_snapshot.snapshot_id
        assert model_request.model_configuration_id == config.configuration_id
        assert model_request.prompt_template_id == config.prompt_template_id
        assert model_request.prompt_template_digest == config.prompt_pin().digest
        payload = json.loads(port.blobs.get(model_request.exact_request_blob))
        assert payload["run_id"] == request.run_id
        if payload["phase"] == "ASSESS":
            assessment_payloads.append(payload)
        backend.model_text = json.dumps(check if payload["phase"] == "PLAN" else assessment)
        return original_invoke(port, ctx, model_request)

    monkeypatch.setattr(LocalModelPort, "invoke", fixture_response)
    spec = service.prepare(context, request)
    assert spec.execution_kind == "MODEL_BACKED"
    assert spec.model == config.pin() and spec.prompt == config.prompt_pin()
    assert service.configuration(spec).local_model_config == config
    runner = service.runner(spec)
    try:
        assert type(runner.port) is LocalModelPort
        state = runner.start_run(context, spec, capability=capability)
        for _ in range(12):
            if state.status == "AWAITING_REVIEW":
                break
            state = runner.advance(
                command_context(context.actor), spec.run_id, state.version, capability=capability
            )
        assert state.status == "AWAITING_REVIEW" and state.review_outcome == "PENDING"
        assert state.budget.model_calls == 2 and state.budget.observed_tokens == 360
        assert state.budget.tool_calls == 1 and state.plan_refs and state.assessment_refs
        posts = [body for method, _, body in backend.calls if method == "POST"]
        assert len(posts) == 2
        observation = assessment_payloads[0]["observation"]["stage_output"]
        summary = json.loads(observation["concise_decision"])
        evidence = json.loads(summary["evidence_data_json"])
        assert not summary["evidence_truncated"]
        assert "untrusted data" in summary["trust"]
        assert evidence["buckets"][0]["required"]["decimal"] == "100.0000"
        assert evidence["buckets"][0]["supported"]["decimal"] == "0.0000"
        assert evidence["coverage"] == "QUALIFIED"
        events = service.kernel.list_stream_events(f"stream:{spec.run_id}")
        for event in events:
            if event.event_type.startswith("graph.model.") and event.event_type.endswith(".result"):
                record = service.store.read(event.operation_id, CallRecord)
                assert record.status == "SUCCESS"
                assert record.model_output.provider_request_ref == "cmpl-test"
                exact = json.loads(service.blobs.get(record.model_output.exact_response_blob))
                assert exact == record.model_output.validated_output_or_null
            if event.event_type.startswith("graph.tool.") and event.event_type.endswith(".result"):
                record = service.store.read(event.operation_id, CallRecord)
                actual = BaselineOutput.model_validate_json(
                    service.blobs.get(record.stage_output.output_blob)
                )
                # The uploaded/normalized PENDING allocation remains unsupported.
                assert actual.calculation.bucket_results[0].supported.decimal == "0.0000"
        assert service.latest_report(spec.run_id).verification.verdict == "QUALIFIED"
    finally:
        runner.close()
    restarted = InvestigationService(service.cases, service.settings, capability=capability)
    assert restarted.configuration(restarted.store.spec(spec.run_id)).local_model_config == config


@pytest.mark.parametrize(
    "field", ["model", "prompt", "code_revision", "dependency_lock_digest", "execution_kind"]
)
def test_frozen_native_configuration_rejects_changed_pins_before_http(native, field):
    service, context, _, request, _, backend = native
    spec = service.prepare(context, request)
    if field in {"model", "prompt"}:
        value = (spec.model if field == "model" else spec.prompt).model_copy(
            update={"digest": "f" * 64}
        )
    elif field == "execution_kind":
        value = "SCRIPTED_TEST"
    else:
        value = "f" * 64
    with pytest.raises(ValueError):
        service.runner(spec.model_copy(update={field: value}))
    assert not backend.calls


def test_native_runner_cannot_advance_differently_composed_frozen_run(native):
    service, context, capability, request, _, backend = native
    spec = service.prepare(context, request)
    runner = service.runner(spec)
    try:
        state = runner.start_run(context, spec, capability=capability)
    finally:
        runner.close()
    other = spec.model_copy(update={"finding_ids": ["finding:other"]})
    runner = service.runner(other)
    before = len(backend.calls)
    try:
        with pytest.raises(ValueError, match="composition differs"):
            runner.advance(
                command_context(context.actor), spec.run_id, state.version, capability=capability
            )
        assert service.store.load(spec.run_id) == state
        assert len(backend.calls) == before
    finally:
        runner.close()


def test_provenance_drift_blocks_restart_before_any_dispatch(native):
    service, context, capability, request, config, backend = native
    spec = service.prepare(context, request)
    runner = service.runner(spec)
    try:
        state = runner.start_run(context, spec, capability=capability)
        config.runtime_lock_path.write_text("changed after run configuration was pinned")
        before = len(backend.calls)
        with pytest.raises(ValueError, match="provenance"):
            runner.advance(
                command_context(context.actor), spec.run_id, state.version, capability=capability
            )
        assert service.store.load(spec.run_id) == state
        assert len(backend.calls) == before
    finally:
        runner.close()


def test_failed_probe_never_falls_back_to_scripted_inference(native):
    service, context, capability, request, _, backend = native
    spec = service.prepare(context, request)
    backend.model_path = "/not/the/configured/model"
    runner = service.runner(spec)
    try:
        with pytest.raises(ValueError, match="inventory"):
            runner.start_run(context, spec, capability=capability)
        with pytest.raises(ValueError):
            service.store.load(spec.run_id)
        assert all(method == "GET" for method, _, _ in backend.calls)
    finally:
        runner.close()


def test_native_call_budget_cannot_exceed_configured_model_limit(native):
    service, context, _, request, _, backend = native
    oversized = request.model_copy(update={"budgets": BudgetLimits(tokens_per_model_call=32768)})
    with pytest.raises(ValueError, match="budget exceeds"):
        service.prepare(context, oversized)
    assert not backend.calls
