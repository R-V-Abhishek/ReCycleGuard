"""Credit lifecycle (F09): an allocation of an expired or cancelled credit is not supported.

Only affirmative evidence demotes. Absence of any expiry/cancellation evidence passes (a limit
the trace states); evidence that cannot be dated or ordered against the allocation is UNKNOWN.
"""

from dataclasses import dataclass
from typing import Literal

from recycleguard.contracts.core import ErrorCode, TemporalValue
from recycleguard.contracts.domain import Allocation, Certificate, CertificateEvent
from recycleguard.domain.allocation import Decision
from recycleguard.domain.chronology import span, span_before
from recycleguard.domain.models import AllocationCheck, CheckState
from recycleguard.domain.refs import Finding, record_ref
from recycleguard.domain.universe import Universe

TerminalKind = Literal["EXPIRED", "CANCELLED"]
_STATUS_WORDS: dict[str, TerminalKind] = {
    "EXPIRED": "EXPIRED",
    "CANCELLED": "CANCELLED",
    "CANCELED": "CANCELLED",
}
_CODES: dict[TerminalKind, ErrorCode] = {
    "EXPIRED": "CREDIT_EXPIRED",
    "CANCELLED": "CREDIT_CANCELLED",
}


@dataclass(frozen=True)
class Terminal:
    kind: TerminalKind
    when: TemporalValue | None
    source_id: str
    supported: bool


@dataclass(frozen=True)
class Verdict:
    state: CheckState
    code: ErrorCode | None
    reason: str
    source_ids: tuple[str, ...]


def terminals(certificate: Certificate, events: list[CertificateEvent]) -> list[Terminal]:
    found = [
        Terminal(
            "EXPIRED" if e.event_kind == "EXPIRED" else "CANCELLED",
            e.event_time,
            e.event_id,
            e.assertion_state == "SUPPORTED",
        )
        for e in events
        if e.event_kind in {"EXPIRED", "CANCELLED"}
    ]
    if certificate.expiry_time is not None:
        found.append(Terminal("EXPIRED", certificate.expiry_time, certificate.certificate_id, True))
    status = _STATUS_WORDS.get((certificate.raw_status or "").strip().upper())
    if status is not None and not any(t.kind == status and span(t.when) for t in found):
        found.append(Terminal(status, None, certificate.certificate_id, True))
    return sorted(found, key=lambda t: (t.kind, t.source_id))


def judge(
    allocation: Allocation,
    transfer: CertificateEvent | None,
    certificate: Certificate,
    certificate_events: list[CertificateEvent],
) -> Verdict:
    facts = terminals(certificate, certificate_events)
    if not facts:
        return Verdict(
            "PASS", None, "No expiry or cancellation evidence in the pinned snapshot", ()
        )
    moved = span(None if transfer is None else transfer.event_time)
    allocated = span(allocation.allocation_time)
    ids = tuple(sorted({f.source_id for f in facts}))
    failed: list[Terminal] = []
    open_reasons: list[str] = []
    for fact in facts:
        ended = span(fact.when)
        if not fact.supported:
            open_reasons.append(f"{fact.kind.lower()} assertion {fact.source_id} is not supported")
        elif ended is None:
            open_reasons.append(f"{fact.kind.lower()} on {fact.source_id} has no usable date")
        elif span_before(ended, moved) is True or span_before(ended, allocated) is True:
            failed.append(fact)
        elif span_before(allocated, ended) is True:
            continue
        else:
            open_reasons.append(
                f"cannot order the allocation against {fact.kind.lower()} on {fact.source_id}"
            )
    if failed:
        first = failed[0]
        return Verdict(
            "FAIL",
            _CODES[first.kind],
            f"Credit was {first.kind.lower()} (evidence {first.source_id}) before it was used",
            ids,
        )
    if open_reasons:
        return Verdict("UNKNOWN", None, "; ".join(open_reasons), ids)
    return Verdict("PASS", None, "Allocated before the credit expired or was cancelled", ids)


def apply_lifecycle(
    decisions: list[Decision],
    certificates: dict[str, Certificate],
    events: dict[str, CertificateEvent],
) -> list[AllocationCheck]:
    """Demote allocations of ended credits; UNKNOWN only flags the bucket for qualification."""
    by_certificate: dict[str, list[CertificateEvent]] = {}
    for event in events.values():
        by_certificate.setdefault(event.certificate_id, []).append(event)
    checks: list[AllocationCheck] = []
    for d in sorted(decisions, key=lambda x: x.allocation.allocation_id):
        if d.state not in {"INCLUDED", "PENDING"}:
            continue
        transfer = events.get(d.allocation.event_id)
        certificate = None if transfer is None else certificates.get(transfer.certificate_id)
        if certificate is None:
            continue
        verdict = judge(
            d.allocation, transfer, certificate, by_certificate[certificate.certificate_id]
        )
        checks.append(
            AllocationCheck(
                rule="LIFECYCLE",
                allocation_id=d.allocation.allocation_id,
                state=verdict.state,
                code=verdict.code,
                reason=verdict.reason,
                evidence_refs=[record_ref(d.allocation), record_ref(certificate)],
            )
        )
        if verdict.state == "FAIL":
            d.state, d.reason = "EXCLUDED", verdict.reason
            d.codes.append(verdict.code)
        elif verdict.state == "UNKNOWN":
            d.open_checks.append(f"lifecycle: {verdict.reason}")
    return checks


def _certificate_of(universe: Universe, subject: str) -> Certificate | None:
    certificates = {c.certificate_id: c for c in universe.active(Certificate)}
    if subject in certificates:
        return certificates[subject]
    for event in universe.active(CertificateEvent):
        if event.event_id == subject:
            return certificates.get(event.certificate_id)
    return None


def history_finding(universe: Universe, subject: str) -> Finding:
    """get_certificate_history: every recorded event, lot and allocation for one certificate."""
    certificate = _certificate_of(universe, subject)
    if certificate is None:
        return Finding(
            (subject,), "UNKNOWN", "MISSING_ARTIFACT", "Certificate is not in the snapshot"
        )
    events = sorted(
        (
            e
            for e in universe.active(CertificateEvent)
            if e.certificate_id == certificate.certificate_id
        ),
        key=lambda e: e.event_id,
    )
    event_ids = {e.event_id for e in events}
    allocations = sorted(
        (a for a in universe.active(Allocation) if a.event_id in event_ids),
        key=lambda a: a.allocation_id,
    )
    ended = terminals(certificate, events)
    values = (
        (
            "events",
            ";".join(
                f"{e.event_id}|{e.event_kind}|{e.assertion_state}|{e.transfer_stage or '-'}"
                for e in events
            ),
        ),
        ("lots", ",".join(sorted({e.credit_lot_id for e in events if e.credit_lot_id}))),
        (
            "allocations",
            ";".join(f"{a.allocation_id}|{a.state}|{a.bucket_id}" for a in allocations),
        ),
        ("terminal", ";".join(f"{t.kind}|{t.source_id}" for t in ended)),
    )
    refs = (certificate.record_id, *sorted(event_ids))
    if any(e.assertion_state != "SUPPORTED" for e in events):
        return Finding(
            (certificate.certificate_id,),
            "UNKNOWN",
            "AMBIGUOUS_EVENT",
            "History includes pending or conflicting event assertions",
            refs,
            values,
        )
    note = (
        "Event history is supported; no expiry or cancellation observed (absence is not proof)"
        if not ended
        else "Event history is supported; terminal evidence is listed"
    )
    return Finding((certificate.certificate_id,), "PASS", None, note, refs, values)


def credit_event_findings(universe: Universe, subject: str) -> list[Finding]:
    """check_credit_events: the lifecycle verdict of each allocation the subject concerns."""
    allocations = universe.active(Allocation)
    events = {e.event_id: e for e in universe.active(CertificateEvent)}
    certificates = {c.certificate_id: c for c in universe.active(Certificate)}
    chosen = [
        a
        for a in allocations
        if a.allocation_id == subject
        or a.event_id == subject
        or (a.event_id in events and events[a.event_id].certificate_id == subject)
    ]
    if not chosen:
        return [Finding((subject,), "UNKNOWN", None, "No allocation concerns this subject")]
    findings = []
    for allocation in sorted(chosen, key=lambda a: a.allocation_id):
        transfer = events.get(allocation.event_id)
        certificate = None if transfer is None else certificates.get(transfer.certificate_id)
        if transfer is None or certificate is None:
            findings.append(
                Finding(
                    (allocation.allocation_id,),
                    "UNKNOWN",
                    "MISSING_ARTIFACT",
                    "Allocation's transfer event or certificate is not in the snapshot",
                )
            )
            continue
        siblings = [e for e in events.values() if e.certificate_id == certificate.certificate_id]
        verdict = judge(allocation, transfer, certificate, siblings)
        findings.append(
            Finding(
                (allocation.allocation_id,),
                verdict.state,
                verdict.code,
                verdict.reason,
                (allocation.record_id, certificate.record_id, *verdict.source_ids),
            )
        )
    return findings
