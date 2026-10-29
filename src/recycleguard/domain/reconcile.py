"""Pure C08 baseline reconciliation engine: no I/O, no model, no caller-supplied records."""

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from recycleguard.contracts.core import ErrorCode, EvidenceRef, Issue, TemporalValue
from recycleguard.contracts.domain import (
    AccountBalanceObservation,
    Allocation,
    Certificate,
    CertificateEvent,
    CommercialRecord,
    Entity,
    ObligationBucket,
    Registration,
)
from recycleguard.contracts.profiles import CalculationProfile
from recycleguard.contracts.results import BucketResult
from recycleguard.domain.allocation import Decision, decide_allocations, enforce_lot_caps
from recycleguard.domain.arith import ZERO, add, mass, signed, subtract, to_kg, total
from recycleguard.domain.chronology import Chronology, span
from recycleguard.domain.commercial import CommercialOutcome, match_commercial
from recycleguard.domain.identity import apply_capability, party_findings, registration_finding
from recycleguard.domain.lifecycle import apply_lifecycle
from recycleguard.domain.lots import derive_lots
from recycleguard.domain.models import (
    AllocationCheck,
    BucketDerivation,
    CheckState,
    Coverage,
    Derivation,
    EligibilityOutcome,
    PortalComparison,
    QuantityDisposition,
)
from recycleguard.domain.priority import evaluate_priority
from recycleguard.domain.refs import make_issue, record_ref
from recycleguard.domain.universe import Universe
from recycleguard.normalization.units import NumericSafetyError
from recycleguard.storage import canonical_json_bytes

TOOL_VERSION = "c08-s04-0.2"
_RANK = {"COMPLETE_WITHIN_SCOPE": 0, "QUALIFIED": 1, "BLOCKED": 2}


class EngineRejected(ValueError):
    """The request cannot be computed at all (distinct from a computed-but-qualified result)."""

    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class EngineOutput:
    bucket_results: list[BucketResult]
    dispositions: list[QuantityDisposition]
    derivation: Derivation
    issues: list[Issue]
    coverage: Coverage
    analyzed_bucket_ids: list[str]


_issue = make_issue


def _instant(value: TemporalValue | None) -> datetime | None:
    if value is None or value.value is None or value.precision != "INSTANT":
        return None
    return datetime.fromisoformat(value.value.replace("Z", "+00:00"))


def _worse(left: Coverage, right: Coverage) -> Coverage:
    return left if _RANK[left] >= _RANK[right] else right


def _required(bucket: ObligationBucket) -> tuple[Decimal, list[Decimal]]:
    adjustments = []
    for adjustment in bucket.adjustments:
        if (
            adjustment.quantity.dimension != "METAL_MASS"
            or adjustment.quantity.metal != bucket.metal
        ):
            raise NumericSafetyError("DIMENSION_MISMATCH: adjustment is not the bucket metal mass")
        adjustments.append(to_kg(adjustment.quantity))
    return add(to_kg(bucket.target), total(adjustments)), adjustments


def compute(
    universe: Universe,
    profile: CalculationProfile,
    bucket_ids: list[str],
    *,
    allocation_order: Mapping[str, int] | None = None,
) -> EngineOutput:
    if profile.review_state != "APPROVED":
        raise EngineRejected("UNAPPROVED_PROFILE", "reconciliation requires an approved profile")
    issues: list[Issue] = []

    all_buckets = {b.bucket_id: b for b in universe.active(ObligationBucket)}
    scoped = {
        k: b
        for k, b in all_buckets.items()
        if b.profile_id == profile.profile_id and b.metal in profile.allowed_metals
    }
    requested = list(dict.fromkeys(bucket_ids)) or sorted(scoped)

    required: dict[str, Decimal] = {}
    adjustments: dict[str, list[Decimal]] = {}
    unusable: set[str] = set()
    for bucket in scoped.values():
        try:
            value, adjustments[bucket.bucket_id] = _required(bucket)
        except NumericSafetyError as exc:
            if "precision" in str(exc):
                raise
            unusable.add(bucket.bucket_id)
            issues.append(_issue("DIMENSION_MISMATCH", "BLOCKING", str(exc), [record_ref(bucket)]))
            continue
        if value < 0:
            unusable.add(bucket.bucket_id)
            issues.append(
                _issue(
                    "INTEGRITY_FAILED",
                    "BLOCKING",
                    f"Required quantity for {bucket.bucket_id} would be negative after adjustments",
                    [record_ref(bucket)],
                )
            )
        else:
            required[bucket.bucket_id] = value

    events = {e.event_id: e for e in universe.active(CertificateEvent)}
    certificates = {c.certificate_id: c for c in universe.active(Certificate)}
    lots = derive_lots(universe)
    allocation_checks: list[AllocationCheck] = []

    def s04_checks(found: list[Decision]) -> None:
        allocation_checks.extend(apply_lifecycle(found, certificates, events))
        allocation_checks.extend(apply_capability(found, universe, events, certificates, scoped))

    allocations = universe.active(Allocation)
    decisions = decide_allocations(
        allocations, scoped, events, lots, profile.profile_id, prechecks=s04_checks
    )
    lot_checks = enforce_lot_caps(decisions, lots)
    chronology = Chronology(
        allocation_order, {a.allocation_id: a.allocation_time for a in allocations}
    )
    priority_checks = evaluate_priority(scoped, required, decisions, chronology)

    commercials = universe.active(CommercialRecord)
    commercial_map = match_commercial(universe, scoped)
    overall: Coverage = "COMPLETE_WITHIN_SCOPE"
    for outcome in commercial_map.values():
        if outcome.state == "MISMATCH":
            issues.append(_issue(outcome.code or "INTEGRITY_FAILED", "WARNING", outcome.reason))
            overall = _worse(overall, "QUALIFIED")
        elif outcome.state == "UNRESOLVED_LINK":
            issues.append(_issue("INCOMPLETE_COVERAGE", "INFO", outcome.reason))

    balances_by_bucket: dict[str, list[AccountBalanceObservation]] = {}
    for balance in universe.active(AccountBalanceObservation):
        balances_by_bucket.setdefault(balance.bucket_id, []).append(balance)

    bucket_results: list[BucketResult] = []
    derivations: list[BucketDerivation] = []
    comparisons: list[PortalComparison] = []
    chosen_balances: set[str] = set()
    analyzed: list[str] = []

    for bucket_id in requested:
        bucket = scoped.get(bucket_id)
        if bucket is None:
            code: ErrorCode = (
                "MISSING_ARTIFACT" if bucket_id not in all_buckets else "UNSUPPORTED_PROFILE"
            )
            issues.append(
                _issue(
                    code,
                    "BLOCKING",
                    f"{bucket_id} cannot be analyzed under this profile or snapshot",
                )
            )
            overall = "BLOCKED"
            continue
        if bucket_id in unusable:
            overall = "BLOCKED"
            continue
        mine = [d for d in decisions if d.allocation.bucket_id == bucket_id]
        supported_d = [d for d in mine if d.state == "INCLUDED"]
        pending_d = [d for d in mine if d.state == "PENDING"]
        pending_c = [
            c
            for c in commercials
            if (o := commercial_map.get(c.commercial_id)) is not None
            and o.state == "COUNTED"
            and o.bucket_id == bucket_id
        ]
        supported = total(d.kg for d in supported_d)
        pending = add(
            total(d.kg for d in pending_d), total(to_kg(c.credit_quantity) for c in pending_c)
        )
        gap = subtract(required[bucket_id], supported)

        portal, comparison, portal_issue = _portal(
            universe, bucket, balances_by_bucket.get(bucket_id, []), supported, supported_d, events
        )
        if comparison is not None:
            comparisons.append(comparison)
            if comparison.balance_observation_id is not None:
                chosen_balances.add(comparison.balance_observation_id)
        issues.extend(portal_issue)

        qualification: list[EvidenceRef] = [record_ref(d.allocation) for d in pending_d]
        qualification += [record_ref(c) for c in pending_c]
        qualification += [
            record_ref(d.allocation) for d in mine if d.open_checks and d.state != "EXCLUDED"
        ]
        related = [d for d in mine if d.state != "EXCLUDED"]
        reviewed = [bucket]
        for d in related:
            reviewed.append(d.allocation)
            event = events.get(d.allocation.event_id)
            if event is not None:
                reviewed.append(event)
            if event is not None and event.certificate_id in certificates:
                reviewed.append(certificates[event.certificate_id])
        qualification += [record_ref(r) for r in reviewed if r.validation_state != "VALID"]

        coverage: Coverage = "COMPLETE_WITHIN_SCOPE"
        if any(d.conservation_fault for d in mine):
            coverage = "BLOCKED"
        lot_ids = {d.allocation.credit_lot_id for d in mine}
        priority_open = [
            p
            for p in priority_checks
            if p.bucket_id == bucket_id and p.state in {"UNKNOWN", "FAIL"}
        ]
        lot_open = [
            c for c in lot_checks if c.credit_lot_id in lot_ids and c.conservation == "UNKNOWN"
        ]
        portal_open = (
            comparison is not None
            and comparison.delta is not None
            and Decimal(comparison.delta.decimal) != 0
        )
        if portal_open:
            issues.append(
                _issue(
                    "INCOMPLETE_COVERAGE",
                    "WARNING",
                    f"Portal figure for {bucket_id} differs from the allocation ledger; the "
                    "difference is not backed by supported allocations",
                    [record_ref(bucket)],
                )
            )
        if qualification or portal is None or portal_open or priority_open or lot_open:
            coverage = _worse(coverage, "QUALIFIED")
        overall = _worse(overall, coverage)

        result = BucketResult(
            bucket_id=bucket_id,
            required=mass(required[bucket_id], bucket.metal),
            supported=mass(supported, bucket.metal),
            signed_gap=signed(gap, bucket.metal),
            shortfall=mass(max(gap, ZERO), bucket.metal),
            surplus=mass(max(-gap, ZERO), bucket.metal),
            pending=mass(pending, bucket.metal),
            portal_reported=None if comparison is None else comparison.portal_reported,
            ledger_supported=mass(supported, bucket.metal),
            delta=None if comparison is None else comparison.delta,
            snapshot_comparison_ref=None
            if comparison is None or comparison.delta is None
            else comparison.comparison_id,
            allocation_ids=sorted(d.allocation.allocation_id for d in supported_d),
            qualification_refs=qualification,
        )
        bucket_results.append(result)
        analyzed.append(bucket_id)
        derivations.append(
            BucketDerivation(
                bucket_id=bucket_id,
                target=bucket.target,
                adjustments=[signed(a, bucket.metal) for a in adjustments[bucket_id]],
                required=result.required,
                supported_allocation_ids=result.allocation_ids,
                pending_allocation_ids=sorted(d.allocation.allocation_id for d in pending_d),
                pending_commercial_ids=sorted(c.record_id for c in pending_c),
                formula="signed_gap = required - supported; pending is reported, not subtracted",
                coverage=coverage,
            )
        )

    return _finish(
        universe,
        profile,
        requested,
        scoped,
        all_buckets,
        decisions,
        commercial_map,
        chosen_balances,
        lots,
        lot_checks,
        priority_checks,
        allocation_checks,
        comparisons,
        bucket_results,
        derivations,
        analyzed,
        overall,
        issues,
    )


def _portal(universe, bucket, balances, supported, supported_d, events):
    """Pick one compatible balance observation; never guess among ambiguous ones."""
    compatible = [
        b
        for b in balances
        if b.producer_entity_id == bucket.producer_entity_id
        and b.reported_supported.metal == bucket.metal
    ]
    ledger = signed(supported, bucket.metal)
    issues: list[Issue] = []
    chosen = None
    if len(compatible) == 1:
        chosen = compatible[0]
    elif len(compatible) > 1:
        times = [_instant(b.source_capture_time) for b in compatible]
        if all(t is not None for t in times):
            ranked = sorted(zip(times, compatible, strict=True), key=lambda x: x[0])
            if ranked[-1][0] > ranked[-2][0]:
                chosen = ranked[-1][1]
        if chosen is None:
            issues.append(
                _issue(
                    "INCOMPLETE_COVERAGE",
                    "WARNING",
                    f"Several portal observations for {bucket.bucket_id} cannot be ordered",
                    [record_ref(b) for b in compatible],
                )
            )
    if chosen is None:
        note = "No compatible portal observation; comparison is null, not zero"
        token = hashlib.sha256(
            canonical_json_bytes([universe.snapshot_id, bucket.bucket_id])
        ).hexdigest()
        return (
            None,
            PortalComparison(
                comparison_id=f"comparison:{token[:24]}",
                bucket_id=bucket.bucket_id,
                balance_observation_id=None,
                portal_reported=None,
                ledger_supported=ledger,
                delta=None,
                source_capture_time=None,
                business_cutoff=None,
                note=note,
            ),
            issues,
        )
    reported = mass(to_kg(chosen.reported_supported), bucket.metal)
    delta = signed(subtract(to_kg(chosen.reported_supported), supported), bucket.metal)
    cutoff = _instant(chosen.business_cutoff)
    note = "Portal view compared with ledger view; portal is never added to supported"
    latest = [
        _instant(events[d.allocation.event_id].event_time)
        for d in supported_d
        if d.allocation.event_id in events
    ]
    if cutoff is not None and any(t is not None and t > cutoff for t in latest):
        issues.append(
            _issue(
                "STALE_SNAPSHOT",
                "WARNING",
                f"Portal cut-off for {bucket.bucket_id} precedes supported ledger events; "
                "the delta compares different dates",
                [record_ref(chosen)],
            )
        )
        note += "; cut-off precedes ledger events"
    token = hashlib.sha256(
        canonical_json_bytes([universe.snapshot_id, bucket.bucket_id, chosen.record_revision_id])
    ).hexdigest()
    comparison = PortalComparison(
        comparison_id=f"comparison:{token[:24]}",
        bucket_id=bucket.bucket_id,
        balance_observation_id=chosen.balance_observation_id,
        portal_reported=reported,
        ledger_supported=ledger,
        delta=delta,
        source_capture_time=chosen.source_capture_time,
        business_cutoff=chosen.business_cutoff,
        note=note,
    )
    return reported, comparison, issues


def _aggregate(states: list[CheckState]) -> CheckState:
    if not states:
        return "NOT_EVALUATED"
    if "FAIL" in states:
        return "FAIL"
    if "UNKNOWN" in states:
        return "UNKNOWN"
    return "PASS"


def _rule_states(
    universe: Universe,
    decisions: list[Decision],
    events: dict[str, CertificateEvent],
    allocation_checks: list[AllocationCheck],
    scoped: dict[str, ObligationBucket],
) -> dict[str, tuple[CheckState, str]]:
    """Evaluated S04 eligibility conditions; anything without evidence stays NOT_EVALUATED."""
    out: dict[str, tuple[CheckState, str]] = {}
    for rule, label in (("LIFECYCLE", "credit lifecycle"), ("CAPABILITY", "recycler capability")):
        mine = [c for c in allocation_checks if c.rule == rule]
        reasons = sorted({c.reason for c in mine if c.state != "PASS"})
        out[rule] = (
            _aggregate([c.state for c in mine]),
            "; ".join(reasons)
            if reasons
            else (
                f"{label} checked for {len(mine)} allocation(s)"
                if mine
                else f"No evidence to test {label}"
            ),
        )
    live = [d for d in decisions if d.state in {"INCLUDED", "PENDING"}]
    pairs = []
    registrations = []
    for d in live:
        event = events.get(d.allocation.event_id)
        bucket = scoped.get(d.allocation.bucket_id)
        if event is None or bucket is None or event.from_entity_id is None:
            continue
        pairs.append((bucket.producer_entity_id, event.from_entity_id))
        for reg in universe.active(Registration):
            if reg.entity_id == event.from_entity_id:
                registrations.append(registration_finding(reg, span(event.event_time)))
    if universe.active(Entity) and pairs:
        findings = [f for pair in sorted(set(pairs)) for f in party_findings(universe, *pair)]
        reasons = sorted({f.reason for f in findings if f.state != "PASS"})
        out["ENTITY"] = (
            _aggregate([f.state for f in findings]),
            "; ".join(reasons) if reasons else "Producer and recycler roles confirmed",
        )
    if registrations:
        reasons = sorted({f.reason for f in registrations if f.state != "PASS"})
        out["REGISTRATION"] = (
            _aggregate([f.state for f in registrations]),
            "; ".join(reasons) if reasons else "Recycler registrations valid at transfer time",
        )
    return out


def _finish(
    universe,
    profile,
    requested,
    scoped,
    all_buckets,
    decisions: list[Decision],
    commercial_map,
    chosen_balances,
    lots,
    lot_checks,
    priority_checks,
    allocation_checks: list[AllocationCheck],
    comparisons,
    bucket_results,
    derivations,
    analyzed,
    overall: Coverage,
    issues: list[Issue],
) -> EngineOutput:
    for d in decisions:
        if d.conservation_fault:
            overall = "BLOCKED"
    seen = set()
    for d in decisions:
        for code in dict.fromkeys(d.codes):
            if code == "OVER_ALLOCATION" and d.conservation_fault:
                key = (code, d.reason, d.allocation.credit_lot_id)
                if key in seen:
                    continue
                seen.add(key)
                issues.append(_issue(code, "BLOCKING", d.reason, [record_ref(d.allocation)]))
            elif code == "LIABILITY_PRIORITY_UNRESOLVED":
                issues.append(
                    _issue(
                        code,
                        "WARNING",
                        "Earlier-liability order cannot be established",
                        [record_ref(d.allocation)],
                    )
                )
            elif code == "EARLIER_LIABILITY_UNMET":
                issues.append(_issue(code, "WARNING", d.reason, [record_ref(d.allocation)]))
            else:
                issues.append(_issue(code, "WARNING", d.reason, [record_ref(d.allocation)]))
                overall = _worse(overall, "QUALIFIED")
    if not analyzed:
        overall = "BLOCKED"
        issues.append(_issue("INCOMPLETE_COVERAGE", "BLOCKING", "No bucket could be analyzed"))
    elif set(requested) != set(scoped):
        issues.append(
            _issue(
                "INCOMPLETE_COVERAGE",
                "INFO",
                "Only some in-scope buckets were requested; this is not a whole-case result",
            )
        )
    events = {e.event_id: e for e in universe.active(CertificateEvent)}
    evaluated = _rule_states(universe, decisions, events, allocation_checks, scoped)
    eligibility = []
    for rule in profile.eligibility_rules:
        if rule.testability == "UNAVAILABLE":
            state, reason = (
                "NOT_EVALUATED",
                "Deadline or condition is unavailable in the approved profile",
            )
        elif rule.condition in evaluated:
            state, reason = evaluated[rule.condition]
        else:
            state, reason = (
                "NOT_EVALUATED",
                "Needs source facts or applicability review (H05/H07) beyond the pinned records",
            )
        eligibility.append(
            EligibilityOutcome(
                condition=rule.condition,
                testability=rule.testability,
                state=state,
                reason=reason,
            )
        )
        if state == "FAIL" and rule.condition in {"ENTITY", "REGISTRATION"}:
            overall = _worse(overall, "QUALIFIED")
            issues.append(_issue("AMBIGUOUS_IDENTITY", "WARNING", f"{rule.condition}: {reason}"))
    if any(rule.testability == "UNAVAILABLE" for rule in profile.eligibility_rules):
        overall = _worse(overall, "QUALIFIED")
        issues.append(
            _issue(
                "APPLICABILITY_UNRESOLVED",
                "WARNING",
                "Profile declares eligibility conditions unavailable; results are qualified",
            )
        )
    ceiling_reason = (
        "Policy is "
        + profile.purchase_ceiling_policy.state
        + "; no ceiling arithmetic is performed by the baseline reconciliation"
    )
    derivation = Derivation(
        tool_version=TOOL_VERSION,
        snapshot_id=universe.snapshot_id,
        membership_digest=universe.digest,
        profile_id=profile.profile_id,
        profile_digest=profile.digest,
        requested_bucket_ids=requested,
        buckets=derivations,
        lots=lot_checks,
        priority_checks=priority_checks,
        allocation_checks=allocation_checks,
        portal_comparisons=comparisons,
        eligibility=eligibility,
        purchase_ceiling="NOT_EVALUATED",
        purchase_ceiling_reason=ceiling_reason,
        unsupported_features=list(profile.unsupported_features),
        coverage=overall,
    )
    dispositions = _dispositions(
        universe, requested, scoped, all_buckets, decisions, commercial_map, chosen_balances, lots
    )
    return EngineOutput(bucket_results, dispositions, derivation, issues, overall, analyzed)


def _dispositions(
    universe, requested, scoped, all_buckets, decisions, commercial_map, chosen_balances, lots
) -> list[QuantityDisposition]:
    by_revision = {d.allocation.record_revision_id: d for d in decisions}
    events = {e.event_id: e for e in universe.active(CertificateEvent)}
    parties = {b.producer_entity_id for b in scoped.values()}
    parties |= {
        events[d.allocation.event_id].from_entity_id
        for d in decisions
        if d.allocation.event_id in events and events[d.allocation.event_id].from_entity_id
    }
    output: list[QuantityDisposition] = []
    for record in universe.records:
        quantity = None
        bucket_id = None
        if record.record_revision_id in universe.superseded:
            state, reason = "EXCLUDED", "Superseded revision kept as history"
        elif record.record_id in universe.ambiguous_ids:
            state, reason = "EXCLUDED", "Several active revisions of one record; none is trusted"
        elif record.record_type == "Allocation":
            d = by_revision[record.record_revision_id]
            state, reason, quantity, bucket_id = (
                d.state,
                d.reason,
                record.quantity,
                record.bucket_id,
            )
        elif record.record_type == "ObligationBucket":
            quantity = record.target
            if record.bucket_id not in scoped:
                state, reason = "OUT_OF_SCOPE", "Bucket is outside the profile's metals or identity"
            elif record.bucket_id in requested or not requested:
                state, reason = "INCLUDED", "Obligation target and reviewed adjustments"
            else:
                state, reason = (
                    "OUT_OF_SCOPE",
                    "Not requested for output; still used for conservation",
                )
            bucket_id = record.bucket_id
        elif record.record_type == "AccountBalanceObservation":
            quantity, bucket_id = record.reported_supported, record.bucket_id
            if record.balance_observation_id in chosen_balances:
                state, reason = "INCLUDED", "Comparison view only; never added to supported"
            else:
                state, reason = (
                    "EXCLUDED",
                    "Comparison-only observation not selected for this bucket",
                )
        elif record.record_type == "CommercialRecord":
            quantity = record.credit_quantity
            outcome: CommercialOutcome | None = commercial_map.get(record.commercial_id)
            bucket_id = None if outcome is None else outcome.bucket_id
            reason = "Not a payable credit record" if outcome is None else outcome.reason
            if outcome is None or outcome.state in {"CONTEXT", "UNRESOLVED_LINK", "LINKED"}:
                state = "OUT_OF_SCOPE"
            elif outcome.state == "MISMATCH":
                state = "EXCLUDED"
            else:  # COUNTED, UNPLACED, AMBIGUOUS: payable credit not yet transferred
                state = "PENDING"
        elif record.record_type == "CertificateEvent":
            quantity = record.quantity
            if record.assertion_state == "SUPPORTED":
                state, reason = (
                    "INCLUDED",
                    "Supported event bounding allocations; not itself summed",
                )
            elif record.assertion_state == "CONFLICTING":
                state, reason = "EXCLUDED", "Conflicting event assertion"
            else:
                state, reason = "PENDING", "Event eligibility is unresolved"
        elif record.record_type == "Certificate":
            quantity = record.face_quantity
            state = (
                "INCLUDED"
                if any(lot.certificate_id == record.certificate_id for lot in lots.values())
                else "OUT_OF_SCOPE"
            )
            reason = (
                "Defines lot capacity"
                if state == "INCLUDED"
                else "No lot is derived from this certificate"
            )
        elif record.record_type in {"Entity", "Registration"}:
            party = record.entity_id in parties
            state = "INCLUDED" if party else "OUT_OF_SCOPE"
            reason = (
                "Party to an analyzed allocation; role and registration are checked, not summed"
                if party
                else "Not a party to any analyzed allocation"
            )
        elif record.record_type in {"ProductMapping", "SalesRecord"}:
            state, reason = "OUT_OF_SCOPE", "Product reference data; never summed into quantities"
        else:  # pragma: no cover - the Record union is closed
            state, reason = "OUT_OF_SCOPE", "Unclassified record type"
        output.append(
            QuantityDisposition(
                record_id=record.record_id,
                record_revision_id=record.record_revision_id,
                record_type=record.record_type,
                state=state,
                quantity=quantity,
                allocated_bucket_id=bucket_id,
                reason=reason,
                evidence_refs=[record_ref(record)],
            )
        )
    return output
