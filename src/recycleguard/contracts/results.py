"""CP0 calculation/finding interchange shapes; no reconciliation or verdict engine."""

from typing import Literal

from pydantic import JsonValue, model_validator

from .core import ID, BlobRef, BoundaryModel, Digest, EvidenceRef, Issue, Quantity
from .domain import NonnegativeMass

FaultFamily = Literal[
    "F01_CLEAN_BASELINE",
    "F02_OVERLAPPING_EXPORT",
    "F03_MULTISTAGE_ID_REUSE",
    "F04_UNIT_DIMENSION_MIX",
    "F05_WRONG_ENTITY_ALIAS",
    "F06_STALE_SNAPSHOT",
    "F07_PAID_NO_TRANSFER",
    "F08_PRIOR_ARREARS_DRAIN",
    "F09_EXPIRED_CANCELLED",
    "F10_CAPABILITY_MISMATCH",
    "F11_WRONG_PERIOD_RULE",
    "F12_UNSEEN_NOTICE_LEAD",
    "F13_WEIGHT_BASIS_CONFLICT",
    "F14_OUT_OF_SCOPE_REGIME",
    "F15_EXTRACTION_PAGE_LOSS",
    "F16_PROMPT_INJECTION",
]
AbstentionReason = Literal[
    "MISSING_EVIDENCE",
    "MISSING_AUTHORITY",
    "RULE_CONFLICT",
    "TEMPORAL_UNCERTAINTY",
    "UNSUPPORTED_FEATURE",
    "INCOMPLETE_HISTORY",
    "BUDGET_LIMIT",
]


class CalculationRequest(BoundaryModel):
    case_version_id: ID
    profile_id: ID
    bucket_ids: list[ID]
    expected_input_membership_digest: Digest | None


class BucketResult(BoundaryModel):
    bucket_id: ID
    required: NonnegativeMass
    supported: NonnegativeMass
    signed_gap: Quantity
    shortfall: NonnegativeMass
    surplus: NonnegativeMass
    pending: NonnegativeMass
    portal_reported: NonnegativeMass | None
    ledger_supported: NonnegativeMass
    delta: Quantity | None
    snapshot_comparison_ref: ID | None
    allocation_ids: list[ID]
    qualification_refs: list[EvidenceRef]

    @model_validator(mode="after")
    def comparison_presence(self):
        quantities = [
            self.required,
            self.supported,
            self.signed_gap,
            self.shortfall,
            self.surplus,
            self.pending,
            self.ledger_supported,
            self.portal_reported,
            self.delta,
        ]
        dimensions = {(q.dimension, q.metal, q.unit) for q in quantities if q is not None}
        if len(dimensions) != 1:
            raise ValueError("bucket result quantities must share dimension, metal and unit")
        if self.delta is not None and self.snapshot_comparison_ref is None:
            raise ValueError("a numeric comparison requires its snapshot reference")
        if self.ledger_supported != self.supported:
            raise ValueError("ledger_supported is the same supported value, not another credit")
        if self.portal_reported is None and (
            self.delta is not None or self.snapshot_comparison_ref is not None
        ):
            raise ValueError("absent portal evidence cannot assert a comparison")
        return self


class CalculationResult(BoundaryModel):
    calculation_id: ID
    case_version_id: ID
    profile_id: ID
    tool_version: str
    input_digest: Digest
    analyzed_input_membership_blob: BlobRef
    analyzed_bucket_ids: list[ID]
    bucket_results: list[BucketResult]
    quantity_dispositions_blob: BlobRef
    derivation_blob: BlobRef
    coverage: Literal["COMPLETE_WITHIN_SCOPE", "QUALIFIED", "BLOCKED"]
    issues: list[Issue]


class CalculationValueRef(BoundaryModel):
    calculation_id: ID
    bucket_id: ID
    field: Literal[
        "required",
        "supported",
        "signed_gap",
        "shortfall",
        "surplus",
        "pending",
        "portal_reported",
        "ledger_supported",
        "delta",
    ]


class Recommendation(BoundaryModel):
    kind: Literal["INVESTIGATE", "REQUEST_EVIDENCE", "ESCALATE", "NO_FURTHER_ACTION"]
    description: str
    evidence_refs: list[EvidenceRef]


class Hypothesis(BoundaryModel):
    text: str
    support_state: Literal["SUPPORTED", "QUALIFIED", "UNSUPPORTED"]
    refs: list[EvidenceRef]


class FindingRecord(BoundaryModel):
    finding_id: ID
    finding_revision_id: ID
    case_version_id: ID
    bucket_ids: list[ID]
    issue_type: FaultFamily
    advisory_status: Literal[
        "RECONCILED_WITHIN_SCOPE",
        "DISCREPANCY_DETECTED",
        "PENDING_VERIFICATION",
        "REQUIRES_EXPERT_REVIEW",
    ]
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    priority_basis: str
    portal_reported_value_ref: CalculationValueRef | None
    ledger_supported_value_ref: CalculationValueRef | None
    delta_value_ref: CalculationValueRef | None
    snapshot_comparison_ref: ID | None
    fact_refs: list[EvidenceRef]
    calculation_refs: list[ID]
    provision_refs: list[EvidenceRef]
    evidence_assessments: list[dict[str, JsonValue]]
    hypotheses: list[Hypothesis]
    abstention_reason: AbstentionReason | None
    withheld_claim_scopes: list[str]
    next_action: Recommendation
    action_owner_ref: ID | None
    scope_limits: list[str]
    supersedes_finding_revision_id: ID | None

    @model_validator(mode="after")
    def explicit_abstention(self):
        if self.abstention_reason is not None:
            if self.advisory_status not in {"PENDING_VERIFICATION", "REQUIRES_EXPERT_REVIEW"}:
                raise ValueError("abstention requires an unresolved advisory status")
            if not self.withheld_claim_scopes:
                raise ValueError("abstention must name the withheld claim scope")
        return self
