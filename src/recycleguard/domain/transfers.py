"""Transfer shapes that share one instrument. Both are reported only: nothing is merged or counted.

An overlapping copy is two transfers of one lot with the same exact quantity, metal and recipient
whose recorded times can denote the same moment, at least one of them unsupported. A shared
instrument is several supported transfers of one certificate at distinct, ordered times. The
supported transfers of the two never coincide: overlapping times can never be distinct tranches.
A certificate with an overlap that is still unresolved is reported as the overlap only.
"""

from itertools import combinations

from recycleguard.contracts.domain import CertificateEvent
from recycleguard.domain.arith import to_kg
from recycleguard.domain.chronology import span, span_before
from recycleguard.domain.universe import Universe


def _transfers(universe: Universe) -> list[CertificateEvent]:
    return sorted(
        (e for e in universe.active(CertificateEvent) if e.event_kind == "TRANSFERRED"),
        key=lambda e: e.event_id,
    )


def overlapping_transfers(universe: Universe) -> list[tuple[CertificateEvent, CertificateEvent]]:
    """Pairs that may be one transfer observed twice. Equivalence is never inferred from them."""
    groups: dict[str, list[CertificateEvent]] = {}
    for event in _transfers(universe):
        groups.setdefault(event.credit_lot_id or event.certificate_id, []).append(event)
    pairs = []
    for group in groups.values():
        for left, right in combinations(group, 2):
            if left.assertion_state == right.assertion_state == "SUPPORTED":
                continue
            if (to_kg(left.quantity), left.quantity.metal) != (
                to_kg(right.quantity),
                right.quantity.metal,
            ):
                continue
            if left.to_entity_id is None or left.to_entity_id != right.to_entity_id:
                continue
            spans = span(left.event_time), span(right.event_time)
            if None in spans or span_before(*spans) is not None:
                continue
            pairs.append((left, right))
    return pairs


def _repeats(copy: CertificateEvent, transfer: CertificateEvent) -> bool:
    """An unsupported record is another observation of a supported transfer, not a new one.

    It must carry the same exact quantity and metal, name no other recipient, and either repeat
    the transfer's external reference or have a time that can denote the same moment.
    """
    if (to_kg(copy.quantity), copy.quantity.metal) != (
        to_kg(transfer.quantity),
        transfer.quantity.metal,
    ):
        return False
    if None not in (copy.to_entity_id, transfer.to_entity_id) and (
        copy.to_entity_id != transfer.to_entity_id
    ):
        return False
    if copy.external_event_ref and copy.external_event_ref == transfer.external_event_ref:
        return True
    spans = span(copy.event_time), span(transfer.event_time)
    return None not in spans and span_before(*spans) is None


def shared_instrument_transfers(universe: Universe) -> dict[str, list[CertificateEvent]]:
    """Certificates whose several supported transfers are distinct events at ordered times.

    Unsupported records that repeat one of those transfers (an export row of a portal transfer)
    are set aside as observations of it. Any other unsupported transfer leaves the certificate
    unresolved, so it is not reported.
    """
    groups: dict[str, list[CertificateEvent]] = {}
    for event in _transfers(universe):
        groups.setdefault(event.certificate_id, []).append(event)
    shared = {}
    for certificate_id, all_events in sorted(groups.items()):
        group = [e for e in all_events if e.assertion_state == "SUPPORTED"]
        others = [e for e in all_events if e.assertion_state != "SUPPORTED"]
        if len(group) < 2 or not all(any(_repeats(o, e) for e in group) for o in others):
            continue
        references = [e.external_event_ref for e in group if e.external_event_ref]
        if len(set(references)) != len(references):
            continue
        spans = [span(e.event_time) for e in group]
        if None in spans or any(span_before(a, b) is None for a, b in combinations(spans, 2)):
            continue
        shared[certificate_id] = group
    return shared


__all__ = ["overlapping_transfers", "shared_instrument_transfers"]
