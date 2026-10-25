"""Finish S01's visible provenance for CP0; no hidden answer file is read here."""

import csv
import hashlib
import json
from pathlib import Path

from recycleguard.contracts import Locator, TemporalValue

STAMP = "2025-04-02T10:00:00Z"  # Fixed synthetic ingestion clock, not a real fetch claim.
ENVELOPE = {
    "record_id",
    "record_revision_id",
    "record_type",
    "case_id",
    "observation_refs",
    "derived_from_record_refs",
    "validation_state",
    "created_by_operation_id",
    "supersedes_revision_id",
}


def write_jsonl(path, records):
    with path.open("w", encoding="utf-8", newline="\n") as file:
        file.write("".join(json.dumps(r, sort_keys=True) + "\n" for r in records))


def locator(kind, **coordinates):
    return {**dict.fromkeys(Locator.model_fields), "kind": kind, **coordinates}


def temporal(value, precision="INSTANT"):
    return TemporalValue(
        raw=value, value=value, precision=precision, timezone="UTC", interpretation_status="PARSED"
    ).model_dump(mode="json")


def complete_visible_provenance(case_dir: Path) -> list[Path]:
    records_dir, docs = case_dir / "records", case_dir / "documents"
    rows = {}
    observations = []
    for path in sorted(records_dir.glob("*.jsonl")):
        if path.stem in {"certificate_observations", "observations", "artifacts", "receipts"}:
            continue
        for record in map(json.loads, path.read_text().splitlines()):
            for observation_id in record["observation_refs"]:
                if observation_id.startswith("obs:cert_"):
                    continue
                rows[observation_id] = {k: v for k, v in record.items() if k not in ENVELOPE}
    source_path = docs / "doc_source_records.json"
    with source_path.open("w", encoding="utf-8", newline="\n") as file:
        file.write(
            json.dumps({"synthetic": True, "source_rows": rows}, indent=2, sort_keys=True) + "\n"
        )
    for observation_id, payload in rows.items():
        observations.append(
            {
                "observation_id": observation_id,
                "extraction_id": "ext:source_records",
                "artifact_revision_id": "art:source_records",
                "locator": locator("JSON_POINTER", json_pointer=f"/source_rows/{observation_id}"),
                "observation_type": "SyntheticSourceRow",
                "raw_fields": payload,
                "parsed_fields": payload,
                "validation_state": "VALID",
                "extraction_method": "JSON",
                "field_quality": {},
                "event_time": {
                    "raw": None,
                    "value": None,
                    "precision": "UNKNOWN",
                    "timezone": None,
                    "interpretation_status": "UNKNOWN",
                },
                "source_capture_time": temporal(STAMP),
                "ingestion_time": STAMP,
            }
        )
    cert_path = records_dir / "certificate_observations.jsonl"
    certs = list(map(json.loads, cert_path.read_text().splitlines()))
    csv_path = docs / "doc_ledger_export.csv"
    with csv_path.open() as file:
        ledger = list(csv.DictReader(file))
    certs[0]["locator"]["row_index_1based"] = 1
    certs[0]["raw_fields"] = ledger[0]
    certs[0]["event_time"] = temporal(ledger[0]["Transfer_Date"], "DATE")
    portal_payload = {
        "portal_transactions": [
            {
                "transaction_id": "TXN-2024-001",
                "certificate_ref": ledger[0]["Certificate_Ref"],
                "quantity": "55.0000",
                "metal": "CU",
                "status": "COMPLETED",
                "event_time": "2024-09-15T11:30:00Z",
            }
        ]
    }
    portal_path = docs / "doc_portal_transactions.json"
    with portal_path.open("w", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(portal_payload, indent=2, sort_keys=True) + "\n")
    certs[1]["raw_fields"] = portal_payload["portal_transactions"][0]
    for cert in certs:
        cert["ingestion_time"] = STAMP
        cert["field_quality"] = {
            name: {
                "raw_score": None,
                "score_scale": "NOT_MEASURED",
                "engine": "synthetic_fixture",
                "validation_checks": ["source_locator_resolved"],
                "review_state": "DRAFT",
            }
            for name in ("certificate_ref", "quantity")
        }
    write_jsonl(cert_path, certs)
    observation_path = records_dir / "observations.jsonl"
    write_jsonl(observation_path, observations)

    # Bind visible original bytes to refs; no C02 persistence is claimed.
    source_specs = [
        (source_path, "art:source_records", "OTHER"),
        (portal_path, "art:doc_portal_json_001", "PORTAL_SNAPSHOT"),
        (csv_path, "art:doc_csv_001", "ERP_CSV"),
        (docs / "doc_invoice_payment.pdf", "art:invoice_pdf", "GST_INVOICE"),
    ]
    artifacts, receipts = [], []
    for path, revision_id, doc_type in source_specs:
        body = path.read_bytes()
        artifacts.append(
            {
                "artifact_id": revision_id.replace("art:", "artifact:"),
                "artifact_revision_id": revision_id,
                "blob": {
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "byte_length": len(body),
                    "media_type": "application/pdf"
                    if path.suffix == ".pdf"
                    else "text/csv"
                    if path.suffix == ".csv"
                    else "application/json",
                },
                "original_filename": path.name,
                "source_kind": "SYNTHETIC_RECORD",
                "doc_type": doc_type,
                "establishes": (
                    ["PAYMENT"]
                    if doc_type == "GST_INVOICE"
                    else ["LIABILITY_ALLOCATION", "REPORTED_ACCOUNT_POSITION", "IDENTITY"]
                    if path == source_path
                    else ["CERTIFICATE_IDENTITY", "TRANSFER_STAGE"]
                ),
                "does_not_establish": (
                    ["LIABILITY_ALLOCATION", "TRANSFER_STAGE", "PHYSICAL_MOVEMENT"]
                    if doc_type == "GST_INVOICE"
                    else ["PAYMENT", "PHYSICAL_MOVEMENT", "LIABILITY_ALLOCATION"]
                    if path != source_path
                    else ["PHYSICAL_MOVEMENT", "FILING_RECEIPT"]
                ),
                "source_url": None,
                "fetch_attempt_id": None,
                "captured_at": temporal(STAMP),
                "ingested_at": STAMP,
                "access_policy_id": "policy:synthetic_fixture",
                "rights_decision_id": "rights:synthetic_fixture",
                "synthetic": True,
                "derived_from": [],
            }
        )
        receipts.append(
            {
                "receipt_id": revision_id.replace("art:", "receipt:"),
                "batch_id": "batch:001",
                "declared_asset_id": revision_id.replace("art:", "asset:"),
                "supplied_path_or_url": f"documents/{path.name}",
                "intake_status": "RECEIVED",
                "artifact_revision_id": revision_id,
                "reason": "Synthetic fixture receipt; no live intake ran",
                "received_at": STAMP,
            }
        )
    artifact_path, receipt_path = records_dir / "artifacts.jsonl", records_dir / "receipts.jsonl"
    write_jsonl(artifact_path, artifacts)
    write_jsonl(receipt_path, receipts)
    return [source_path, portal_path, observation_path, artifact_path, receipt_path]
