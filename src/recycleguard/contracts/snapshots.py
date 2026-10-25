"""A03 snapshot storage requests. These do not implement profile policy or CLI login."""

from typing import Literal

from pydantic import model_validator

from .core import ID, BlobRef, BoundaryModel, Digest, Nonempty


class SnapshotPublication(BoundaryModel):
    scope_id: ID
    snapshot_id: ID
    snapshot_kind: Literal["CASE", "CORPUS"]
    expected_head: ID | None
    membership_blob: BlobRef
    membership_digest: Digest
    coverage_blob: BlobRef
    source_receipt_ids: list[ID]

    @model_validator(mode="after")
    def pinned_membership(self):
        if self.membership_blob.sha256 != self.membership_digest:
            raise ValueError("membership digest does not match exact blob")
        if self.snapshot_id == self.expected_head:
            raise ValueError("a revision requires a new snapshot ID")
        if len(self.source_receipt_ids) != len(set(self.source_receipt_ids)):
            raise ValueError("duplicate source receipt IDs")
        return self


class SnapshotReview(BoundaryModel):
    scope_id: ID
    target_snapshot_id: ID
    target_membership_digest: Digest
    expected_head: ID
    new_snapshot_id: ID
    decision: Literal["APPROVE", "REJECT"]
    reason: Nonempty

    @model_validator(mode="after")
    def exact_review_target(self):
        if self.target_snapshot_id != self.expected_head:
            raise ValueError("review must bind the expected current revision")
        if self.new_snapshot_id == self.target_snapshot_id:
            raise ValueError("review creates a child revision; it cannot overwrite the target")
        return self
