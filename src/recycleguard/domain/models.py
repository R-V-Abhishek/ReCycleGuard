"""C08 archived-derivation models.

These are internal to the dispositions/derivation blobs. `QuantityDisposition` is described in
CONTRACTS §6.2 prose but has no generated boundary schema yet (see the S03 handoff note).
"""

from typing import Literal

from recycleguard.contracts.core import (
    ID,
    BoundaryModel,
    EvidenceRef,
    Nonempty,
    Quantity,
    TemporalValue,
)

CheckState = Literal["PASS", "FAIL", "UNKNOWN", "NOT_EVALUATED"]
DispositionState = Literal["INCLUDED", "EXCLUDED", "PENDING", "OUT_OF_SCOPE"]
Coverage = Literal["COMPLETE_WITHIN_SCOPE", "QUALIFIED", "BLOCKED"]


class QuantityDisposition(BoundaryModel):
    record_id: ID
    record_revision_id: ID
    record_type: Nonempty
    state: DispositionState
    quantity: Quantity | None
    allocated_bucket_id: ID | None
    reason: Nonempty
    evidence_refs: list[EvidenceRef]


class LotCheck(BoundaryModel):
    credit_lot_id: ID
    certificate_id: ID | None
    resolution_state: Literal["SUPPORTED", "PENDING", "CONFLICTING"]
    capacity: Quantity | None
    supported_allocated: Quantity | None
    observed_allocated: Quantity | None
    conservation: CheckState
    reason: Nonempty


class PriorityCheck(BoundaryModel):
    allocation_id: ID
    bucket_id: ID
    state: CheckState
    earlier_bucket_ids: list[ID]
    reason: Nonempty


class PortalComparison(BoundaryModel):
    comparison_id: ID
    bucket_id: ID
    balance_observation_id: ID | None
    portal_reported: Quantity | None
    ledger_supported: Quantity
    delta: Quantity | None
    source_capture_time: TemporalValue | None
    business_cutoff: TemporalValue | None
    note: Nonempty


class EligibilityOutcome(BoundaryModel):
    condition: Nonempty
    testability: Literal["TESTABLE", "UNAVAILABLE"]
    state: CheckState
    reason: Nonempty


class BucketDerivation(BoundaryModel):
    bucket_id: ID
    target: Quantity
    adjustments: list[Quantity]
    required: Quantity
    supported_allocation_ids: list[ID]
    pending_allocation_ids: list[ID]
    pending_commercial_ids: list[ID]
    formula: Nonempty
    coverage: Coverage


class Derivation(BoundaryModel):
    tool_version: Nonempty
    snapshot_id: ID
    membership_digest: Nonempty
    profile_id: ID
    profile_digest: Nonempty
    requested_bucket_ids: list[ID]
    buckets: list[BucketDerivation]
    lots: list[LotCheck]
    priority_checks: list[PriorityCheck]
    portal_comparisons: list[PortalComparison]
    eligibility: list[EligibilityOutcome]
    purchase_ceiling: CheckState
    purchase_ceiling_reason: Nonempty
    unsupported_features: list[Nonempty]
    coverage: Coverage
