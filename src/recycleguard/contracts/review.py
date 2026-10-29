"""Boundary models for trusted review transitions, review packets and filing acknowledgments.

Implements C13 Authenticated human review and CONTRACTS.md §12 models.
"""

from typing import Literal

from pydantic import Field

from recycleguard.contracts.artifacts import SnapshotRef
from recycleguard.contracts.core import (
    ID,
    ActorRef,
    BlobRef,
    BoundaryModel,
    Digest,
    Issue,
    Nonempty,
    Timestamp,
)

ReviewDecisionKind = Literal["APPROVE", "REJECT", "REQUEST_CHANGES", "ESCALATE"]
ReviewOutcome = Literal[
    "NOT_REQUESTED",
    "PENDING",
    "APPROVED",
    "REJECTED",
    "CHANGES_REQUESTED",
    "ESCALATED",
    "CLOSED_WITHOUT_DECISION",
]
AcknowledgmentValidationState = Literal["VALID", "INVALID", "PENDING_VERIFICATION"]


class ReviewPacket(BoundaryModel):
    packet_id: ID
    creation_operation_id: ID
    run_id: ID
    report_blob: BlobRef
    report_revision_id: ID
    review_dependency_digest: Digest
    input_snapshot_refs: list[SnapshotRef]
    proposed_action_refs: list[ID]
    unresolved_issue_refs: list[ID]
    permitted_decisions: list[ReviewDecisionKind]
    created_at: Timestamp


class ReviewDecision(BoundaryModel):
    decision: ReviewDecisionKind
    authenticated_reviewer_ref: ActorRef
    reason: Nonempty
    recorded_at: str


class ReviewRecord(BoundaryModel):
    review_id: ID
    run_id: ID
    report_revision_id: ID
    input_snapshot_refs: list[SnapshotRef]
    packet_id: ID
    review_dependency_digest: Digest
    decision: ReviewDecisionKind
    authenticated_reviewer_ref: ActorRef
    reason: Nonempty
    recorded_at: Timestamp
    supersedes_review_id: ID | None = None


class AcknowledgmentRecord(BoundaryModel):
    acknowledgment_id: ID
    artifact_revision_id: ID
    linked_case_version_id: ID
    linked_report_revision_id: ID | None = None
    claimed_external_reference: str
    validation_state: AcknowledgmentValidationState
    review_ref: ID | None = None


class ReviewTransitionResult(BoundaryModel):
    new_run_status: str
    new_review_outcome: ReviewOutcome
    stop_reason: str | None = None
    review_record: ReviewRecord | None = None
    issues: list[Issue] = Field(default_factory=list)


__all__ = [
    "AcknowledgmentRecord",
    "AcknowledgmentValidationState",
    "ReviewDecision",
    "ReviewDecisionKind",
    "ReviewOutcome",
    "ReviewPacket",
    "ReviewRecord",
    "ReviewTransitionResult",
]
