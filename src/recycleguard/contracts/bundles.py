"""C14 Bundle manifest, integrity verification, replay and rights-through-derivatives models.

Normative models pursuant to CONTRACTS.md §§3.1, 12 and SYSTEM_DESIGN.md §§8.4, 9, 10.
"""

from typing import Literal

from pydantic import Field

from .core import ID, BlobRef, BoundaryModel, Digest, EvidenceRef, Issue, Timestamp

BundleKind = Literal["COMPLETE_LOCAL", "QUALIFIED_PUBLIC"]
BundleCompleteness = Literal["COMPLETE_LOCAL", "QUALIFIED_PUBLIC", "PARTIAL"]
IntegrityVerdict = Literal["PASS", "FAIL", "PARTIAL"]
ReplayMode = Literal["ARTIFACT", "RECOMPUTE", "MODEL_RERUN"]
RightsDecisionState = Literal["ALLOW", "DENY", "REVIEW_REQUIRED"]
RestrictionReason = Literal[
    "RIGHTS_RESTRICTED",
    "PROMPT_DERIVATIVE_RESTRICTED",
    "SENSITIVE_DATA",
    "REDIS_NOT_PERMITTED",
    "CONFIDENTIAL",
]


class RightsDecision(BoundaryModel):
    """Asset-level rights decision governing redistribution and derivative exposure."""

    rights_decision_id: ID
    owner_or_provider: str
    intended_use: str
    license_or_basis: str
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    access_allowed: RightsDecisionState = "ALLOW"
    model_use_allowed: RightsDecisionState = "ALLOW"
    local_retention_allowed: RightsDecisionState = "ALLOW"
    redistribution_status: RightsDecisionState = "REVIEW_REQUIRED"
    reviewer_id: ID | None = None
    reviewed_at: str | None = None


class OmissionDisposition(BoundaryModel):
    """Explicit disclosure of omitted artifacts or derivative context in public exports."""

    object_ref: ID
    object_kind: str
    restriction_reason: RestrictionReason
    explanation: str
    hash_disclosed: bool = True
    original_sha256: Digest | None = None


class AttributionRecord(BoundaryModel):
    """Attribution and licensing metadata for included or reviewed sources."""

    artifact_revision_id: ID
    title_or_description: str
    copyright_owner: str
    license_or_basis: str
    attribution_text: str
    redistribution_status: RightsDecisionState


class IncludedObjectEntry(BoundaryModel):
    """Metadata entry for an object bundled in an audit or publication package."""

    object_ref: ID
    object_kind: str
    sha256: Digest
    byte_length: int
    media_type: str = "application/json"


class BundleManifest(BoundaryModel):
    """Authoritative bundle manifest for complete local or qualified public export
    (CONTRACTS §12).
    """

    bundle_id: ID
    bundle_kind: BundleKind
    selected_run_refs: list[ID]
    included_objects_blob: BlobRef
    omission_dispositions_blob: BlobRef
    attribution_blob: BlobRef
    audit_head_refs: list[ID]
    dependency_digest: Digest
    completeness: BundleCompleteness
    integrity_result_ref: ID | None = None


class IntegrityResult(BoundaryModel):
    """Integrity verification report covering bundled objects and audit continuity
    (CONTRACTS §12).
    """

    check_id: ID
    target_ref: ID
    checked_at: Timestamp
    verdict: IntegrityVerdict
    checked_count: int
    missing_or_mismatched_refs: list[ID] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    verifier_version: str = "1.0.0"


class ReplayRequest(BoundaryModel):
    """Request for offline artifact replay or deterministic recomputation (CONTRACTS §12)."""

    bundle_id: ID
    mode: ReplayMode = "ARTIFACT"
    dependency_environment_ref: str
    access_scope_id: str


class ReplayResult(BoundaryModel):
    """Outcome of offline replay or recomputation (CONTRACTS §12)."""

    replay_id: ID
    mode: ReplayMode
    source_bundle_id: ID
    reconstructed_state_refs: list[ID]
    comparison_refs: list[ID]
    new_run_id: ID | None = None
    integrity_result_ref: ID
    issues: list[Issue] = Field(default_factory=list)
