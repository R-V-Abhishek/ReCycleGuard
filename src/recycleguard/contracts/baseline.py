"""Pinned baseline execution and trusted evidence-support review requests."""

from pydantic import Field

from .artifacts import SnapshotRef
from .core import ID, BoundaryModel, EvidenceRef, Nonempty
from .results import CalculationRequest


class BaselineRequest(BoundaryModel):
    snapshot: SnapshotRef
    calculation: CalculationRequest


class RecordSupportAssertion(BoundaryModel):
    target_record_revision_id: ID
    evidence_refs: list[EvidenceRef] = Field(min_length=1)
    reason: Nonempty


class RecordSupportReview(BoundaryModel):
    target: SnapshotRef
    reviewed_snapshot_id: ID
    approved_snapshot_id: ID
    assertions: list[RecordSupportAssertion] = Field(min_length=1)
    reason: Nonempty
