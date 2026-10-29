"""The six S04 development worlds: one visible effect each for the S04 domain tools.

These are hand-built variants of the S05 clean worlds, not S06 fault recipes: the S04 evidence is
ordinary, dated and contract-valid, and its effect on the supported quantity is stated in the
hidden reference (``hidden.allocation_outcomes``), computed without C08. They use their own
dataset version, so the six S05 dossiers and their hidden record stay untouched.

Every effect is deterministic for a seed: expired and cancelled credits, an invoice paired with
its payment, a recycler registered for the wrong EEE category, a product weight basis conflict,
and an earlier liability whose priority is proven only by allocation time.
"""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from benchmarks.generator.s05_cases import Draft, _completed, _recycler
from benchmarks.generator.world import PRODUCERS, World, kg

DATASET_VERSION = "s04-dev-0.1"


def _draft(template, seed, group, producer, recyclers) -> Draft:
    return Draft(template, seed, group, producer, recyclers, dataset_version=DATASET_VERSION)


def _day(transfer) -> date:
    return date.fromisoformat(transfer.when[:10])


def expired_credit(seed=6101):
    """A credit that expired before it was transferred is allocated; the portal still reports it."""
    d = _draft("expired_credit", seed, "tl:north_q3", PRODUCERS[0], [_recycler("recycler_a")])
    target = d.amount(6000, 12000)
    bucket = d.bucket("2024-2025", "CU", target)
    good = d.share(target, 0.45, 0.60)
    stale = d.share(target, 0.20, 0.30)
    window = (date(2024, 6, 1), date(2024, 9, 30))
    d.allocate(_completed(d, "recycler_a", "CU", good, window, bucket), bucket)
    on = d.day(date(2024, 11, 1), date(2025, 2, 15))
    expires = on - timedelta(days=d.rng.randint(20, 60))
    lot = d.lot(
        "recycler_a",
        "CU",
        stale,
        expires - timedelta(days=d.rng.randint(150, 300)),
        expires_on=expires,
        status="EXPIRED",
    )
    transfer = d.transfer(lot, stale, on)
    d.invoice(transfer, bucket)
    d.allocate(transfer, bucket)
    d.notes.append("The second credit expired before its transfer; the portal still reports it")
    d.begin_portal_capture()
    d.balance(bucket)
    return d.build()


def cancelled_credit(seed=6202):
    """A credit cancelled after transfer and before the producer allocated it."""
    d = _draft("cancelled_credit", seed, "tl:west_q1", PRODUCERS[1], [_recycler("recycler_c")])
    target = d.amount(9000, 15000)
    bucket = d.bucket("2024-2025", "CU", target)
    good = d.share(target, 0.45, 0.60)
    voided = d.share(target, 0.20, 0.30)
    kept = _completed(d, "recycler_c", "CU", good, (date(2024, 6, 1), date(2024, 9, 30)), bucket)
    d.allocate(kept, bucket, allocated_on=_day(kept) + timedelta(days=d.rng.randint(1, 10)))
    on = d.day(date(2024, 10, 15), date(2025, 1, 31))
    lot = d.lot("recycler_c", "CU", voided, on - timedelta(days=d.rng.randint(12, 55)))
    transfer = d.transfer(lot, voided, on)
    d.invoice(transfer, bucket)
    cancelled = on + timedelta(days=d.rng.randint(10, 30))
    d.end_credit(lot, "CANCELLED", cancelled)
    d.allocate(transfer, bucket, allocated_on=cancelled + timedelta(days=d.rng.randint(5, 20)))
    d.notes.append("The second credit was cancelled before it was allocated")
    d.begin_portal_capture()
    d.balance(bucket)
    return d.build()


def linked_invoice_payment(seed=6303):
    """Invoices and the payments that settle them: one quantity each, never double counted."""
    d = _draft(
        "linked_invoice_payment", seed, "tl:south_q1", PRODUCERS[2], [_recycler("recycler_b")]
    )
    target = d.amount(8000, 14000)
    bucket = d.bucket("2024-2025", "CU", target)
    window = (date(2024, 6, 1), date(2024, 10, 31))
    done = _completed(d, "recycler_b", "CU", d.share(target, 0.45, 0.60), window, bucket)
    d.allocate(done, bucket)
    d.pay(d.invoices[-1])
    on = d.day(date(2025, 2, 20), date(2025, 3, 25))
    quantity = d.share(target, 0.15, 0.25)
    lot = d.lot("recycler_b", "CU", quantity, on - timedelta(days=d.rng.randint(10, 30)))
    pending = d.transfer(lot, quantity, on, stage="INITIATED")
    d.pay(d.invoice(pending, bucket, lead_days=(6, 14)))
    d.notes.append("The initiated transfer is invoiced and paid once, so it is pending once")
    d.begin_portal_capture()
    d.balance(bucket)
    return d.build()


def capability_mismatch(seed=6404):
    """One recycler is registered for another EEE category than the producer's."""
    wrong = replace(_recycler("recycler_c"), eee_codes=("ITEW",))
    d = _draft(
        "capability_mismatch",
        seed,
        "tl:west_q3",
        PRODUCERS[3],
        [wrong, _recycler("recycler_d")],
    )
    target = d.amount(7000, 13000)
    bucket = d.bucket("2024-2025", "CU", target)
    for code in d.producer.eee_codes:
        d.product(f"SKU-{code}", code, kg(Decimal(d.rng.randint(15, 60)) / 10))
    ok = _completed(
        d,
        "recycler_d",
        "CU",
        d.share(target, 0.45, 0.60),
        (date(2024, 6, 1), date(2024, 10, 31)),
        bucket,
    )
    d.allocate(ok, bucket)
    bad = _completed(
        d,
        "recycler_c",
        "CU",
        d.share(target, 0.20, 0.30),
        (date(2024, 11, 1), date(2025, 2, 15)),
        bucket,
    )
    d.allocate(bad, bucket)
    d.notes.append("The second recycler is registered for ITEW, not the producer's CEEW codes")
    d.begin_portal_capture()
    d.balance(bucket)
    return d.build()


def weight_basis_conflict(seed=6505):
    """One SKU has a net and a packaged weight in force together; balances are unaffected."""
    d = _draft(
        "weight_basis_conflict",
        seed,
        "tl:north_q4",
        PRODUCERS[4],
        [_recycler("recycler_e"), _recycler("recycler_a")],
    )
    target = d.amount(6000, 12000)
    bucket = d.bucket("2024-2025", "CU", target)
    first = d.share(target, 0.45, 0.60)
    for quantity, recycler, window in (
        (first, "recycler_e", (date(2024, 6, 1), date(2024, 9, 30))),
        (target - first, "recycler_a", (date(2024, 11, 1), date(2025, 2, 15))),
    ):
        d.allocate(_completed(d, recycler, "CU", quantity, window, bucket), bucket)
    steady, split = d.producer.eee_codes
    d.product("SKU-A", steady, kg(Decimal(d.rng.randint(15, 60)) / 10))
    net = Decimal(d.rng.randint(15, 60)) / 10
    d.product("SKU-B", split, kg(net))
    d.product("SKU-B", split, kg(net + Decimal(d.rng.randint(2, 9)) / 10), "GROSS_PACKAGED")
    d.sale("SKU-A", d.rng.randint(2, 20) * 1000)
    d.sale("SKU-B", d.rng.randint(2, 20) * 1000)
    d.notes.append("SKU-B carries NET_EEE and GROSS_PACKAGED weights together")
    d.begin_portal_capture()
    d.balance(bucket)
    return d.build()


def earlier_liability_dated(seed=6606):
    """The earlier year is met first, and only allocation dates prove it."""
    d = _draft(
        "earlier_liability_dated",
        seed,
        "tl:south_q2",
        PRODUCERS[5],
        [_recycler("recycler_e"), _recycler("recycler_a")],
    )
    old = d.bucket("2023-2024", "CU", d.amount(1500, 3500))
    new = d.bucket("2024-2025", "CU", d.amount(6000, 12000))
    carried = d.share(Decimal(new.target_kg), 0.25, 0.40)
    face = Decimal(old.target_kg) + carried
    shared = _completed(d, "recycler_e", "CU", face, (date(2024, 4, 20), date(2024, 6, 30)), old)
    met = _day(shared) + timedelta(days=d.rng.randint(1, 5))
    d.allocate(shared, old, Decimal(old.target_kg), allocated_on=met)
    d.allocate(shared, new, carried, allocated_on=met + timedelta(days=d.rng.randint(1, 8)))
    rest = d.share(Decimal(new.target_kg) - carried, 0.80, 0.95)
    later = _completed(d, "recycler_a", "CU", rest, (date(2024, 10, 1), date(2025, 2, 28)), new)
    d.allocate(later, new, allocated_on=_day(later) + timedelta(days=d.rng.randint(1, 10)))
    d.notes.append("No explicit allocation order is supplied; allocation dates establish it")
    d.begin_portal_capture()
    d.balance(old)
    d.balance(new)
    return d.build()


TEMPLATES = (
    expired_credit,
    cancelled_credit,
    linked_invoice_payment,
    capability_mismatch,
    weight_basis_conflict,
    earlier_liability_dated,
)


def build_s04_worlds() -> list[World]:
    return [template() for template in TEMPLATES]


__all__ = ["DATASET_VERSION", "TEMPLATES", "build_s04_worlds"]
