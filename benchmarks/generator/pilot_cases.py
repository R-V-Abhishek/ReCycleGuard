"""The S07 pilot (``pilot-0.1``): 24 development and 24 held-out dossiers, split before rendering.

Each split has one dossier per fault family F01-F16 and eight combinations. The split is made by
fictional entity, template and timeline group, never by row: development dossiers use the S05/S06
party catalogue, held-out dossiers use parties no development dossier uses, and the two splits
share no template (shape plus parameters) and no recipe combination. Where a family has variants
(F08 dated/undated, F10 capability/metal, F15 textless/truncated) the splits take different ones.

Templates, seeds, groups and the split itself are hidden truth; the visible dossiers carry none.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache, partial

from benchmarks.generator.faults import recipes as r
from benchmarks.generator.s05_cases import Draft, _recycler
from benchmarks.generator.s06_cases import H1, H2, _deal, _finish, _products
from benchmarks.generator.world import (
    HELDOUT_PRODUCERS,
    HELDOUT_RECYCLER_KEYS,
    PRODUCERS,
    S06_FRAGMENTS,
    World,
)

DATASET_VERSION = "pilot-0.1"
SPLIT_POLICY = "GROUPED_DEV_HELDOUT_V1"
DEV, HELD_OUT = "DEV", "HELD_OUT"
DEV_PRODUCERS = PRODUCERS[:12]
DEV_RECYCLER_KEYS = tuple(f"recycler_{c}" for c in "abcdefgh")
# Three windows inside FY 2024-25 for tranche dates; a shape takes as many as it has tranches.
WINDOWS = (
    (date(2024, 4, 20), date(2024, 7, 31)),
    (date(2024, 8, 20), date(2024, 11, 30)),
    (date(2024, 12, 20), date(2025, 3, 10)),
)


@dataclass(frozen=True)
class Spec:
    """One pilot dossier before generation: everything that decides its split and template."""

    split: str
    name: str  # family or combination label (hidden)
    shape: str  # builder name in SHAPES
    params: tuple  # shape parameters, part of the template key
    steps: tuple  # recipe callables, in order
    seed: int
    group: str
    producer: int  # index into the split's producer pool
    recyclers: tuple[str, ...]

    @property
    def template_key(self) -> str:
        return f"{self.shape}." + ".".join(str(p) for p in self.params)

    @property
    def combination(self) -> tuple[str, ...]:
        return tuple(_step_key(s) for s in self.steps)


@dataclass(frozen=True)
class PilotCase:
    split: str
    spec: Spec
    corrupted: r.Corrupted

    @property
    def world(self) -> World:
        return self.corrupted.world


def _step_key(step) -> str:
    if isinstance(step, partial):
        options = ",".join(f"{k}={v}" for k, v in sorted(step.keywords.items()))
        return f"{step.func.__name__}({options})"
    return step.__name__


# --- shapes --------------------------------------------------------------------------------
def _target(d: Draft, band: str) -> Decimal:
    lo, hi = {"small": (5000, 9000), "mid": (9000, 16000), "large": (16000, 30000)}[band]
    return d.amount(lo, hi)


def tranches(
    d: Draft, metal, n, band, portal, *, pending=False, spare=None, products=False, same=False
):
    """One bucket of ``metal`` covered by ``n`` dated tranches from the dossier's recyclers.

    The first tranche comes from the first recycler and later ones from the second; ``same``
    gives the first two tranches the same recycler and metal (two certificates that can be one).
    ``pending`` adds an invoiced transfer that has not completed; ``spare`` adds a completed,
    unallocated credit of another metal; ``products`` adds the producer's product master."""
    target = _target(d, band)
    bucket = d.bucket("2024-2025", metal, target)
    covered = d.share(target, 0.82, 0.97)
    keys = list(d.recyclers)
    channels = ("LEDGER", "PORTAL") if portal else ("LEDGER",)
    left = covered
    for i in range(n):
        last = i == n - 1
        part = left if last else d.share(covered, 0.75 / n, 1.15 / n)
        left -= part
        recycler = keys[0] if i == 0 or (same and i == 1) else keys[-1]
        _deal(d, recycler, metal, part, WINDOWS[i % len(WINDOWS)], bucket, channels=channels)
    if pending:
        on = d.day(date(2025, 2, 15), date(2025, 3, 25))
        quantity = d.share(target, 0.10, 0.20)
        lot = d.lot(keys[-1], metal, quantity, on - timedelta(days=d.rng.randint(10, 30)))
        d.invoice(d.transfer(lot, quantity, on, stage="INITIATED"), bucket, lead_days=(6, 14))
    if spare:
        _deal(d, keys[-1], spare, d.amount(800, 3000), H2, bucket, allocate=False)
    if products:
        _products(d)
    return (bucket,)


def two_years(d: Draft, metal, band, *, products=False):
    """An earlier and a later liability of one metal sharing a lot, then a later lot."""
    lo, hi = {"small": (1200, 3000), "mid": (2500, 5000)}[band]
    old = d.bucket("2023-2024", metal, d.amount(lo, hi))
    new = d.bucket("2024-2025", metal, d.amount(lo * 3, hi * 3))
    keys = list(d.recyclers)
    carried = d.share(Decimal(new.target_kg), 0.25, 0.40)
    on = d.day(date(2024, 4, 20), date(2024, 6, 30))
    face = Decimal(old.target_kg) + carried
    lot = d.lot(keys[0], metal, face, on - timedelta(days=d.rng.randint(12, 55)))
    shared = d.transfer(lot, face, on)
    d.invoice(shared, old)
    met = on + timedelta(days=d.rng.randint(1, 4))
    d.allocate(shared, old, Decimal(old.target_kg), allocated_on=met)
    d.allocate(shared, new, carried, allocated_on=met + timedelta(days=d.rng.randint(1, 8)))
    rest = d.share(Decimal(new.target_kg) - carried, 0.80, 0.95)
    later_on = d.day(*H2)
    later_lot = d.lot(keys[-1], metal, rest, later_on - timedelta(days=d.rng.randint(12, 55)))
    later = d.transfer(later_lot, rest, later_on)
    d.invoice(later, new)
    d.allocate(later, new, allocated_on=later_on + timedelta(days=d.rng.randint(1, 6)))
    if products:
        _products(d)
    return old, new


def two_metals(d: Draft, big, small, *, spare=None):
    """A lakh-scale bucket of ``big`` beside a bucket of ``small``, two tranches each."""
    major = d.bucket("2024-2025", big, d.amount(260000, 480000))
    minor = d.bucket("2024-2025", small, d.amount(40000, 160000))
    keys = list(d.recyclers)
    for bucket, recycler in ((major, keys[0]), (minor, keys[-1])):
        covered = d.share(Decimal(bucket.target_kg), 0.80, 0.95)
        first = d.share(covered, 0.45, 0.65)
        _deal(d, recycler, bucket.metal, first, H1, bucket)
        _deal(d, recycler, bucket.metal, covered - first, H2, bucket)
    if spare:
        _deal(d, keys[-1], spare, d.amount(20000, 60000), H2, major, allocate=False)
    return major, minor


def with_gold(d: Draft, base, gold_band):
    """An ordinary bucket of ``base`` and an ordinary gold (AU) bucket."""
    main = d.bucket("2024-2025", base, d.amount(6000, 14000))
    lo, hi = {"small": (6, 24), "mid": (20, 60)}[gold_band]
    au = d.bucket("2024-2025", "AU", d.amount(lo, hi))
    keys = list(d.recyclers)
    _deal(d, keys[0], base, d.share(Decimal(main.target_kg), 0.85, 0.98), H1, main)
    _deal(d, keys[-1], "AU", d.share(Decimal(au.target_kg), 0.55, 0.85), H2, au)
    return main, au


SHAPES = {"tranches": tranches, "two_years": two_years, "two_metals": two_metals, "gold": with_gold}


# --- the pilot ------------------------------------------------------------------------------
def _f(name):
    return getattr(r, name)


TEXTLESS = partial(r.extraction_page_loss, kind="TEXTLESS")
MISSING = partial(r.extraction_page_loss, kind="MISSING")
UNDATED = partial(r.prior_arrears_drain, dated=False)
CAPABILITY_ONLY = partial(r.capability_mismatch, metal=False)
METAL_ONLY = partial(r.capability_mismatch, capability=False)

# (name, shape, params, kwargs, steps). Development rows use CU-led shapes and the S06 catalogue;
# held-out rows use other metals, tranche counts or bands, and new parties.
DEV_ROWS = (
    ("F01", "tranches", ("CU", 2, "mid", "portal"), {}, (r.clean_baseline,)),
    ("F02", "tranches", ("CU", 2, "small", "portal"), {}, (r.overlapping_export,)),
    ("F03", "tranches", ("CU", 3, "mid", "ledger", "same"), {"same": True}, (r.multistage_reuse,)),
    ("F04", "two_metals", ("CU", "AL"), {}, (r.unit_dimension_mix,)),
    ("F05", "tranches", ("CU", 3, "small", "ledger"), {}, (r.wrong_entity_alias,)),
    ("F06", "tranches", ("CU", 3, "large", "ledger"), {}, (r.stale_snapshot,)),
    (
        "F07",
        "tranches",
        ("CU", 1, "mid", "ledger", "pending"),
        {"pending": True},
        (r.paid_no_transfer,),
    ),
    ("F08", "two_years", ("CU", "small"), {}, (r.prior_arrears_drain,)),
    ("F09", "tranches", ("CU", 2, "large", "ledger"), {}, (r.expired_cancelled,)),
    (
        "F10",
        "tranches",
        ("CU", 2, "mid", "ledger", "products"),
        {"products": True},
        (CAPABILITY_ONLY,),
    ),
    ("F11", "tranches", ("CU", 2, "small", "ledger"), {}, (r.wrong_period_rule,)),
    ("F12", "tranches", ("CU", 1, "large", "ledger"), {}, (r.unseen_notice_lead,)),
    (
        "F13",
        "tranches",
        ("CU", 1, "small", "ledger", "products"),
        {"products": True},
        (r.weight_basis_conflict,),
    ),
    ("F14", "gold", ("CU", "small"), {}, (r.out_of_scope_regime,)),
    ("F15", "tranches", ("CU", 1, "small", "ledger"), {}, (TEXTLESS,)),
    ("F16", "tranches", ("CU", 3, "mid", "portal"), {}, (r.prompt_injection,)),
    (
        "F02+F06",
        "tranches",
        ("CU", 3, "small", "portal"),
        {},
        (r.overlapping_export, r.stale_snapshot),
    ),
    ("F08+F09", "two_years", ("CU", "mid"), {}, (UNDATED, r.expired_cancelled)),
    (
        "F04+F10",
        "two_metals",
        ("CU", "AL", "spare-FE"),
        {"spare": "FE"},
        (r.unit_dimension_mix, METAL_ONLY),
    ),
    ("F15+F16", "tranches", ("CU", 2, "large", "portal"), {}, (TEXTLESS, r.prompt_injection)),
    (
        "F03+F13",
        "tranches",
        ("CU", 2, "large", "ledger", "products", "same"),
        {"products": True, "same": True},
        (r.multistage_reuse, r.weight_basis_conflict),
    ),
    (
        "F05+F12",
        "tranches",
        ("CU", 2, "mid", "ledger"),
        {},
        (r.wrong_entity_alias, r.unseen_notice_lead),
    ),
    ("F11+F14", "gold", ("CU", "mid"), {}, (r.wrong_period_rule, r.out_of_scope_regime)),
    (
        "F06+F07",
        "tranches",
        ("CU", 2, "mid", "ledger", "pending"),
        {"pending": True},
        (r.stale_snapshot, r.paid_no_transfer),
    ),
)
HELD_OUT_ROWS = (
    ("F01", "tranches", ("AL", 3, "large", "ledger"), {}, (r.clean_baseline,)),
    ("F02", "tranches", ("AL", 3, "mid", "portal"), {}, (r.overlapping_export,)),
    (
        "F03",
        "tranches",
        ("AL", 2, "large", "ledger", "same"),
        {"same": True},
        (r.multistage_reuse,),
    ),
    ("F04", "two_metals", ("AL", "CU"), {}, (r.unit_dimension_mix,)),
    ("F05", "tranches", ("AL", 2, "large", "ledger"), {}, (r.wrong_entity_alias,)),
    ("F06", "tranches", ("AL", 2, "small", "ledger"), {}, (r.stale_snapshot,)),
    (
        "F07",
        "tranches",
        ("AL", 2, "small", "ledger", "pending"),
        {"pending": True},
        (r.paid_no_transfer,),
    ),
    ("F08", "two_years", ("AL", "mid"), {}, (UNDATED,)),
    ("F09", "tranches", ("FE", 3, "mid", "ledger"), {}, (r.expired_cancelled,)),
    ("F10", "tranches", ("AL", 2, "mid", "ledger", "spare-CU"), {"spare": "CU"}, (METAL_ONLY,)),
    ("F11", "tranches", ("FE", 2, "large", "ledger"), {}, (r.wrong_period_rule,)),
    ("F12", "tranches", ("AL", 3, "small", "ledger"), {}, (r.unseen_notice_lead,)),
    (
        "F13",
        "tranches",
        ("AL", 2, "mid", "ledger", "products"),
        {"products": True},
        (r.weight_basis_conflict,),
    ),
    ("F14", "gold", ("AL", "mid"), {}, (r.out_of_scope_regime,)),
    ("F15", "tranches", ("FE", 2, "mid", "ledger"), {}, (MISSING,)),
    ("F16", "tranches", ("AL", 2, "small", "portal"), {}, (r.prompt_injection,)),
    (
        "F02+F07",
        "tranches",
        ("AL", 2, "mid", "portal", "pending"),
        {"pending": True},
        (r.overlapping_export, r.paid_no_transfer),
    ),
    (
        "F08+F10",
        "two_years",
        ("AL", "small", "products"),
        {"products": True},
        (r.prior_arrears_drain, CAPABILITY_ONLY),
    ),
    ("F04+F06", "two_metals", ("FE", "AL"), {}, (r.unit_dimension_mix, r.stale_snapshot)),
    ("F15+F11", "tranches", ("AL", 1, "large", "ledger"), {}, (MISSING, r.wrong_period_rule)),
    (
        "F03+F09",
        "tranches",
        ("FE", 3, "large", "ledger", "same"),
        {"same": True},
        (r.multistage_reuse, r.expired_cancelled),
    ),
    (
        "F05+F16",
        "tranches",
        ("FE", 3, "small", "portal"),
        {},
        (r.wrong_entity_alias, r.prompt_injection),
    ),
    (
        "F12+F13",
        "tranches",
        ("FE", 2, "small", "ledger", "products"),
        {"products": True},
        (r.unseen_notice_lead, r.weight_basis_conflict),
    ),
    (
        "F10+F13",
        "tranches",
        ("FE", 2, "mid", "ledger", "spare-AL", "products"),
        {"spare": "AL", "products": True},
        (METAL_ONLY, r.weight_basis_conflict),
    ),
)
REGIONS = ("north", "south", "east", "west", "central", "coast")


def _shape_args(shape: str, params: tuple) -> tuple:
    if shape == "tranches":
        metal, n, band, channel = params[:4]
        return (metal, n, band, channel == "portal")
    if shape == "two_years":
        return params[:2]
    return params[:2]


def _specs(split: str, rows, seed0: int, producers, recycler_keys) -> list[Spec]:
    specs = []
    for i, (name, shape, params, _kwargs, steps) in enumerate(rows):
        # Each producer appears twice in its split; recyclers rotate in pairs.
        first = recycler_keys[(2 * i) % len(recycler_keys)]
        second = recycler_keys[(2 * i + 1) % len(recycler_keys)]
        tag = "d" if split == DEV else "h"
        specs.append(
            Spec(
                split=split,
                name=name,
                shape=shape,
                params=params,
                steps=steps,
                seed=seed0 + i,
                group=f"tl:p7{tag}_{REGIONS[i % len(REGIONS)]}_{i // len(REGIONS) + 1}",
                producer=i % len(producers),
                recyclers=(first, second),
            )
        )
    return specs


def all_specs() -> list[Spec]:
    return [
        *_specs(DEV, DEV_ROWS, 7201, DEV_PRODUCERS, DEV_RECYCLER_KEYS),
        *_specs(HELD_OUT, HELD_OUT_ROWS, 7301, HELDOUT_PRODUCERS, HELDOUT_RECYCLER_KEYS),
    ]


def _build(spec: Spec) -> PilotCase:
    pool = DEV_PRODUCERS if spec.split == DEV else HELDOUT_PRODUCERS
    rows = DEV_ROWS if spec.split == DEV else HELD_OUT_ROWS
    kwargs = next(row[3] for row in rows if row[0] == spec.name)
    d = Draft(
        spec.template_key,
        spec.seed,
        spec.group,
        pool[spec.producer],
        [_recycler(k) for k in spec.recyclers],
        dataset_version=DATASET_VERSION,
        forbid=S06_FRAGMENTS,
    )
    buckets = SHAPES[spec.shape](d, *_shape_args(spec.shape, spec.params), **kwargs)
    clean = _finish(d, *buckets)
    return PilotCase(spec.split, spec, r.corrupt(clean, spec.steps, clean.seed))


@lru_cache(maxsize=1)
def build_pilot_cases() -> tuple[PilotCase, ...]:
    return tuple(_build(spec) for spec in all_specs())


__all__ = [
    "DATASET_VERSION",
    "DEV",
    "HELD_OUT",
    "SPLIT_POLICY",
    "PilotCase",
    "Spec",
    "all_specs",
    "build_pilot_cases",
]
