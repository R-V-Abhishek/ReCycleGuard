import pytest

from recycleguard.config import Settings
from recycleguard.contracts import BlobRef, CommandContext, ServiceResult
from recycleguard.model_port import ModelCallRequest, ModelCallResult
from recycleguard.recorded_port import RecordedReplayModelPort

SETTINGS = Settings(mode="test", enable_test_adapters=True)


def request(request_digest="b" * 64, template_digest="a" * 64):
    return ModelCallRequest(
        model_configuration_id="model_configuration:test",
        prompt_template_id="prompt:1",
        prompt_template_digest=template_digest,
        exact_request_blob=BlobRef(
            sha256=request_digest, byte_length=2, media_type="application/json"
        ),
        context_manifest_id="context_manifest:1",
        allowed_tool_schema_digest="c" * 64,
        response_schema_id="schema:test",
        budget_ref="budget:1",
    )


def recorded(ctx, marker):
    output = ModelCallResult(
        model_call_id="model_call:recorded",
        provider_request_ref=None,
        exact_response_blob=BlobRef(sha256="d" * 64, byte_length=2, media_type="application/json"),
        validated_output_or_null={"marker": marker},
        validation_issues=[],
        usage={"total_tokens": 7},
        timing={"seconds": 1.5},
        outcome="SUCCESS",
    )
    return ServiceResult[ModelCallResult](
        contract_version="1.1",
        operation_id="operation:recorded",
        attempt_id="attempt:recorded",
        status="SUCCESS",
        output=output,
        output_blob=None,
        issues=[],
        dependencies=[],
        audit_event_ids=["audit:old"],
    )


def test_identical_requests_replay_in_order_rebound_to_the_new_attempt(context_payload):
    ctx = CommandContext.model_validate(context_payload)
    port = RecordedReplayModelPort(
        SETTINGS, [(request(), recorded(ctx, "first")), (request(), recorded(ctx, "second"))]
    )
    first = port.invoke(ctx, request())
    assert (first.operation_id, first.attempt_id) == (ctx.operation_id, ctx.attempt_id)
    assert first.output.model_call_id == f"model_call:{ctx.attempt_id.split(':', 1)[1]}"
    assert first.output.validated_output_or_null == {"marker": "first"}
    assert first.output.usage == {"total_tokens": 7} and first.audit_event_ids == []
    assert port.invoke(ctx, request()).output.validated_output_or_null == {"marker": "second"}
    assert port.remaining() == 0 and port.served == 2


def test_a_different_request_or_exhausted_recording_raises(context_payload):
    ctx = CommandContext.model_validate(context_payload)
    port = RecordedReplayModelPort(SETTINGS, [(request(), recorded(ctx, "only"))])
    for other in (request("e" * 64), request(template_digest="f" * 64)):
        with pytest.raises(RuntimeError, match="no recorded response"):
            port.invoke(ctx, other)
    assert port.remaining() == 1
    port.invoke(ctx, request())
    with pytest.raises(RuntimeError, match="no recorded response"):
        port.invoke(ctx, request())


def test_replay_requires_explicit_enablement():
    with pytest.raises(ValueError, match="explicitly enabled test mode"):
        RecordedReplayModelPort(Settings(mode="test"), [])
