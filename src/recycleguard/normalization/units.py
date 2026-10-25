"""Unit and dimension normalization engine for ReCycleGuard (Gate G03 Numeric Safety).

Enforces exact Decimal arithmetic, strict unit standardization (Tonne -> KG),
and dimension isolation across METAL_MASS, EQUIPMENT_MASS, MONEY, and COUNT.
"""

from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Literal

from recycleguard.contracts.core import DecimalString, Quantity
from recycleguard.contracts.domain import Metal, NonnegativeMass

# Canonical numeric context: 28 digits of precision, bankers rounding
NUMERIC_CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999)

MASS_CONVERSION_FACTORS: dict[str, Decimal] = {
    "KG": Decimal("1"),
    "TONNE": Decimal("1000"),
}


class NumericSafetyError(ValueError):
    """Raised when numeric parsing, unit conversion, or dimension safety fails."""


def parse_strict_decimal(value: str | int | Decimal) -> Decimal:
    """Parse an input into a strict Decimal without using binary floats."""
    if isinstance(value, float):
        raise NumericSafetyError(
            f"Binary float {value} is strictly prohibited; supply a DecimalString"
        )
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if not isinstance(value, str):
        raise NumericSafetyError(f"Expected decimal string or int, got {type(value)}")

    val_str = value.strip().replace(",", "")
    if "e" in val_str.lower():
        raise NumericSafetyError(
            f"Scientific notation is forbidden in decimal values: {value}"
        )
    try:
        d = Decimal(val_str)
        if not d.is_finite():
            raise NumericSafetyError(f"Non-finite decimal: {value}")
        return d
    except InvalidOperation as e:
        raise NumericSafetyError(f"Invalid decimal string: {value}") from e


def format_decimal_string(d: Decimal, decimal_places: int = 4) -> str:
    """Format a Decimal into an exact DecimalString with fixed fractional digits."""
    q = Decimal(10) ** -decimal_places
    quantized = d.quantize(q, context=NUMERIC_CONTEXT)
    s = f"{quantized:f}"
    # Validate against contract rules
    integral, _, fractional = s.lstrip("-").partition(".")
    if len(integral) > 18 or len(fractional) > 8:
        raise NumericSafetyError(f"Decimal exceeds 18 integral or 8 fractional digits: {s}")
    return s


def convert_mass_to_kg(value: str | int | Decimal, unit: str) -> Decimal:
    """Convert any supported mass unit to exact Kilograms (KG)."""
    unit_upper = unit.strip().upper()
    if unit_upper not in MASS_CONVERSION_FACTORS:
        raise NumericSafetyError(
            f"Unsupported mass unit '{unit}'. Supported units: {list(MASS_CONVERSION_FACTORS.keys())}"
        )
    d = parse_strict_decimal(value)
    factor = MASS_CONVERSION_FACTORS[unit_upper]
    return d * factor


def normalize_quantity(
    raw_value: str | int | Decimal,
    raw_unit: str,
    dimension: Literal["METAL_MASS", "EQUIPMENT_MASS", "MONEY", "COUNT"],
    metal: Metal | None = None,
    decimal_places: int = 4,
) -> Quantity:
    """Normalize a raw quantity into a validated Quantity conforming to CONTRACTS §3.2."""
    raw_unit_upper = raw_unit.strip().upper()

    if dimension == "METAL_MASS":
        if metal not in {"AU", "CU", "AL", "FE"}:
            raise NumericSafetyError(
                f"METAL_MASS requires a valid Metal code (AU, CU, AL, FE), got: {metal}"
            )
        # Standardize mass to KG
        kg_decimal = convert_mass_to_kg(raw_value, raw_unit_upper)
        if kg_decimal < 0:
            raise NumericSafetyError(f"Metal mass cannot be negative: {kg_decimal}")
        formatted_dec = format_decimal_string(kg_decimal, decimal_places=decimal_places)
        return Quantity(
            decimal=formatted_dec,
            unit="KG",
            dimension="METAL_MASS",
            metal=metal,
        )

    elif dimension == "EQUIPMENT_MASS":
        if metal is not None:
            raise NumericSafetyError("EQUIPMENT_MASS must have metal=None")
        kg_decimal = convert_mass_to_kg(raw_value, raw_unit_upper)
        if kg_decimal < 0:
            raise NumericSafetyError(f"Equipment mass cannot be negative: {kg_decimal}")
        formatted_dec = format_decimal_string(kg_decimal, decimal_places=decimal_places)
        return Quantity(
            decimal=formatted_dec,
            unit="KG",
            dimension="EQUIPMENT_MASS",
            metal=None,
        )

    elif dimension == "MONEY":
        if metal is not None:
            raise NumericSafetyError("MONEY must have metal=None")
        if raw_unit_upper != "INR":
            raise NumericSafetyError(f"MONEY unit must be INR, got: {raw_unit}")
        d = parse_strict_decimal(raw_value)
        formatted_dec = format_decimal_string(d, decimal_places=decimal_places)
        return Quantity(
            decimal=formatted_dec,
            unit="INR",
            dimension="MONEY",
            metal=None,
        )

    elif dimension == "COUNT":
        if metal is not None:
            raise NumericSafetyError("COUNT must have metal=None")
        if raw_unit_upper != "UNIT_COUNT":
            raise NumericSafetyError(f"COUNT unit must be UNIT_COUNT, got: {raw_unit}")
        d = parse_strict_decimal(raw_value)
        if d % 1 != 0:
            raise NumericSafetyError(f"COUNT must be an integer, got: {d}")
        formatted_dec = format_decimal_string(d, decimal_places=0)
        return Quantity(
            decimal=formatted_dec,
            unit="UNIT_COUNT",
            dimension="COUNT",
            metal=None,
        )

    else:
        raise NumericSafetyError(f"Unknown dimension: {dimension}")


def add_quantities(q1: Quantity, q2: Quantity) -> Quantity:
    """Add two compatible quantities together with dimension isolation."""
    if q1.dimension != q2.dimension:
        raise NumericSafetyError(
            f"Dimension mismatch: cannot add {q1.dimension} and {q2.dimension}"
        )
    if q1.metal != q2.metal:
        raise NumericSafetyError(
            f"Metal mismatch: cannot add metal {q1.metal} and {q2.metal}"
        )
    if q1.unit != q2.unit:
        raise NumericSafetyError(
            f"Unit mismatch: quantities must be normalized to same unit first ({q1.unit} vs {q2.unit})"
        )

    d1 = Decimal(q1.decimal)
    d2 = Decimal(q2.decimal)
    total = d1 + d2
    formatted = format_decimal_string(total)
    return Quantity(
        decimal=formatted,
        unit=q1.unit,
        dimension=q1.dimension,
        metal=q1.metal,
    )


def subtract_quantities(minuend: Quantity, subtrahend: Quantity) -> Quantity:
    """Subtract subtrahend from minuend with dimension isolation."""
    if minuend.dimension != subtrahend.dimension:
        raise NumericSafetyError(
            f"Dimension mismatch: cannot subtract {subtrahend.dimension} from {minuend.dimension}"
        )
    if minuend.metal != subtrahend.metal:
        raise NumericSafetyError(
            f"Metal mismatch: cannot subtract metal {subtrahend.metal} from {minuend.metal}"
        )
    if minuend.unit != subtrahend.unit:
        raise NumericSafetyError(
            f"Unit mismatch: quantities must be normalized to same unit first ({minuend.unit} vs {subtrahend.unit})"
        )

    d1 = Decimal(minuend.decimal)
    d2 = Decimal(subtrahend.decimal)
    res = d1 - d2
    formatted = format_decimal_string(res)
    return Quantity(
        decimal=formatted,
        unit=minuend.unit,
        dimension=minuend.dimension,
        metal=minuend.metal,
    )
