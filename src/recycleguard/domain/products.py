"""Product mappings and sales (F13): weight basis conflicts are escalated, never averaged.

Sales do not establish a statutory obligation, so nothing here generates a target. Totals are
kept per weight basis and never mixed across NET_EEE, GROSS_PACKAGED and COMPONENT.
"""

from datetime import UTC, datetime
from decimal import Decimal

from recycleguard.contracts.domain import ProductMapping, ReviewedInterval, SalesRecord
from recycleguard.domain.arith import ZERO, add, multiply
from recycleguard.domain.chronology import Span
from recycleguard.domain.identity import interval_state
from recycleguard.domain.refs import Finding
from recycleguard.domain.universe import Universe
from recycleguard.normalization.units import (
    NumericSafetyError,
    convert_mass_to_kg,
    format_decimal_string,
)


def fiscal_year_span(fiscal_year: str) -> Span:
    """Indian financial year: 1 April of the first year up to 1 April of the second."""
    first, second = (int(part) for part in fiscal_year.split("-"))
    return datetime(first, 4, 1, tzinfo=UTC), datetime(second, 4, 1, tzinfo=UTC)


def _kg(mapping: ProductMapping) -> Decimal:
    return convert_mass_to_kg(mapping.unit_weight.decimal, mapping.unit_weight.unit)


def _overlap(left: ReviewedInterval, right: ReviewedInterval) -> bool:
    """Unreviewed or open intervals are treated as overlapping: a conflict is not excused."""
    if left.start is None or right.start is None:
        return True
    if left.review_state != "APPROVED" or right.review_state != "APPROVED":
        return True
    left_end, right_end = left.end, right.end
    return (left_end is None or right.start < left_end) and (
        right_end is None or left.start < right_end
    )


def _group(universe: Universe, entity_id: str, sku: str) -> list[ProductMapping]:
    return [m for m in universe.active(ProductMapping) if m.entity_id == entity_id and m.sku == sku]


def _resolve(
    universe: Universe, entity_id: str, sku: str, when: Span | None
) -> tuple[ProductMapping | None, Finding]:
    targets = (entity_id, sku)
    mappings = _group(universe, entity_id, sku)
    if not mappings:
        return None, Finding(
            targets, "UNKNOWN", "MISSING_ARTIFACT", "No reviewed product mapping for SKU"
        )
    refs = tuple(sorted(m.record_id for m in mappings))
    states = [interval_state(m.validity, when)[0] for m in mappings]
    valid = [m for m, state in zip(mappings, states, strict=True) if state == "PASS"]
    if len(valid) == 1:
        m = valid[0]
        values = (("eee_code", m.eee_code), ("weight_basis", m.weight_basis))
        found = Finding(targets, "PASS", None, "One mapping is valid for the period", refs, values)
        return m, found
    if len(valid) > 1:
        found = Finding(
            targets, "UNKNOWN", "AMBIGUOUS_IDENTITY", "Several mappings are valid at once", refs
        )
        return None, found
    if all(state == "FAIL" for state in states):
        return None, Finding(targets, "FAIL", None, "Every mapping is outside the period", refs)
    return None, Finding(
        targets, "UNKNOWN", None, "Mapping validity for the period is unresolved", refs
    )


def mapping_finding(universe: Universe, entity_id: str, sku: str, when: Span | None) -> Finding:
    return _resolve(universe, entity_id, sku, when)[1]


def weight_basis_finding(universe: Universe, entity_id: str, sku: str) -> Finding:
    targets = (entity_id, sku)
    mappings = _group(universe, entity_id, sku)
    refs = tuple(sorted(m.record_id for m in mappings))
    if not mappings:
        return Finding(targets, "UNKNOWN", "MISSING_ARTIFACT", "No product mapping for SKU")
    for i, left in enumerate(mappings):
        for right in mappings[i + 1 :]:
            differs = left.weight_basis != right.weight_basis or _kg(left) != _kg(right)
            if differs and _overlap(left.validity, right.validity):
                return Finding(
                    targets,
                    "FAIL",
                    "WEIGHT_BASIS_CONFLICT",
                    f"{left.weight_basis} and {right.weight_basis} both apply; not averaged",
                    refs,
                    (
                        (left.weight_basis, format_decimal_string(_kg(left))),
                        (right.weight_basis, format_decimal_string(_kg(right))),
                    ),
                )
    return Finding(targets, "PASS", None, "One consistent weight basis", refs)


def sales_finding(universe: Universe, entity_id: str, fiscal_year: str) -> Finding:
    """Aggregate sales mass per weight basis; unmapped SKUs leave the total UNKNOWN."""
    targets = (entity_id, fiscal_year)
    sales = [
        s
        for s in universe.active(SalesRecord)
        if s.entity_id == entity_id and s.fiscal_year == fiscal_year
    ]
    if not sales:
        return Finding(targets, "UNKNOWN", None, "No sales records for the period")
    period = fiscal_year_span(fiscal_year)
    totals: dict[str, Decimal] = {}
    refs = tuple(sorted(s.record_id for s in sales))
    unresolved: list[str] = []
    for sale in sorted(sales, key=lambda s: s.record_id):
        conflict = weight_basis_finding(universe, entity_id, sale.sku)
        if conflict.state == "FAIL":
            return Finding(targets, "FAIL", conflict.code, conflict.reason, refs + conflict.refs)
        mapping, found = _resolve(universe, entity_id, sale.sku, period)
        if mapping is None:
            unresolved.append(f"{sale.sku}: {found.reason}")
            continue
        try:
            mass = multiply(Decimal(sale.quantity_units), _kg(mapping))
            totals[mapping.weight_basis] = add(totals.get(mapping.weight_basis, ZERO), mass)
        except NumericSafetyError:
            return Finding(targets, "UNKNOWN", None, "Sales mass exceeds supported precision", refs)
        if sale.mass is not None and convert_mass_to_kg(sale.mass.decimal, sale.mass.unit) != mass:
            return Finding(
                targets,
                "FAIL",
                "WEIGHT_BASIS_CONFLICT",
                f"Supplied mass for {sale.sku} disagrees with units x mapped weight",
                refs,
            )
    values = tuple(
        sorted((f"total_kg_{basis}", format_decimal_string(v)) for basis, v in totals.items())
    )
    if unresolved:
        return Finding(targets, "UNKNOWN", None, "; ".join(unresolved), refs, values)
    return Finding(targets, "PASS", None, "Sales aggregated per weight basis", refs, values)
