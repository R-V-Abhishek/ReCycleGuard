"""Clean-world invariants. A world that fails any check is never rendered.

Every check has a stable rule id. A world built by an S06 fault recipe names the rules its
recorded corruption deliberately breaks in ``World.relaxed``; every other rule still applies,
and naming an unknown rule is itself an error, so a recipe cannot switch checks off silently.
"""

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
    portal_counts,
)

DECIMAL = re.compile(r"^(0|[1-9][0-9]*)\.[0-9]{4}$")
# Shapes of real Indian identifiers; synthetic identifiers must never match them.
REAL_GSTIN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
REAL_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
REAL_CIN = re.compile(r"\b[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b")

RULES = frozenset(
    {
        "IDS_UNIQUE",
        "REFS_UNIQUE",
        "SYNTHETIC_IDENTITY",
        "QUANTITY_FORMAT",
        "TRANSFER_AFTER_GENERATION",
        "TRANSFER_IN_PERIOD",
        "TRANSFER_WITHIN_FACE",
        "ALLOCATION_NEEDS_COMPLETED",
        "ALLOCATION_SAME_METAL",
        "ALLOCATION_TO_PRODUCER",
        "ALLOCATION_WITHIN_TRANSFER",
        "ALLOCATION_WITHIN_LOT",
        "EARLIER_LIABILITY_FIRST",
        "INVOICE_DESCRIBES_TRANSFER",
        "INVOICE_ORDER",
        "INVOICE_PRICE_BAND",
        "INVOICE_ARITHMETIC",
        "PENDING_INVOICE_ONE_BUCKET",
        "BALANCE_TIMING",
        "BALANCE_MATCHES_PORTAL",
        "BALANCE_PER_BUCKET",
        "LIFECYCLE_DATES",
        "ALLOCATION_DATES",
        "PAYMENTS",
        "PRODUCTS",
        "DUPLICATE_EXPORT",
        "ALIASES",
        "PLANTS",
        "PAGE_LOSS",
    }
)


class WorldInvariantError(ValueError):
    pass


class _Checker:
    def __init__(self, relaxed):
        unknown = set(relaxed) - RULES
        if unknown:
            raise WorldInvariantError(f"unknown invariant ids relaxed: {sorted(unknown)}")
        self.relaxed = frozenset(relaxed)

    def fail(self, rule: str, message: str):
        if rule not in RULES:
            raise AssertionError(rule)
        if rule not in self.relaxed:
            raise WorldInvariantError(f"{rule}: {message}")


def check_world(world: World) -> None:
    check = _Checker(world.relaxed)
    fail = check.fail
    parties = (world.producer, *world.recyclers, *world.affiliates)
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
        *(e.event_id for e in world.lifecycle),
        *(p.commercial_id for p in world.payments),
        *(p.mapping_id for p in world.products),
    ]
    if len(ids) != len(set(ids)):
        fail("IDS_UNIQUE", "world identifiers must be unique")
    refs = [lot.external_ref for lot in world.lots] + [t.txn_ref for t in world.transfers]
    refs += [i.number for i in world.invoices]
    if len(refs) != len(set(refs)):
        fail("REFS_UNIQUE", "external references must be unique")

    for p in parties:
        for value in (gstin(p), pan(p), corporate_id(p)[1], epr_registration(p)):
            if not value.startswith("SYNTH"):
                fail("SYNTHETIC_IDENTITY", f"identifier is not unmistakably synthetic: {value}")
            if REAL_GSTIN.search(value) or REAL_PAN.search(value) or REAL_CIN.search(value):
                fail(
                    "SYNTHETIC_IDENTITY", f"identifier looks like a real Indian identifier: {value}"
                )
        if "synth" not in p.legal_name.lower() or not p.domain.endswith(".example"):
            fail("SYNTHETIC_IDENTITY", f"party is not marked fictional: {p.legal_name}")

    quantities = [b.target_kg for b in world.buckets] + [lot.face_kg for lot in world.lots]
    quantities += [t.quantity_kg for t in world.transfers]
    quantities += [a.quantity_kg for a in world.allocations]
    quantities += [b.reported_kg for b in world.balances]
    for q in quantities:
        if type(q) is not str or not DECIMAL.match(q) or Decimal(q) < 0:
            fail("QUANTITY_FORMAT", f"quantity must be a nonnegative 4dp decimal string: {q!r}")

    for t in world.transfers:
        lot = lots[t.lot]
        if t.when[:10] < lot.generated_on:
            fail("TRANSFER_AFTER_GENERATION", f"{t.key} precedes certificate generation")
        if not world.period_start <= t.when[:10] < world.period_end_exclusive:
            fail("TRANSFER_IN_PERIOD", f"{t.key} is outside the case period")
        if t.recipient not in {"producer", *(a.key for a in world.affiliates)}:
            fail("ALLOCATION_TO_PRODUCER", f"{t.key}: unknown recipient {t.recipient}")
    for lot in world.lots:
        on_lot = [t for t in world.transfers if t.lot == lot.key]
        if sum(Decimal(t.quantity_kg) for t in on_lot) > Decimal(lot.face_kg):
            fail("TRANSFER_WITHIN_FACE", f"{lot.key}: transfers exceed certificate face quantity")

    for a in world.allocations:
        t, b = transfers[a.transfer], buckets[a.bucket]
        if t.stage != "COMPLETED":
            fail("ALLOCATION_NEEDS_COMPLETED", f"{a.key}: allocations require a completed transfer")
        if lots[t.lot].metal != b.metal:
            fail("ALLOCATION_SAME_METAL", f"{a.key}: metal differs from bucket (never combine)")
        if t.recipient != "producer":
            fail("ALLOCATION_TO_PRODUCER", f"{a.key}: the credit was transferred to another entity")
    for t in world.transfers:
        used = sum(Decimal(a.quantity_kg) for a in world.allocations if a.transfer == t.key)
        if used > Decimal(t.quantity_kg):
            fail("ALLOCATION_WITHIN_TRANSFER", f"{t.key}: allocations exceed the transfer")
    for lot in world.lots:
        used = sum(
            Decimal(a.quantity_kg)
            for a in world.allocations
            if transfers[a.transfer].lot == lot.key
        )
        if used > Decimal(lot.face_kg):
            fail("ALLOCATION_WITHIN_LOT", f"{lot.key}: allocations exceed lot capacity")

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
                fail(
                    "EARLIER_LIABILITY_FIRST",
                    f"{later.key} received credits before {earlier.key} was met",
                )

    for inv in world.invoices:
        t = transfers[inv.transfer]
        if inv.quantity_kg != t.quantity_kg or inv.metal != lots[t.lot].metal:
            fail("INVOICE_DESCRIBES_TRANSFER", f"{inv.key}: invoice does not describe its transfer")
        if not inv.issued[:10] <= inv.paid_on <= t.when[:10]:
            fail("INVOICE_ORDER", f"{inv.key}: invoice, payment and transfer are out of order")
        low, high = PRICE_BAND_INR_PER_KG[world.producer.category]
        if not low <= Decimal(inv.rate_inr_per_kg) <= high:
            fail("INVOICE_PRICE_BAND", f"{inv.key}: price outside the CPCB floor/ceiling band")
        taxable, gst, total = map(Decimal, (inv.taxable_inr, inv.gst_inr, inv.total_inr))
        if taxable + gst != total or abs(taxable * GST_RATE_ASSUMED / 100 - gst) > Decimal("0.01"):
            fail("INVOICE_ARITHMETIC", f"{inv.key}: invoice arithmetic")
        if t.stage != "COMPLETED":
            compatible = [b for b in world.buckets if b.metal == inv.metal and b.key == inv.bucket]
            same_metal = [b for b in world.buckets if b.metal == inv.metal]
            if len(compatible) != 1 or len(same_metal) != 1:
                fail(
                    "PENDING_INVOICE_ONE_BUCKET",
                    f"{inv.key}: a paid-pending invoice must map to exactly one bucket",
                )

    for bal in world.balances:
        if not bal.cutoff < bal.capture < world.knowledge_cutoff:
            fail("BALANCE_TIMING", f"{bal.key}: capture must follow the cut-off, precede knowledge")
        reportable = sum(
            (
                Decimal(a.quantity_kg)
                for a in world.allocations
                if a.bucket == bal.bucket
                and portal_counts(
                    transfers[a.transfer],
                    lots[transfers[a.transfer].lot],
                    buckets[a.bucket],
                    bal.cutoff,
                )
            ),
            Decimal(0),
        )
        if Decimal(bal.reported_kg) != reportable:
            fail("BALANCE_MATCHES_PORTAL", f"{bal.key}: the portal reports what it recorded")
    if {b.bucket for b in world.balances} != set(buckets) or len(world.balances) != len(buckets):
        fail("BALANCE_PER_BUCKET", "every bucket needs exactly one portal balance")
    _check_lifecycle_and_dates(world, fail)
    _check_payments_and_products(world, fail)
    _check_visible_effects(world, fail)


def _check_lifecycle_and_dates(world: World, fail) -> None:
    """Dates that decide an allocation's validity must be unambiguous at day resolution."""
    lots = {lot.key: lot for lot in world.lots}
    transfers = {t.key: t for t in world.transfers}
    ends: dict[str, list[str]] = {}
    for lot in world.lots:
        if lot.expires_on is not None:
            if lot.expires_on <= lot.generated_on:
                fail("LIFECYCLE_DATES", f"{lot.key}: expires on or before it was generated")
            ends.setdefault(lot.key, []).append(lot.expires_on)
    for e in world.lifecycle:
        if e.lot not in lots or e.when[:10] <= lots[e.lot].generated_on:
            fail("LIFECYCLE_DATES", f"{e.key}: an unknown lot, or it ends on or before generation")
            continue
        ends.setdefault(e.lot, []).append(e.when[:10])
    for a in world.allocations:
        t = transfers[a.transfer]
        if a.allocated_on is not None:
            if a.allocated_on < t.when[:10] or a.allocated_on >= world.period_end_exclusive:
                fail("ALLOCATION_DATES", f"{a.key}: allocated before its transfer or after period")
        for day in ends.get(t.lot, []):
            # A same-day end cannot be ordered against a day-precision time, so it is never used.
            if day == t.when[:10] or day == a.allocated_on:
                fail("LIFECYCLE_DATES", f"{a.key}: a lifecycle date falls on a transfer/use day")
    dated = [a for a in world.allocations if a.allocated_on is not None]
    for first in dated:
        for second in dated:
            if first.order < second.order and first.allocated_on > second.allocated_on:
                fail("ALLOCATION_DATES", f"{first.key}: allocation order contradicts its dates")


def _check_payments_and_products(world: World, fail) -> None:
    invoices = {i.key: i for i in world.invoices}
    for pay in world.payments:
        if pay.invoice not in invoices or pay.paid_on != invoices[pay.invoice].paid_on:
            fail("PAYMENTS", f"{pay.key}: a payment must record an existing invoice's payment day")
    skus = {p.sku for p in world.products}
    for product in world.products:
        if not DECIMAL.match(product.unit_weight_kg) or Decimal(product.unit_weight_kg) <= 0:
            fail("PRODUCTS", f"{product.key}: unit weight must be a positive 4dp decimal string")
        if product.eee_code not in world.producer.eee_codes:
            fail("PRODUCTS", f"{product.key}: EEE code is not one of the producer's codes")
    for sale in world.sales:
        if sale.sku not in skus or not sale.units.isdigit():
            fail("PRODUCTS", f"{sale.key}: sales need a mapped SKU and whole units")


def _check_visible_effects(world: World, fail) -> None:
    """S06 effects must be supported by the world they describe."""
    transfers = {t.key: t for t in world.transfers}
    for t in world.transfers:
        if t.duplicate_of is None:
            continue
        original = transfers.get(t.duplicate_of)
        if (
            original is None
            or original.duplicate_of is not None
            or (original.lot, original.quantity_kg, original.when[:10])
            != (t.lot, t.quantity_kg, t.when[:10])
        ):
            fail("DUPLICATE_EXPORT", f"{t.key}: a duplicate must repeat one real transfer exactly")
        if "PORTAL" not in t.channels or "LEDGER" in t.channels:
            fail("DUPLICATE_EXPORT", f"{t.key}: the unreconciled copy is a portal export only")
    keys = {p.key for p in (world.producer, *world.recyclers, *world.affiliates)}
    for alias in world.aliases:
        if alias.party not in keys or not alias.start < alias.end_exclusive:
            fail("ALIASES", f"alias {alias.name}: unknown party or empty interval")
        if any(alias.name.casefold() == p.legal_name.casefold() for p in world.affiliates):
            fail("ALIASES", f"alias {alias.name}: an affiliate's name is never a proven alias")
    for plant in world.plants:
        if plant.channel == "invoice" and plant.target not in {i.key for i in world.invoices}:
            fail("PLANTS", f"invoice text targets an unknown invoice {plant.target}")
        if plant.channel in {"ledger", "portal"} and plant.target not in transfers:
            fail("PLANTS", f"{plant.channel} text targets an unknown transfer {plant.target}")
        if plant.channel == "portal" and "PORTAL" not in transfers[plant.target].channels:
            fail("PLANTS", f"portal text targets a transfer without a portal row {plant.target}")
        if world.surface != "s06":
            fail("PLANTS", "planted text needs the S06 rendering surface")
    for loss in world.page_losses:
        if world.surface != "s06" or loss.page in {0, 1}:
            fail("PAGE_LOSS", "page loss needs the S06 memo and never removes the first page")


__all__ = ["REAL_CIN", "REAL_GSTIN", "REAL_PAN", "RULES", "WorldInvariantError", "check_world"]
