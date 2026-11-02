"""C10 call boundary only. No provider, transport, retry or fallback implementation."""

from typing import Protocol

from pydantic import JsonValue

from recycleguard.contracts import BlobRef, BoundaryModel, CommandContext, Issue, ServiceResult
from recycleguard.contracts.core import ID, Digest, Nonempty, Status


class ModelCallRequest(BoundaryModel):
    model_configuration_id: ID
    prompt_template_id: ID
    prompt_template_digest: Digest
    exact_request_blob: BlobRef
    context_manifest_id: ID
    allowed_tool_schema_digest: Digest
    response_schema_id: ID
    budget_ref: ID


class ModelCallResult(BoundaryModel):
    model_call_id: ID
    provider_request_ref: Nonempty | None
    exact_response_blob: BlobRef
    validated_output_or_null: JsonValue
    validation_issues: list[Issue]
    # Provider usage/timing shapes are intentionally not invented before A02.
    usage: dict[str, JsonValue] | None
    timing: dict[str, JsonValue]
    outcome: Status


class ModelPort(Protocol):
    """Caller provides cleared/redacted blobs; C11 auditing is required at integration."""

    def invoke(
        self, context: CommandContext, request: ModelCallRequest
    ) -> ServiceResult[ModelCallResult]: ...
