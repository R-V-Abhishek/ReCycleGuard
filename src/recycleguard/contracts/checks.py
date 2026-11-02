"""C08 structured check results (CONTRACTS section 12 StructuredCheckResult)."""

from typing import Literal

from pydantic import model_validator

from .core import ID, BlobRef, BoundaryModel, Digest, EvidenceRef, Issue, Nonempty

CheckKind = Literal[
    "COMPARE_IDENTITY",
    "LOOKUP_REGISTRATION_EVIDENCE",
    "CHECK_CAPABILITY",
    "LOOKUP_PRODUCT_MAPPING",
    "COMPARE_WEIGHT_BASIS",
    "AGGREGATE_SALES",
    "GET_CERTIFICATE_HISTORY",
    "CHECK_CREDIT_EVENTS",
    "MATCH_TRANSACTIONS",
]
Verdict = Literal["PASS", "FAIL", "UNKNOWN"]


class CheckRequest(BoundaryModel):
    """Selects results only: the checked universe is always the whole pinned snapshot.

    Subjects by kind: COMPARE_IDENTITY [left, right entity]; LOOKUP_REGISTRATION_EVIDENCE
    [entity]; CHECK_CAPABILITY [recycler, producer]; LOOKUP_PRODUCT_MAPPING and
    COMPARE_WEIGHT_BASIS [entity, sku]; AGGREGATE_SALES [entity] with `period`;
    GET_CERTIFICATE_HISTORY certificate or event ids; CHECK_CREDIT_EVENTS allocation or
    certificate ids; MATCH_TRANSACTIONS commercial ids (empty means every commercial record).
    """

    check_kind: CheckKind
    case_version_id: ID
    subjects: list[Nonempty]
    period: Nonempty | None = None
    reference_event_id: ID | None = None
    profile_id: ID | None = None
    expected_input_membership_digest: Digest | None = None


class CheckTarget(BoundaryModel):
    """One checked subject and its verdict; reasons are machine-readable and ordered."""

    target_refs: list[ID]
    verdict: Verdict
    reasons: list[Nonempty]
    evidence: list[EvidenceRef]
    values: dict[str, str] = {}

    @model_validator(mode="after")
    def explained(self):
        if self.verdict != "PASS" and not self.reasons:
            raise ValueError("FAIL and UNKNOWN verdicts require a reason")
        if not self.target_refs:
            raise ValueError("a check result names its target")
        return self


class StructuredCheckResult(BoundaryModel):
    check_id: ID
    check_kind: CheckKind
    input_membership_blob: BlobRef
    results: list[CheckTarget]
    tool_version: Nonempty
    issues: list[Issue]
