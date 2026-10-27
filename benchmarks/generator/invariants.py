"""Clean-world invariants. A world that fails any check is never rendered."""

import re
from decimal import Decimal

from benchmarks.generator.world import (
    GST_RATE_ASSUMED,
    PRICE_BAND_INR_PER_KG,
    World,
    corporate_id,
    epr_registration,
    gstin,
    pan,
)

DECIMAL = re.compile(r"^(0|[1-9][0-9]*)\.[0-9]{4}$")
# Shapes of real Indian identifiers; synthetic identifiers must never match them.
REAL_GSTIN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
REAL_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
REAL_CIN = re.compile(r"\b[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b")


class WorldInvariantError(ValueError):
    pass


def _fail(message):
    raise WorldInvariantError(message)


def check_world(world: World) -> None:
    parties = (world.producer, *world.recyclers)
    buckets = {b.key: b for b in world.buckets}
    lots = {lot.key: lot for lot in world.lots}
    transfers = {t.key: t for t in world.transfers}

    ids = [
        world.case_id,
        *(b.bucket_id for b in world.buckets),
        *(x for lot in world.lots for x in (lot.lot_id, lot.certificate_id)),
        *(t.event_id for t in world.transfers),
        *(a.allocation_id for a in world.allocations),
        *(i.commercial_id for i in world.invoices),
        *(b.balance_id for b in world.balances),
    ]
    if len(ids) != len(set(ids)):
        _fail("world identifiers must be unique")
    refs = [lot.external_ref for lot in world.lots] + [t.txn_ref for t in world.transfers]
    refs += [i.number for i in world.invoices]
    if len(refs) != len(set(refs)):
        _fail("external references must be unique")

    for p in parties:
        for value in (gstin(p), pan(p), corporate_id(p)[1], epr_registration(p)):
            if not value.startswith("SYNTH"):
                _fail(f"identifier is not unmistakably synthetic: {value}")
            if REAL_GSTIN.search(value) or REAL_PAN.search(value) or REAL_CIN.search(value):
                _fail(f"identifier looks like a real Indian identifier: {value}")
        if "synth" not in p.legal_name.lower() or not p.domain.endswith(".example"):
            _fail(f"party is not marked fictional: {p.legal_name}")

    quantities = [b.target_kg for b in world.buckets] + [lot.face_kg for lot in world.lots]
    quantities += [t.quantity_kg for t in world.transfers]
    quantities += [a.quantity_kg for a in world.allocations]
    quantities += [b.reported_kg for b in world.balances]
    for q in quantities:
        if type(q) is not str or not DECIMAL.match(q) or Decimal(q) < 0:
            _fail(f"quantity must be a nonnegative 4dp decimal string: {q!r}")

    for t in world.transfers:
        lot = lots[t.lot]
        if t.when[:10] < lot.generated_on:
            _fail(f"{t.key} precedes certificate generation")
        if not world.period_start <= t.when[:10] < world.period_end_exclusive:
            _fail(f"{t.key} is outside the case period")
    for lot in world.lots:
        on_lot = [t for t in world.transfers if t.lot == lot.key]
        if sum(Decimal(t.quantity_kg) for t in on_lot) > Decimal(lot.face_kg):
            _fail(f"{lot.key}: transfers exceed certificate face quantity")

    for a in world.allocations:
        t, b = transfers[a.transfer], buckets[a.bucket]
        if t.stage != "COMPLETED":
            _fail(f"{a.key}: allocations require a completed transfer")
        if lots[t.lot].metal != b.metal:
            _fail(f"{a.key}: metal differs from bucket (never combine metals)")
    for t in world.transfers:
        used = sum(Decimal(a.quantity_kg) for a in world.allocations if a.transfer == t.key)
        if used > Decimal(t.quantity_kg):
            _fail(f"{t.key}: allocations exceed the transfer")
    for lot in world.lots:
        used = sum(
            Decimal(a.quantity_kg)
            for a in world.allocations
            if transfers[a.transfer].lot == lot.key
        )
        if used > Decimal(lot.face_kg):
            _fail(f"{lot.key}: allocations exceed lot capacity across buckets and years")

    # Earlier liabilities are met in allocation order before later ones receive credits.
    by_year = sorted(world.buckets, key=lambda b: b.liability_year)
    for later in by_year:
        for earlier in by_year:
            if earlier.metal != later.metal or earlier.liability_year >= later.liability_year:
                continue
            first_later = min(
                (a.order for a in world.allocations if a.bucket == later.key), default=None
            )
            met = sum(
                Decimal(a.quantity_kg)
                for a in world.allocations
                if a.bucket == earlier.key and first_later is not None and a.order < first_later
            )
            if first_later is not None and met < Decimal(earlier.target_kg):
                _fail(f"{later.key} received credits before {earlier.key} was met")

    for inv in world.invoices:
        t = transfers[inv.transfer]
        if inv.quantity_kg != t.quantity_kg or inv.metal != lots[t.lot].metal:
            _fail(f"{inv.key}: invoice does not describe its transfer")
        if not inv.issued[:10] <= inv.paid_on <= t.when[:10]:
            _fail(f"{inv.key}: invoice, payment and transfer are out of order")
        low, high = PRICE_BAND_INR_PER_KG[world.producer.category]
        if not low <= Decimal(inv.rate_inr_per_kg) <= high:
            _fail(f"{inv.key}: price outside the CPCB floor/ceiling band")
        taxable, gst, total = map(Decimal, (inv.taxable_inr, inv.gst_inr, inv.total_inr))
        if taxable + gst != total or abs(taxable * GST_RATE_ASSUMED / 100 - gst) > Decimal("0.01"):
            _fail(f"{inv.key}: invoice arithmetic")
        if t.stage != "COMPLETED":
            compatible = [b for b in world.buckets if b.metal == inv.metal and b.key == inv.bucket]
            same_metal = [b for b in world.buckets if b.metal == inv.metal]
            if len(compatible) != 1 or len(same_metal) != 1:
                _fail(f"{inv.key}: a paid-pending invoice must map to exactly one bucket")

    for bal in world.balances:
        if not bal.cutoff < bal.capture < world.knowledge_cutoff:
            _fail(f"{bal.key}: portal capture must follow the cut-off and precede knowledge")
        supported = sum(Decimal(a.quantity_kg) for a in world.allocations if a.bucket == bal.bucket)
        if Decimal(bal.reported_kg) != supported:
            _fail(f"{bal.key}: clean worlds report exactly the supported allocations")
    if {b.bucket for b in world.balances} != set(buckets):
        _fail("every bucket needs exactly one portal balance in a clean world")


__all__ = ["REAL_CIN", "REAL_GSTIN", "REAL_PAN", "WorldInvariantError", "check_world"]
