import pytest

from recycleguard.config import Settings
from recycleguard.contracts import BlobRef, CommandContext, Issue, ServiceResult
from recycleguard.model_port import ModelCallRequest, ModelCallResult, ModelPort
from tests.support.model_port import ScriptedModelPort


def request():
    return ModelCallRequest(
        model_configuration_id="model_configuration:test",
        prompt_template_id="prompt:1",
        prompt_template_digest="a" * 64,
        exact_request_blob=BlobRef(sha256="b" * 64, byte_length=2, media_type="application/json"),
        context_manifest_id="context_manifest:1",
        allowed_tool_schema_digest="c" * 64,
        response_schema_id="schema:test",
        budget_ref="budget:1",
    )


@pytest.mark.parametrize(
    "status,code",
    [
        ("SUCCESS", None),
        ("PARTIAL", "PROVIDER_INVALID_OUTPUT"),
        ("OUTCOME_UNKNOWN", "PROVIDER_TIMEOUT"),
    ],
)
def test_scripted_port_preserves_outcome_and_usage(context_payload, status, code):
    ctx = CommandContext.model_validate(context_payload)
    issues = (
        []
        if code is None
        else [
            Issue(
                issue_id="issue:1",
                code=code,
                severity="BLOCKING",
                message="Scripted provider outcome",
                field_path=None,
                evidence_refs=[],
                retryable=False,
            )
        ]
    )
    output = ModelCallResult(
        model_call_id="model_call:1",
        provider_request_ref=None,
        exact_response_blob=BlobRef(sha256="d" * 64, byte_length=2, media_type="application/json"),
        validated_output_or_null=None,
        validation_issues=issues,
        usage=None,
        timing={},
        outcome=status,
    )
    result = ServiceResult[ModelCallResult](
        contract_version="1.1",
        operation_id=ctx.operation_id,
        attempt_id=ctx.attempt_id,
        status=status,
        output=None if status == "OUTCOME_UNKNOWN" else output,
        output_blob=None,
        issues=issues,
        dependencies=[],
        audit_event_ids=[],
    )
    port: ModelPort = ScriptedModelPort(Settings(mode="test", enable_test_adapters=True), [result])
    assert port.invoke(ctx, request()) == result
    if status == "OUTCOME_UNKNOWN":
        assert result.output is None
    else:
        assert result.output.usage is None
    with pytest.raises(RuntimeError, match="exhausted"):
        port.invoke(ctx, request())


def test_script_requires_explicit_enablement():
    with pytest.raises(ValueError, match="explicitly enabled test mode"):
        ScriptedModelPort(Settings(mode="test"), [])


def test_attempt_mismatch_is_not_consumed(context_payload):
    ctx = CommandContext.model_validate(context_payload)
    result = ServiceResult[ModelCallResult](
        contract_version="1.1",
        operation_id=ctx.operation_id,
        attempt_id="attempt:wrong",
        status="SUCCESS",
        output=None,
        output_blob=None,
        issues=[],
        dependencies=[],
        audit_event_ids=[],
    )
    port = ScriptedModelPort(Settings(mode="test", enable_test_adapters=True), [result])
    with pytest.raises(ValueError, match="does not belong"):
        port.invoke(ctx, request())
    assert len(port.results) == 1
    assert port.calls == []
