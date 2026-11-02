"""Entity, registration and recycler-capability checks (F05, F10).

Unknown is not false: missing, unreviewed or undated evidence is UNKNOWN. FAIL needs an
affirmative conflict. Names are never fuzzy-matched; only confirmed identifiers and reviewed,
dated aliases establish that two parties are the same.
"""

from datetime import UTC, date, datetime, time

from recycleguard.contracts.core import EvidenceRef
from recycleguard.contracts.domain import (
    Certificate,
    CertificateEvent,
    Entity,
    ObligationBucket,
    ProductMapping,
    Registration,
    ReviewedInterval,
)
from recycleguard.domain.allocation import Decision
from recycleguard.domain.chronology import Span, span
from recycleguard.domain.models import AllocationCheck
from recycleguard.domain.refs import Finding, record_ref
from recycleguard.domain.universe import Universe

_ENDED = {"REVOKED", "SUSPENDED", "CANCELLED", "CANCELED", "EXPIRED", "LAPSED"}


def _day(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def interval_state(interval: ReviewedInterval, when: Span | None) -> tuple[str, str]:
    """PASS/FAIL/UNKNOWN for a half-open reviewed interval against a time span."""
    if interval.review_state != "APPROVED":
        return "UNKNOWN", "validity interval is not reviewed"
    if interval.start is None:
        return "UNKNOWN", "validity start is unknown"
    if interval.end is None and not interval.end_open_ended:
        return "UNKNOWN", "validity end is unknown"
    if when is None:
        return "UNKNOWN", "no reference time to test validity against"
    start = _day(interval.start)
    if when[1] <= start:
        return "FAIL", "not yet valid at the reference time"
    if interval.end is not None:
        end = _day(interval.end)
        if when[0] >= end:
            return "FAIL", "validity had ended at the reference time"
        if when[1] > end:
            return "UNKNOWN", "reference time straddles the end of validity"
    if when[0] < start:
        return "UNKNOWN", "reference time straddles the start of validity"
    return "PASS", "valid at the reference time"


def registration_finding(registration: Registration, when: Span | None) -> Finding:
    refs = (registration.record_id,)
    status = registration.status_assertion.strip().upper()
    if status in _ENDED:
        return Finding(
            (registration.record_id,),
            "FAIL",
            "CAPABILITY_MISMATCH",
            f"Registration status is {status}",
            refs,
        )
    state, reason = interval_state(registration.validity, when)
    return Finding(
        (registration.record_id,),
        state,  # type: ignore[arg-type]
        "CAPABILITY_MISMATCH" if state == "FAIL" else None,
        f"Registration {registration.registration_ref}: {reason}",
        refs,
    )


def code_covers(covered: str, producer: str) -> bool:
    """Exact code match, or a purely alphabetic category code covering its numbered items.

    A registration for category "ITEW" covers the producer item code "ITEW15"; a numbered or
    punctuated code such as "EEE-1" covers only itself. Matching is case-sensitive and never fuzzy.
    """
    if covered == producer:
        return True
    suffix = producer[len(covered) :]
    return covered.isalpha() and producer.startswith(covered) and suffix.isdigit()


def capability_finding(
    universe: Universe, recycler_id: str, producer_id: str, when: Span | None
) -> Finding:
    """Does an in-force registration of the recycler cover the producer's EEE categories?"""
    targets = (recycler_id, producer_id)
    registrations = [r for r in universe.active(Registration) if r.entity_id == recycler_id]
    codes = sorted(
        {m.eee_code for m in universe.active(ProductMapping) if m.entity_id == producer_id}
    )
    if not registrations:
        return Finding(targets, "UNKNOWN", None, "No registration evidence for the recycler")
    if not codes:
        return Finding(targets, "UNKNOWN", None, "Producer EEE categories are not mapped")
    findings = [registration_finding(r, when) for r in registrations]
    in_force = [r for r, f in zip(registrations, findings, strict=True) if f.state == "PASS"]
    refs = tuple(sorted(r.record_id for r in registrations))
    if not in_force:
        if any(f.state == "UNKNOWN" for f in findings):
            return Finding(targets, "UNKNOWN", None, "Registration validity is unresolved", refs)
        return Finding(targets, "FAIL", "CAPABILITY_MISMATCH", "No registration is in force", refs)
    covered = {code for r in in_force for code in r.covered_eee_codes}
    missing = [c for c in codes if not any(code_covers(k, c) for k in covered)]
    values = (("producer_eee_codes", ",".join(codes)), ("covered", ",".join(sorted(covered))))
    if not missing:
        return Finding(
            targets, "PASS", None, "Every producer EEE category is covered", refs, values
        )
    if len(missing) == len(codes):
        return Finding(
            targets,
            "FAIL",
            "CAPABILITY_MISMATCH",
            "Recycler registration covers none of the producer's EEE categories",
            refs,
            values,
        )
    return Finding(
        targets,
        "UNKNOWN",
        None,
        f"Recycler covers only some producer categories (missing {', '.join(missing)})",
        refs,
        values,
    )


def apply_capability(
    decisions: list[Decision],
    universe: Universe,
    events: dict[str, CertificateEvent],
    certificates: dict[str, Certificate],
    buckets: dict[str, ObligationBucket],
) -> list[AllocationCheck]:
    """F10: demote credits from a recycler not registered for the producer's categories.

    Applies only when the snapshot holds both registration and product-mapping evidence. With
    either missing the rule cannot be tested, so it is reported NOT_EVALUATED and nothing changes
    (the standalone CHECK_CAPABILITY tool still answers UNKNOWN for that pair).
    """
    if not universe.active(Registration) or not universe.active(ProductMapping):
        return []
    checks: list[AllocationCheck] = []
    for d in sorted(decisions, key=lambda x: x.allocation.allocation_id):
        if d.state not in {"INCLUDED", "PENDING"}:
            continue
        event = events.get(d.allocation.event_id)
        bucket = buckets.get(d.allocation.bucket_id)
        if event is None or bucket is None:
            continue
        certificate = certificates.get(event.certificate_id)
        recycler = event.from_entity_id or (
            None if certificate is None else certificate.issuer_entity_id
        )
        if recycler is None:
            continue
        finding = capability_finding(
            universe, recycler, bucket.producer_entity_id, span(event.event_time)
        )
        checks.append(
            AllocationCheck(
                rule="CAPABILITY",
                allocation_id=d.allocation.allocation_id,
                state=finding.state,
                code=finding.code,
                reason=finding.reason,
                evidence_refs=[record_ref(d.allocation)]
                + [
                    EvidenceRef(
                        ref_kind="RECORD", ref_id=r, artifact_revision_id=None, locator=None
                    )
                    for r in finding.refs
                ],
            )
        )
        if finding.state == "FAIL":
            d.state, d.reason = "EXCLUDED", finding.reason
            d.codes.append("CAPABILITY_MISMATCH")
        elif finding.state == "UNKNOWN":
            d.open_checks.append(f"capability: {finding.reason}")
    return checks


def identity_finding(
    universe: Universe, left_id: str, right_id: str, when: Span | None = None
) -> Finding:
    entities = {e.entity_id: e for e in universe.active(Entity)}
    targets = (left_id, right_id)
    left, right = entities.get(left_id), entities.get(right_id)
    if left is None or right is None:
        return Finding(targets, "UNKNOWN", "MISSING_ARTIFACT", "An entity is not in the snapshot")
    refs = (left.record_id, right.record_id)
    if left_id == right_id:
        return Finding(targets, "PASS", None, "Same entity record", refs)
    same: list[str] = []
    for a in left.identifiers:
        for b in right.identifiers:
            if a.kind != b.kind:
                continue
            if a.validation_state != "VALID" or b.validation_state != "VALID":
                return Finding(
                    targets,
                    "UNKNOWN",
                    "UNCONFIRMED_IDENTIFIER",
                    f"A {a.kind} identifier is not confirmed",
                    refs,
                )
            if a.value != b.value:
                return Finding(
                    targets,
                    "FAIL",
                    "AMBIGUOUS_IDENTITY",
                    f"Distinct confirmed {a.kind} identifiers; name overlap is not identity",
                    refs,
                )
            same.append(a.kind)
    if same:
        return Finding(targets, "PASS", None, f"Shared confirmed {', '.join(sorted(same))}", refs)
    name = right.legal_name.casefold()
    for alias in left.aliases:
        if alias.alias.casefold() == name:
            state, reason = interval_state(alias.interval, when)
            return Finding(targets, state, None, f"Dated alias: {reason}", refs)  # type: ignore[arg-type]
    return Finding(
        targets,
        "UNKNOWN",
        "AMBIGUOUS_IDENTITY",
        "No comparable confirmed identifier or reviewed alias; names are not matched",
        refs,
    )


def party_findings(universe: Universe, producer_id: str, recycler_id: str) -> list[Finding]:
    """Entity roles for one transfer: the producer must be a producer, the issuer a recycler."""
    entities = {e.entity_id: e for e in universe.active(Entity)}
    out: list[Finding] = []
    for entity_id, want, label in (
        (producer_id, {"PRODUCER"}, "producer"),
        (recycler_id, {"RECYCLER"}, "recycler"),
    ):
        entity = entities.get(entity_id)
        if entity is None:
            out.append(
                Finding((entity_id,), "UNKNOWN", "MISSING_ARTIFACT", f"{label} entity is absent")
            )
        elif not entity.roles:
            out.append(
                Finding(
                    (entity_id,),
                    "UNKNOWN",
                    None,
                    f"{label} has no stated role",
                    (entity.record_id,),
                )
            )
        elif want & set(entity.roles):
            out.append(
                Finding((entity_id,), "PASS", None, f"{label} role confirmed", (entity.record_id,))
            )
        else:
            out.append(
                Finding(
                    (entity_id,),
                    "FAIL",
                    "AMBIGUOUS_IDENTITY",
                    f"Entity is not recorded as a {label}",
                    (entity.record_id,),
                )
            )
    return out


__all__ = [
    "capability_finding",
    "code_covers",
    "identity_finding",
    "interval_state",
    "party_findings",
    "registration_finding",
    "span",
]
