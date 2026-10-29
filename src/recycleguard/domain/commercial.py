"""Commercial matching (F07, T09): a payment or invoice is never a fulfilment allocation.

A payable record linked to a recorded transfer or allocation is evidence about it and adds no
quantity of its own. A payable record with no link, or linked to a transfer that no allocation
uses, is pending credit, placed only when exactly one compatible bucket exists. An invoice and
the payment that references it are one quantity group: counted once, and backed or failed
together. Money is never converted to credit; anything ambiguous stays unplaced and uncounted.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from recycleguard.contracts.core import ErrorCode
from recycleguard.contracts.domain import (
    Allocation,
    Certificate,
    CertificateEvent,
    CommercialRecord,
    ObligationBucket,
)
from recycleguard.domain.arith import to_kg, total
from recycleguard.domain.refs import Finding
from recycleguard.domain.universe import Universe

State = Literal[
    "COUNTED", "LINKED", "MISMATCH", "AMBIGUOUS", "UNRESOLVED_LINK", "CONTEXT", "UNPLACED"
]
Verdict = Literal["PASS", "FAIL", "UNKNOWN"]


@dataclass(frozen=True)
class CommercialOutcome:
    commercial_id: str
    state: State
    bucket_id: str | None
    reason: str
    code: ErrorCode | None = None
    verdict: Verdict = "UNKNOWN"

    def finding(self) -> Finding:
        return Finding((self.commercial_id,), self.verdict, self.code, self.reason)


def _payable(record: CommercialRecord) -> bool:
    return record.record_kind in {"INVOICE", "PAYMENT"} and record.credit_quantity is not None


def _lead(group: list[CommercialRecord]) -> CommercialRecord:
    """The invoice names the buyer as recipient, so it places the group; else the first record."""
    return next((r for r in group if r.record_kind == "INVOICE"), group[0])


def _single_bucket(
    group: list[CommercialRecord], buckets: dict[str, ObligationBucket]
) -> str | None:
    lead = _lead(group)
    assert lead.credit_quantity is not None
    producers = {lead.recipient_entity_id}
    if lead.record_kind == "PAYMENT":  # the payer is the buyer; direction is not fixed by data
        producers.add(lead.issuer_entity_id)
    compatible = [
        b.bucket_id
        for b in buckets.values()
        if b.producer_entity_id in producers and b.metal == lead.credit_quantity.metal
    ]
    return compatible[0] if len(compatible) == 1 else None


class _Index:
    """Resolves a link to the recorded transfer it concerns, from the pinned snapshot only."""

    def __init__(self, universe: Universe):
        self.events = {e.event_id: e for e in universe.active(CertificateEvent)}
        self.allocations = {a.allocation_id: a for a in universe.active(Allocation)}
        self.certificates = {c.certificate_id: c for c in universe.active(Certificate)}
        self.commercial = {c.commercial_id for c in universe.active(CommercialRecord)}
        self.lots: dict[str, list[CertificateEvent]] = {}
        for event in self.events.values():
            if event.credit_lot_id is not None:
                self.lots.setdefault(event.credit_lot_id, []).append(event)
        self.used_events = {a.event_id for a in self.allocations.values()}
        self.used_lots = {a.credit_lot_id for a in self.allocations.values()}

    def resolve(self, ref: str) -> list[CertificateEvent] | None:
        """Transfer events the reference concerns; None if it is not in the snapshot."""
        if ref in self.allocations:
            event = self.events.get(self.allocations[ref].event_id)
            return [] if event is None else [event]
        if ref in self.events:
            return [self.events[ref]]
        if ref in self.lots:
            return list(self.lots[ref])
        if ref in self.certificates:
            return [e for e in self.events.values() if e.certificate_id == ref]
        return None

    def allocated(self, ref: str, event: CertificateEvent) -> bool:
        return (
            ref in self.allocations
            or event.event_id in self.used_events
            or (event.credit_lot_id is not None and event.credit_lot_id in self.used_lots)
        )


def _groups(payable: list[CommercialRecord]) -> list[list[CommercialRecord]]:
    """Union records that reference one another (payment -> invoice) into one quantity group."""
    parent = {r.commercial_id: r.commercial_id for r in payable}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for record in payable:
        for ref in record.linked_credit_refs:
            if ref in parent:
                parent[find(record.commercial_id)] = find(ref)
    grouped: dict[str, list[CommercialRecord]] = {}
    for record in payable:
        grouped.setdefault(find(record.commercial_id), []).append(record)
    return [sorted(g, key=lambda r: r.commercial_id) for _, g in sorted(grouped.items())]


def _mismatch(record: CommercialRecord, code: ErrorCode, reason: str) -> CommercialOutcome:
    return CommercialOutcome(record.commercial_id, "MISMATCH", None, reason, code, "FAIL")


def _parties_agree(record: CommercialRecord, event: CertificateEvent) -> str | None:
    """Reason the parties contradict the transfer, or None. A payment may run either way."""
    sender, receiver = event.from_entity_id, event.to_entity_id
    if record.record_kind == "PAYMENT":
        seen = {record.issuer_entity_id, record.recipient_entity_id}
        expected = {p for p in (sender, receiver) if p is not None}
        return None if len(expected) < 2 or seen == expected else "Payment parties differ"
    if receiver not in {None, record.recipient_entity_id}:
        return "Recipient differs from the linked transfer"
    if sender not in {None, record.issuer_entity_id}:
        return "Issuer differs from the linked transfer"
    return None


def _check_link(
    record: CommercialRecord,
    refs: list[str],
    index: _Index,
    taken: dict[str, dict[str, Decimal]],
    group_key: str,
) -> CommercialOutcome | None:
    """Outcome for a linked record; None means the transfer is unallocated, so it is pending."""
    quantity = record.credit_quantity
    assert quantity is not None
    backed = False
    unallocated = False
    for ref in refs:
        events = index.resolve(ref)
        if events is None:
            continue
        for event in events:
            if event.quantity.metal != quantity.metal:
                return _mismatch(record, "DIMENSION_MISMATCH", "Linked transfer is another metal")
            problem = _parties_agree(record, event)
            if problem is not None:
                return _mismatch(record, "AMBIGUOUS_IDENTITY", problem)
            # One quantity group counts once against the transfer, however many records it has.
            claims = taken.setdefault(event.event_id, {})
            claims[group_key] = to_kg(quantity)
            if total(claims.values()) > to_kg(event.quantity):
                return _mismatch(
                    record, "INTEGRITY_FAILED", "Linked quantity exceeds the transfer quantity"
                )
            backed = True
            unallocated = unallocated or not index.allocated(ref, event)
    if not backed:
        return CommercialOutcome(
            record.commercial_id,
            "UNRESOLVED_LINK",
            None,
            f"Linked reference {', '.join(sorted(refs))} concerns no transfer in the snapshot",
            "MISSING_ARTIFACT",
        )
    if unallocated:
        return None
    return CommercialOutcome(
        record.commercial_id,
        "LINKED",
        None,
        "Backs a recorded allocation; its quantity is counted there, not here",
        verdict="PASS",
    )


def match_commercial(
    universe: Universe, buckets: dict[str, ObligationBucket]
) -> dict[str, CommercialOutcome]:
    records = sorted(universe.active(CommercialRecord), key=lambda r: r.commercial_id)
    index = _Index(universe)
    out: dict[str, CommercialOutcome] = {
        r.commercial_id: CommercialOutcome(
            r.commercial_id,
            "CONTEXT",
            None,
            "Commercial context without a payable credit quantity",
            verdict="PASS",
        )
        for r in records
        if not _payable(r)
    }
    taken: dict[str, dict[str, Decimal]] = {}
    pending: list[list[CommercialRecord]] = []
    for group in _groups([r for r in records if _payable(r)]):
        sizes = {
            (to_kg(r.credit_quantity), r.credit_quantity.metal) for r in group if r.credit_quantity
        }
        if len(sizes) > 1:
            for r in group:
                out[r.commercial_id] = _mismatch(
                    r,
                    "INTEGRITY_FAILED",
                    "Invoice and payment disagree on credit quantity or metal",
                )
            continue
        key = group[0].commercial_id
        paired_only: list[CommercialRecord] = []  # linked only to a commercial partner
        unallocated: list[CommercialRecord] = []  # linked to a transfer no allocation uses
        for record in group:
            refs = [ref for ref in record.linked_credit_refs if ref not in index.commercial]
            if not refs:
                paired_only.append(record)
                continue
            outcome = _check_link(record, refs, index, taken, key)
            if outcome is None:
                unallocated.append(record)
            else:
                out[record.commercial_id] = outcome
        decided = [out[r.commercial_id] for r in group if r.commercial_id in out]
        if any(o.state == "MISMATCH" for o in decided):
            # A rejected group contributes no quantity against a transfer. Retaining its
            # provisional claim would falsely invalidate an unrelated later group.
            for claims in taken.values():
                claims.pop(key, None)
            for r in group:
                if r.commercial_id not in out or out[r.commercial_id].state != "MISMATCH":
                    out[r.commercial_id] = _mismatch(
                        r, "INTEGRITY_FAILED", "A paired record failed its transfer checks"
                    )
            paired_only = []
            unallocated = []
        elif any(o.state == "LINKED" for o in decided) and not unallocated:
            for r in paired_only:
                out[r.commercial_id] = CommercialOutcome(
                    r.commercial_id,
                    "LINKED",
                    None,
                    "Paired with a record that backs a recorded allocation; counted there",
                    verdict="PASS",
                )
            paired_only = []
        waiting = [*paired_only, *unallocated]
        if waiting:
            pending.append(sorted(waiting, key=lambda r: r.commercial_id))
    placed: dict[str, list[list[CommercialRecord]]] = {}
    for group in pending:
        bucket_id = _single_bucket(group, buckets)
        if bucket_id is None:
            for r in group:
                out[r.commercial_id] = CommercialOutcome(
                    r.commercial_id,
                    "UNPLACED",
                    None,
                    "No single compatible bucket; left unassigned rather than guessed",
                )
        else:
            placed.setdefault(bucket_id, []).append(group)
    for bucket_id, groups in placed.items():
        for group in groups:
            lead = _lead(group)
            for r in group:
                if len(groups) > 1:
                    out[r.commercial_id] = CommercialOutcome(
                        r.commercial_id,
                        "AMBIGUOUS",
                        None,
                        "Several payable records target one bucket; double counting not excluded",
                    )
                elif r is lead:
                    out[r.commercial_id] = CommercialOutcome(
                        r.commercial_id,
                        "COUNTED",
                        bucket_id,
                        "Paid or invoiced credits not yet transferred",
                        verdict="PASS",
                    )
                else:
                    out[r.commercial_id] = CommercialOutcome(
                        r.commercial_id,
                        "LINKED",
                        None,
                        "Same quantity as its paired invoice or payment; counted once",
                        verdict="PASS",
                    )
    return out
