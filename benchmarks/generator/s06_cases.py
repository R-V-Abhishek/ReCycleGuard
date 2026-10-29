"""The S06 development set: one dossier per fault family, both page-loss forms, four combinations.

Each template first builds a clean world on the S06 rendering surface (the same columns, fields,
annexures and notice note in every dossier, so their presence is never a clue), then applies its
recipes from ``faults.recipes``. The clean world is kept as the private counterpart. Template
keys, recipe names, seeds and timeline groups are hidden truth.
"""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache, partial

from benchmarks.generator.faults import recipes as r
from benchmarks.generator.s05_cases import Draft, _recycler
from benchmarks.generator.world import PRODUCERS, S06_FRAGMENTS, World, kg

DATASET_VERSION = "s06-dev-0.1"
H1 = (date(2024, 5, 1), date(2024, 9, 30))
H2 = (date(2024, 10, 15), date(2025, 3, 10))


def _draft(template, seed, group, producer, recyclers) -> Draft:
    return Draft(
        template,
        seed,
        group,
        producer,
        [_recycler(k) for k in recyclers],
        dataset_version=DATASET_VERSION,
        forbid=S06_FRAGMENTS,
    )


def _deal(
    d: Draft, recycler, metal, quantity, window, bucket, *, channels=("LEDGER",), allocate=True
):
    """A certificate generated, invoiced, paid, transferred and (by default) allocated on a
    dated day a little after the transfer, as the portal's allocation screen records it."""
    on = d.day(*window)
    lot = d.lot(recycler, metal, quantity, on - timedelta(days=d.rng.randint(12, 55)))
    transfer = d.transfer(lot, quantity, on, channels=channels)
    d.invoice(transfer, bucket)
    if allocate:
        d.allocate(transfer, bucket, allocated_on=on + timedelta(days=d.rng.randint(1, 6)))
    return transfer


def _finish(d: Draft, *buckets) -> World:
    # The allocation screen lists allocations in the order they were made.
    if d.allocations and all(a.allocated_on for a in d.allocations):
        ranked = sorted(d.allocations, key=lambda a: (a.allocated_on, a.order))
        d.allocations = [replace(a, order=i) for i, a in enumerate(ranked, 1)]
    d.begin_portal_capture()
    for bucket in buckets:
        d.balance(bucket)
    return replace(d.build(), surface="s06")


def _single_cu(d: Draft, recyclers, share=(0.45, 0.60), portal=False, cover=(0.85, 1.0)):
    target = d.amount(6000, 15000)
    bucket = d.bucket("2024-2025", "CU", target)
    covered = d.share(target, *cover)
    first = d.share(covered, *share)
    channels = ("LEDGER", "PORTAL") if portal else ("LEDGER",)
    _deal(d, recyclers[0], "CU", first, H1, bucket, channels=channels)
    _deal(d, recyclers[-1], "CU", covered - first, H2, bucket, channels=channels)
    return bucket


def _two_years(d: Draft, recyclers):
    old = d.bucket("2023-2024", "CU", d.amount(1500, 3500))
    new = d.bucket("2024-2025", "CU", d.amount(6000, 12000))
    carried = d.share(Decimal(new.target_kg), 0.25, 0.40)
    on = d.day(date(2024, 4, 20), date(2024, 6, 30))
    face = Decimal(old.target_kg) + carried
    lot = d.lot(recyclers[0], "CU", face, on - timedelta(days=d.rng.randint(12, 55)))
    shared = d.transfer(lot, face, on)
    d.invoice(shared, old)
    met = on + timedelta(days=d.rng.randint(1, 4))
    d.allocate(shared, old, Decimal(old.target_kg), allocated_on=met)
    d.allocate(shared, new, carried, allocated_on=met + timedelta(days=d.rng.randint(1, 8)))
    rest = d.share(Decimal(new.target_kg) - carried, 0.80, 0.95)
    later_on = d.day(*H2)
    later_lot = d.lot(recyclers[-1], "CU", rest, later_on - timedelta(days=d.rng.randint(12, 55)))
    later = d.transfer(later_lot, rest, later_on)
    d.invoice(later, new)
    d.allocate(later, new, allocated_on=later_on + timedelta(days=d.rng.randint(1, 6)))
    return old, new


def _products(d: Draft):
    for code in d.producer.eee_codes:
        d.product(
            f"SKU-{code}-{d.rng.randint(100, 999)}", code, kg(Decimal(d.rng.randint(15, 90)) / 10)
        )
    for p in d.products:
        d.sale(p.sku, d.rng.randint(4, 40) * 500)


# --- single-family templates ---------------------------------------------------------------
def baseline(seed=7101):
    d = _draft("baseline", seed, "tl:s6_west_a", PRODUCERS[6], ["recycler_a", "recycler_b"])
    bucket = _single_cu(d, ["recycler_a", "recycler_b"], portal=True)
    return _finish(d, bucket), [r.clean_baseline]


def overlap(seed=7102):
    d = _draft("overlap", seed, "tl:s6_south_a", PRODUCERS[7], ["recycler_f"])
    bucket = _single_cu(d, ["recycler_f"], portal=True)
    return _finish(d, bucket), [r.overlapping_export]


def reuse(seed=7103):
    d = _draft("reuse", seed, "tl:s6_north_a", PRODUCERS[8], ["recycler_g"])
    target = d.amount(7000, 14000)
    bucket = d.bucket("2024-2025", "CU", target)
    first = d.share(target, 0.30, 0.40)
    second = d.share(target, 0.25, 0.35)
    _deal(d, "recycler_g", "CU", first, H1, bucket)
    _deal(d, "recycler_g", "CU", second, H2, bucket)
    _deal(d, "recycler_g", "CU", d.share(target, 0.15, 0.25), H2, bucket)
    return _finish(d, bucket), [r.multistage_reuse]


def units(seed=7104):
    d = _draft("units", seed, "tl:s6_east_a", PRODUCERS[9], ["recycler_h", "recycler_c"])
    cu = d.bucket("2024-2025", "CU", d.amount(150000, 400000))
    al = d.bucket("2024-2025", "AL", d.amount(60000, 180000))
    for bucket, recycler in ((cu, "recycler_h"), (al, "recycler_c")):
        covered = d.share(Decimal(bucket.target_kg), 0.80, 0.95)
        first = d.share(covered, 0.40, 0.60)
        _deal(d, recycler, bucket.metal, first, H1, bucket)
        _deal(d, recycler, bucket.metal, covered - first, H2, bucket)
    return _finish(d, cu, al), [r.unit_dimension_mix]


def alias(seed=7105):
    d = _draft("alias", seed, "tl:s6_central_a", PRODUCERS[10], ["recycler_a", "recycler_e"])
    target = d.amount(8000, 15000)
    bucket = d.bucket("2024-2025", "CU", target)
    for share, recycler, window in (
        ((0.35, 0.45), "recycler_a", H1),
        ((0.25, 0.35), "recycler_e", H2),
        ((0.15, 0.20), "recycler_e", H2),
    ):
        _deal(d, recycler, "CU", d.share(target, *share), window, bucket)
    return _finish(d, bucket), [r.wrong_entity_alias]


def stale(seed=7106):
    d = _draft("stale", seed, "tl:s6_south_b", PRODUCERS[11], ["recycler_b"])
    target = d.amount(8000, 15000)
    bucket = d.bucket("2024-2025", "CU", target)
    for share, window in (
        ((0.30, 0.40), (date(2024, 5, 1), date(2024, 7, 31))),
        ((0.25, 0.35), (date(2024, 9, 1), date(2024, 11, 30))),
        ((0.20, 0.30), (date(2025, 1, 15), date(2025, 3, 10))),
    ):
        _deal(d, "recycler_b", "CU", d.share(target, *share), window, bucket)
    return _finish(d, bucket), [r.stale_snapshot]


def paid(seed=7107):
    d = _draft("paid", seed, "tl:s6_west_b", PRODUCERS[0], ["recycler_g"])
    target = d.amount(9000, 15000)
    bucket = d.bucket("2024-2025", "CU", target)
    _deal(d, "recycler_g", "CU", d.share(target, 0.50, 0.65), H1, bucket)
    on = d.day(date(2025, 2, 20), date(2025, 3, 25))
    quantity = d.share(target, 0.15, 0.25)
    lot = d.lot("recycler_g", "CU", quantity, on - timedelta(days=d.rng.randint(10, 30)))
    d.invoice(d.transfer(lot, quantity, on, stage="INITIATED"), bucket, lead_days=(6, 14))
    return _finish(d, bucket), [r.paid_no_transfer]


def arrears(seed=7108):
    d = _draft("arrears", seed, "tl:s6_north_b", PRODUCERS[1], ["recycler_e", "recycler_a"])
    old, new = _two_years(d, ["recycler_e", "recycler_a"])
    return _finish(d, old, new), [r.prior_arrears_drain]


def cancelled(seed=7109):
    d = _draft("cancelled", seed, "tl:s6_east_b", PRODUCERS[2], ["recycler_b", "recycler_h"])
    bucket = _single_cu(d, ["recycler_b", "recycler_h"])
    return _finish(d, bucket), [r.expired_cancelled]


def capability(seed=7110):
    d = _draft("capability", seed, "tl:s6_west_c", PRODUCERS[3], ["recycler_c", "recycler_d"])
    bucket = _single_cu(d, ["recycler_c", "recycler_d"])
    _products(d)
    # Aluminium credit bought for a later return and not allocated this year.
    _deal(d, "recycler_d", "AL", d.amount(800, 2500), H2, bucket, allocate=False)
    return _finish(d, bucket), [r.capability_mismatch]


def period(seed=7111):
    d = _draft("period", seed, "tl:s6_north_c", PRODUCERS[4], ["recycler_f"])
    bucket = _single_cu(d, ["recycler_f"])
    return _finish(d, bucket), [r.wrong_period_rule]


def notice(seed=7112):
    d = _draft("notice", seed, "tl:s6_south_c", PRODUCERS[5], ["recycler_a"])
    bucket = _single_cu(d, ["recycler_a"])
    return _finish(d, bucket), [r.unseen_notice_lead]


def weights(seed=7113):
    d = _draft("weights", seed, "tl:s6_central_b", PRODUCERS[8], ["recycler_e", "recycler_g"])
    bucket = _single_cu(d, ["recycler_e", "recycler_g"])
    _products(d)
    return _finish(d, bucket), [r.weight_basis_conflict]


def gold(seed=7114):
    d = _draft("gold", seed, "tl:s6_east_c", PRODUCERS[9], ["recycler_f", "recycler_b"])
    cu = d.bucket("2024-2025", "CU", d.amount(6000, 12000))
    au = d.bucket("2024-2025", "AU", d.amount(8, 40))
    covered = d.share(Decimal(cu.target_kg), 0.85, 0.98)
    _deal(d, "recycler_f", "CU", covered, H1, cu)
    _deal(d, "recycler_b", "AU", d.share(Decimal(au.target_kg), 0.60, 0.80), H2, au)
    return _finish(d, cu, au), [r.out_of_scope_regime]


def textless(seed=7115):
    d = _draft("textless", seed, "tl:s6_west_d", PRODUCERS[10], ["recycler_c", "recycler_h"])
    bucket = _single_cu(d, ["recycler_c", "recycler_h"])
    return _finish(d, bucket), [partial(r.extraction_page_loss, kind="TEXTLESS")]


def truncated(seed=7116):
    d = _draft("truncated", seed, "tl:s6_central_c", PRODUCERS[11], ["recycler_d", "recycler_e"])
    bucket = _single_cu(d, ["recycler_d", "recycler_e"])
    return _finish(d, bucket), [partial(r.extraction_page_loss, kind="MISSING")]


def injection(seed=7117):
    d = _draft("injection", seed, "tl:s6_south_d", PRODUCERS[0], ["recycler_b", "recycler_g"])
    bucket = _single_cu(d, ["recycler_b", "recycler_g"], portal=True)
    return _finish(d, bucket), [r.prompt_injection]


# --- combinations ----------------------------------------------------------------------------
def overlap_stale(seed=7121):
    d = _draft("overlap_stale", seed, "tl:s6_north_d", PRODUCERS[1], ["recycler_h"])
    target = d.amount(8000, 15000)
    bucket = d.bucket("2024-2025", "CU", target)
    for share, window in (((0.30, 0.40), H1), ((0.30, 0.40), H2)):
        _deal(
            d,
            "recycler_h",
            "CU",
            d.share(target, *share),
            window,
            bucket,
            channels=("LEDGER", "PORTAL"),
        )
    return _finish(d, bucket), [r.overlapping_export, r.stale_snapshot]


def arrears_cancelled(seed=7122):
    d = _draft(
        "arrears_cancelled", seed, "tl:s6_east_d", PRODUCERS[2], ["recycler_a", "recycler_f"]
    )
    old, new = _two_years(d, ["recycler_a", "recycler_f"])  # the recipe removes the history
    return _finish(d, old, new), [partial(r.prior_arrears_drain, dated=False), r.expired_cancelled]


def units_metal(seed=7123):
    d = _draft("units_metal", seed, "tl:s6_west_e", PRODUCERS[3], ["recycler_g", "recycler_h"])
    cu = d.bucket("2024-2025", "CU", d.amount(260000, 420000))
    al = d.bucket("2024-2025", "AL", d.amount(50000, 150000))
    for bucket, recycler in ((cu, "recycler_g"), (al, "recycler_h")):
        covered = d.share(Decimal(bucket.target_kg), 0.80, 0.95)
        first = d.share(covered, 0.40, 0.60)
        _deal(d, recycler, bucket.metal, first, H1, bucket)
        _deal(d, recycler, bucket.metal, covered - first, H2, bucket)
    _deal(d, "recycler_h", "FE", d.amount(20000, 60000), H2, cu, allocate=False)
    return _finish(d, cu, al), [
        r.unit_dimension_mix,
        partial(r.capability_mismatch, capability=False),
    ]


def textless_injection(seed=7124):
    d = _draft(
        "textless_injection", seed, "tl:s6_central_d", PRODUCERS[4], ["recycler_c", "recycler_a"]
    )
    bucket = _single_cu(d, ["recycler_c", "recycler_a"], portal=True)
    return _finish(d, bucket), [
        partial(r.extraction_page_loss, kind="TEXTLESS"),
        r.prompt_injection,
    ]


TEMPLATES = (
    baseline,
    overlap,
    reuse,
    units,
    alias,
    stale,
    paid,
    arrears,
    cancelled,
    capability,
    period,
    notice,
    weights,
    gold,
    textless,
    truncated,
    injection,
    overlap_stale,
    arrears_cancelled,
    units_metal,
    textless_injection,
)


@lru_cache(maxsize=1)
def build_s06_cases() -> tuple[r.Corrupted, ...]:
    cases = []
    for template in TEMPLATES:
        clean, steps = template()
        cases.append(r.corrupt(clean, steps, clean.seed))
    return tuple(cases)


def build_s06_worlds() -> list[World]:
    return [case.world for case in build_s06_cases()]


__all__ = ["DATASET_VERSION", "TEMPLATES", "build_s06_cases", "build_s06_worlds"]
