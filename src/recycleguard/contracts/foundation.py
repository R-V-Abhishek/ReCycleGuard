"""A04 persisted evidence foundation. These records cannot approve themselves."""

from recycleguard.contracts.artifacts import (
    ArtifactRevision,
    AssetReceipt,
    FrozenSnapshot,
    ProfileRef,
)
from recycleguard.contracts.core import ID, BlobRef, BoundaryModel, Issue, Nonempty
from recycleguard.contracts.domain import ReviewedInterval
from recycleguard.contracts.extraction import CoverageItem, ExtractionResult, Observation
from recycleguard.contracts.sources import ProvisionVersion, Role, SourceLead, SourceVersion


class ApplicabilityProposal(BoundaryModel):
    assertion_id: ID
    provision_version_id: ID
    interval: ReviewedInterval
    affected_roles: list[Role]
    category_scope: list[str]
    scope_notes: str


class SourceBatch(BoundaryModel):
    artifact_revisions: list[ArtifactRevision]
    receipts: list[AssetReceipt]
    leads: list[SourceLead]
    source_versions: list[SourceVersion]
    provisions: list[ProvisionVersion]
    applicability: list[ApplicabilityProposal]


class ExtractedBatch(BoundaryModel):
    results: list[ExtractionResult]
    observations: list[Observation]
    coverage: list[CoverageItem]


class FoundationRequest(BoundaryModel):
    case_root: str
    r02_path: str
    r08_path: str
    case_snapshot_id: ID
    corpus_snapshot_id: ID
    profile_version: Nonempty
    expected_case_head: ID | None = None
    expected_corpus_head: ID | None = None
    expected_profile_head: ProfileRef | None = None


class FoundationResult(BoundaryModel):
    case_snapshot: FrozenSnapshot
    corpus_snapshot: FrozenSnapshot
    profile: ProfileRef
    inventory_count: int
    extraction_count: int
    observation_count: int
    record_count: int
    normalization_quarantine_count: int
    issues: list[Issue]


class FoundationApproval(BoundaryModel):
    candidate_blob: BlobRef
    approval_evidence_blob: BlobRef
    approval_reference: ID
    accepted_qualifications: Nonempty
    reviewed_profile_version: Nonempty
    approved_profile_version: Nonempty
    reviewed_case_snapshot_id: ID
    approved_case_snapshot_id: ID
    reviewed_corpus_snapshot_id: ID
    approved_corpus_snapshot_id: ID
