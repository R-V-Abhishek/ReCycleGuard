"""Deterministic starter world generator for Task S01.

Constructs the canonical 100/55/45 reference scenario (case_001) embodying:
- 100.0000 KG Copper obligation (FY 2024-25) for Apex Electronics India Pvt Ltd
- 55.0000 KG supported allocation from GreenTech Recyclers LLP (cert:rec_001)
- Two overlapping observations of the 55.0000 KG transfer (F02 duplication)
- 25.0000 KG commercial invoice/payment with transfer pending (not supported)
- Official portal account snapshot showing 55.0000 KG for comparison
- Reference calculations (100 required, 55 supported, 45 gap, 25 pending)
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from benchmarks.generator.cp0_sources import STAMP, complete_visible_provenance
from benchmarks.generator.invoice_builder import (
    B2BInvoiceData,
    InvoiceItem,
    build_b2b_invoice_pdf,
)

# Constants for case_001
CASE_ID = "case:001"
PRODUCER_ID = "entity:prod_001"
RECYCLER_ID = "entity:rec_001"
BUCKET_ID = "bucket:prod_001_cu_2024_2025"
CERT_ID = "cert:rec_001"
LOT_ID = "lot:rec_001"
EVENT_ID = "evt:trans_001"
ALLOCATION_ID = "alloc:001"
COMMERCIAL_ID = "comm:inv_001"
BALANCE_OBS_ID = "bal:snap_001"
WATERMARK = "SYNTHETIC - NOT A CPCB RECORD"


def compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hexadecimal digest."""
    return hashlib.sha256(data).hexdigest()


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Write records as LF-terminated, key-sorted JSON lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for rec in records:
            line = json.dumps(rec, sort_keys=True, ensure_ascii=False)
            f.write(line + "\n")


def build_case_001(fixtures_dir: Path | str) -> dict[str, Any]:
    """Generate all records, documents, manifest, and expected oracle assertions."""
    root = Path(fixtures_dir)
    case_dir = root / "visible" / "case_001"
    records_dir = case_dir / "records"
    docs_dir = case_dir / "documents"
    expected_dir = root / "expected"

    records_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    expected_dir.mkdir(parents=True, exist_ok=True)

    # 1. entities.jsonl
    entities = [
        {
            "record_id": PRODUCER_ID,
            "record_revision_id": "rev:ent_001",
            "record_type": "Entity",
            "case_id": CASE_ID,
            "observation_refs": ["obs:ent_001"],
            "derived_from_record_refs": [],
            "validation_state": "VALID",
            "created_by_operation_id": "op:init_001",
            "supersedes_revision_id": None,
            "entity_id": PRODUCER_ID,
            "legal_name": "Apex Electronics India Pvt Ltd",
            "roles": ["PRODUCER"],
            "identifiers": [
                {
                    "kind": "GSTIN",
                    "value": "29AAACA1234A1Z5",
                    "validation_state": "VALID",
                    "evidence_refs": [],
                },
                {
                    "kind": "PAN",
                    "value": "AAACA1234A",
                    "validation_state": "VALID",
                    "evidence_refs": [],
                },
            ],
            "synthetic": True,
            "aliases": [],
        },
        {
            "record_id": RECYCLER_ID,
            "record_revision_id": "rev:ent_002",
            "record_type": "Entity",
            "case_id": CASE_ID,
            "observation_refs": ["obs:ent_002"],
            "derived_from_record_refs": [],
            "validation_state": "VALID",
            "created_by_operation_id": "op:init_001",
            "supersedes_revision_id": None,
            "entity_id": RECYCLER_ID,
            "legal_name": "GreenTech Recyclers LLP",
            "roles": ["RECYCLER"],
            "identifiers": [
                {
                    "kind": "GSTIN",
                    "value": "27AAACG9876B1Z2",
                    "validation_state": "VALID",
                    "evidence_refs": [],
                }
            ],
            "synthetic": True,
            "aliases": [],
        },
    ]
    write_jsonl(records_dir / "entities.jsonl", entities)

    # 2. registrations.jsonl
    registrations = [
        {
            "record_id": "reg:prod_001",
            "record_revision_id": "rev:reg_001",
            "record_type": "Registration",
            "case_id": CASE_ID,
            "observation_refs": ["obs:reg_001"],
            "derived_from_record_refs": [],
            "validation_state": "VALID",
            "created_by_operation_id": "op:init_001",
            "supersedes_revision_id": None,
            "entity_id": PRODUCER_ID,
            "registration_ref": "CPCB/EPR/PROD/2023/1042",
            "validity": {
                "start": "2023-04-01",
                "end": "2028-03-31",
                "end_open_ended": False,
                "review_state": "APPROVED",
                "applicability_scope": "GENERAL",
                "evidence_refs": [],
            },
            "covered_eee_codes": ["ITEW4"],
            "status_assertion": "ACTIVE",
            "evidence_as_of": {
                "raw": "2024-04-01T00:00:00Z",
                "value": "2024-04-01",
                "precision": "DATE",
                "timezone": "UTC",
                "interpretation_status": "REVIEWED",
            },
        },
        {
            "record_id": "reg:rec_001",
            "record_revision_id": "rev:reg_002",
            "record_type": "Registration",
            "case_id": CASE_ID,
            "observation_refs": ["obs:reg_002"],
            "derived_from_record_refs": [],
            "validation_state": "VALID",
            "created_by_operation_id": "op:init_001",
            "supersedes_revision_id": None,
            "entity_id": RECYCLER_ID,
            "registration_ref": "CPCB/EPR/REC/2023/0589",
            "validity": {
                "start": "2023-04-01",
                "end": "2028-03-31",
                "end_open_ended": False,
                "review_state": "APPROVED",
                "applicability_scope": "GENERAL",
                "evidence_refs": [],
            },
            "covered_eee_codes": ["ITEW4"],
            "status_assertion": "ACTIVE",
            "capacity": {
                "decimal": "500000.0000",
                "unit": "KG",
                "dimension": "METAL_MASS",
                "metal": "CU",
            },
            "evidence_as_of": {
                "raw": "2024-04-01T00:00:00Z",
                "value": "2024-04-01",
                "precision": "DATE",
                "timezone": "UTC",
                "interpretation_status": "REVIEWED",
            },
        },
    ]
    write_jsonl(records_dir / "registrations.jsonl", registrations)

    # 3. obligations.jsonl
    obligations = [
        {
            "record_id": BUCKET_ID,
            "record_revision_id": "rev:ob_001",
            "record_type": "ObligationBucket",
            "case_id": CASE_ID,
            "observation_refs": ["obs:ob_001"],
            "derived_from_record_refs": [],
            "validation_state": "VALID",
            "created_by_operation_id": "op:init_001",
            "supersedes_revision_id": None,
            "bucket_id": BUCKET_ID,
            "producer_entity_id": PRODUCER_ID,
            "liability_year": "2024-2025",
            "component": "STANDARD",
            "metal": "CU",
            "target": {
                "decimal": "100.0000",
                "unit": "KG",
                "dimension": "METAL_MASS",
                "metal": "CU",
            },
            "basis": "SUPPLIED_ACCOUNT",
            "basis_refs": [
                {
                    "ref_kind": "OBSERVATION",
                    "ref_id": "obs:ob_001",
                    "artifact_revision_id": None,
                    "locator": None,
                }
            ],
            "profile_id": "profile:producer_snapshot_v1",
            "adjustments": [],
        }
    ]
    write_jsonl(records_dir / "obligations.jsonl", obligations)

    # 4. certificates.jsonl
    certificates = [
        {
            "record_id": CERT_ID,
            "record_revision_id": "rev:cert_001",
            "record_type": "Certificate",
            "case_id": CASE_ID,
            "observation_refs": ["obs:cert_001"],
            "derived_from_record_refs": [],
            "validation_state": "VALID",
            "created_by_operation_id": "op:init_001",
            "supersedes_revision_id": None,
            "certificate_id": CERT_ID,
            "external_certificate_ref": "CPCB/EPR/REC/2024-25/KA/0589/CU/0001",
            "issuer_entity_id": RECYCLER_ID,
            "metal": "CU",
            "face_quantity": {
                "decimal": "55.0000",
                "unit": "KG",
                "dimension": "METAL_MASS",
                "metal": "CU",
            },
            "identity_evidence": [
                {
                    "ref_kind": "OBSERVATION",
                    "ref_id": "obs:cert_001",
                    "artifact_revision_id": None,
                    "locator": None,
                }
            ],
        }
    ]
    write_jsonl(records_dir / "certificates.jsonl", certificates)

    # 5. certificate_events.jsonl
    certificate_events = [
        {
            "record_id": EVENT_ID,
            "record_revision_id": "rev:evt_001",
            "record_type": "CertificateEvent",
            "case_id": CASE_ID,
            "observation_refs": ["obs:cert_001", "obs:cert_002"],
            "derived_from_record_refs": [],
            "validation_state": "VALID",
            "created_by_operation_id": "op:init_001",
            "supersedes_revision_id": None,
            "event_id": EVENT_ID,
            "certificate_id": CERT_ID,
            "credit_lot_id": LOT_ID,
            "event_kind": "TRANSFERRED",
            "external_event_ref": "TXN-2024-001",
            "event_time": {
                "raw": "2024-09-15T11:30:00Z",
                "value": "2024-09-15T11:30:00Z",
                "precision": "INSTANT",
                "timezone": "UTC",
                "interpretation_status": "REVIEWED",
            },
            "quantity": {
                "decimal": "55.0000",
                "unit": "KG",
                "dimension": "METAL_MASS",
                "metal": "CU",
            },
            "assertion_state": "SUPPORTED",
            "supporting_observations": ["obs:cert_001", "obs:cert_002"],
            "from_entity_id": RECYCLER_ID,
            "to_entity_id": PRODUCER_ID,
            "transfer_stage": "COMPLETED",
        }
    ]
    write_jsonl(records_dir / "certificate_events.jsonl", certificate_events)

    # 6. certificate_observations.jsonl (F02 duplication demonstration)
    certificate_observations = [
        {
            "observation_id": "obs:cert_001",
            "extraction_id": "ext:csv_001",
            "artifact_revision_id": "art:doc_csv_001",
            "locator": {
                "kind": "CSV_ROW",
                "page_index_1based": None,
                "printed_page_label": None,
                "row_index_1based": 2,
                "column_name": None,
                "json_pointer": None,
                "text_start": None,
                "text_end": None,
                "table_id": None,
                "cell_row": None,
                "cell_column": None,
            },
            "observation_type": "CertificateObservation",
            "raw_fields": {
                "txn_id": "TXN-2024-001",
                "cert_ref": "CPCB/EPR/REC/2024-25/KA/0589/CU/0001",
                "qty_kg": "55.0000",
                "metal": "CU",
                "stage": "COMPLETED",
            },
            "parsed_fields": {
                "certificate_id": CERT_ID,
                "quantity": "55.0000",
                "metal": "CU",
                "transfer_stage": "COMPLETED",
            },
            "validation_state": "VALID",
            "extraction_method": "CSV",
            "field_quality": {"certificate_ref": "EXACT", "quantity": "EXACT"},
            "event_time": {
                "raw": "2024-09-15T11:30:00Z",
                "value": "2024-09-15T11:30:00Z",
                "precision": "INSTANT",
                "timezone": "UTC",
                "interpretation_status": "PARSED",
            },
            "source_capture_time": {
                "raw": "2024-09-30T18:00:00Z",
                "value": "2024-09-30T18:00:00Z",
                "precision": "INSTANT",
                "timezone": "UTC",
                "interpretation_status": "REVIEWED",
            },
        },
        {
            "observation_id": "obs:cert_002",
            "extraction_id": "ext:json_001",
            "artifact_revision_id": "art:doc_portal_json_001",
            "locator": {
                "kind": "JSON_POINTER",
                "page_index_1based": None,
                "printed_page_label": None,
                "row_index_1based": None,
                "column_name": None,
                "json_pointer": "/portal_transactions/0",
                "text_start": None,
                "text_end": None,
                "table_id": None,
                "cell_row": None,
                "cell_column": None,
            },
            "observation_type": "CertificateObservation",
            "raw_fields": {
                "portal_reference": "CPCB/EPR/REC/2024-25/KA/0589/CU/0001",
                "transferred_amount": "55.0000",
                "metal_code": "CU",
                "status": "COMPLETED",
            },
            "parsed_fields": {
                "certificate_id": CERT_ID,
                "quantity": "55.0000",
                "metal": "CU",
                "transfer_stage": "COMPLETED",
            },
            "validation_state": "VALID",
            "extraction_method": "JSON",
            "field_quality": {"certificate_ref": "EXACT", "quantity": "EXACT"},
            "event_time": {
                "raw": "2024-09-15T11:30:00Z",
                "value": "2024-09-15T11:30:00Z",
                "precision": "INSTANT",
                "timezone": "UTC",
                "interpretation_status": "PARSED",
            },
            "source_capture_time": {
                "raw": "2024-10-05T12:00:00Z",
                "value": "2024-10-05T12:00:00Z",
                "precision": "INSTANT",
                "timezone": "UTC",
                "interpretation_status": "REVIEWED",
            },
        },
    ]
    write_jsonl(records_dir / "certificate_observations.jsonl", certificate_observations)

    # 7. allocations.jsonl
    allocations = [
        {
            "record_id": ALLOCATION_ID,
            "record_revision_id": "rev:alloc_001",
            "record_type": "Allocation",
            "case_id": CASE_ID,
            "observation_refs": ["obs:alloc_001"],
            "derived_from_record_refs": [EVENT_ID],
            "validation_state": "VALID",
            "created_by_operation_id": "op:init_001",
            "supersedes_revision_id": None,
            "allocation_id": ALLOCATION_ID,
            "credit_lot_id": LOT_ID,
            "event_id": EVENT_ID,
            "bucket_id": BUCKET_ID,
            "quantity": {
                "decimal": "55.0000",
                "unit": "KG",
                "dimension": "METAL_MASS",
                "metal": "CU",
            },
            "basis_refs": [
                {
                    "ref_kind": "RECORD",
                    "ref_id": EVENT_ID,
                    "artifact_revision_id": None,
                    "locator": None,
                }
            ],
            "state": "SUPPORTED",
            "profile_id": "profile:producer_snapshot_v1",
        }
    ]
    write_jsonl(records_dir / "allocations.jsonl", allocations)

    # 8. commercial_records.jsonl (Pending 25 kg invoice/payment record)
    commercial_records = [
        {
            "record_id": COMMERCIAL_ID,
            "record_revision_id": "rev:comm_001",
            "record_type": "CommercialRecord",
            "case_id": CASE_ID,
            "observation_refs": ["obs:inv_001"],
            "derived_from_record_refs": [],
            "validation_state": "VALID",
            "created_by_operation_id": "op:init_001",
            "supersedes_revision_id": None,
            "commercial_id": COMMERCIAL_ID,
            "record_kind": "INVOICE",
            "issuer_entity_id": RECYCLER_ID,
            "recipient_entity_id": PRODUCER_ID,
            "external_ref": "INV/2024-25/0842",
            "event_time": {
                "raw": "2024-10-10T14:15:00Z",
                "value": "2024-10-10T14:15:00Z",
                "precision": "INSTANT",
                "timezone": "UTC",
                "interpretation_status": "REVIEWED",
            },
            "linked_credit_refs": [],
            "money": {
                "decimal": "12500.0000",
                "unit": "INR",
                "dimension": "MONEY",
                "metal": None,
            },
            "credit_quantity": {
                "decimal": "25.0000",
                "unit": "KG",
                "dimension": "METAL_MASS",
                "metal": "CU",
            },
        }
    ]
    write_jsonl(records_dir / "commercial_records.jsonl", commercial_records)

    # 9. account_balances.jsonl (Comparison snapshot)
    account_balances = [
        {
            "record_id": BALANCE_OBS_ID,
            "record_revision_id": "rev:bal_001",
            "record_type": "AccountBalanceObservation",
            "case_id": CASE_ID,
            "observation_refs": ["obs:portal_snap_001"],
            "derived_from_record_refs": [],
            "validation_state": "VALID",
            "created_by_operation_id": "op:init_001",
            "supersedes_revision_id": None,
            "balance_observation_id": BALANCE_OBS_ID,
            "producer_entity_id": PRODUCER_ID,
            "bucket_id": BUCKET_ID,
            "reported_supported": {
                "decimal": "55.0000",
                "unit": "KG",
                "dimension": "METAL_MASS",
                "metal": "CU",
            },
            "reported_pending": {
                "decimal": "0.0000",
                "unit": "KG",
                "dimension": "METAL_MASS",
                "metal": "CU",
            },
            "source_capture_time": {
                "raw": "2024-10-15T09:00:00Z",
                "value": "2024-10-15T09:00:00Z",
                "precision": "INSTANT",
                "timezone": "UTC",
                "interpretation_status": "REVIEWED",
            },
            "business_cutoff": {
                "raw": "2024-09-30T23:59:59Z",
                "value": "2024-09-30T23:59:59Z",
                "precision": "INSTANT",
                "timezone": "UTC",
                "interpretation_status": "REVIEWED",
            },
            "basis_refs": [
                {
                    "ref_kind": "OBSERVATION",
                    "ref_id": "obs:portal_snap_001",
                    "artifact_revision_id": None,
                    "locator": None,
                }
            ],
        }
    ]
    write_jsonl(records_dir / "account_balances.jsonl", account_balances)

    # 10. Document 1: doc_ledger_export.csv
    csv_path = docs_dir / "doc_ledger_export.csv"
    csv_rows = [
        "Transaction_ID,Certificate_Ref,Transfer_Date,Issuer_GSTIN,Recipient_GSTIN,Metal,Quantity_KG,Transfer_Stage\n",
        "TXN-2024-001,CPCB/EPR/REC/2024-25/KA/0589/CU/0001,2024-09-15,27AAACG9876B1Z2,29AAACA1234A1Z5,CU,55.0000,COMPLETED\n",
        "TXN-2024-002,CPCB/EPR/REC/2024-25/KA/0589/CU/0002,2024-10-10,27AAACG9876B1Z2,29AAACA1234A1Z5,CU,25.0000,INITIATED\n",
    ]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        f.writelines(csv_rows)

    # 11. Synthetic B2B invoice/payment statement.
    pdf_path = docs_dir / "doc_invoice_payment.pdf"
    invoice_data = B2BInvoiceData(
        invoice_number="INV/2024-25/0842",
        invoice_date="2024-10-10",
        payment_terms="Due on Receipt (NEFT)",
        seller_name="GreenTech Recyclers LLP",
        seller_tagline="Authorised E-Waste Recycler & Material Recovery Facility",
        seller_address="Plot 42, Industrial Area, Phase II, Bangalore, KA - 560058",
        seller_contact="Phone: +91 80 2852 9000  |  Email: accounts@greentech.in",
        seller_gstin="27AAACG9876B1Z2",
        seller_reg_no="CPCB/EPR/REC/2023/0589",
        buyer_name="Apex Electronics India Pvt Ltd",
        buyer_gstin="29AAACA1234A1Z5",
        buyer_address="Electronics City Phase 1, Bangalore, KA - 560100",
        buyer_contact="Phone: +91 80 4123 4567  |  Email: accounts@apexelectronics.in",
        buyer_state="Karnataka (State Code: 29)",
        ship_to_facility="GreenTech Material Recovery Facility - Unit 1",
        ship_to_address="Plot 42, Industrial Area, Bangalore KA",
        ship_to_eee_code="EPR Category: ITEW4 (Information Technology Equipment)",
        ship_to_place="Place of Supply: Karnataka (State Code: 29)",
        items=[
            InvoiceItem(
                description="EPR Certificate Advance Booking - Copper (CU)",
                subtext="Category: ITEW4 | Target FY: 2024-25 | Pre-issuance Allotment",
                quantity="25.0000",
                unit="KG",
                unit_price="500.0000",
                total="12500.0000",
            )
        ],
        subtotal="12500.0000",
        discount="0.0000",
        subtotal_less_discount="12500.0000",
        tax_rate="0.00%",
        total_tax="0.0000",
        shipping_handling="0.0000",
        total_amount="12500.0000",
        amount_paid="12500.0000",
        balance_due="0.00",
        payment_remarks=[
            "Payment Mode: NEFT Ref N28492049182 (PAID IN FULL)",
            "Payment Date: 2024-10-10  |  Bank: HDFC Bank A/c 50200012345678",
            "",
            "CRITICAL REGULATORY COMPLIANCE STATUS:",
            "EPR Portal Transfer Status: PENDING RECYCLER AUTHENTICATION",
            "",
            "Rule 10 Guidance Notice:",
            "Formal credit transfer on the CPCB portal is subject to OTP and",
            "DSA digital key dispatch. Payment alone does not confer compliance.",
        ],
        watermark=WATERMARK,
    )
    build_b2b_invoice_pdf(pdf_path, invoice_data, seed=42)

    extra_paths = complete_visible_provenance(case_dir)

    # 12. case_manifest.json
    # Measure all asset digests and lengths
    all_asset_paths = [
        records_dir / "entities.jsonl",
        records_dir / "registrations.jsonl",
        records_dir / "obligations.jsonl",
        records_dir / "certificates.jsonl",
        records_dir / "certificate_events.jsonl",
        records_dir / "certificate_observations.jsonl",
        records_dir / "allocations.jsonl",
        records_dir / "commercial_records.jsonl",
        records_dir / "account_balances.jsonl",
        docs_dir / "doc_ledger_export.csv",
        docs_dir / "doc_invoice_payment.pdf",
        *extra_paths,
    ]

    assets_manifest = []
    for p in all_asset_paths:
        data = p.read_bytes()
        digest = compute_sha256(data)
        rel_path = str(p.relative_to(case_dir)).replace("\\", "/")

        if p.name.endswith(".jsonl"):
            record_types = {
                "entities": "Entity",
                "registrations": "Registration",
                "obligations": "ObligationBucket",
                "certificates": "Certificate",
                "certificate_events": "CertificateEvent",
                "certificate_observations": "Observation",
                "observations": "Observation",
                "allocations": "Allocation",
                "commercial_records": "CommercialRecord",
                "account_balances": "AccountBalanceObservation",
                "artifacts": "ArtifactRevision",
                "receipts": "AssetReceipt",
            }
            rec_type = record_types[p.stem]
            media_type = "application/x-ndjson"
        elif p.name.endswith(".csv"):
            rec_type = "DocumentExport"
            media_type = "text/csv"
        elif p.name.endswith(".pdf"):
            rec_type = "DocumentInvoice"
            media_type = "application/pdf"
        elif p.suffix == ".json":
            rec_type = "SourceDocument"
            media_type = "application/json"
        else:
            rec_type = "Unknown"
            media_type = "application/octet-stream"

        assets_manifest.append(
            {
                "relative_path": rel_path,
                "media_type": media_type,
                "body_digest": digest,
                "byte_length": len(data),
                "logical_record_type": rec_type,
                "source_capture_time": {
                    "raw": STAMP,
                    "value": STAMP,
                    "precision": "INSTANT",
                    "timezone": "UTC",
                    "interpretation_status": "REVIEWED",
                },
                "visibility": "VISIBLE",
            }
        )

    case_manifest = {
        "schema_version": "1.0",
        "case_id": CASE_ID,
        "synthetic": True,
        "watermark": WATERMARK,
        "producer_entity_id": PRODUCER_ID,
        "fiscal_year": "2024-2025",
        "period_start": "2024-04-01",
        "period_end_exclusive": "2025-04-01",
        "quarter": "ANNUAL",
        "allowed_eee_codes": ["ITEW4"],
        "allowed_metals": ["CU", "AL", "FE"],
        "calculation_profile_id": "profile:producer_snapshot_v1",
        "assets": assets_manifest,
        "optional_table_dispositions": [
            {
                "table": "product_mappings",
                "disposition": "ABSENT",
                "reason": "Supplied metal obligation profile v1",
            },
            {
                "table": "sales",
                "disposition": "ABSENT",
                "reason": "Target derived from supplied account baseline",
            },
            {
                "table": "return_drafts",
                "disposition": "ABSENT",
                "reason": "Return draft pending audit reconciliation",
            },
        ],
        "status": "DRAFT",
        "business_cutoff": {
            "raw": "2025-04-01T00:00:00Z",
            "value": "2025-04-01T00:00:00Z",
            "precision": "INSTANT",
            "timezone": "UTC",
            "interpretation_status": "PARSED",
        },
        "knowledge_cutoff": "2025-04-02T10:00:00Z",
        "adapter_versions": {"structured_json": "1.0", "ledger_csv": "1.0"},
        "evidence_expectations": [
            "supplied obligation",
            "supported allocation",
            "dated account comparison",
            "financial evidence does not establish allocation",
        ],
    }

    manifest_path = case_dir / "case_manifest.json"
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(case_manifest, indent=2, sort_keys=True) + "\n")

    # 13. tests/fixtures/expected/case_001_expected.json
    expected_oracle = {
        "case_id": CASE_ID,
        "profile_id": "profile:producer_snapshot_v1",
        "expected_balances": [
            {
                "bucket_id": BUCKET_ID,
                "metal": "CU",
                "fiscal_year": "2024-2025",
                "required_target": "100.0000",
                "ledger_supported": "55.0000",
                "signed_gap": "45.0000",
                "pending_quantity": "25.0000",
                "portal_reported": "55.0000",
                "delta_portal_vs_ledger": "0.0000",
                "status": "DISCREPANCY_DETECTED",
            }
        ],
        "expected_findings": [
            {
                "issue_type": "F02_OVERLAPPING_EXPORT",
                "description": (
                    "Two raw observations of cert:rec_001 corroborate the same "
                    "55.0000 KG allocation without double-counting."
                ),
                "resolution": "SUPPORTED_EQUIVALENCE",
                "quantity": "55.0000",
            },
            {
                "issue_type": "F07_PAID_NO_TRANSFER",
                "description": (
                    "Commercial record comm:inv_001 records payment for 25.0000 KG "
                    "of CU credits; transfer remains pending."
                ),
                "resolution": "PENDING_VERIFICATION",
                "quantity": "25.0000",
            },
        ],
        "audit_invariants": {
            "total_required": "100.0000",
            "total_supported": "55.0000",
            "total_gap": "45.0000",
            "total_pending": "25.0000",
            "unit": "KG",
            "dimension": "METAL_MASS",
        },
    }

    expected_path = expected_dir / "case_001_expected.json"
    with open(expected_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(expected_oracle, indent=2, sort_keys=True) + "\n")

    return {
        "manifest_path": manifest_path,
        "expected_path": expected_path,
        "total_assets": len(all_asset_paths),
    }


if __name__ == "__main__":
    out = build_case_001(Path("tests/fixtures"))
    print(f"Built starter world case_001 successfully with {out['total_assets']} assets.")
    print(f"Manifest written to: {out['manifest_path']}")
    print(f"Expected assertions written to: {out['expected_path']}")
