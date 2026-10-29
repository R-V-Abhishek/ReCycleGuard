"""H08: Final corpus/profile audit and retrieval regression scaffolding.

Owned by Sampreeth (H08).

Produces a machine-readable manifest of:
- Active corpus sources and their exact SHA-256 digests, physical page locators,
  index manifest digests and rights metadata.
- Active calculation profile (producer_snapshot_v1) metal-bucket mapping,
  purchase-ceiling policy state, and dependency hashes.
- Explicit recorded limitations including unreviewed provisions, missing extension
  orders, disabled purchase ceilings, notice leads without signed orders, and
  external redistribution disclaimers.

No invented legal opinions, no semantic LLM grades (C10 is TEST_DOUBLE only).
Temporal applicability for individual provisions remains UNRESOLVED at this stage.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from recycleguard.contracts.core import BoundaryModel, Digest

# ──────────────────────────────────────────────────────────────────────────────
# Audit record models
# ──────────────────────────────────────────────────────────────────────────────


class SourceAuditRecord(BoundaryModel):
    """Pinned digest and locator record for a single active corpus source."""

    artifact_revision_id: str
    source_alias: str
    document_title: str
    source_kind: Literal["GAZETTE", "OFFICIAL_GUIDANCE"]
    source_url: str
    sha256_digest: Digest
    total_pages: int
    active_physical_pages: list[int]
    active_provision_ids: list[str]
    access_policy_id: str
    rights_decision_id: str
    copyright_owner: str
    statutory_exception: str
    redistribution_allowed: bool
    review_state: Literal["DRAFT", "APPROVED", "REJECTED"]
    review_note: str


class IndexAuditRecord(BoundaryModel):
    """Pinned index manifest digest for the active lexical index."""

    index_id: str
    corpus_snapshot_id: str
    corpus_membership_digest: Digest | None
    index_integrity_digest: Digest
    tokenizer: str
    bm25_k1: float
    bm25_b: float
    total_chunks: int
    build_code_revision: str


class ProfileAuditRecord(BoundaryModel):
    """Pinned digest and policy summary for the active calculation profile."""

    profile_id: str
    profile_version: str
    profile_digest: Digest
    review_state: Literal["DRAFT", "APPROVED", "REJECTED"]
    supported_regime: str
    target_basis: str
    allowed_metals: list[str]
    category_scope: list[str]
    priority_check: str
    purchase_ceiling_state: str
    purchase_ceiling_note: str
    unsupported_features: list[str]
    source_dependency_digests: list[dict[str, str]]


class AuditLimitation(BoundaryModel):
    """Explicit recorded limitation for handoff documentation."""

    limitation_id: str
    kind: Literal[
        "UNREVIEWED_PROVISION",
        "MISSING_EXTENSION_ORDER",
        "DISABLED_PURCHASE_CEILING",
        "NOTICE_LEAD_NO_ORDER",
        "REDISTRIBUTION_RESTRICTED",
        "TEMPORAL_APPLICABILITY_UNRESOLVED",
        "SEMANTIC_GRADE_UNRESOLVED",
        "UNSUPPORTED_FEATURE",
    ]
    scope: str
    description: str
    effect_on_retrieval: str


class CorpusProfileAuditManifest(BoundaryModel):
    """Complete H08 handoff manifest for CP4 integration.

    Summarises the exact state of the corpus, index and profile as entered into
    CP3. All fields are derived from pinned source constants; none are inferred
    from live network calls or LLM outputs.
    """

    manifest_id: str = "manifest:h08_corpus_profile_audit_v1"
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    owner: str = "Sampreeth (H08)"
    task_ref: str = "H08"
    checkpoint_ref: str = "checkpoint-3"
    sources: list[SourceAuditRecord]
    index: IndexAuditRecord | None = None
    profile: ProfileAuditRecord
    limitations: list[AuditLimitation]
    retrieval_engine_note: str = (
        "FTS5 SQLite BM25 lexical index. Semantic grades remain UNRESOLVED "
        "(C10 is TEST_DOUBLE; no live model provider selected)."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Static corpus constants (from provisions.py / profile_v1.py)
# ──────────────────────────────────────────────────────────────────────────────

_R02_REV_ID = "artifact_rev:r02_rules_2022_official_pdf"
_R08_REV_ID = "artifact_rev:cpcb_faq_20240123_pdf"

_SOURCE_DIGESTS: dict[str, str] = {
    _R02_REV_ID: ("d03f8744bc79d67a94b06e1020537e93d15572b0cf1d575cb32b76c89f30a5fb"),
    _R08_REV_ID: ("30f56238fb7db53dd82f69d198be9a92e31d98ea5b21d2724eb7397641a80d16"),
}

_SOURCE_PAGES: dict[str, int] = {_R02_REV_ID: 38, _R08_REV_ID: 13}

_ACTIVE_PAGES: dict[str, list[int]] = {
    _R02_REV_ID: [24, 27],
    _R08_REV_ID: [9],
}

_ACTIVE_PROVISIONS: dict[str, list[str]] = {
    _R02_REV_ID: [
        "provision:r02_rule6_sub4",
        "provision:r02_rule15_sub1_sub3",
    ],
    _R08_REV_ID: ["provision:r08_sec_c_recycler_capability"],
}


# ──────────────────────────────────────────────────────────────────────────────
# Audit functions
# ──────────────────────────────────────────────────────────────────────────────


def audit_corpus_sources() -> list[SourceAuditRecord]:
    """Return pinned source audit records for the two active corpus sources.

    Does NOT require live PDF bytes; the digests are the pinned originals.
    Call register_reviewed_sources() separately to verify actual file bytes.
    """
    return [
        SourceAuditRecord(
            artifact_revision_id=_R02_REV_ID,
            source_alias="R02",
            document_title=(
                "E-Waste (Management) Rules 2022 — Official Gazette, "
                "Ministry of Environment, Forest and Climate Change"
            ),
            source_kind="GAZETTE",
            source_url=("https://eprewaste.cpcb.gov.in/assets/PDF/e-waste_rules_2022.pdf"),
            sha256_digest=_SOURCE_DIGESTS[_R02_REV_ID],
            total_pages=_SOURCE_PAGES[_R02_REV_ID],
            active_physical_pages=_ACTIVE_PAGES[_R02_REV_ID],
            active_provision_ids=_ACTIVE_PROVISIONS[_R02_REV_ID],
            access_policy_id="policy:local_source_review",
            rights_decision_id="decision:review_required",
            copyright_owner="Government of India (Crown/India copyright)",
            statutory_exception=(
                "Section 52(1)(q) Copyright Act 1957 — reproduction for compliance review"
            ),
            redistribution_allowed=False,
            review_state="DRAFT",
            review_note=(
                "Physical page context reviewed for pages 24 and 27 only. "
                "Remaining 36 pages are not individually reviewed. "
                "External redistribution restricted; local compliance use only."
            ),
        ),
        SourceAuditRecord(
            artifact_revision_id=_R08_REV_ID,
            source_alias="R08",
            document_title=(
                "CPCB FAQ on E-Waste (Management) Rules 2022 — Guidance for Producers, January 2024"
            ),
            source_kind="OFFICIAL_GUIDANCE",
            source_url=("https://eprewaste.cpcb.gov.in/assets/PDF/faqewaste.pdf"),
            sha256_digest=_SOURCE_DIGESTS[_R08_REV_ID],
            total_pages=_SOURCE_PAGES[_R08_REV_ID],
            active_physical_pages=_ACTIVE_PAGES[_R08_REV_ID],
            active_provision_ids=_ACTIVE_PROVISIONS[_R08_REV_ID],
            access_policy_id="policy:local_source_review",
            rights_decision_id="decision:review_required",
            copyright_owner="Government of India / CPCB (Crown/India copyright)",
            statutory_exception=(
                "Section 52(1)(q) Copyright Act 1957 — reproduction for compliance review"
            ),
            redistribution_allowed=False,
            review_state="DRAFT",
            review_note=(
                "Physical page 9 reviewed for Section C (EEE capability). "
                "FAQ status is official guidance, not a statute; "
                "it cannot override Rule text. "
                "External redistribution restricted; local compliance use only."
            ),
        ),
    ]


def audit_profile(profile_payload: dict) -> ProfileAuditRecord:
    """Derive a ProfileAuditRecord from a serialised CalculationProfile payload.

    Args:
        profile_payload: ``CalculationProfile.model_dump(mode="json")``.

    Returns:
        Pinned ProfileAuditRecord capturing digest, policy state and limitations.
    """
    dep_digests = [
        {
            "artifact_revision_id": dep["artifact_revision_id"],
            "blob_digest": dep["blob_digest"],
        }
        for dep in profile_payload.get("source_dependencies", [])
    ]
    return ProfileAuditRecord(
        profile_id=profile_payload["profile_id"],
        profile_version=profile_payload["profile_version"],
        profile_digest=profile_payload["digest"],
        review_state=profile_payload["review_state"],
        supported_regime=profile_payload["supported_regime"],
        target_basis=profile_payload["target_basis"],
        allowed_metals=profile_payload["allowed_metals"],
        category_scope=profile_payload["category_scope"],
        priority_check=profile_payload["allocation_policy"]["priority_check"],
        purchase_ceiling_state=profile_payload["purchase_ceiling_policy"]["state"],
        purchase_ceiling_note=(
            "DISABLED_REVIEW_REQUIRED: Rule 15 purchase ceiling is not "
            "yet applied. A separate reviewed ProfileReview decision "
            "with signed authority is required before it can be enabled."
        ),
        unsupported_features=profile_payload["unsupported_features"],
        source_dependency_digests=dep_digests,
    )


def build_audit_limitations() -> list[AuditLimitation]:
    """Return the explicit recorded limitation set for H08 handoff."""
    return [
        AuditLimitation(
            limitation_id="limit:h08_01_provision_review",
            kind="UNREVIEWED_PROVISION",
            scope="R02 pages 1-23, 25-26, 28-38; R08 pages 1-8, 10-13",
            description=(
                "Only R02 pages 24, 27 and R08 page 9 were individually reviewed. "
                "Remaining pages are captured but not individually reviewed. "
                "No conclusions are drawn from unreviewed pages."
            ),
            effect_on_retrieval=(
                "Retrieval candidates from unreviewed page ranges carry "
                "review_state=DRAFT; authority grade remains UNRESOLVED unless "
                "the source_class qualifies under the deterministic rule."
            ),
        ),
        AuditLimitation(
            limitation_id="limit:h08_02_extension_order",
            kind="MISSING_EXTENSION_ORDER",
            scope="Rule 9A enabling provision; FY 2024-25 RETURN_FILING deadline",
            description=(
                "Rule 9A is an enabling provision permitting deadline extensions. "
                "No signed, reviewed extension order has been captured. "
                "A notice lead or press report cannot substitute for the issued order."
            ),
            effect_on_retrieval=(
                "DeadlineRegister returns ABSTAIN (fallback to baseline_due) "
                "when unverified_notice=True or extension_order_refs is empty. "
                "F12 (UNSEEN_NOTICE_LEAD) fault family is covered by tests."
            ),
        ),
        AuditLimitation(
            limitation_id="limit:h08_03_purchase_ceiling",
            kind="DISABLED_PURCHASE_CEILING",
            scope="producer_snapshot_v1 PurchaseCeilingPolicy",
            description=(
                "The purchase ceiling (Rule 15) policy state is "
                "DISABLED_REVIEW_REQUIRED. No approved ceiling parameters "
                "(current_liability_basis, prior_liability_basis, buffer_rate) "
                "are present. A separate ProfileReview decision with signed "
                "authority is required to enable it."
            ),
            effect_on_retrieval=(
                "Calculation profiles built from producer_snapshot_v1 cannot "
                "enforce purchase ceilings. This is an explicit gap, not a silent omission."
            ),
        ),
        AuditLimitation(
            limitation_id="limit:h08_04_redistribution",
            kind="REDISTRIBUTION_RESTRICTED",
            scope="R02, R08 — all derived corpus chunks",
            description=(
                "Both sources carry Crown/India copyright. "
                "Redistribution is restricted. Only local compliance-review "
                "use is permitted under Section 52(1)(q) Copyright Act 1957. "
                "Publication bundles must omit original PDF bytes and full page text."
            ),
            effect_on_retrieval=(
                "Export bundles must apply rights filters before distribution. "
                "Corpus chunks are stored as BlobRefs; original bytes are "
                "never embedded directly in exported JSON."
            ),
        ),
        AuditLimitation(
            limitation_id="limit:h08_05_temporal_applicability",
            kind="TEMPORAL_APPLICABILITY_UNRESOLVED",
            scope="All three active provisions",
            description=(
                "ApplicabilityAssertions remain in DRAFT review_state for all "
                "three provisions. Effective intervals (effective_from, "
                "effective_until) are not populated with reviewed dates. "
                "Temporal applicability checks therefore return UNRESOLVED."
            ),
            effect_on_retrieval=(
                "All grading_assessments will show temporal_fit=UNRESOLVED "
                "until assertions are reviewed and approved. "
                "F11 (WRONG_PERIOD_RULE) tests verify the UNRESOLVED path."
            ),
        ),
        AuditLimitation(
            limitation_id="limit:h08_06_semantic_grade",
            kind="SEMANTIC_GRADE_UNRESOLVED",
            scope="direct_support, contradiction grades for all candidates",
            description=(
                "Semantic support and contradiction grades require a live "
                "C10 gateway. The current integration uses a TEST_DOUBLE "
                "that stores model_backend=TEST_DOUBLE and returns "
                "predetermined proposals. No actual model provider has been "
                "selected or activated."
            ),
            effect_on_retrieval=(
                "direct_support=UNRESOLVED and contradiction=UNRESOLVED for "
                "all candidates. Retrieval results are suitable for lexical "
                "regression testing but not for production claim grading."
            ),
        ),
        AuditLimitation(
            limitation_id="limit:h08_07_gold_offset",
            kind="UNSUPPORTED_FEATURE",
            scope="GOLD_OFFSETS, REFURBISHING_DEFERRALS, SALES_DERIVED_TARGETS",
            description=(
                "Gold-offset refurbishing, sales-derived targets, environmental "
                "compensation, tax/pricing and solar features are explicitly "
                "unsupported in producer_snapshot_v1. "
                "F14 (OUT_OF_SCOPE_REGIME) test verifies explicit abstention."
            ),
            effect_on_retrieval=(
                "Queries about gold offsets, refurbishing deferrals or solar "
                "regimes must be withheld or marked F14_DISPOSITION. "
                "No calculation output is produced for these regimes."
            ),
        ),
    ]


def build_index_audit_record(manifest_payload: dict) -> IndexAuditRecord:
    """Derive an IndexAuditRecord from a serialised IndexManifest payload."""
    lex = manifest_payload.get("lexical_configuration", {})
    return IndexAuditRecord(
        index_id=manifest_payload["index_id"],
        corpus_snapshot_id=manifest_payload["corpus_snapshot_id"],
        corpus_membership_digest=manifest_payload.get("corpus_membership_digest"),
        index_integrity_digest=manifest_payload["integrity_digest"],
        tokenizer=lex.get("tokenizer", "unicode61"),
        bm25_k1=lex.get("bm25_k1", 1.2),
        bm25_b=lex.get("bm25_b", 0.75),
        total_chunks=manifest_payload.get("total_chunks", 0),
        build_code_revision=manifest_payload.get("build_code_revision", "unknown"),
    )


def build_corpus_profile_audit_manifest(
    *,
    profile_payload: dict,
    index_manifest_payload: dict | None = None,
) -> CorpusProfileAuditManifest:
    """Assemble a complete H08 audit manifest.

    Args:
        profile_payload: ``CalculationProfile.model_dump(mode="json")``.
        index_manifest_payload: Optional ``IndexManifest.model_dump(mode="json")``.
            Omit when auditing in isolation (no live index required).

    Returns:
        CorpusProfileAuditManifest ready for documentation and handoff.
    """
    sources = audit_corpus_sources()
    profile = audit_profile(profile_payload)
    limitations = build_audit_limitations()
    index = build_index_audit_record(index_manifest_payload) if index_manifest_payload else None
    return CorpusProfileAuditManifest(
        sources=sources,
        index=index,
        profile=profile,
        limitations=limitations,
    )


def verify_source_digest(artifact_revision_id: str, pdf_bytes: bytes) -> bool:
    """Verify that supplied PDF bytes match the pinned SHA-256 digest.

    Returns True if the digest matches; False if it differs.
    Raises KeyError if the revision ID is unknown.
    """
    expected = _SOURCE_DIGESTS[artifact_revision_id]
    actual = hashlib.sha256(pdf_bytes).hexdigest()
    return actual == expected
