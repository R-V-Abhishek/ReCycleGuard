"""Findings the deterministic checks already established, one per fault family.

Two sources feed it. The reconciliation's own structured results (its derivation and issues),
and a sweep of the allowlisted domain checks over every allocation, product mapping and sales
record of the analyzed buckets: the reconciliation tests lifecycle and capability only on
allocations that survived earlier checks, and never compares weight bases at all.

A family is emitted at most once. Definite failures are asserted; checks that found evidence
but could not settle it are withheld with the public scope for that kind of claim. Every rule
follows the public family definitions in ``docs/design/CONTRACTS.md``; none reads benchmark data.
"""

import hashlib

from recycleguard.contracts.core import EvidenceRef
from recycleguard.contracts.domain import (
    Allocation,
    Certificate,
    CertificateEvent,
    ObligationBucket,
    ProductMapping,
    SalesRecord,
)
from recycleguard.contracts.results import CalculationResult, FindingRecord, Recommendation
from recycleguard.domain.chronology import span
from recycleguard.domain.identity import capability_finding, identity_finding
from recycleguard.domain.lifecycle import credit_event_findings
from recycleguard.domain.models import Derivation
from recycleguard.domain.products import sales_finding, weight_basis_finding
from recycleguard.domain.universe import Universe
from recycleguard.storage import canonical_json_bytes

DETERMINISTIC_SOURCE = "DETERMINISTIC_CALCULATION"

# family: (basis, action, abstention when any signal is unsettled, abstention always)
_FAMILIES = {
    "F04_UNIT_DIMENSION_MIX": (
        "A quantity's unit or dimension does not match the metal mass it is added to.",
        "Restate the quantity in the bucket's metal mass from its source before reconciling.",
        None,
        None,
    ),
    "F05_WRONG_ENTITY_ALIAS": (
        "Credits went to, or roles were held by, a party not shown to be the producer.",
        "Confirm the counterparty identity and any alias from registration records.",
        None,
        None,
    ),
    "F06_STALE_SNAPSHOT": (
        "The portal statement was captured before supported ledger events.",
        "Obtain a portal statement captured after the latest supported transfer.",
        None,
        ("TEMPORAL_UNCERTAINTY", "stale_portal_statement"),
    ),
    "F08_PRIOR_ARREARS_DRAIN": (
        "Allocations do not respect, or cannot show, earlier liability priority.",
        "Establish the allocation order against earlier unmet liabilities.",
        ("INCOMPLETE_HISTORY", "earlier_liability_priority"),
        None,
    ),
    "F09_EXPIRED_CANCELLED": (
        "An allocated credit is expired or cancelled, or its lifecycle evidence is unresolved.",
        "Establish when the credit ended against the transfer and allocation dates.",
        ("TEMPORAL_UNCERTAINTY", "undated_history"),
        None,
    ),
    "F10_CAPABILITY_MISMATCH": (
        "The recycler was not authorised or capable for the allocated transfer.",
        "Check the recycler registration and capability at transfer time.",
        None,
        None,
    ),
    "F13_WEIGHT_BASIS_CONFLICT": (
        "Incompatible weight bases apply to the same product at the same time.",
        "Establish which approved weight basis applies; the bases are never averaged.",
        None,
        ("RULE_CONFLICT", "weight_basis_selection"),
    ),
}


def _calculation_ref(calculation: CalculationResult) -> EvidenceRef:
    return EvidenceRef(
        ref_kind="CALCULATION",
        ref_id=calculation.calculation_id,
        artifact_revision_id=None,
        locator=None,
    )


def _records(ids) -> list[EvidenceRef]:
    return [
        EvidenceRef(ref_kind="RECORD", ref_id=ref, artifact_revision_id=None, locator=None)
        for ref in ids
    ]


class _Signals:
    def __init__(self):
        self.by_family: dict[str, dict] = {}

    def add(self, family, signal, refs, *, settled=True):
        entry = self.by_family.setdefault(family, {"signals": [], "refs": [], "unsettled": False})
        entry["signals"].append(signal)
        entry["refs"].extend(refs)
        entry["unsettled"] = entry["unsettled"] or not settled


def _finding(calculation: CalculationResult, family: str, entry: dict) -> FindingRecord:
    basis, action, if_unsettled, always = _FAMILIES[family]
    abstention = always or (if_unsettled if entry["unsettled"] else None)
    refs = list(
        {ref.ref_id: ref for ref in [*entry["refs"], _calculation_ref(calculation)]}.values()
    )
    signals = entry["signals"]
    token = hashlib.sha256(
        canonical_json_bytes([calculation.calculation_id, family, signals])
    ).hexdigest()[:24]
    reason, scope = abstention if abstention is not None else (None, None)
    return FindingRecord(
        finding_id=f"finding:calc_{token}",
        finding_revision_id=f"finding_revision:calc_{token}",
        case_version_id=calculation.case_version_id,
        bucket_ids=[],
        issue_type=family,
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


def _from_calculation(signals: _Signals, calculation: CalculationResult, derivation: Derivation):
    for issue in calculation.issues:
        # Every reconciliation dimension check, bucket or allocation, is a unit/dimension mix.
        if issue.code == "DIMENSION_MISMATCH":
            signals.add(
                "F04_UNIT_DIMENSION_MIX",
                {"issue": issue.issue_id, "severity": issue.severity},
                issue.evidence_refs,
            )
        elif issue.code == "STALE_SNAPSHOT":
            signals.add("F06_STALE_SNAPSHOT", {"issue": issue.issue_id}, issue.evidence_refs)
    for outcome in derivation.eligibility:
        if outcome.state != "FAIL":
            continue
        if outcome.condition == "ENTITY":
            signals.add("F05_WRONG_ENTITY_ALIAS", {"condition": "ENTITY", "state": "FAIL"}, [])
        elif outcome.condition == "REGISTRATION":
            signals.add(
                "F10_CAPABILITY_MISMATCH", {"condition": "REGISTRATION", "state": "FAIL"}, []
            )
    for check in derivation.priority_checks:
        if check.state in {"FAIL", "UNKNOWN"}:
            signals.add(
                "F08_PRIOR_ARREARS_DRAIN",
                {
                    "allocation": check.allocation_id,
                    "bucket": check.bucket_id,
                    "state": check.state,
                },
                [],
                settled=check.state == "FAIL",
            )
    for check in derivation.allocation_checks:
        family = {"LIFECYCLE": "F09_EXPIRED_CANCELLED", "CAPABILITY": "F10_CAPABILITY_MISMATCH"}
        # An UNKNOWN capability is missing evidence, not a capability fault.
        if check.state == "FAIL" or (check.rule == "LIFECYCLE" and check.state == "UNKNOWN"):
            signals.add(
                family[check.rule],
                {"allocation": check.allocation_id, "state": check.state, "code": check.code},
                check.evidence_refs,
                settled=check.state == "FAIL",
            )


def _from_domain_checks(signals: _Signals, calculation: CalculationResult, universe: Universe):
    analyzed = set(calculation.analyzed_bucket_ids)
    buckets = {b.bucket_id: b for b in universe.active(ObligationBucket)}
    events = {e.event_id: e for e in universe.active(CertificateEvent)}
    certificates = {c.certificate_id: c for c in universe.active(Certificate)}
    allocations = sorted(
        (
            a
            for a in universe.active(Allocation)
            if a.bucket_id in analyzed and a.state != "REJECTED"
        ),
        key=lambda a: a.allocation_id,
    )
    for allocation in allocations:
        bucket = buckets.get(allocation.bucket_id)
        event = events.get(allocation.event_id)
        if bucket is None or event is None:
            continue
        when = span(event.event_time)
        recipient = event.to_entity_id
        if recipient is not None and recipient != bucket.producer_entity_id:
            found = identity_finding(universe, recipient, bucket.producer_entity_id, when)
            # A confirmed identifier or reviewed, dated alias makes them the same party.
            if found.state != "PASS":
                signals.add(
                    "F05_WRONG_ENTITY_ALIAS",
                    {
                        "allocation": allocation.allocation_id,
                        "check": "COMPARE_IDENTITY",
                        "state": found.state,
                    },
                    _records(found.refs),
                )
        for found in credit_event_findings(universe, allocation.allocation_id):
            # UNKNOWN without a code is terminal evidence that cannot be dated or ordered.
            if found.state == "FAIL" or (found.state == "UNKNOWN" and found.code is None):
                signals.add(
                    "F09_EXPIRED_CANCELLED",
                    {
                        "allocation": allocation.allocation_id,
                        "check": "CHECK_CREDIT_EVENTS",
                        "state": found.state,
                        "code": found.code,
                    },
                    _records(found.refs),
                    settled=found.state == "FAIL",
                )
        certificate = certificates.get(event.certificate_id)
        recycler = event.from_entity_id or (
            None if certificate is None else certificate.issuer_entity_id
        )
        if recycler is not None:
            found = capability_finding(universe, recycler, bucket.producer_entity_id, when)
            if found.state == "FAIL":
                signals.add(
                    "F10_CAPABILITY_MISMATCH",
                    {"allocation": allocation.allocation_id, "check": "CHECK_CAPABILITY"},
                    _records(found.refs),
                )
    for entity, sku in sorted({(m.entity_id, m.sku) for m in universe.active(ProductMapping)}):
        found = weight_basis_finding(universe, entity, sku)
        if found.state == "FAIL":
            signals.add(
                "F13_WEIGHT_BASIS_CONFLICT",
                {"entity": entity, "check": "COMPARE_WEIGHT_BASIS"},
                _records(found.refs),
            )
    for entity, year in sorted(
        {(s.entity_id, s.fiscal_year) for s in universe.active(SalesRecord)}
    ):
        found = sales_finding(universe, entity, year)
        if found.state == "FAIL" and found.code == "WEIGHT_BASIS_CONFLICT":
            signals.add(
                "F13_WEIGHT_BASIS_CONFLICT",
                {"entity": entity, "check": "AGGREGATE_SALES"},
                _records(found.refs),
            )


def calculation_findings(
    calculation: CalculationResult, derivation: Derivation, universe: Universe | None = None
) -> list[FindingRecord]:
    signals = _Signals()
    _from_calculation(signals, calculation, derivation)
    if universe is not None:
        _from_domain_checks(signals, calculation, universe)
    return [
        _finding(calculation, family, signals.by_family[family])
        for family in _FAMILIES
        if family in signals.by_family
    ]


def load_derivation(calculation: CalculationResult, blobs) -> Derivation:
    return Derivation.model_validate_json(blobs.get(calculation.derivation_blob))
