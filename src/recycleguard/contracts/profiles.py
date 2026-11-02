"""A03 executable policy subset. Actual legal content remains a reviewed H04 input."""

import hashlib
import json
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .artifacts import ProfileRef
from .core import ID, BoundaryModel, DecimalString, Digest, EvidenceRef, Nonempty


class SourceDependency(BoundaryModel):
    artifact_revision_id: ID
    blob_digest: Digest


class EligibilityRule(BoundaryModel):
    condition: Literal[
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
    testability: Literal["TESTABLE", "UNAVAILABLE"]
    missing_fact_outcome: Literal["UNRESOLVED"]
    source_refs: list[EvidenceRef] = Field(min_length=1)


class AllocationPolicy(BoundaryModel):
    priority_check: Literal["EARLIER_COMPATIBLE_AT_ALLOCATION_TIME"]
    missing_history_outcome: Literal["LIABILITY_PRIORITY_UNRESOLVED"]
    prohibited_allocation_outcome: Literal["EARLIER_LIABILITY_UNMET"]
    supported_basis: Literal["SUPPORTED_ALLOCATIONS_ONLY"]
    historical_buckets: Literal["SEPARATE"]


class EventEquivalencePolicy(BoundaryModel):
    policy_version: Nonempty
    required_exact_fields: list[
        Literal[
            "CERTIFICATE_LOT",
            "KIND_STAGE",
            "TIME_VALUE_PRECISION_TIMEZONE",
            "QUANTITY_DIMENSION_METAL",
            "FROM_TO_PARTIES",
        ]
    ]
    corroboration: Literal["EXTERNAL_ID_OR_COMPLETE_KEY_WITH_SOURCE_CONTINUITY"]
    missing_or_conflicting_outcome: Literal["PENDING"]
    coarse_time_collision_outcome: Literal["PENDING"]

    @model_validator(mode="after")
    def complete_key(self):
        required = {
            "CERTIFICATE_LOT",
            "KIND_STAGE",
            "TIME_VALUE_PRECISION_TIMEZONE",
            "QUANTITY_DIMENSION_METAL",
            "FROM_TO_PARTIES",
        }
        if set(self.required_exact_fields) != required or len(self.required_exact_fields) != 5:
            raise ValueError("event equivalence requires every exact field once")
        return self


class PurchaseCeilingPolicy(BoundaryModel):
    state: Literal["DISABLED_REVIEW_REQUIRED", "APPROVED"]
    source_refs: list[EvidenceRef]
    applicability_refs: list[EvidenceRef]
    current_liability_basis: Nonempty | None
    prior_liability_basis: Nonempty | None
    buffer_rate: DecimalString | None
    review_ref: ID | None

    @model_validator(mode="after")
    def reviewed_only(self):
        if self.state == "APPROVED" and (
            not self.source_refs
            or not self.applicability_refs
            or self.review_ref is None
            or self.current_liability_basis is None
            or self.prior_liability_basis is None
            or self.buffer_rate is None
        ):
            raise ValueError("approved ceiling requires sources, applicability, bases and review")
        if self.buffer_rate is not None and not Decimal("0") <= Decimal(self.buffer_rate) <= 1:
            raise ValueError("buffer_rate must be a fraction between zero and one")
        return self


class NumericPolicy(BoundaryModel):
    precision: Literal[28]
    display_places: Literal[4]
    rounding: Literal["ROUND_HALF_EVEN"]
    trap_inexact: Literal[True]
    trap_overflow: Literal[True]
    rounding_stage: Literal["FINAL_DISPLAY_ONLY"]


class ProfileDefinition(BoundaryModel):
    supported_regime: Literal["EWASTE_EPR_SUPPLIED_TARGETS"]
    target_basis: Literal["SUPPLIED_METAL_WISE_OBLIGATIONS"]
    supported_components: list[Literal["SUPPORTED_ALLOCATIONS", "HISTORICAL_LIABILITIES"]]
    allowed_metals: list[Literal["AU", "CU", "AL", "FE"]] = Field(min_length=1)
    category_scope: list[Nonempty] = Field(min_length=1, max_length=2)
    applicability_assertion_refs: list[EvidenceRef] = Field(min_length=1)
    eligibility_rules: list[EligibilityRule]
    allocation_policy: AllocationPolicy
    event_equivalence_policy: EventEquivalencePolicy
    purchase_ceiling_policy: PurchaseCeilingPolicy
    numeric_policy: NumericPolicy
    unsupported_features: list[
        Literal[
            "GOLD_OFFSETS",
            "REFURBISHING_DEFERRALS",
            "SALES_DERIVED_TARGETS",
            "TAX_PRICING",
            "SOLAR",
            "ENVIRONMENTAL_COMPENSATION",
        ]
    ]
    source_dependencies: list[SourceDependency] = Field(min_length=1)

    @model_validator(mode="after")
    def explicit_scope(self):
        required = {
            "ENTITY",
            "PERIOD",
            "METAL",
            "CATEGORY",
            "LIFECYCLE",
            "CAPABILITY",
            "REGISTRATION",
            "ACHIEVEMENT_DEADLINE",
            "CREDIT_EVENT_DEADLINE",
        }
        conditions = [rule.condition for rule in self.eligibility_rules]
        if set(conditions) != required or len(conditions) != len(required):
            raise ValueError("declare testability for every eligibility condition exactly once")
        if set(self.supported_components) != {"SUPPORTED_ALLOCATIONS", "HISTORICAL_LIABILITIES"}:
            raise ValueError("declare supported allocations and separate historical liabilities")
        if len(self.unsupported_features) != 6 or len(set(self.unsupported_features)) != 6:
            raise ValueError("declare all six unsupported feature groups")
        for values in (self.allowed_metals, self.category_scope, self.supported_components):
            if len(values) != len(set(values)):
                raise ValueError("duplicate scope entry")
        ids = [dep.artifact_revision_id for dep in self.source_dependencies]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate source dependency")
        return self


class CalculationProfile(ProfileDefinition):
    profile_id: ID
    profile_version: Nonempty
    review_state: Literal["DRAFT", "APPROVED", "REJECTED"]
    review_refs: list[ID]
    digest: Digest

    @model_validator(mode="after")
    def exact_digest(self):
        if self.digest != profile_digest(self.model_dump(mode="json", exclude={"digest"})):
            raise ValueError("profile digest does not match exact revision")
        if (self.review_state == "DRAFT") != (not self.review_refs):
            raise ValueError("only reviewed revisions carry review references")
        return self


def profile_digest(payload: dict) -> str:
    data = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class ProfilePublication(BoundaryModel):
    profile_id: ID
    profile_version: Nonempty
    expected_head: ProfileRef | None
    definition: ProfileDefinition


class ProfileReview(BoundaryModel):
    target: ProfileRef
    new_profile_version: Nonempty
    decision: Literal["APPROVE", "REJECT"]
    reason: Nonempty

    @model_validator(mode="after")
    def new_revision(self):
        if self.target.profile_version == self.new_profile_version:
            raise ValueError("review must create a new profile revision")
        return self
