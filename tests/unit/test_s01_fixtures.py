"""Automated verification suite for Task S01: Starter World and Visible Dossier Fixtures.

Validates:
1. Manifest integrity (asset existence, exact byte lengths, SHA-256 digests).
2. Numeric safety (strict Decimal strings, no floating-point JSON values).
3. Opaque naming (no truth leakage or fault labels in file names or visible paths).
4. Mandatory watermark presence in synthetic PDF documents.
5. Exact 100/55/45 reference calculation and F02/F07 expectations in oracle fixtures.
"""

import hashlib
import json
import re
import unittest
from decimal import Decimal
from pathlib import Path

import pdfplumber

FIXTURES_ROOT = Path("tests/fixtures")
CASE_DIR = FIXTURES_ROOT / "visible" / "case_001"
MANIFEST_PATH = CASE_DIR / "case_manifest.json"
EXPECTED_PATH = FIXTURES_ROOT / "expected" / "case_001_expected.json"

DECIMAL_STRING_PATTERN = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")
FORBIDDEN_LEAK_WORDS = ["clean", "fault", "f02", "has_gap", "leak", "oracle"]


class TestS01StarterWorld(unittest.TestCase):
    """Test suite for S01 visible dossier and reference oracle fixtures."""

    def setUp(self) -> None:
        self.assertTrue(
            MANIFEST_PATH.exists(), f"Missing manifest at {MANIFEST_PATH}"
        )
        self.assertTrue(
            EXPECTED_PATH.exists(), f"Missing expected fixture at {EXPECTED_PATH}"
        )
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            self.manifest = json.load(f)
        with open(EXPECTED_PATH, "r", encoding="utf-8") as f:
            self.expected = json.load(f)

    def test_01_manifest_assets_integrity(self) -> None:
        """Every asset in manifest exists, and its byte length and SHA-256 match disk bytes."""
        assets = self.manifest.get("assets", [])
        self.assertGreater(
            len(assets), 0, "Manifest must have at least one asset"
        )

        for asset in assets:
            rel_path = asset["relative_path"]
            expected_digest = asset["body_digest"]
            expected_len = asset["byte_length"]

            file_path = CASE_DIR / rel_path
            self.assertTrue(
                file_path.exists(), f"Asset file missing on disk: {file_path}"
            )

            disk_bytes = file_path.read_bytes()
            actual_len = len(disk_bytes)
            actual_digest = hashlib.sha256(disk_bytes).hexdigest()

            self.assertEqual(
                actual_len,
                expected_len,
                f"Byte length mismatch for {rel_path}: expected {expected_len}, got {actual_len}",
            )
            self.assertEqual(
                actual_digest,
                expected_digest,
                f"SHA-256 mismatch for {rel_path}: expected {expected_digest}, got {actual_digest}",
            )

    def test_02_numeric_safety_and_no_floats(self) -> None:
        """All quantities must be valid Decimal strings, and no float values are in JSON records."""
        records_dir = CASE_DIR / "records"
        for jsonl_file in records_dir.glob("*.jsonl"):
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line_idx, line in enumerate(f, start=1):
                    rec = json.loads(line)

                    # Recursively verify no python float types exist
                    def check_no_floats(obj: object, path: str = "") -> None:
                        if isinstance(obj, float):
                            self.fail(
                                f"Float found in {jsonl_file.name}:{line_idx} at {path}: {obj}"
                            )
                        elif isinstance(obj, dict):
                            for k, v in obj.items():
                                check_no_floats(v, f"{path}.{k}" if path else k)
                                # Check quantity decimals
                                if k == "decimal" and isinstance(v, str):
                                    self.assertTrue(
                                        DECIMAL_STRING_PATTERN.match(v),
                                        f"Invalid decimal string {v} in {jsonl_file.name}:{line_idx} at {path}",
                                    )
                        elif isinstance(obj, list):
                            for i, v in enumerate(obj):
                                check_no_floats(v, f"{path}[{i}]")

                    check_no_floats(rec)

    def test_03_opaque_naming_and_no_leakage(self) -> None:
        """Visible paths, filenames, and IDs must never contain forbidden answer/fault words."""
        for asset in self.manifest.get("assets", []):
            rel_path = asset["relative_path"].lower()
            for forbidden in FORBIDDEN_LEAK_WORDS:
                self.assertNotIn(
                    forbidden,
                    rel_path,
                    f"Forbidden word '{forbidden}' leaked in asset path: {rel_path}",
                )

        # Check records IDs
        records_dir = CASE_DIR / "records"
        for jsonl_file in records_dir.glob("*.jsonl"):
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    rec_id = rec.get("record_id", "").lower()
                    for forbidden in FORBIDDEN_LEAK_WORDS:
                        self.assertNotIn(
                            forbidden,
                            rec_id,
                            f"Forbidden word '{forbidden}' leaked in record_id: {rec_id}",
                        )

    def test_04_pdf_watermark_present(self) -> None:
        """Rendered synthetic PDF must contain the mandatory CPCB watermark and B2B layout tokens."""
        pdf_path = CASE_DIR / "documents" / "doc_invoice_payment.pdf"
        self.assertTrue(pdf_path.exists(), f"PDF document not found: {pdf_path}")

        with pdfplumber.open(pdf_path) as pdf:
            self.assertGreater(len(pdf.pages), 0, "PDF has no pages")
            text = pdf.pages[0].extract_text() or ""
            self.assertIn(
                "SYNTHETIC - NOT A CPCB RECORD",
                text,
                "Mandatory watermark not found in PDF content",
            )
            self.assertIn("INV/2024-25/0842", text, "Invoice number missing in PDF")
            self.assertIn("25.0000", text, "Invoice quantity missing in PDF")
            self.assertIn("BILL TO", text, "BILL TO header missing in B2B PDF")
            self.assertIn("SHIP TO", text, "SHIP TO header missing in B2B PDF")
            self.assertIn("Balance Due", text, "Balance Due missing in B2B PDF")
            self.assertIn("LOGO", text, "Logo monogram missing in B2B PDF")

    def test_07_theme_diversity_and_determinism(self) -> None:
        """Invoice builder picks deterministic theme when seeded and supports palette variation."""
        from benchmarks.generator.invoice_builder import (
            INVOICE_THEMES,
            B2BInvoiceData,
            build_b2b_invoice_pdf,
        )

        dummy_data = B2BInvoiceData(
            invoice_number="INV/TEST/001",
            invoice_date="2024-10-10",
            payment_terms="Due on Receipt",
            seller_name="Seller A",
            seller_tagline="Recycler",
            seller_address="Addr 1",
            seller_contact="Contact",
            seller_gstin="27AAACG9876B1Z2",
            seller_reg_no="CPCB/001",
            buyer_name="Buyer B",
            buyer_gstin="29AAACA1234A1Z5",
            buyer_address="Addr 2",
            buyer_contact="Contact",
            buyer_state="KA",
            ship_to_facility="Facility 1",
            ship_to_address="Addr 3",
            ship_to_eee_code="ITEW4",
            ship_to_place="KA",
        )

        temp_pdf1 = Path("temp_theme_1.pdf")
        temp_pdf2 = Path("temp_theme_2.pdf")

        try:
            # Seed 42 should always yield Royal Purple
            theme1 = build_b2b_invoice_pdf(temp_pdf1, dummy_data, seed=42)
            theme1_repeat = build_b2b_invoice_pdf(temp_pdf2, dummy_data, seed=42)
            self.assertEqual(theme1.name, theme1_repeat.name)
            self.assertEqual(temp_pdf1.read_bytes(), temp_pdf2.read_bytes())

            # Seed 1 should deterministically yield Emerald Eco
            theme2 = build_b2b_invoice_pdf(temp_pdf2, dummy_data, seed=1)
            self.assertEqual(theme2.name, "Emerald Eco")
            self.assertNotEqual(theme1.name, theme2.name)

            # Palette coverage check
            self.assertEqual(len(INVOICE_THEMES), 7)
        finally:
            if temp_pdf1.exists():
                temp_pdf1.unlink()
            if temp_pdf2.exists():
                temp_pdf2.unlink()

    def test_05_reference_arithmetic_integrity(self) -> None:
        """Expected calculations must strictly satisfy 100 required - 55 supported = 45 gap, 25 pending."""
        expected_balances = self.expected.get("expected_balances", [])
        self.assertEqual(len(expected_balances), 1)

        bal = expected_balances[0]
        req = Decimal(bal["required_target"])
        supp = Decimal(bal["ledger_supported"])
        gap = Decimal(bal["signed_gap"])
        pending = Decimal(bal["pending_quantity"])

        self.assertEqual(req, Decimal("100.0000"))
        self.assertEqual(supp, Decimal("55.0000"))
        self.assertEqual(gap, Decimal("45.0000"))
        self.assertEqual(pending, Decimal("25.0000"))

        # Invariant: required - supported = gap
        self.assertEqual(
            req - supp, gap, "Arithmetic violation: required - supported != gap"
        )

        # Audit invariants
        inv = self.expected.get("audit_invariants", {})
        self.assertEqual(Decimal(inv["total_required"]), Decimal("100.0000"))
        self.assertEqual(Decimal(inv["total_supported"]), Decimal("55.0000"))
        self.assertEqual(Decimal(inv["total_gap"]), Decimal("45.0000"))
        self.assertEqual(Decimal(inv["total_pending"]), Decimal("25.0000"))

    def test_06_f02_and_f07_findings_registered(self) -> None:
        """Expected findings must cover F02 duplication and F07 pending payment."""
        findings = self.expected.get("expected_findings", [])
        issue_types = {f["issue_type"] for f in findings}

        self.assertIn(
            "F02_OVERLAPPING_EXPORT",
            issue_types,
            "F02 expected finding missing from oracle",
        )
        self.assertIn(
            "F07_PAID_NO_TRANSFER",
            issue_types,
            "F07 expected finding missing from oracle",
        )


if __name__ == "__main__":
    unittest.main()
