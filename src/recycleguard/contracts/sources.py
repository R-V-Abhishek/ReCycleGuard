"""Source knowledge and regulatory lead boundary models from CONTRACTS section 4.1.

Owned by Sampreeth (H01). Reviewed by A02 before freeze.
"""

from typing import Literal

from .core import ID, BlobRef, BoundaryModel, EvidenceRef, Locator, TemporalValue

SourceClass = Literal[
    "STATUTE",
    "GAZETTE_RULE",
    "ORDER",
    "TECHNICAL_FRAMEWORK",
    "SOP",
    "PORTAL_INSTRUCTION",
    "FAQ",
    "NOTICE_LEAD",
    "SUPPORTING_CONTEXT",
]

SourceLeadState = Literal[
    "DISCOVERED",
    "FETCH_FAILED",
    "ACQUIRED",
    "EXTRACTED",
    "REVIEW_REQUIRED",
    "READY",
    "EXCLUDED",
]

Role = Literal["PRODUCER", "MANUFACTURER", "RECYCLER", "REFURBISHER"]


class RightsMetadata(BoundaryModel):
    """Asset-level rights and licensing decisions pursuant to Indian copyright law."""

    copyright_owner: str
    statutory_exception_sec52: str | None
    asset_rights_seed: Literal["REVIEW_REQUIRED", "ALLOW", "DENY"]
    redistribution_allowed: bool
    attribution_text: str


class SourceLead(BoundaryModel):
    """Authoritative discovery lead for regulatory or operational sources (CONTRACTS §4.1)."""

    source_lead_id: ID
    aliases: list[str]
    official_url: str
    discovery_evidence_refs: list[EvidenceRef]
    source_class: SourceClass
    regime: str
    state: SourceLeadState
    acquired_artifact_revision_id: ID | None
    rights_and_license: RightsMetadata


class SourceVersion(BoundaryModel):
    """Acquired and versioned primary instrument or operational publication (CONTRACTS §4.1)."""

    source_version_id: ID
    source_lead_id: ID
    artifact_revision_id: ID
    title: str
    issuer: str
    notification_number: str | None
    notification_date: TemporalValue
    publication_date: TemporalValue
    commencement: TemporalValue
    commencement_basis_refs: list[EvidenceRef]
    website_upload_date: TemporalValue
    completeness: Literal["COMPLETE_TEXT", "PARTIAL_TEXT", "HTML_SHELL", "NOTICE_LEAD"]
    review_state: Literal["DRAFT", "APPROVED", "REJECTED"]


class ProvisionVersion(BoundaryModel):
    """Granular segment or rule within a reviewed source version (CONTRACTS §4.1)."""

    provision_version_id: ID
    source_version_id: ID
    parent_provision_id: ID | None
    locator: Locator
    legal_path: str
    text_blob: BlobRef
    regime: str
    role_scope: Literal["GENERAL", "SPECIFIC", "UNKNOWN"]
    affected_roles: list[Role]
    applicability_assertion_id: ID | None
    table_context_refs: list[EvidenceRef]
    review_state: Literal["DRAFT", "APPROVED", "REJECTED"]
