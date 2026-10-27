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
from recycleguard.domain.lots import derive_lots
from recycleguard.domain.models import (
    BucketDerivation,
    Coverage,
    Derivation,
    EligibilityOutcome,
    PortalComparison,
    QuantityDisposition,
)
from recycleguard.domain.priority import evaluate_priority
from recycleguard.domain.universe import Universe
from recycleguard.normalization.units import NumericSafetyError
from recycleguard.storage import canonical_json_bytes

TOOL_VERSION = "c08-s03-0.1"
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


def record_ref(record) -> EvidenceRef:
    return EvidenceRef(
        ref_kind="RECORD", ref_id=record.record_id, artifact_revision_id=None, locator=None
    )


def _issue(code: ErrorCode, severity: str, message: str, refs=None) -> Issue:
    token = hashlib.sha256(canonical_json_bytes([code, message])).hexdigest()[:12]
    return Issue(
        issue_id=f"issue:{code.lower()}_{token}",
        code=code,
        severity=severity,
        message=message,
        field_path=None,
        evidence_refs=list(refs or []),
        retryable=False,
    )


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


def _assign_commercial(
    commercials: list[CommercialRecord], buckets: dict[str, ObligationBucket]
) -> dict[str, tuple[str | None, str]]:
    """Minimal F07 baseline: map a paid-but-unlinked credit quantity to exactly one bucket."""
    candidates: dict[str, list[CommercialRecord]] = {}
    outcome: dict[str, tuple[str | None, str]] = {}
    for record in commercials:
        if record.record_kind not in {"INVOICE", "PAYMENT"} or record.credit_quantity is None:
            outcome[record.record_id] = (
                None,
                "Commercial context without a payable credit quantity",
            )
        elif record.linked_credit_refs:
            outcome[record.record_id] = (None, "Linked to credit references; matching is S04")
        else:
            compatible = [
                b.bucket_id
                for b in buckets.values()
                if b.producer_entity_id == record.recipient_entity_id
                and b.metal == record.credit_quantity.metal
            ]
            if len(compatible) == 1:
                candidates.setdefault(compatible[0], []).append(record)
            else:
                outcome[record.record_id] = (
                    None,
                    "No single compatible bucket; left unassigned rather than guessed",
                )
    for bucket_id, records in candidates.items():
        for record in records:
            if len(records) == 1:
                outcome[record.record_id] = (
                    bucket_id,
                    "Paid or invoiced credits not yet transferred",
                )
            else:
                outcome[record.record_id] = (
                    None,
                    "Several payable records target one bucket; cannot rule out double counting",
                )
    return outcome


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
    lots = derive_lots(universe)
    decisions = decide_allocations(
        universe.active(Allocation), scoped, events, lots, profile.profile_id
    )
    lot_checks = enforce_lot_caps(decisions, lots)
    priority_checks = evaluate_priority(scoped, required, decisions, allocation_order)

    commercials = universe.active(CommercialRecord)
    commercial_map = _assign_commercial(commercials, scoped)

    balances_by_bucket: dict[str, list[AccountBalanceObservation]] = {}
    for balance in universe.active(AccountBalanceObservation):
        balances_by_bucket.setdefault(balance.bucket_id, []).append(balance)

    certificates = {c.certificate_id: c for c in universe.active(Certificate)}
    bucket_results: list[BucketResult] = []
    derivations: list[BucketDerivation] = []
    comparisons: list[PortalComparison] = []
    chosen_balances: set[str] = set()
    analyzed: list[str] = []
    overall: Coverage = "COMPLETE_WITHIN_SCOPE"

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
            c for c in commercials if commercial_map.get(c.record_id, (None, ""))[0] == bucket_id
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
            if code in {"INTEGRITY_FAILED"} and d.conservation_fault:
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
    eligibility = [
        EligibilityOutcome(
            condition=rule.condition,
            testability=rule.testability,
            state="NOT_EVALUATED",
            reason="Deadline or condition is unavailable in the approved profile"
            if rule.testability == "UNAVAILABLE"
            else "Eligibility evaluation belongs to S04/H05, not the baseline reconciliation",
        )
        for rule in profile.eligibility_rules
    ]
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
    output: list[QuantityDisposition] = []
    for record in universe.records:
        quantity = None
        bucket_id = None
        if record.record_revision_id in universe.superseded:
            state, reason = "EXCLUDED", "Superseded revision kept as history"
        elif record.record_id in universe.ambiguous_ids:
            state, reason = "EXCLUDED", "Several active revisions of one record; none is trusted"
        elif isinstance(record, Allocation):
            d = by_revision[record.record_revision_id]
            state, reason, quantity, bucket_id = (
                d.state,
                d.reason,
                record.quantity,
                record.bucket_id,
            )
        elif isinstance(record, ObligationBucket):
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
        elif isinstance(record, AccountBalanceObservation):
            quantity, bucket_id = record.reported_supported, record.bucket_id
            if record.balance_observation_id in chosen_balances:
                state, reason = "INCLUDED", "Comparison view only; never added to supported"
            else:
                state, reason = (
                    "EXCLUDED",
                    "Comparison-only observation not selected for this bucket",
                )
        elif isinstance(record, CommercialRecord):
            quantity = record.credit_quantity
            target, why = commercial_map.get(
                record.record_id, (None, "Not a payable credit record")
            )
            bucket_id = target
            payable = record.record_kind in {"INVOICE", "PAYMENT"} and quantity is not None
            state = "PENDING" if payable and not record.linked_credit_refs else "OUT_OF_SCOPE"
            reason = why
        elif isinstance(record, CertificateEvent):
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
        elif isinstance(record, Certificate):
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
        elif isinstance(record, (Entity, Registration)):
            state, reason = "OUT_OF_SCOPE", "Identity or registration context; checked by S04"
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
