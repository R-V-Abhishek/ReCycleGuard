"""The six S05 development worlds: clean variations plus the two fixture-1 behaviours.

Template keys, seeds and timeline groups are hidden truth; they never reach a visible path,
identifier or file. Quantities come from a seeded RNG inside per-shape constraints, so the
same seed always yields the same world and S07 can reuse the shapes with fresh seeds.
"""

import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from benchmarks.generator.world import (
    DATASET_VERSION,
    PRICE_BAND_INR_PER_KG,
    PRODUCERS,
    RECYCLERS,
    AllocationW,
    Bucket,
    Invoice,
    Lifecycle,
    Lot,
    Payment,
    PortalBalance,
    Product,
    Sale,
    Transfer,
    World,
    invoice_amounts,
    kg,
    opaque,
    tonnes_to_kg,
)

FY_START, FY_END = date(2024, 4, 1), date(2025, 3, 31)
CUTOFF = "2025-03-31T23:59:59Z"
STEP = Decimal("0.5")


class Draft:
    """Mutable builder; ``build()`` freezes it into a ``World``."""

    def __init__(
        self,
        template_key,
        seed,
        timeline_group,
        producer,
        recyclers,
        dataset_version=DATASET_VERSION,
    ):
        self.rng = random.Random(seed)
        self.template_key, self.seed, self.timeline_group = template_key, seed, timeline_group
        self.dataset_version = dataset_version
        self.tag = opaque(f"{dataset_version}|{template_key}|{seed}")
        self.producer = producer
        self.recyclers = {r.key: r for r in recyclers}
        self.buckets, self.lots, self.transfers = [], [], []
        self.allocations, self.invoices, self.balances = [], [], []
        self.ended, self.payments, self.products, self.sales, self.notes = [], [], [], [], []
        self._n = 0
        self._invoice_serial = {r.key: self.rng.randint(40, 380) for r in recyclers}

    def _next(self) -> int:
        self._n += 1
        return self._n

    def amount(self, lo, hi) -> Decimal:
        steps = int((Decimal(hi) - Decimal(lo)) / STEP)
        return Decimal(lo) + STEP * self.rng.randint(0, steps)

    def share(self, total: Decimal, lo: float, hi: float) -> Decimal:
        """A seeded fraction of ``total`` on the 0.5 kg grid (never a float in the output)."""
        permille = self.rng.randint(int(lo * 1000), int(hi * 1000))
        return (total * permille / 1000 / STEP).to_integral_value() * STEP

    def day(self, start: date, end: date) -> date:
        return start + timedelta(days=self.rng.randint(0, (end - start).days))

    def instant(self, on: date) -> str:
        # Indian business hours, 10:00-17:00 IST, written in UTC.
        minutes = self.rng.randint(4 * 60 + 30, 11 * 60 + 30)
        moment = datetime(on.year, on.month, on.day) + timedelta(minutes=minutes)
        return moment.strftime("%Y-%m-%dT%H:%M:00Z")

    def bucket(self, year, metal, target_kg: Decimal, supplied_unit="KG") -> Bucket:
        start, end = year.split("-")
        target = kg(target_kg)
        supplied = target if supplied_unit == "KG" else kg(target_kg / 1000)
        if supplied_unit == "TONNE" and tonnes_to_kg(supplied) != target:
            raise ValueError("tonne target must convert exactly")
        item = Bucket(
            key=f"bucket_{metal.lower()}_{start}",
            bucket_id=f"bucket:{self.tag}_{metal.lower()}_{start}_{end}",
            liability_year=year,
            metal=metal,
            supplied_target=supplied,
            supplied_unit=supplied_unit,
            target_kg=target,
        )
        self.buckets.append(item)
        return item

    def lot(
        self,
        recycler,
        metal,
        face: Decimal,
        generated_on: date,
        expires_on: date | None = None,
        status="TRANSFERRED",
    ) -> Lot:
        n = self._next()
        party = self.recyclers[recycler]
        item = Lot(
            key=f"lot_{n}",
            lot_id=f"lot:{self.tag}_{n:03d}",
            certificate_id=f"cert:{self.tag}_{n:03d}",
            external_ref=(
                f"SYNTH/EPR-EW/CERT/2024-25/{party.state_abbr}/{party.serial:04d}/{metal}/"
                f"{self.rng.randint(1000, 9999)}"
            ),
            recycler=recycler,
            metal=metal,
            face_kg=kg(face),
            generated_on=generated_on.isoformat(),
            expires_on=None if expires_on is None else expires_on.isoformat(),
            status=status,
        )
        self.lots.append(item)
        return item

    def transfer(self, lot, quantity: Decimal, on: date, stage="COMPLETED", channels=("LEDGER",)):
        n = self._next()
        item = Transfer(
            key=f"transfer_{n}",
            event_id=f"evt:{self.tag}_{n:03d}",
            txn_ref=f"SYNTH-TXN-2425-{self.rng.randint(100000, 999999)}",
            lot=lot.key,
            quantity_kg=kg(quantity),
            when=self.instant(on),
            stage=stage,
            channels=tuple(channels),
        )
        self.transfers.append(item)
        return item

    def allocate(
        self, transfer, bucket, quantity: Decimal | None = None, allocated_on: date | None = None
    ):
        n = self._next()
        item = AllocationW(
            key=f"allocation_{n}",
            allocation_id=f"alloc:{self.tag}_{n:03d}",
            transfer=transfer.key,
            bucket=bucket.key,
            quantity_kg=kg(Decimal(transfer.quantity_kg) if quantity is None else quantity),
            order=len(self.allocations) + 1,
            allocated_on=None if allocated_on is None else allocated_on.isoformat(),
        )
        self.allocations.append(item)
        return item

    def end_credit(self, lot, kind, on: date) -> Lifecycle:
        """The lot's certificate expires or is cancelled on ``on`` (a calendar day)."""
        n = self._next()
        item = Lifecycle(
            key=f"lifecycle_{n}",
            event_id=f"evt:{self.tag}_{n:03d}",
            lot=lot.key,
            kind=kind,
            when=self.instant(on),
        )
        self.ended.append(item)
        return item

    def pay(self, invoice) -> Payment:
        """The producer's payment of ``invoice``, on the day the invoice records it was paid."""
        n = self._next()
        item = Payment(
            key=f"payment_{n}",
            commercial_id=f"comm:{self.tag}_{n:03d}",
            invoice=invoice.key,
            paid_on=invoice.paid_on,
        )
        self.payments.append(item)
        return item

    def product(self, sku, eee_code, weight_kg: str, basis="NET_EEE") -> Product:
        n = self._next()
        item = Product(
            key=f"product_{n}",
            mapping_id=f"map:{self.tag}_{n:03d}",
            sku=sku,
            eee_code=eee_code,
            unit_weight_kg=weight_kg,
            weight_basis=basis,
        )
        self.products.append(item)
        return item

    def sale(self, sku, units: int) -> Sale:
        n = self._next()
        item = Sale(key=f"sale_{n}", sku=sku, units=str(units))
        self.sales.append(item)
        return item

    def invoice(self, transfer, bucket, lead_days=(4, 21)) -> Invoice:
        lot = next(lot for lot in self.lots if lot.key == transfer.lot)
        party = self.recyclers[lot.recycler]
        on = date.fromisoformat(transfer.when[:10])
        issued = on - timedelta(days=self.rng.randint(*lead_days))
        paid = issued + timedelta(days=self.rng.randint(0, max(0, (on - issued).days - 1)))
        low, high = PRICE_BAND_INR_PER_KG[self.producer.category]
        rate = (low + (high - low) * Decimal(self.rng.randint(1000, 7000)) / 10000).quantize(
            Decimal("0.01")
        )
        taxable, gst, total = invoice_amounts(transfer.quantity_kg, str(rate))
        self._invoice_serial[party.key] += self.rng.randint(1, 9)
        prefix = "".join(w[0] for w in party.legal_name.split()[:3]).upper()
        n = self._next()
        item = Invoice(
            key=f"invoice_{n}",
            commercial_id=f"comm:{self.tag}_{n:03d}",
            number=f"{prefix}/24-25/{self._invoice_serial[party.key]:04d}",
            recycler=party.key,
            metal=lot.metal,
            quantity_kg=transfer.quantity_kg,
            rate_inr_per_kg=f"{rate:.2f}",
            taxable_inr=taxable,
            gst_inr=gst,
            total_inr=total,
            issued=self.instant(issued),
            paid_on=paid.isoformat(),
            utr=f"SYNTHN{paid.strftime('%y%j')}{self.rng.randint(10000, 99999)}",
            transfer=transfer.key,
            bucket=bucket.key,
        )
        self.invoices.append(item)
        return item

    def balance(self, bucket) -> PortalBalance:
        """Clean worlds: the portal reports exactly the supported allocations to the bucket."""
        reported = sum(
            (Decimal(a.quantity_kg) for a in self.allocations if a.bucket == bucket.key),
            Decimal(0),
        )
        n = self._next()
        item = PortalBalance(
            key=f"balance_{n}",
            balance_id=f"bal:{self.tag}_{n:03d}",
            bucket=bucket.key,
            reported_kg=kg(reported),
            capture=self.capture,
            cutoff=CUTOFF,
        )
        self.balances.append(item)
        return item

    def build(self) -> World:
        knowledge = date.fromisoformat(self.capture[:10]) + timedelta(days=self.rng.randint(1, 3))
        return World(
            dataset_version=self.dataset_version,
            template_key=self.template_key,
            seed=self.seed,
            timeline_group=self.timeline_group,
            case_tag=self.tag,
            case_id=f"case:{self.tag}",
            fiscal_year="2024-2025",
            period_start=FY_START.isoformat(),
            period_end_exclusive=(FY_END + timedelta(days=1)).isoformat(),
            knowledge_cutoff=f"{knowledge.isoformat()}T10:00:00Z",
            producer=self.producer,
            recyclers=tuple(self.recyclers.values()),
            buckets=tuple(self.buckets),
            lots=tuple(self.lots),
            transfers=tuple(self.transfers),
            allocations=tuple(self.allocations),
            invoices=tuple(self.invoices),
            balances=tuple(self.balances),
            memo_date=knowledge.isoformat(),
            notes=tuple(self.notes),
            lifecycle=tuple(self.ended),
            payments=tuple(self.payments),
            products=tuple(self.products),
            sales=tuple(self.sales),
        )

    def begin_portal_capture(self):
        on = date(2025, 4, 1) + timedelta(days=self.rng.randint(1, 8))
        self.capture = f"{on.isoformat()}T05:30:00Z"


def _recycler(key):
    return next(r for r in RECYCLERS if r.key == key)


def _completed(d: Draft, recycler, metal, quantity, window, bucket, channels=("LEDGER",)):
    """Certificate generated, invoiced, paid and transferred in full to the producer."""
    on = d.day(*window)
    lot = d.lot(recycler, metal, quantity, on - timedelta(days=d.rng.randint(12, 55)))
    transfer = d.transfer(lot, quantity, on, channels=channels)
    d.invoice(transfer, bucket)
    return transfer


def exact_coverage(seed=5101):
    d = Draft("exact_coverage", seed, "tl:north_q1", PRODUCERS[0], [_recycler("recycler_a")])
    target = d.amount(6000, 14000)
    bucket = d.bucket("2024-2025", "CU", target)
    first = d.share(target, 0.45, 0.60)
    for quantity, window in (
        (first, (date(2024, 6, 1), date(2024, 9, 30))),
        (target - first, (date(2024, 11, 1), date(2025, 2, 15))),
    ):
        d.allocate(_completed(d, "recycler_a", "CU", quantity, window, bucket), bucket)
    d.begin_portal_capture()
    d.balance(bucket)
    return d.build()


def overlap_and_paid_pending(seed=5202):
    d = Draft(
        "overlap_and_paid_pending", seed, "tl:west_q2", PRODUCERS[1], [_recycler("recycler_c")]
    )
    target = d.amount(9000, 16000)
    bucket = d.bucket("2024-2025", "CU", target)
    done = _completed(
        d,
        "recycler_c",
        "CU",
        d.share(target, 0.50, 0.65),
        (date(2024, 7, 1), date(2024, 10, 31)),
        bucket,
        channels=("LEDGER", "PORTAL"),
    )
    d.allocate(done, bucket)
    # Paid in full, transfer initiated on the portal but not completed by the cut-off.
    on = d.day(date(2025, 2, 20), date(2025, 3, 25))
    quantity = d.share(target, 0.15, 0.25)
    lot = d.lot("recycler_c", "CU", quantity, on - timedelta(days=d.rng.randint(10, 30)))
    pending = d.transfer(lot, quantity, on, stage="INITIATED")
    d.invoice(pending, bucket, lead_days=(6, 14))
    d.begin_portal_capture()
    d.balance(bucket)
    return d.build()


def surplus(seed=5303):
    d = Draft("surplus", seed, "tl:south_q3", PRODUCERS[2], [_recycler("recycler_b")])
    target = d.amount(4000, 9000)
    bucket = d.bucket("2024-2025", "CU", target)
    purchased = d.share(target, 1.12, 1.25)
    first = d.share(purchased, 0.55, 0.70)
    for quantity, window in (
        (first, (date(2024, 5, 10), date(2024, 8, 31))),
        (purchased - first, (date(2024, 12, 1), date(2025, 3, 10))),
    ):
        d.allocate(_completed(d, "recycler_b", "CU", quantity, window, bucket), bucket)
    d.begin_portal_capture()
    d.balance(bucket)
    return d.build()


def two_metals(seed=5404):
    d = Draft(
        "two_metals",
        seed,
        "tl:west_q4",
        PRODUCERS[3],
        [_recycler("recycler_c"), _recycler("recycler_d")],
    )
    cu = d.bucket("2024-2025", "CU", d.amount(5000, 11000))
    al = d.bucket("2024-2025", "AL", d.amount(2000, 5000))
    cu_qty = d.share(Decimal(cu.target_kg), 0.70, 0.90)
    d.allocate(
        _completed(d, "recycler_c", "CU", cu_qty, (date(2024, 8, 1), date(2024, 12, 20)), cu), cu
    )
    al_qty = Decimal(al.target_kg)
    d.allocate(
        _completed(d, "recycler_d", "AL", al_qty, (date(2024, 9, 1), date(2025, 1, 31)), al), al
    )
    d.begin_portal_capture()
    d.balance(cu)
    d.balance(al)
    return d.build()


def historical_shared_lot(seed=5505):
    d = Draft(
        "historical_shared_lot",
        seed,
        "tl:north_q2",
        PRODUCERS[4],
        [_recycler("recycler_e"), _recycler("recycler_a")],
    )
    old = d.bucket("2023-2024", "CU", d.amount(1500, 3500))
    new = d.bucket("2024-2025", "CU", d.amount(6000, 12000))
    carried = d.share(Decimal(new.target_kg), 0.25, 0.40)
    face = Decimal(old.target_kg) + carried
    shared = _completed(d, "recycler_e", "CU", face, (date(2024, 4, 20), date(2024, 6, 30)), old)
    d.allocate(shared, old, Decimal(old.target_kg))  # Earlier year met first...
    d.allocate(shared, new, carried)  # ...then the remainder of the same lot.
    rest = d.share(Decimal(new.target_kg) - carried, 0.80, 0.95)
    d.allocate(
        _completed(d, "recycler_a", "CU", rest, (date(2024, 10, 1), date(2025, 2, 28)), new), new
    )
    d.begin_portal_capture()
    d.balance(old)
    d.balance(new)
    return d.build()


def tonne_two_recyclers(seed=5606):
    d = Draft(
        "tonne_two_recyclers",
        seed,
        "tl:south_q4",
        PRODUCERS[5],
        [_recycler("recycler_b"), _recycler("recycler_e")],
    )
    tonnes = Decimal(d.rng.randint(32, 88)) * Decimal("0.25")  # 8.00 .. 22.00 tonne
    bucket = d.bucket("2024-2025", "CU", tonnes * 1000, supplied_unit="TONNE")
    covered = d.share(Decimal(bucket.target_kg), 0.88, 0.96)
    first = d.share(covered, 0.40, 0.60)
    d.allocate(
        _completed(d, "recycler_b", "CU", first, (date(2024, 6, 15), date(2024, 10, 15)), bucket),
        bucket,
    )
    d.allocate(
        _completed(
            d, "recycler_e", "CU", covered - first, (date(2024, 11, 1), date(2025, 3, 15)), bucket
        ),
        bucket,
    )
    d.begin_portal_capture()
    d.balance(bucket)
    return d.build()


TEMPLATES = (
    exact_coverage,
    overlap_and_paid_pending,
    surplus,
    two_metals,
    historical_shared_lot,
    tonne_two_recyclers,
)


def build_worlds() -> list[World]:
    return [template() for template in TEMPLATES]


__all__ = ["TEMPLATES", "build_worlds", "Draft"]
