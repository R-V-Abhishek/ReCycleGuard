"""Exact metal-mass arithmetic for C08; thin wrappers over the audited normalization helpers."""

from collections.abc import Iterable
from decimal import Decimal, Inexact, InvalidOperation, Overflow, localcontext

from recycleguard.contracts.core import Quantity
from recycleguard.contracts.domain import NonnegativeMass
from recycleguard.normalization.units import (
    NUMERIC_CONTEXT,
    NumericSafetyError,
    convert_mass_to_kg,
    format_decimal_string,
)

ZERO = Decimal("0")


def to_kg(quantity: Quantity) -> Decimal:
    """Exact kilograms of a metal-mass quantity; any other dimension is a hard error."""
    if quantity.dimension != "METAL_MASS":
        raise NumericSafetyError(f"DIMENSION_MISMATCH: {quantity.dimension} is not METAL_MASS")
    return convert_mass_to_kg(quantity.decimal, quantity.unit)


def add(left: Decimal, right: Decimal) -> Decimal:
    try:
        with localcontext(NUMERIC_CONTEXT):
            return left + right
    except (Inexact, Overflow, InvalidOperation) as exc:
        raise NumericSafetyError("numeric precision exceeded") from exc


def subtract(left: Decimal, right: Decimal) -> Decimal:
    try:
        with localcontext(NUMERIC_CONTEXT):
            return left - right
    except (Inexact, Overflow, InvalidOperation) as exc:
        raise NumericSafetyError("numeric precision exceeded") from exc


def total(values: Iterable[Decimal]) -> Decimal:
    accumulated = ZERO
    for value in values:
        accumulated = add(accumulated, value)
    return accumulated


def _clean(value: Decimal) -> Decimal:
    # Negative zero must never reach a quantity string.
    return value.copy_abs() if value == 0 else value


def signed(value: Decimal, metal: str) -> Quantity:
    return Quantity(
        decimal=format_decimal_string(_clean(value)),
        unit="KG",
        dimension="METAL_MASS",
        metal=metal,
    )


def mass(value: Decimal, metal: str) -> NonnegativeMass:
    if value < 0:
        raise NumericSafetyError("a nonnegative mass cannot be negative")
    return NonnegativeMass(
        decimal=format_decimal_string(_clean(value)),
        unit="KG",
        dimension="METAL_MASS",
        metal=metal,
    )
