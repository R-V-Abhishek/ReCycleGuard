"""Canonical calculation profile producer_snapshot_v1 with internal review.

Owned by Sampreeth (H04 / C05 / C07).
Specifies the authoritative profile definition for CP1:
- Supported regime: EWASTE_EPR_SUPPLIED_TARGETS
- Target basis: SUPPLIED_METAL_WISE_OBLIGATIONS
- Supported components: SUPPORTED_ALLOCATIONS, HISTORICAL_LIABILITIES
- Allowed metals: AU, CU, AL, FE
- Category scope: ITEW4, CEEW1
- Strict priority check: EARLIER_COMPATIBLE_AT_ALLOCATION_TIME
- Event equivalence policy requiring all 5 exact fields
- Purchase ceiling policy: DISABLED_REVIEW_REQUIRED
- Pinned source dependencies to reviewed R02 and R08 revisions
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from recycleguard.contracts.artifacts import ArtifactRevision, ProfileRef
from recycleguard.contracts.core import EvidenceRef, Locator
from recycleguard.contracts.profiles import (
    AllocationPolicy,
    CalculationProfile,
    EligibilityRule,
    EventEquivalencePolicy,
    NumericPolicy,
    ProfileDefinition,
    ProfilePublication,
    ProfileReview,
    PurchaseCeilingPolicy,
    SourceDependency,
    profile_digest,
)
from recycleguard.knowledge.provisions import R02_ARTIFACT_REV_ID, R08_ARTIFACT_REV_ID

if TYPE_CHECKING:
    from recycleguard.case_service import CaseService
    from recycleguard.contracts.core import CommandContext
    from recycleguard.profiles import ProfileStore
    from recycleguard.storage.authority import Capability


def build_v1_profile_definition(
    r02_revision: ArtifactRevision,
    r08_revision: ArtifactRevision,
) -> ProfileDefinition:
    """Build the reviewed ProfileDefinition for producer_snapshot_v1."""
    # Evidence refs to reviewed provisions
    r02_ref = EvidenceRef(
        ref_kind="PROVISION",
        ref_id="provision:r02_rule15_sub1_sub3",
        artifact_revision_id=r02_revision.artifact_revision_id,
        locator=Locator(
            kind="PDF_PAGE",
            page_index_1based=14,
            printed_page_label="14",
            row_index_1based=None,
            column_name=None,
            json_pointer=None,
            text_start=None,
            text_end=None,
            table_id=None,
            cell_row=None,
            cell_column=None,
        ),
    )

    r08_ref = EvidenceRef(
        ref_kind="PROVISION",
        ref_id="provision:r08_sec_c_recycler_capability",
        artifact_revision_id=r08_revision.artifact_revision_id,
        locator=Locator(
            kind="PDF_PAGE",
            page_index_1based=9,
            printed_page_label="9",
            row_index_1based=None,
            column_name=None,
            json_pointer=None,
            text_start=None,
            text_end=None,
            table_id=None,
            cell_row=None,
            cell_column=None,
        ),
    )

    eligibility_conditions = [
        "ENTITY",
        "PERIOD",
        "METAL",
        "CATEGORY",
        "LIFECYCLE",
        "CAPABILITY",
        "REGISTRATION",
        "ACHIEVEMENT_DEADLINE",
        "CREDIT_EVENT_DEADLINE",
    ]

    eligibility_rules = [
        EligibilityRule(
            condition=cond,
            testability="TESTABLE",
            missing_fact_outcome="UNRESOLVED",
            source_refs=[r02_ref if cond != "CAPABILITY" else r08_ref],
        )
        for cond in eligibility_conditions
    ]

    return ProfileDefinition(
        supported_regime="EWASTE_EPR_SUPPLIED_TARGETS",
        target_basis="SUPPLIED_METAL_WISE_OBLIGATIONS",
        supported_components=["SUPPORTED_ALLOCATIONS", "HISTORICAL_LIABILITIES"],
        allowed_metals=["AU", "CU", "AL", "FE"],
        category_scope=["ITEW4", "CEEW1"],
        applicability_assertion_refs=[r02_ref, r08_ref],
        eligibility_rules=eligibility_rules,
        allocation_policy=AllocationPolicy(
            priority_check="EARLIER_COMPATIBLE_AT_ALLOCATION_TIME",
            missing_history_outcome="LIABILITY_PRIORITY_UNRESOLVED",
            prohibited_allocation_outcome="EARLIER_LIABILITY_UNMET",
            supported_basis="SUPPORTED_ALLOCATIONS_ONLY",
            historical_buckets="SEPARATE",
        ),
        event_equivalence_policy=EventEquivalencePolicy(
            policy_version="1.0",
            required_exact_fields=[
                "CERTIFICATE_LOT",
                "KIND_STAGE",
                "TIME_VALUE_PRECISION_TIMEZONE",
                "QUANTITY_DIMENSION_METAL",
                "FROM_TO_PARTIES",
            ],
            corroboration="EXTERNAL_ID_OR_COMPLETE_KEY_WITH_SOURCE_CONTINUITY",
            missing_or_conflicting_outcome="PENDING",
            coarse_time_collision_outcome="PENDING",
        ),
        purchase_ceiling_policy=PurchaseCeilingPolicy(
            state="DISABLED_REVIEW_REQUIRED",
            source_refs=[r02_ref],
            applicability_refs=[r02_ref],
            current_liability_basis=None,
            prior_liability_basis=None,
            buffer_rate=None,
            review_ref=None,
        ),
        numeric_policy=NumericPolicy(
            precision=28,
            display_places=4,
            rounding="ROUND_HALF_EVEN",
            trap_inexact=True,
            trap_overflow=True,
            rounding_stage="FINAL_DISPLAY_ONLY",
        ),
        unsupported_features=[
            "GOLD_OFFSETS",
            "REFURBISHING_DEFERRALS",
            "SALES_DERIVED_TARGETS",
            "TAX_PRICING",
            "SOLAR",
            "ENVIRONMENTAL_COMPENSATION",
        ],
        source_dependencies=[
            SourceDependency(
                artifact_revision_id=r02_revision.artifact_revision_id,
                blob_digest=r02_revision.blob.sha256,
            ),
            SourceDependency(
                artifact_revision_id=r08_revision.artifact_revision_id,
                blob_digest=r08_revision.blob.sha256,
            ),
        ],
    )


def build_v1_calculation_profile(
    r02_revision: ArtifactRevision,
    r08_revision: ArtifactRevision,
    *,
    review_state: str = "APPROVED",
    review_refs: list[str] | None = None,
) -> CalculationProfile:
    """Construct complete CalculationProfile with exact digest matching CONTRACTS."""
    defn = build_v1_profile_definition(r02_revision, r08_revision)
    refs = review_refs if review_refs is not None else (
        ["review:h04_initial_source_review"] if review_state != "DRAFT" else []
    )

    payload = defn.model_dump(mode="json")
    payload["profile_id"] = "profile:producer_snapshot_v1"
    payload["profile_version"] = "1.0"
    payload["review_state"] = review_state
    payload["review_refs"] = refs

    digest = profile_digest(payload)
    payload["digest"] = digest

    return CalculationProfile.model_validate(payload)
