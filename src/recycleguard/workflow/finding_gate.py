"""Deterministic gate for model finding proposals. Rejections are retained, never dropped."""

import hashlib
import re
from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Literal, get_args

from recycleguard.contracts.core import BoundaryModel, EvidenceRef
from recycleguard.contracts.results import (
    FindingRecord,
    Hypothesis,
    Recommendation,
    WithheldScope,
)
from recycleguard.contracts.workflow import FindingProposal
from recycleguard.reporting.baseline import PROHIBITED_CLAIM
from recycleguard.storage import canonical_json_bytes

MODEL_PROPOSAL_SOURCE = "MODEL_PROPOSAL"
_CLEAN = "F01_CLEAN_BASELINE"
_RECONCILED = "RECONCILED_WITHIN_SCOPE"
_ABSTAINING = {"PENDING_VERIFICATION", "REQUIRES_EXPERT_REVIEW"}
_MAX_TEXT = 400
_DIGIT = re.compile(r"\d")
# Authority or instruction wording, for example copied from an injected dossier document.
# "Certificate" is the domain's own noun for an EPR credit record, so only the verb forms and
# "certification" count as a claim of authority.
_AUTHORITY = re.compile(
    r"\b(?:approved?|certif(?:y|ies|ied|ying|ications?)|ignore\s+(?:all|any|previous|prior)"
    r"|instructions?)\b",
    re.IGNORECASE,
)

RejectionReason = Literal[
    "NO_EVIDENCE_REF",
    "UNKNOWN_EVIDENCE_REF",
    "DIGITS_IN_TEXT",
    "PROHIBITED_TEXT",
    "AUTHORITY_TEXT",
    "TEXT_TOO_LONG",
    "CLEAN_NOT_ESTABLISHED",
    "INVALID_STATUS",
    "INVALID_ABSTENTION",
    "DUPLICATE_ISSUE_TYPE",
    "CONTRADICTED_BY_CALCULATION",
    "NO_VERIFIED_CLAIM",
]


class RejectedFindingProposal(BoundaryModel):
    proposal: FindingProposal
    reason: RejectionReason


def _rejection(
    proposal: FindingProposal, allowed_refs: Mapping[str, EvidenceRef]
) -> RejectionReason | None:
    if not proposal.evidence_ref_ids:
        return "NO_EVIDENCE_REF"
    if any(ref not in allowed_refs for ref in proposal.evidence_ref_ids):
        return "UNKNOWN_EVIDENCE_REF"
    texts = (proposal.basis, proposal.next_action_text)
    if any(len(text) > _MAX_TEXT for text in texts):
        return "TEXT_TOO_LONG"
    if any(_DIGIT.search(text) for text in texts):
        return "DIGITS_IN_TEXT"
    if any(PROHIBITED_CLAIM.search(text) for text in texts):
        return "PROHIBITED_TEXT"
    if any(_AUTHORITY.search(text) for text in texts):
        return "AUTHORITY_TEXT"
    if (proposal.issue_type == _CLEAN) != (proposal.advisory_status == _RECONCILED):
        return "INVALID_STATUS"
    scopes, reason = proposal.withheld_claim_scopes, proposal.abstention_reason
    if (
        bool(scopes) != (reason is not None)
        or any(scope not in get_args(WithheldScope) for scope in scopes)
        or (reason is not None and proposal.advisory_status not in _ABSTAINING)
    ):
        return "INVALID_ABSTENTION"
    return None


def _finding(
    proposal: FindingProposal,
    refs: list[EvidenceRef],
    case_version_id: str,
    calculation_ids: set[str],
) -> FindingRecord:
    digest = hashlib.sha256(
        canonical_json_bytes([case_version_id, proposal.model_dump(mode="json")])
    ).hexdigest()[:24]
    return FindingRecord(
        finding_id=f"finding:model_{digest}",
        finding_revision_id=f"finding_revision:model_{digest}",
        case_version_id=case_version_id,
        bucket_ids=[],
        issue_type=proposal.issue_type,
        advisory_status=proposal.advisory_status,
        priority="MEDIUM",
        priority_basis="Model proposal that passed the evidence gate; it requires human review.",
        portal_reported_value_ref=None,
        ledger_supported_value_ref=None,
        delta_value_ref=None,
        snapshot_comparison_ref=None,
        fact_refs=refs,
        calculation_refs=[ref.ref_id for ref in refs if ref.ref_id in calculation_ids],
        provision_refs=[],
        evidence_assessments=[{"source": MODEL_PROPOSAL_SOURCE}],
        hypotheses=[Hypothesis(text=proposal.basis, support_state="QUALIFIED", refs=refs)],
        abstention_reason=proposal.abstention_reason,
        withheld_claim_scopes=proposal.withheld_claim_scopes,
        next_action=Recommendation(
            kind=proposal.next_action_kind,
            description=proposal.next_action_text,
            evidence_refs=refs,
        ),
        action_owner_ref=None,
        scope_limits=[
            "Model proposal; not a verified determination.",
            *(
                ["No fault found within scope; this does not establish that the target was met."]
                if proposal.issue_type == _CLEAN
                else []
            ),
        ],
        supersedes_finding_revision_id=None,
    )


def reconciliation_settled(calculation, run_calculation_ids: Iterable[str]) -> bool:
    """This run's reconciliation has nothing pending. A shortfall alone is not a fault."""
    return calculation.calculation_id in set(run_calculation_ids) and all(
        Decimal(bucket.pending.decimal) == 0 for bucket in calculation.bucket_results
    )


def gate_finding_proposals(
    proposals: Iterable[FindingProposal],
    *,
    allowed_refs: Mapping[str, EvidenceRef],
    deterministic_issue_types: Iterable[str],
    reconciliation_settled: bool,
    case_version_id: str,
    calculation_ids: Iterable[str] = (),
    contradicted_issue_types: Iterable[str] = (),
) -> tuple[list[FindingRecord], list[RejectedFindingProposal]]:
    """Accept at most one finding per family. Deterministic findings always win a family.

    A family whose complete deterministic check ran and found nothing is contradicted: the
    model cannot assert it against the computed facts. A clean claim is checked last: it needs
    a reconciliation from this run with nothing pending and no other finding, whichever order
    the model proposed them in. It means no fault was found. It does not mean the target was
    met; a shortfall stays in the reconciliation.
    """
    taken = set(deterministic_issue_types)
    contradicted = set(contradicted_issue_types) - taken
    calculations = set(calculation_ids)
    accepted: list[FindingRecord] = []
    rejected: list[RejectedFindingProposal] = []
    ordered = sorted(proposals, key=lambda proposal: proposal.issue_type == _CLEAN)
    for proposal in ordered:
        reason = _rejection(proposal, allowed_refs)
        if reason is None and proposal.issue_type in taken:
            reason = "DUPLICATE_ISSUE_TYPE"
        if reason is None and proposal.issue_type in contradicted:
            reason = "CONTRADICTED_BY_CALCULATION"
        if (
            reason is None
            and proposal.issue_type == _CLEAN
            and (taken or not reconciliation_settled)
        ):
            reason = "CLEAN_NOT_ESTABLISHED"
        if reason is not None:
            rejected.append(RejectedFindingProposal(proposal=proposal, reason=reason))
            continue
        refs = [allowed_refs[ref] for ref in dict.fromkeys(proposal.evidence_ref_ids)]
        accepted.append(_finding(proposal, refs, case_version_id, calculations))
        taken.add(proposal.issue_type)
    return accepted, rejected
