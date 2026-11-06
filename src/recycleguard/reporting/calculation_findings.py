"""Findings the deterministic checks already established, one per fault family.

Two sources feed it. The reconciliation's own structured results (its derivation and issues),
and a sweep of the allowlisted domain checks over the records of the analyzed buckets: the
reconciliation tests lifecycle and capability only on allocations that survived earlier checks,
and never compares weight bases, supplied units or transfers that share an instrument at all.

A family is emitted at most once. Definite failures are asserted; checks that found evidence
but could not settle it are withheld with the public scope for that kind of claim. A family is
decided from the records a signal cites, never from a shared issue code alone. Every rule
follows the public family definitions in ``docs/design/CONTRACTS.md``; none reads benchmark data.
"""

import hashlib
from collections.abc import Iterable
from decimal import Decimal
from typing import NamedTuple

from recycleguard.contracts.core import EvidenceRef
from recycleguard.contracts.domain import (
    AccountBalanceObservation,
    Allocation,
    Certificate,
    CertificateEvent,
    CommercialRecord,
    ObligationBucket,
    ProductMapping,
    SalesRecord,
)
from recycleguard.contracts.extraction import Observation
from recycleguard.contracts.results import CalculationResult, FindingRecord, Recommendation
from recycleguard.domain.chronology import span, span_before
from recycleguard.domain.commercial import match_commercial
from recycleguard.domain.identity import capability_finding, identity_finding
from recycleguard.domain.lifecycle import credit_event_findings
from recycleguard.domain.models import Derivation
from recycleguard.domain.products import sales_finding, weight_basis_finding
from recycleguard.domain.transfers import overlapping_transfers, shared_instrument_transfers
from recycleguard.domain.universe import Universe
from recycleguard.storage import canonical_json_bytes

DETERMINISTIC_SOURCE = "DETERMINISTIC_CALCULATION"
PENDING_CREDITS = ("MISSING_EVIDENCE", "pending_untransferred_credits")
# Families whose check is complete over the pinned records: when the universe was swept and the
# check found nothing, a model claim of that family contradicts a computed fact.
COMPLETE_FAMILIES = frozenset(
    {"F02_OVERLAPPING_EXPORT", "F04_UNIT_DIMENSION_MIX", "F07_PAID_NO_TRANSFER"}
)
_MASS_UNITS = {"KG", "TONNE"}
_INTERMEDIATE_STAGES = {"INITIATED", "OTP_INITIATED", "PUBLIC_KEY_DISPATCHED"}


class _Family(NamedTuple):
    basis: str
    action: str
    # (reason, scope) withheld when any signal is unsettled, and withheld always
    if_unsettled: tuple[str, str] | None = None
    always: tuple[str, str] | None = None
    # status and priority when nothing is withheld
    status: str = "DISCREPANCY_DETECTED"
    priority: str = "HIGH"


_FAMILIES = {
    "F02_OVERLAPPING_EXPORT": _Family(
        "Two records of one lot may be one transfer observed twice; neither is merged and the "
        "unsupported copy is not counted.",
        "Obtain the export record that corroborates a single transfer identity.",
        always=PENDING_CREDITS,
        status="REQUIRES_EXPERT_REVIEW",
        priority="MEDIUM",
    ),
    "F03_MULTISTAGE_ID_REUSE": _Family(
        "Several distinct transfers share one certificate; each is counted once on its own event.",
        "Confirm each tranche is a distinct transfer record; none is merged or counted twice.",
        status="REQUIRES_EXPERT_REVIEW",
        priority="LOW",
    ),
    "F04_UNIT_DIMENSION_MIX": _Family(
        "Quantities were supplied in different mass units or dimensions; they were converted "
        "exactly and never added as supplied.",
        "Confirm each supplied unit against its source before relying on the converted figures.",
    ),
    "F05_WRONG_ENTITY_ALIAS": _Family(
        "Credits went to, or roles were held by, a party not shown to be the producer.",
        "Confirm the counterparty identity and any alias from registration records.",
    ),
    "F06_STALE_SNAPSHOT": _Family(
        "The portal statement was captured before supported ledger events.",
        "Obtain a portal statement captured after the latest supported transfer.",
        always=("TEMPORAL_UNCERTAINTY", "stale_portal_statement"),
    ),
    "F07_PAID_NO_TRANSFER": _Family(
        "A payment or invoice has no completed supported transfer; it is not counted as credit.",
        "Obtain the completed transfer record for the commercial claim.",
        always=PENDING_CREDITS,
    ),
    "F08_PRIOR_ARREARS_DRAIN": _Family(
        "Allocations do not respect, or cannot show, earlier liability priority.",
        "Establish the allocation order against earlier unmet liabilities.",
        if_unsettled=("INCOMPLETE_HISTORY", "earlier_liability_priority"),
        status="REQUIRES_EXPERT_REVIEW",
    ),
    "F09_EXPIRED_CANCELLED": _Family(
        "An allocated credit is expired or cancelled, or its lifecycle evidence is unresolved.",
        "Establish when the credit ended against the transfer and allocation dates.",
        if_unsettled=("TEMPORAL_UNCERTAINTY", "undated_history"),
    ),
    "F10_CAPABILITY_MISMATCH": _Family(
        "The recycler was not authorised or capable for the allocated transfer, or a credit of "
        "another metal was allocated.",
        "Check the recycler registration and capability at transfer time, and the credit metal.",
    ),
    "F13_WEIGHT_BASIS_CONFLICT": _Family(
        "Incompatible weight bases apply to the same product at the same time.",
        "Establish which approved weight basis applies; the bases are never averaged.",
        always=("RULE_CONFLICT", "weight_basis_selection"),
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

    def add(self, family, signal, refs, *, settled=True, withheld=()):
        entry = self.by_family.setdefault(
            family, {"signals": [], "refs": [], "unsettled": False, "withheld": []}
        )
        entry["signals"].append(signal)
        entry["refs"].extend(refs)
        entry["unsettled"] = entry["unsettled"] or not settled
        entry["withheld"].extend(withheld)


def _finding(calculation: CalculationResult, family: str, entry: dict) -> FindingRecord:
    spec = _FAMILIES[family]
    withheld = [
        *([spec.always] if spec.always else []),
        *([spec.if_unsettled] if spec.if_unsettled and entry["unsettled"] else []),
        *entry["withheld"],
    ]
    scopes = list(dict.fromkeys(scope for _, scope in withheld))
    reason = withheld[0][0] if withheld else None
    if reason is None:
        status, priority = spec.status, spec.priority
    else:
        status = spec.status if spec.status == "REQUIRES_EXPERT_REVIEW" else "PENDING_VERIFICATION"
        priority = "MEDIUM"
    refs = list(
        {ref.ref_id: ref for ref in [*entry["refs"], _calculation_ref(calculation)]}.values()
    )
    signals = entry["signals"]
    token = hashlib.sha256(
        canonical_json_bytes([calculation.calculation_id, family, signals])
    ).hexdigest()[:24]
    return FindingRecord(
        finding_id=f"finding:calc_{token}",
        finding_revision_id=f"finding_revision:calc_{token}",
        case_version_id=calculation.case_version_id,
        bucket_ids=[],
        issue_type=family,
        advisory_status=status,
        priority=priority,
        priority_basis=spec.basis,
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
        withheld_claim_scopes=scopes,
        next_action=Recommendation(
            kind="INVESTIGATE" if reason is None else "REQUEST_EVIDENCE",
            description=spec.action,
            evidence_refs=refs,
        ),
        action_owner_ref=None,
        scope_limits=["Deterministic check result; a reviewer confirms its consequence."],
        supersedes_finding_revision_id=None,
    )


def _metal_differs(ref_id: str, universe: Universe | None) -> bool:
    """The cited allocation, or its transfer, is not the metal of the bucket it was added to."""
    if universe is None:
        return False
    allocation = next((a for a in universe.active(Allocation) if a.record_id == ref_id), None)
    if allocation is None:
        return False
    bucket = next(
        (b for b in universe.active(ObligationBucket) if b.bucket_id == allocation.bucket_id),
        None,
    )
    event = next(
        (e for e in universe.active(CertificateEvent) if e.event_id == allocation.event_id), None
    )
    if bucket is None:
        return False
    return allocation.quantity.metal != bucket.metal or (
        event is not None and event.quantity.metal != bucket.metal
    )


def _undated_order(check, universe: Universe | None) -> bool:
    """The allocation order is unknown because an allocation time is missing, not tied."""
    if universe is None:
        return "not recorded" in check.reason
    allocations = universe.active(Allocation)
    involved = [
        a
        for a in allocations
        if a.allocation_id == check.allocation_id or a.bucket_id in check.earlier_bucket_ids
    ]
    return any(span(a.allocation_time) is None for a in involved if a.state != "REJECTED")


def _from_calculation(
    signals: _Signals,
    calculation: CalculationResult,
    derivation: Derivation,
    universe: Universe | None,
):
    for issue in calculation.issues:
        if issue.code == "DIMENSION_MISMATCH":
            # One code covers a unit, a dimension and a metal; the cited records decide which.
            metal = [r for r in issue.evidence_refs if _metal_differs(r.ref_id, universe)]
            if metal:
                signals.add(
                    "F10_CAPABILITY_MISMATCH",
                    {"issue": issue.issue_id, "check": "METAL_COMPATIBILITY"},
                    metal,
                )
            if len(metal) < len(issue.evidence_refs) or not issue.evidence_refs:
                signals.add(
                    "F04_UNIT_DIMENSION_MIX",
                    {"issue": issue.issue_id, "severity": issue.severity},
                    [r for r in issue.evidence_refs if r not in metal],
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
            withheld = []
            if check.state == "FAIL":
                # The supplied order is refuted; the correct order is still not established.
                withheld.append(("RULE_CONFLICT", "earlier_liability_priority"))
            elif _undated_order(check, universe):
                withheld.append(("INCOMPLETE_HISTORY", "undated_history"))
            signals.add(
                "F08_PRIOR_ARREARS_DRAIN",
                {
                    "allocation": check.allocation_id,
                    "bucket": check.bucket_id,
                    "state": check.state,
                },
                [],
                settled=check.state == "FAIL",
                withheld=withheld,
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


def _observation_units(observation: Observation) -> set[str]:
    """Mass units an observation was supplied in, before normalization converted them."""
    found = set()
    for fields in (observation.parsed_fields, observation.raw_fields):
        values = [fields.get("unit"), fields.get("UOM")]
        values += [
            nested.get("unit")
            for key in ("quantity", "target", "credit_quantity")
            if isinstance(nested := fields.get(key), dict)
        ]
        found |= {v.upper() for v in values if isinstance(v, str) and v.upper() in _MASS_UNITS}
    return found


def _unit_mix(signals: _Signals, analyzed, universe: Universe, observations):
    """Quantities for one bucket supplied in more than one mass unit, as records or as sources."""
    units_by_observation = {o.observation_id: _observation_units(o) for o in observations}
    allocations = [a for a in universe.active(Allocation) if a.state != "REJECTED"]
    transfers = [e for e in universe.active(CertificateEvent) if e.event_kind == "TRANSFERRED"]
    for bucket in sorted(universe.active(ObligationBucket), key=lambda b: b.bucket_id):
        if bucket.bucket_id not in analyzed:
            continue
        mine = [a for a in allocations if a.bucket_id == bucket.bucket_id]
        allocated = {a.event_id for a in mine}
        received = [
            e
            for e in transfers
            if e.event_id in allocated
            or (e.quantity.metal == bucket.metal and e.to_entity_id == bucket.producer_entity_id)
        ]
        supplied: dict[str, set[str]] = {}
        for record, quantities in (
            (bucket, [bucket.target, *(a.quantity for a in bucket.adjustments)]),
            *((a, [a.quantity]) for a in mine),
            *((e, [e.quantity]) for e in received),
        ):
            sources = [*record.observation_refs, *getattr(record, "supporting_observations", [])]
            units = {q.unit for q in quantities if q.unit in _MASS_UNITS}
            for source in sources:
                units |= units_by_observation.get(source, set())
            supplied[record.record_id] = units
        mixed = set().union(*supplied.values())
        if len(mixed) > 1:
            signals.add(
                "F04_UNIT_DIMENSION_MIX",
                {"bucket": bucket.bucket_id, "check": "UNIT_MIX", "units": sorted(mixed)},
                _records(sorted(r for r, units in supplied.items() if units - {"KG"})),
            )


def _paid_no_transfer(
    signals: _Signals, calculation, derivation: Derivation, analyzed, universe: Universe
):
    """Payable records and intermediate transfer stages without a completed supported transfer."""
    by_record = {c.record_id: c for c in universe.active(CommercialRecord)}
    for bucket in derivation.buckets:
        if bucket.bucket_id in analyzed and bucket.pending_commercial_ids:
            signals.add(
                "F07_PAID_NO_TRANSFER",
                {"bucket": bucket.bucket_id, "check": "PENDING_COMMERCIAL"},
                _records(bucket.pending_commercial_ids),
                settled=False,
            )
    buckets = {
        b.bucket_id: b
        for b in universe.active(ObligationBucket)
        if b.profile_id == calculation.profile_id
    }
    by_commercial = {c.commercial_id: c for c in by_record.values()}
    for commercial_id, outcome in sorted(match_commercial(universe, buckets).items()):
        # Pending credit that could not be placed in one bucket is still uncounted credit.
        if outcome.state in {"UNPLACED", "AMBIGUOUS"} and commercial_id in by_commercial:
            signals.add(
                "F07_PAID_NO_TRANSFER",
                {"commercial": commercial_id, "check": outcome.state},
                _records([by_commercial[commercial_id].record_id]),
                settled=False,
            )
    events = {e.event_id: e for e in universe.active(CertificateEvent)}
    for allocation in sorted(universe.active(Allocation), key=lambda a: a.allocation_id):
        event = events.get(allocation.event_id)
        if (
            allocation.bucket_id in analyzed
            and allocation.state != "REJECTED"
            and event is not None
            and event.event_kind == "TRANSFERRED"
            and event.transfer_stage in _INTERMEDIATE_STAGES
        ):
            signals.add(
                "F07_PAID_NO_TRANSFER",
                {"allocation": allocation.allocation_id, "check": "INTERMEDIATE_STAGE"},
                _records([allocation.record_id, event.record_id]),
                settled=False,
            )


def _shared_instruments(signals: _Signals, derivation: Derivation, universe: Universe):
    """Overlapping copies of one transfer (F02) and distinct tranches of one certificate (F03)."""
    lots = {lot.credit_lot_id: lot for lot in derivation.lots}
    pending = {a for b in derivation.buckets for a in b.pending_allocation_ids}
    allocations = [a for a in universe.active(Allocation) if a.state != "REJECTED"]
    overlapping = set()
    for left, right in overlapping_transfers(universe):
        copies = [e for e in (left, right) if e.assertion_state != "SUPPORTED"]
        held = [a for a in allocations if a.event_id in {e.event_id for e in copies}]
        lot = lots.get(left.credit_lot_id) if left.credit_lot_id else None
        if (lot is not None and lot.conservation in {"UNKNOWN", "FAIL"}) or any(
            a.allocation_id in pending for a in held
        ):
            overlapping |= {left.certificate_id, right.certificate_id}
            signals.add(
                "F02_OVERLAPPING_EXPORT",
                {"events": [left.event_id, right.event_id], "check": "CANDIDATE_OVERLAP"},
                _records([left.record_id, right.record_id, *(a.record_id for a in held)]),
                settled=False,
            )
    for certificate_id, group in shared_instrument_transfers(universe).items():
        # An unresolved overlap on the certificate is reported as that, not as distinct tranches.
        if certificate_id in overlapping:
            continue
        checked = [lots.get(e.credit_lot_id) for e in group if e.credit_lot_id]
        if checked and all(lot is not None and lot.conservation == "PASS" for lot in checked):
            signals.add(
                "F03_MULTISTAGE_ID_REUSE",
                {"certificate": certificate_id, "check": "SHARED_INSTRUMENT"},
                _records([e.record_id for e in group]),
            )


def _stale_by_date(signals: _Signals, derivation: Derivation, analyzed, universe: Universe):
    """A statement cut-off wholly before an allocated transfer, at whatever precision both have."""
    balances = {b.balance_observation_id: b for b in universe.active(AccountBalanceObservation)}
    events = {e.event_id: e for e in universe.active(CertificateEvent)}
    allocations = [a for a in universe.active(Allocation) if a.state != "REJECTED"]
    for comparison in derivation.portal_comparisons:
        balance = balances.get(comparison.balance_observation_id)
        if comparison.bucket_id not in analyzed or balance is None:
            continue
        cutoff = span(balance.business_cutoff)
        later = [
            a
            for a in allocations
            if a.bucket_id == comparison.bucket_id
            and (event := events.get(a.event_id)) is not None
            and span_before(cutoff, span(event.event_time)) is True
        ]
        if later:
            signals.add(
                "F06_STALE_SNAPSHOT",
                {"balance": balance.balance_observation_id, "check": "CUTOFF_BEFORE_TRANSFER"},
                _records([balance.record_id]),
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
    calculation: CalculationResult,
    derivation: Derivation,
    universe: Universe | None = None,
    observations: Iterable[Observation] = (),
) -> list[FindingRecord]:
    signals = _Signals()
    _from_calculation(signals, calculation, derivation, universe)
    if universe is not None:
        analyzed = set(calculation.analyzed_bucket_ids)
        _from_domain_checks(signals, calculation, universe)
        _unit_mix(signals, analyzed, universe, list(observations))
        _paid_no_transfer(signals, calculation, derivation, analyzed, universe)
        _shared_instruments(signals, derivation, universe)
        _stale_by_date(signals, derivation, analyzed, universe)
    return [
        _finding(calculation, family, signals.by_family[family])
        for family in _FAMILIES
        if family in signals.by_family
    ]


def contradicted_families(findings: Iterable[FindingRecord], universe: Universe | None) -> set:
    """Complete-check families the sweep did not find; a model claim of one is contradicted."""
    if universe is None:
        return set()
    return set(COMPLETE_FAMILIES - {finding.issue_type for finding in findings})


def settled_without_finding(calculation: CalculationResult) -> bool:
    """Every analyzed bucket has nothing pending and no issue is above WARNING."""
    return (
        bool(calculation.bucket_results)
        and all(Decimal(b.pending.decimal) == 0 for b in calculation.bucket_results)
        and all(issue.severity in {"INFO", "WARNING"} for issue in calculation.issues)
    )


def load_derivation(calculation: CalculationResult, blobs) -> Derivation:
    return Derivation.model_validate_json(blobs.get(calculation.derivation_blob))
