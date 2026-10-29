"""Unit tests for Gate G03 Numeric Safety:
Decimal arithmetic, conversions, and dimension isolation.
"""

import unittest
from decimal import Decimal

from recycleguard.normalization.units import (
    NumericSafetyError,
    add_quantities,
    convert_mass_to_kg,
    normalize_quantity,
    parse_strict_decimal,
    subtract_quantities,
)


class TestNumericSafety(unittest.TestCase):
    """Test suite asserting Gate G03 Numeric Safety compliance."""

    def test_01_parse_strict_decimal(self) -> None:
        """Parses clean string decimals and rejects binary floats / scientific notation."""
        d = parse_strict_decimal("100.0000")
        self.assertEqual(d, Decimal("100"))

        d_comma = parse_strict_decimal("1,250.50")
        self.assertEqual(d_comma, Decimal("1250.50"))

        # Floats must be rejected
        with self.assertRaises(NumericSafetyError):
            parse_strict_decimal(55.5)  # type: ignore

        # Scientific notation must be rejected
        with self.assertRaises(NumericSafetyError):
            parse_strict_decimal("1e5")

    def test_01b_indian_digit_grouping(self) -> None:
        """Lakh/crore grouping parses exactly and agrees with Western grouping."""
        cases = {
            "1,23,456.50": "123456.50",
            "12,34,56,789": "123456789",
            "10,00,000": "1000000",
            "1,00,000.0001": "100000.0001",
            "-2,50,000": "-250000",
            "12,345": "12345",
        }
        for raw, expected in cases.items():
            self.assertEqual(parse_strict_decimal(raw), Decimal(expected), raw)
        self.assertEqual(parse_strict_decimal("1,23,45,678"), parse_strict_decimal("12,345,678"))
        for bad in ("1,2,3", "1,23,4567", "12,3456", ",123", "1,23,", "123,45,678", "1,,234"):
            with self.assertRaises(NumericSafetyError, msg=bad):
                parse_strict_decimal(bad)

    def test_01c_indian_grouping_through_quantities(self) -> None:
        """Indian-grouped raw values convert exactly for mass, money and count."""
        self.assertEqual(
            normalize_quantity("1,23,456.5", "KG", "METAL_MASS", metal="CU").decimal, "123456.5000"
        )
        self.assertEqual(convert_mass_to_kg("1,234.5675", "TONNE"), Decimal("1234567.5"))
        self.assertEqual(normalize_quantity("4,72,118.40", "INR", "MONEY").decimal, "472118.4000")
        self.assertEqual(normalize_quantity("1,20,000", "UNIT_COUNT", "COUNT").decimal, "120000")

    def test_02_mass_conversion_tonne_to_kg(self) -> None:
        """Exact 1 Tonne = 1000 KG conversion."""
        self.assertEqual(convert_mass_to_kg("1", "TONNE"), Decimal("1000"))
        self.assertEqual(convert_mass_to_kg("0.055", "TONNE"), Decimal("55"))
        self.assertEqual(convert_mass_to_kg("55.0000", "KG"), Decimal("55"))

        with self.assertRaises(NumericSafetyError):
            convert_mass_to_kg("10", "POUNDS")

    def test_03_normalize_quantity_metal_mass(self) -> None:
        """Normalizes metal mass into standardized KG with valid metal code."""
        q = normalize_quantity("0.055", "TONNE", "METAL_MASS", metal="CU")
        self.assertEqual(q.decimal, "55.0000")
        self.assertEqual(q.unit, "KG")
        self.assertEqual(q.dimension, "METAL_MASS")
        self.assertEqual(q.metal, "CU")

        # Missing metal for METAL_MASS must fail
        with self.assertRaises(NumericSafetyError):
            normalize_quantity("55.0000", "KG", "METAL_MASS", metal=None)

        # Negative mass must fail
        with self.assertRaises(NumericSafetyError):
            normalize_quantity("-5.0000", "KG", "METAL_MASS", metal="CU")

    def test_04_normalize_quantity_money_and_count(self) -> None:
        """Normalizes money and count dimensions with unit constraints."""
        q_money = normalize_quantity("12500.5", "INR", "MONEY")
        self.assertEqual(q_money.decimal, "12500.5000")
        self.assertEqual(q_money.unit, "INR")
        self.assertEqual(q_money.dimension, "MONEY")
        self.assertIsNone(q_money.metal)

        q_count = normalize_quantity("42", "UNIT_COUNT", "COUNT")
        self.assertEqual(q_count.decimal, "42")
        self.assertEqual(q_count.dimension, "COUNT")

        # Fractional count must fail
        with self.assertRaises(NumericSafetyError):
            normalize_quantity("42.5", "UNIT_COUNT", "COUNT")

    def test_05_dimension_isolation_and_arithmetic(self) -> None:
        """Enforces dimension isolation during quantity addition and subtraction."""
        q_cu_100 = normalize_quantity("100.0000", "KG", "METAL_MASS", metal="CU")
        q_cu_55 = normalize_quantity("55.0000", "KG", "METAL_MASS", metal="CU")
        q_al_55 = normalize_quantity("55.0000", "KG", "METAL_MASS", metal="AL")
        q_money = normalize_quantity("5000.0000", "INR", "MONEY")

        # Compatible subtraction
        gap = subtract_quantities(q_cu_100, q_cu_55)
        self.assertEqual(gap.decimal, "45.0000")
        self.assertEqual(gap.metal, "CU")

        # Compatible addition
        total = add_quantities(q_cu_55, gap)
        self.assertEqual(total.decimal, "100.0000")

        # Cross-metal addition must fail
        with self.assertRaises(NumericSafetyError):
            add_quantities(q_cu_55, q_al_55)

        # Cross-dimension addition must fail
        with self.assertRaises(NumericSafetyError):
            add_quantities(q_cu_55, q_money)


if __name__ == "__main__":
    unittest.main()
