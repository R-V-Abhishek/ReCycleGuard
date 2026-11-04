"""Findings the deterministic reconciliation already established, one per fault family.

Each rule reads a structured check result, never an issue code alone: several codes are shared
by different faults (``DIMENSION_MISMATCH`` also marks a wrong metal). A family is emitted only
when its own check reached a definite state, or, for earlier liability, when the check says the
order cannot be established. Everything here follows the public family definitions in
``docs/design/CONTRACTS.md``; no rule reads benchmark data.
"""

import hashlib

from recycleguard.contracts.core import EvidenceRef
from recycleguard.contracts.results import CalculationResult, FindingRecord, Recommendation
from recycleguard.domain.models import Derivation
from recycleguard.storage import canonical_json_bytes

DETERMINISTIC_SOURCE = "DETERMINISTIC_CALCULATION"


def _calculation_ref(calculation: CalculationResult) -> EvidenceRef:
    return EvidenceRef(
        ref_kind="CALCULATION",
        ref_id=calculation.calculation_id,
        artifact_revision_id=None,
        locator=None,
    )


def _finding(
    calculation: CalculationResult,
    issue_type: str,
    signals: list[dict],
    refs: list[EvidenceRef],
    *,
    abstention: tuple[str, str] | None,
    basis: str,
    action: str,
) -> FindingRecord:
    refs = list({ref.ref_id: ref for ref in [*refs, _calculation_ref(calculation)]}.values())
    token = hashlib.sha256(
        canonical_json_bytes([calculation.calculation_id, issue_type, signals])
    ).hexdigest()[:24]
    reason, scope = abstention if abstention is not None else (None, None)
    return FindingRecord(
        finding_id=f"finding:calc_{token}",
        finding_revision_id=f"finding_revision:calc_{token}",
        case_version_id=calculation.case_version_id,
        bucket_ids=[],
        issue_type=issue_type,
        advisory_status="DISCREPANCY_DETECTED" if abstention is None else "PENDING_VERIFICATION",
        priority="HIGH" if abstention is None else "MEDIUM",
        priority_basis=basis,
        portal_reported_value_ref=None,
        ledger_supported_value_ref=None,
        delta_value_ref=None,
        snapshot_comparison_ref=None,
        fact_refs=refs,
        calculation_refs=[calculation.calculation_id],
        provision_refs=[],
        evidence_assessments=[{"source": DETERMINISTIC_SOURCE, "signals": signals}],
        hypotheses=[],
        abstention_reason=reason,
        withheld_claim_scopes=[] if scope is None else [scope],
        next_action=Recommendation(
            kind="INVESTIGATE" if abstention is None else "REQUEST_EVIDENCE",
            description=action,
            evidence_refs=refs,
        ),
        action_owner_ref=None,
        scope_limits=["Deterministic check result; a reviewer confirms its consequence."],
        supersedes_finding_revision_id=None,
    )


def calculation_findings(
    calculation: CalculationResult, derivation: Derivation
) -> list[FindingRecord]:
    findings = []

    blocking_dimension = [
        issue
        for issue in calculation.issues
        if issue.code == "DIMENSION_MISMATCH" and issue.severity == "BLOCKING"
    ]
    if blocking_dimension:
        findings.append(
            _finding(
                calculation,
                "F04_UNIT_DIMENSION_MIX",
                [{"issue": issue.issue_id, "code": issue.code} for issue in blocking_dimension],
                [ref for issue in blocking_dimension for ref in issue.evidence_refs],
                abstention=None,
                basis="A bucket quantity has a dimension that cannot be added to metal mass.",
                action="Restate the quantity in metal mass from its source before reconciling.",
            )
        )

    entity = [o for o in derivation.eligibility if o.condition == "ENTITY" and o.state == "FAIL"]
    if entity:
        findings.append(
            _finding(
                calculation,
                "F05_WRONG_ENTITY_ALIAS",
                [{"condition": o.condition, "state": o.state} for o in entity],
                [],
                abstention=None,
                basis="Producer or recycler roles do not match a supported entity alias.",
                action="Confirm the counterparty identity and any alias from registration records.",
            )
        )

    stale = [issue for issue in calculation.issues if issue.code == "STALE_SNAPSHOT"]
    if stale:
        findings.append(
            _finding(
                calculation,
                "F06_STALE_SNAPSHOT",
                [{"issue": issue.issue_id, "code": issue.code} for issue in stale],
                [ref for issue in stale for ref in issue.evidence_refs],
                abstention=("TEMPORAL_UNCERTAINTY", "stale_portal_statement"),
                basis="The portal statement was captured before supported ledger events.",
                action="Obtain a portal statement captured after the latest supported transfer.",
            )
        )

    failed = [c for c in derivation.priority_checks if c.state == "FAIL"]
    unresolved = [c for c in derivation.priority_checks if c.state == "UNKNOWN"]
    if failed or unresolved:
        findings.append(
            _finding(
                calculation,
                "F08_PRIOR_ARREARS_DRAIN",
                [
                    {"allocation": c.allocation_id, "bucket": c.bucket_id, "state": c.state}
                    for c in [*failed, *unresolved]
                ],
                [],
                # An order that cannot be established is withheld, even beside a definite breach.
                abstention=None
                if not unresolved
                else ("INCOMPLETE_HISTORY", "earlier_liability_priority"),
                basis="Allocations do not respect, or cannot show, earlier liability priority.",
                action="Establish the allocation order against earlier unmet liabilities.",
            )
        )

    lifecycle = [c for c in derivation.allocation_checks if c.rule == "LIFECYCLE"]
    ended = [c for c in lifecycle if c.state == "FAIL"]
    if ended:
        findings.append(
            _finding(
                calculation,
                "F09_EXPIRED_CANCELLED",
                [{"allocation": c.allocation_id, "code": c.code} for c in ended],
                [ref for c in ended for ref in c.evidence_refs],
                abstention=None,
                basis="An allocated credit is expired or cancelled.",
                action="Replace the allocation with a credit that is live at transfer time.",
            )
        )

    capability = [
        c for c in derivation.allocation_checks if c.rule == "CAPABILITY" and c.state == "FAIL"
    ]
    registration = [
        o for o in derivation.eligibility if o.condition == "REGISTRATION" and o.state == "FAIL"
    ]
    if capability or registration:
        findings.append(
            _finding(
                calculation,
                "F10_CAPABILITY_MISMATCH",
                [{"allocation": c.allocation_id, "code": c.code} for c in capability]
                + [{"condition": o.condition, "state": o.state} for o in registration],
                [ref for c in capability for ref in c.evidence_refs],
                abstention=None,
                basis="The recycler was not authorised or capable for the allocated transfer.",
                action="Check the recycler registration and capability at transfer time.",
            )
        )
    return findings


def load_derivation(calculation: CalculationResult, blobs) -> Derivation:
    return Derivation.model_validate_json(blobs.get(calculation.derivation_blob))
