"""Source knowledge and regulatory lead boundary models from CONTRACTS sections 4.1 and 4.3.

Owned by Sampreeth (H01 / H07). Reviewed by A02 before freeze.
"""

from typing import Any, Literal

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


class ApplicabilityAssertion(BoundaryModel):
    """Reviewed half-open interval and event-basis for a provision (CONTRACTS §4.3).

    Stores which roles/categories the provision applies to, the temporal interval,
    the question basis (reporting period, event time, filing date), and review state.
    A missing or unverified assertion leaves applicability UNRESOLVED.
    """

    assertion_id: ID
    provision_version_id: ID
    # Half-open interval: [effective_from, effective_until)
    effective_from: TemporalValue | None = None
    effective_until: TemporalValue | None = None
    # Which temporal basis drives the interval check
    event_basis: Literal[
        "TRANSACTION_DATE", "CAPTURE_DATE", "REPORTING_PERIOD", "FILING_DATE"
    ] = "REPORTING_PERIOD"
    affected_roles: list[Role]
    scope_note: str | None = None
    reviewer: str | None = None
    review_state: Literal["DRAFT", "APPROVED", "REJECTED"] = "DRAFT"
    sources: list[EvidenceRef] = []
    metadata: dict[str, Any] = {}


class AmendmentEdge(BoundaryModel):
    """Directed amendment relationship between two provision versions (CONTRACTS §4.3).

    Relation kinds:
      AMENDS         — partial textual change
      REPLACES       — full replacement of the prior provision
      INSERTS        — new provision inserted at this point
      RELAXES_DEADLINE — extends an existing deadline (requires extension order ref)
      REFERENCES     — informational cross-reference only

    A link from the rule that *allows* extensions is not itself evidence that a
    particular extension was issued — 'RELAXES_DEADLINE' requires extension_order_refs.
    """

    edge_id: ID
    from_provision_id: ID
    to_provision_id: ID
    relation: Literal["AMENDS", "REPLACES", "INSERTS", "RELAXES_DEADLINE", "REFERENCES"]
    affected_scope: str | None = None
    applicability_assertion_id: ID | None = None
    extension_order_refs: list[EvidenceRef] = []
    review_state: Literal["DRAFT", "APPROVED", "REJECTED"] = "DRAFT"


DeadlineKind = Literal["OBLIGATION_ACHIEVEMENT", "CREDIT_EVENT", "RETURN_FILING"]


class DeadlineEntry(BoundaryModel):
    """Frozen deadline register entry with mandatory kind separation (CONTRACTS §4.3).

    OBLIGATION_ACHIEVEMENT, CREDIT_EVENT, and RETURN_FILING are independent deadlines.
    A RETURN_FILING extension cannot extend OBLIGATION_ACHIEVEMENT or CREDIT_EVENT
    without separate reviewed authority.

    Rule 9A is an enabling provision, not the extension order itself.
    A notice lead never creates a verified extension — extension_order_refs must be present
    and reviewed for extended_due to be treated as verified.
    """

    deadline_id: ID
    producer_or_role_scope: str
    fiscal_year: str
    quarter: str | None = None
    kind: DeadlineKind
    baseline_due: TemporalValue
    baseline_basis_refs: list[EvidenceRef] = []
    extended_due: TemporalValue | None = None
    extension_order_refs: list[EvidenceRef] = []
    enabling_provision_refs: list[EvidenceRef] = []
    unverified_notice: bool = False
    review_state: Literal["DRAFT", "APPROVED", "REJECTED"] = "DRAFT"
    supersedes_deadline_id: ID | None = None
