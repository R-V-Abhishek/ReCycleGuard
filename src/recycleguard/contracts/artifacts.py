"""CP0 receipt and snapshot boundaries, without publication or approval handlers."""

from typing import Literal

from pydantic import model_validator

from .core import ID, BlobRef, BoundaryModel, Digest, Nonempty, TemporalValue, Timestamp

EvidenceCapability = Literal[
    "IDENTITY",
    "REGISTRATION_COVERAGE",
    "REPORTED_ACCOUNT_POSITION",
    "CERTIFICATE_IDENTITY",
    "TRANSFER_STAGE",
    "LIABILITY_ALLOCATION",
    "PAYMENT",
    "PHYSICAL_MOVEMENT",
    "DESTRUCTION",
    "AWARENESS_ACTIVITY",
    "FILING_RECEIPT",
    "RULE_TEXT",
    "CONTEXT_ONLY",
]


class AssetReceipt(BoundaryModel):
    receipt_id: ID
    batch_id: ID
    declared_asset_id: ID | None
    supplied_path_or_url: str
    intake_status: Literal["RECEIVED", "DECLARED_MISSING", "REJECTED_ACCESS", "FETCH_FAILED"]
    artifact_revision_id: ID | None
    reason: str | None
    received_at: Timestamp

    @model_validator(mode="after")
    def receipt_outcome(self):
        if self.intake_status == "RECEIVED" and self.artifact_revision_id is None:
            raise ValueError("received asset requires an artifact revision")
        if self.intake_status != "RECEIVED" and (
            self.artifact_revision_id is not None or not self.reason
        ):
            raise ValueError("unsuccessful receipt requires a reason and no invented artifact")
        return self


class FrozenSnapshot(BoundaryModel):
    snapshot_id: ID
    snapshot_kind: Literal["CASE", "CORPUS"]
    schema_version: str
    parent_snapshot_id: ID | None
    membership_blob: BlobRef
    membership_digest: Digest
    coverage_blob: BlobRef
    created_at: Timestamp
    created_by: ID
    source_receipt_ids: list[ID]
    review_state: Literal["DRAFT", "APPROVED", "REJECTED"]


class SnapshotRef(BoundaryModel):
    """Pinned reference; introduced by A02, not an implemented C05 lookup."""

    snapshot_id: ID
    membership_digest: Digest


class ProfileRef(BoundaryModel):
    profile_id: ID
    profile_version: Nonempty
    digest: Digest


class ArtifactRevision(BoundaryModel):
    artifact_id: ID
    artifact_revision_id: ID
    blob: BlobRef
    original_filename: str | None
    source_kind: Literal[
        "GAZETTE",
        "OFFICIAL_GUIDANCE",
        "PORTAL_CAPTURE",
        "COMPANY_RECORD",
        "SYNTHETIC_RECORD",
        "AGGREGATE_STATISTICS",
        "RESEARCH_NOTE",
    ]
    doc_type: Literal[
        "STATUTORY_INSTRUMENT",
        "SOP",
        "TECHNICAL_FRAMEWORK",
        "FAQ",
        "PORTAL_INSTRUCTION",
        "NOTICE",
        "REGISTRATION_CERTIFICATE",
        "PORTAL_SNAPSHOT",
        "PORTAL_EPR_CERTIFICATE",
        "GST_INVOICE",
        "ERP_CSV",
        "CONTRACT",
        "PURCHASE_ORDER",
        "PAYMENT_RECORD",
        "WEIGHT_TICKET",
        "RECYCLING_ACKNOWLEDGMENT",
        "DESTRUCTION_CERTIFICATE",
        "AWARENESS_PROOF",
        "RETURN_DRAFT",
        "FILING_ACKNOWLEDGMENT",
        "OTHER",
    ]
    establishes: list[EvidenceCapability]
    does_not_establish: list[EvidenceCapability]
    source_url: str | None
    fetch_attempt_id: ID | None
    captured_at: TemporalValue
    ingested_at: Timestamp
    access_policy_id: ID
    rights_decision_id: ID
    synthetic: bool
    derived_from: list[ID]
