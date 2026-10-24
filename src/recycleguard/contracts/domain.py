"""CP0 normalized record boundaries; validators do not implement C04/C08 services."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, model_validator

from .core import ID, BoundaryModel, EvidenceRef, Nonempty, Quantity, TemporalValue
from .extraction import ValidationState
from .sources import Role

Metal = Literal["AU", "CU", "AL", "FE"]
ReviewState = Literal["DRAFT", "APPROVED", "REJECTED"]
FiscalYear = Annotated[str, Field(pattern=r"^\d{4}-\d{4}$")]


class ReviewedInterval(BoundaryModel):
    start: date | None
    end: date | None
    end_open_ended: bool
    review_state: ReviewState
    applicability_scope: Literal["GENERAL", "SPECIFIC", "UNKNOWN"]
    evidence_refs: list[EvidenceRef]

    @model_validator(mode="after")
    def ordered(self):
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError("interval must be nonempty and half-open")
        if self.end_open_ended and self.end is not None:
            raise ValueError("open-ended interval cannot assert an end")
        return self


class Identifier(BoundaryModel):
    kind: Literal["GSTIN", "PAN", "CIN", "IEC", "PROJECT_ID", "OTHER"]
    value: Nonempty
    validation_state: ValidationState
    evidence_refs: list[EvidenceRef]


class DatedAlias(BoundaryModel):
    alias: Nonempty
    interval: ReviewedInterval
    evidence_refs: list[EvidenceRef]


class NormalizedRecord(BoundaryModel):
    record_id: ID
    record_revision_id: ID
    case_id: ID
    observation_refs: list[ID]
    derived_from_record_refs: list[ID]
    validation_state: ValidationState
    created_by_operation_id: ID
    supersedes_revision_id: ID | None

    @model_validator(mode="after")
    def provenance_required(self):
        if not self.observation_refs and not self.derived_from_record_refs:
            raise ValueError("record requires source observations or derivation inputs")
        return self


class Entity(NormalizedRecord):
    record_type: Literal["Entity"]
    entity_id: ID
    legal_name: Nonempty
    roles: list[Role]
    identifiers: list[Identifier]
    synthetic: bool
    aliases: list[DatedAlias] = Field(default_factory=list)


class Registration(NormalizedRecord):
    record_type: Literal["Registration"]
    entity_id: ID
    registration_ref: Nonempty
    validity: ReviewedInterval
    covered_eee_codes: list[str]
    status_assertion: str
    evidence_as_of: TemporalValue
    facility_id: ID | None = None
    capacity: Quantity | None = None
    consent_refs: list[EvidenceRef] = Field(default_factory=list)


class NonnegativeMass(Quantity):
    @model_validator(mode="after")
    def mass(self):
        if self.dimension != "METAL_MASS" or Decimal(self.decimal) < 0:
            raise ValueError("requires nonnegative metal mass")
        return self


class SignedAdjustment(BoundaryModel):
    adjustment_id: ID
    quantity: Quantity
    basis_refs: list[EvidenceRef]
    review_ref: ID


class ObligationBucket(NormalizedRecord):
    record_type: Literal["ObligationBucket"]
    bucket_id: ID
    producer_entity_id: ID
    liability_year: FiscalYear
    component: Nonempty
    metal: Metal
    target: NonnegativeMass
    basis: Literal["SUPPLIED_ACCOUNT", "REVIEWED_CALCULATION"]
    basis_refs: list[EvidenceRef]
    profile_id: ID
    adjustments: list[SignedAdjustment] = Field(default_factory=list)

    @model_validator(mode="after")
    def bucket_metal(self):
        if self.target.metal != self.metal:
            raise ValueError("target metal does not match bucket")
        start, end = map(int, self.liability_year.split("-"))
        if end != start + 1:
            raise ValueError("liability year must span consecutive years")
        return self


class Certificate(NormalizedRecord):
    record_type: Literal["Certificate"]
    certificate_id: ID
    external_certificate_ref: Nonempty
    issuer_entity_id: ID
    metal: Metal
    face_quantity: NonnegativeMass
    identity_evidence: list[EvidenceRef]
    generation_time: TemporalValue | None = None
    expiry_time: TemporalValue | None = None
    raw_status: str | None = None

    @model_validator(mode="after")
    def certificate_metal(self):
        if self.face_quantity.metal != self.metal:
            raise ValueError("face quantity metal does not match certificate")
        return self


class CertificateEvent(NormalizedRecord):
    record_type: Literal["CertificateEvent"]
    event_id: ID
    certificate_id: ID
    credit_lot_id: ID | None
    event_kind: Literal[
        "GENERATED", "TRANSFERRED", "ADJUSTED", "EXPIRED", "CANCELLED", "STATUS_OBSERVED"
    ]
    event_time: TemporalValue
    quantity: NonnegativeMass
    assertion_state: Literal["SUPPORTED", "PENDING", "CONFLICTING"]
    supporting_observations: list[ID]
    external_event_ref: str | None = None
    from_entity_id: ID | None = None
    to_entity_id: ID | None = None
    equivalence_assertion_id: ID | None = None
    transfer_stage: (
        Literal[
            "NOT_OBSERVED",
            "INITIATED",
            "OTP_INITIATED",
            "PUBLIC_KEY_DISPATCHED",
            "COMPLETED",
            "UNKNOWN",
        ]
        | None
    ) = None
    transfer_stage_mapping_ref: ID | None = None

    @model_validator(mode="after")
    def supported_transfer(self):
        if self.assertion_state == "SUPPORTED" and self.event_kind == "TRANSFERRED":
            if self.transfer_stage not in {None, "COMPLETED"}:
                raise ValueError("intermediate transfer stage cannot establish supported transfer")
        return self


class Allocation(NormalizedRecord):
    record_type: Literal["Allocation"]
    allocation_id: ID
    credit_lot_id: ID
    event_id: ID
    bucket_id: ID
    quantity: NonnegativeMass
    basis_refs: list[EvidenceRef]
    state: Literal["SUPPORTED", "PENDING", "REJECTED"]
    profile_id: ID
    supersedes_allocation_id: ID | None = None


class AccountBalanceObservation(NormalizedRecord):
    record_type: Literal["AccountBalanceObservation"]
    balance_observation_id: ID
    producer_entity_id: ID
    bucket_id: ID
    reported_supported: NonnegativeMass
    source_capture_time: TemporalValue
    business_cutoff: TemporalValue
    basis_refs: list[EvidenceRef]
    reported_pending: NonnegativeMass | None = None


class CommercialRecord(NormalizedRecord):
    record_type: Literal["CommercialRecord"]
    commercial_id: ID
    record_kind: Literal["CONTRACT", "PO", "INVOICE", "PAYMENT"]
    issuer_entity_id: ID
    recipient_entity_id: ID
    external_ref: Nonempty
    event_time: TemporalValue
    linked_credit_refs: list[ID]
    money: Quantity | None = None
    credit_quantity: NonnegativeMass | None = None

    @model_validator(mode="after")
    def money_dimension(self):
        if self.money is not None and self.money.dimension != "MONEY":
            raise ValueError("commercial money requires MONEY dimension")
        return self


class CreditLot(BoundaryModel):
    credit_lot_id: ID
    certificate_id: ID
    supported_capacity: NonnegativeMass
    supporting_refs: list[EvidenceRef]
    resolution_state: Literal["SUPPORTED", "PENDING", "CONFLICTING"]


Record = Annotated[
    Entity
    | Registration
    | ObligationBucket
    | Certificate
    | CertificateEvent
    | Allocation
    | AccountBalanceObservation
    | CommercialRecord,
    Field(discriminator="record_type"),
]
RECORD_ADAPTER = TypeAdapter(Record)
