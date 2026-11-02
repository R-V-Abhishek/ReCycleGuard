"""Shared CP0 audit shapes; operation envelopes support the V01 prototype only."""

from typing import Annotated

from pydantic import Field, model_validator

from .core import (
    ID,
    ActorRef,
    BlobRef,
    BoundaryModel,
    CommandContext,
    Digest,
    ErrorCode,
    EvidenceRef,
    Nonempty,
    Status,
    Timestamp,
)


class OperationIntent(BoundaryModel):
    context: CommandContext
    idempotency_key: Nonempty
    event_type: Nonempty
    payload: BlobRef
    stream_id: ID = "stream:prototype"
    input_refs: list[BlobRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def same_key(self):
        if self.idempotency_key != self.context.idempotency_key:
            raise ValueError("intent and command-context idempotency keys differ")
        return self


class OperationResult(BoundaryModel):
    operation_id: ID
    attempt_id: ID
    status: Status
    payload: BlobRef | None
    output_refs: list[BlobRef] = Field(default_factory=list)
    issue_codes: list[ErrorCode] = Field(default_factory=list)

    @model_validator(mode="after")
    def explicit_failure(self):
        if self.status != "SUCCESS" and not self.issue_codes:
            raise ValueError("non-success operation result requires issues")
        return self


class AuditEvent(BoundaryModel):
    event_id: ID
    stream_id: ID
    sequence: Annotated[int, Field(ge=1)]
    event_type: Nonempty
    recorded_at: Timestamp
    actor: ActorRef
    command_id: ID
    operation_id: ID
    attempt_id: ID
    case_version_id: ID | None
    run_id: ID | None
    turn_id: ID | None
    input_refs: list[BlobRef]
    output_refs: list[BlobRef]
    dependency_refs: list[EvidenceRef]
    payload_blob: BlobRef
    previous_event_hash: Digest | None
    event_hash: Digest
