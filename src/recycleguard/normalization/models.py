"""Normalization boundary models conforming to CONTRACTS v1.1 §3.4 and §7."""

from typing import Literal

from pydantic import Field

from recycleguard.contracts.core import ID, BoundaryModel, Issue
from recycleguard.contracts.domain import NormalizedRecord

ObservationDispositionKind = Literal[
    "ACCEPTED", "QUARANTINED", "EXCLUDED", "OUT_OF_SCOPE"
]
EquivalenceBasis = Literal[
    "AUTHORITATIVE_EVENT_ID", "EXACT_COMPOUND_KEY_AND_CORROBORATION"
]
EquivalenceAssertionState = Literal["SUPPORTED", "PENDING", "CONFLICTING"]
ReviewState = Literal["DRAFT", "APPROVED", "REJECTED"]


class ObservationDisposition(BoundaryModel):
    """Disposition of an individual raw observation following normalization."""

    observation_id: ID
    disposition: ObservationDispositionKind
    reason: str
    derived_record_ids: list[ID] = Field(default_factory=list)


class EventEquivalence(BoundaryModel):
    """Explicit mapping linking multiple raw observations to one resolved event."""

    equivalence_id: ID
    certificate_id: ID
    resolved_event_id: ID
    observation_ids: list[ID]
    matching_basis: EquivalenceBasis
    assertion_state: EquivalenceAssertionState
    review_state: ReviewState = "APPROVED"


class NormalizationBatch(BoundaryModel):
    """Container envelope for all normalized domain records from a case."""

    batch_id: ID
    case_id: ID
    records: list[NormalizedRecord]
    dispositions: list[ObservationDisposition]
    equivalences: list[EventEquivalence] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    mapping_version: str = "1.0"
