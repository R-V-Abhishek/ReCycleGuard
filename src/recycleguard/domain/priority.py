"""Earlier-liability priority, checked at allocation time (SYSTEM_DESIGN §6.2).

Order comes from an explicit ordering input or an allocation's own reviewed allocation_time
(see `Chronology`). Without either the outcome is UNKNOWN: end-of-year totals and transfer
times are never used to infer what happened at allocation time.
"""

from decimal import Decimal

from recycleguard.contracts.domain import ObligationBucket
from recycleguard.domain.allocation import Decision
from recycleguard.domain.arith import subtract, total
from recycleguard.domain.chronology import Chronology
from recycleguard.domain.models import CheckState, PriorityCheck


def _year(bucket: ObligationBucket) -> int:
    return int(bucket.liability_year.split("-")[0])


def evaluate_priority(
    buckets: dict[str, ObligationBucket],
    required: dict[str, Decimal],
    decisions: list[Decision],
    chronology: Chronology,
) -> list[PriorityCheck]:
    """Process buckets oldest first so a later bucket sees earlier buckets' final decisions."""
    checks: list[PriorityCheck] = []
    by_bucket: dict[str, list[Decision]] = {}
    for d in decisions:
        by_bucket.setdefault(d.allocation.bucket_id, []).append(d)
    for bucket in sorted(buckets.values(), key=lambda b: (_year(b), b.bucket_id)):
        earlier = [
            other
            for other in buckets.values()
            if other.producer_entity_id == bucket.producer_entity_id
            and other.metal == bucket.metal
            and other.profile_id == bucket.profile_id
            and _year(other) < _year(bucket)
        ]
        earlier_ids = sorted(b.bucket_id for b in earlier)
        for d in sorted(
            by_bucket.get(bucket.bucket_id, []), key=lambda x: x.allocation.allocation_id
        ):
            if d.state not in {"INCLUDED", "PENDING"}:
                continue
            state, reason = _evaluate(d, earlier, required, by_bucket, chronology)
            checks.append(
                PriorityCheck(
                    allocation_id=d.allocation.allocation_id,
                    bucket_id=bucket.bucket_id,
                    state=state,
                    earlier_bucket_ids=earlier_ids,
                    reason=reason,
                )
            )
            if state == "FAIL":
                d.codes.append("EARLIER_LIABILITY_UNMET")
                if d.state == "INCLUDED":
                    d.state = "EXCLUDED"
                    d.reason = reason
            elif state == "UNKNOWN":
                d.codes.append("LIABILITY_PRIORITY_UNRESOLVED")
    return checks


def _evaluate(
    d: Decision,
    earlier: list[ObligationBucket],
    required: dict[str, Decimal],
    by_bucket: dict[str, list[Decision]],
    chronology: Chronology,
) -> tuple[CheckState, str]:
    if not earlier:
        return (
            "NOT_EVALUATED",
            "No earlier compatible liability was supplied; completeness of history is not "
            "verifiable from this case",
        )
    if any(b.bucket_id not in required for b in earlier):
        return "UNKNOWN", "An earlier compatible liability has an unusable required quantity"
    owing = [b for b in earlier if required[b.bucket_id] > 0]
    if not owing:
        return "PASS", "Every earlier compatible liability is zero"
    mine = d.allocation.allocation_id
    if not chronology.known(mine):
        return (
            "UNKNOWN",
            "An earlier compatible liability exists and allocation order is not recorded",
        )
    outcomes: list[CheckState] = []
    for bucket in owing:
        paid = [x for x in by_bucket.get(bucket.bucket_id, []) if x.state == "INCLUDED"]
        order = [chronology.before(x.allocation.allocation_id, mine) for x in paid]
        if any(o is None for o in order):
            outcomes.append("UNKNOWN")
            continue
        before = total(x.kg for x, o in zip(paid, order, strict=True) if o)
        outstanding = subtract(required[bucket.bucket_id], before)
        outcomes.append("FAIL" if outstanding > 0 else "PASS")
    if "FAIL" in outcomes:
        return (
            "FAIL",
            "An earlier compatible liability was still outstanding when this was allocated",
        )
    if "UNKNOWN" in outcomes:
        return "UNKNOWN", "Allocation order for an earlier liability is incomplete or tied"
    return "PASS", "Earlier compatible liabilities were already met when this was allocated"
