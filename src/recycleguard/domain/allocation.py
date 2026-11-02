"""Allocation validity and conservation. Checks only ever demote; nothing is promoted."""

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from recycleguard.contracts.core import ErrorCode
from recycleguard.contracts.domain import Allocation, CertificateEvent, ObligationBucket
from recycleguard.domain.arith import signed, to_kg, total
from recycleguard.domain.lots import Lot
from recycleguard.domain.models import LotCheck

AllocState = Literal["INCLUDED", "PENDING", "EXCLUDED"]


@dataclass
class Decision:
    allocation: Allocation
    kg: Decimal
    state: AllocState
    reason: str
    codes: list[ErrorCode] = field(default_factory=list)
    # A conservation fault makes the bucket's supported figure untrustworthy, not just lower.
    conservation_fault: bool = False
    # S04 rules that returned UNKNOWN: the allocation keeps its state but the bucket is qualified.
    open_checks: list[str] = field(default_factory=list)


def _exclude(decision: Decision, reason: str, code: ErrorCode, *, fault: bool = False):
    decision.state = "EXCLUDED"
    decision.reason = reason
    decision.codes.append(code)
    decision.conservation_fault = decision.conservation_fault or fault


def _pend(decision: Decision, reason: str, code: ErrorCode | None = None):
    decision.state = "PENDING"
    decision.reason = reason
    if code is not None:
        decision.codes.append(code)


def _initial(
    allocation: Allocation,
    bucket: ObligationBucket | None,
    event: CertificateEvent | None,
    lot: Lot | None,
    profile_id: str,
) -> Decision:
    kg = to_kg(allocation.quantity)
    decision = Decision(allocation, kg, "INCLUDED", "Supported allocation passing every check")
    if allocation.state == "REJECTED":
        _exclude(decision, "Allocation state is REJECTED; preserved as history", "INTEGRITY_FAILED")
        decision.codes.clear()
        return decision
    if bucket is None:
        _exclude(decision, "Bucket is not in the pinned snapshot", "MISSING_ARTIFACT")
        return decision
    if allocation.profile_id != bucket.profile_id or allocation.profile_id != profile_id:
        _exclude(
            decision,
            "Allocation profile differs from bucket or requested profile",
            "UNSUPPORTED_PROFILE",
        )
        return decision
    if kg <= 0 or allocation.quantity.metal != bucket.metal:
        _exclude(
            decision,
            "Allocation quantity is not positive or metal differs from bucket",
            "DIMENSION_MISMATCH",
        )
        return decision
    if event is not None:
        if event.credit_lot_id != allocation.credit_lot_id:
            _exclude(decision, "Event belongs to a different credit lot", "INTEGRITY_FAILED")
        elif event.event_kind != "TRANSFERRED" or event.quantity.metal != bucket.metal:
            _exclude(decision, "Event is not a transfer of the bucket metal", "DIMENSION_MISMATCH")
        elif event.to_entity_id != bucket.producer_entity_id:
            _exclude(decision, "Event recipient is not the bucket producer", "AMBIGUOUS_IDENTITY")
        if decision.state == "EXCLUDED":
            return decision
    # Violations are settled; what remains is uncertainty, which is PENDING and never zero.
    if allocation.state == "PENDING":
        decision.state, decision.reason = (
            "PENDING",
            "Supplied allocation claim is not yet supported",
        )
    elif event is None:
        _pend(decision, "Referenced event is not in the pinned snapshot", "MISSING_ARTIFACT")
    elif event.assertion_state == "CONFLICTING":
        _pend(decision, "Referenced event has conflicting assertions", "AMBIGUOUS_EVENT")
    elif event.assertion_state != "SUPPORTED" or event.transfer_stage not in {None, "COMPLETED"}:
        _pend(decision, "Referenced event is not a supported completed transfer", "AMBIGUOUS_EVENT")
    elif lot is None:
        _pend(decision, "Credit lot cannot be resolved from a certificate", "MISSING_ARTIFACT")
    elif lot.state != "SUPPORTED":
        _pend(decision, f"Credit lot is {lot.state}: {lot.reason}", "AMBIGUOUS_EVENT")
    return decision


def decide_allocations(
    allocations: list[Allocation],
    buckets: dict[str, ObligationBucket],
    events: dict[str, CertificateEvent],
    lots: dict[str, Lot],
    profile_id: str,
    prechecks: Callable[[list[Decision]], None] | None = None,
) -> list[Decision]:
    decisions = [
        _initial(
            a,
            buckets.get(a.bucket_id),
            events.get(a.event_id),
            lots.get(a.credit_lot_id),
            profile_id,
        )
        for a in allocations
    ]
    if prechecks is not None:
        # Lifecycle/capability demotions run first so ended credits never consume event capacity.
        prechecks(decisions)
    _enforce_event_caps(decisions, events)
    return decisions


def _enforce_event_caps(decisions: list[Decision], events: dict[str, CertificateEvent]):
    by_event: dict[str, list[Decision]] = {}
    for d in decisions:
        if d.state == "INCLUDED":
            by_event.setdefault(d.allocation.event_id, []).append(d)
    for event_id, group in by_event.items():
        event = events.get(event_id)
        if event is not None and total(d.kg for d in group) > to_kg(event.quantity):
            for d in group:
                _exclude(
                    d,
                    "Supported allocations exceed the event quantity; excess cannot be identified",
                    "OVER_ALLOCATION",
                    fault=True,
                )


def enforce_lot_caps(decisions: list[Decision], lots: dict[str, Lot]) -> list[LotCheck]:
    """Lot-level conservation across every event, bucket and year; returns one check per lot."""
    checks: list[LotCheck] = []
    lot_ids = sorted(set(lots) | {d.allocation.credit_lot_id for d in decisions})
    for lot_id in lot_ids:
        lot = lots.get(lot_id)
        mine = [d for d in decisions if d.allocation.credit_lot_id == lot_id]
        supported = [d for d in mine if d.state == "INCLUDED"]
        observed = [d for d in mine if d.state in {"INCLUDED", "PENDING"}]
        if lot is None or lot.capacity is None:
            conservation, reason, capacity = "UNKNOWN", "Lot capacity cannot be established", None
        else:
            capacity = lot.capacity
            if total(d.kg for d in supported) > capacity:
                conservation = "FAIL"
                reason = "Supported allocations exceed lot capacity; excess cannot be identified"
                for d in supported:
                    _exclude(d, reason, "OVER_ALLOCATION", fault=True)
            elif total(d.kg for d in observed) > capacity:
                conservation = "UNKNOWN"
                reason = "Supported fits, but supported plus pending would exceed lot capacity"
            else:
                conservation, reason = "PASS", "Active allocations fit within lot capacity"
        remaining = [d for d in mine if d.state == "INCLUDED"]
        metal = (lot.metal if lot is not None else None) or (
            mine[0].allocation.quantity.metal if mine else None
        )
        checks.append(
            LotCheck(
                credit_lot_id=lot_id,
                certificate_id=None if lot is None else lot.certificate_id,
                resolution_state="PENDING" if lot is None else lot.state,
                capacity=None if capacity is None or metal is None else signed(capacity, metal),
                supported_allocated=None
                if metal is None
                else signed(total(d.kg for d in remaining), metal),
                observed_allocated=None
                if metal is None
                else signed(total(d.kg for d in observed), metal),
                conservation=conservation,
                reason=reason,
            )
        )
    return checks


__all__ = ["Decision", "decide_allocations", "enforce_lot_caps"]
