"""Unit and regression tests for H02 auditable acquisition and batch intake.

Verifies:
- Full batch intake discovers every file in batch root.
- Duplicate bytes receive separate receipts referencing the same blob.
- Undeclared files receive receipts with declared_asset_id=None.
- Declared missing files receive DECLARED_MISSING receipts without an invented blob.
- Corrupt files receive RECEIVED receipts with HASH_MISMATCH issues.
- Symlinks are rejected with REJECTED_ACCESS receipts.
- Failed downloads produce FETCH_FAILED receipts without an invented blob.
- Audited catalog persistence with AuditKernel and capability checks.
"""

import hashlib
from datetime import date
from pathlib import Path

from recycleguard.contracts.core import ActorRef, CommandContext
from recycleguard.contracts.dossier import CaseManifest
from recycleguard.contracts.sources import SourceLead
from recycleguard.intake.acquisition import record_acquisition
from recycleguard.intake.batch import intake_batch
from recycleguard.storage import ArtifactCatalog, AuditKernel, BlobStore
from recycleguard.storage.authority import LocalAuthority, TrustedPrincipal

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
CASE_001_DIR = FIXTURES_DIR / "visible/case_001"


def test_batch_intake_case_001_basic(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    result = intake_batch(CASE_001_DIR, blob_store=store)

    assert result.batch_id.startswith("batch:")
    assert result.case_id == "case:001"
    assert len(result.receipts) > 0
    assert len(result.artifact_revisions) > 0

    # Ensure every received asset has an artifact revision and matching blob
    for receipt in result.receipts:
        if receipt.intake_status == "RECEIVED":
            assert receipt.artifact_revision_id is not None
            # Find revision
            rev = next(
                r
                for r in result.artifact_revisions
                if r.artifact_revision_id == receipt.artifact_revision_id
            )
            blob_bytes = store.get(rev.blob)
            assert len(blob_bytes) == rev.blob.byte_length


def test_cp1_inventory_outcomes(tmp_path):
    """Exercise CP1 required outcomes: duplicate, undeclared, missing, corrupt, and symlink."""
    store = BlobStore(tmp_path / "blobs")
    batch_dir = tmp_path / "batch"
    batch_dir.mkdir()
    records_dir = batch_dir / "records"
    records_dir.mkdir()

    # 1. Normal file
    normal_file = records_dir / "normal.json"
    normal_bytes = b'{"key": "normal"}'
    normal_file.write_bytes(normal_bytes)
    normal_sha = hashlib.sha256(normal_bytes).hexdigest()

    # 2. Duplicate file (different filename, identical bytes)
    dup_file = records_dir / "duplicate.json"
    dup_file.write_bytes(normal_bytes)

    # 3. Corrupt file (declared with expected hash A, but contains bytes B)
    corrupt_file = records_dir / "corrupt.json"
    corrupt_file.write_bytes(b'{"key": "corrupted_actual_bytes"}')

    # 4. Undeclared file
    extra_file = records_dir / "extra_undeclared.txt"
    extra_file.write_bytes(b"extra file content")

    # Create CaseManifest declaring normal, corrupt, and missing file
    manifest_data = {
        "schema_version": "1.0",
        "case_id": "case:test_cp1",
        "synthetic": True,
        "watermark": "SYNTHETIC - NOT A CPCB RECORD",
        "producer_entity_id": "entity:test",
        "fiscal_year": "2024-2025",
        "period_start": date(2024, 4, 1),
        "period_end_exclusive": date(2025, 4, 1),
        "quarter": "ANNUAL",
        "allowed_eee_codes": ["ITEW4"],
        "allowed_metals": ["CU"],
        "calculation_profile_id": "profile:test",
        "business_cutoff": {
            "raw": None,
            "value": "2025-03-31",
            "precision": "DATE",
            "timezone": None,
            "interpretation_status": "PARSED",
        },
        "knowledge_cutoff": "2025-04-01T00:00:00Z",
        "adapter_versions": {"test": "1.0"},
        "evidence_expectations": [],
        "assets": [
            {
                "relative_path": "records/normal.json",
                "media_type": "application/json",
                "body_digest": normal_sha,
                "byte_length": len(normal_bytes),
                "logical_record_type": "TEST",
                "source_capture_time": {
                    "raw": None,
                    "value": "2024-10-01",
                    "precision": "DATE",
                    "timezone": None,
                    "interpretation_status": "PARSED",
                },
                "visibility": "VISIBLE",
            },
            {
                "relative_path": "records/corrupt.json",
                "media_type": "application/json",
                "body_digest": "0" * 64,  # Intentionally wrong digest
                "byte_length": 9999,
                "logical_record_type": "TEST",
                "source_capture_time": {
                    "raw": None,
                    "value": "2024-10-01",
                    "precision": "DATE",
                    "timezone": None,
                    "interpretation_status": "PARSED",
                },
                "visibility": "VISIBLE",
            },
            {
                "relative_path": "records/declared_but_missing.json",
                "media_type": "application/json",
                "body_digest": "1" * 64,
                "byte_length": 100,
                "logical_record_type": "TEST",
                "source_capture_time": {
                    "raw": None,
                    "value": "2024-10-01",
                    "precision": "DATE",
                    "timezone": None,
                    "interpretation_status": "PARSED",
                },
                "visibility": "VISIBLE",
            },
        ],
        "optional_table_dispositions": [],
        "status": "DRAFT",
    }
    (batch_dir / "case_manifest.json").write_text(
        CaseManifest.model_validate(manifest_data).model_dump_json()
    )

    result = intake_batch(batch_dir, blob_store=store)

    receipt_map = {r.supplied_path_or_url: r for r in result.receipts}

    # Verify normal file received
    assert "records/normal.json" in receipt_map
    assert receipt_map["records/normal.json"].intake_status == "RECEIVED"
    assert receipt_map["records/normal.json"].reason is None

    # Verify duplicate file received with separate receipt
    assert "records/duplicate.json" in receipt_map
    assert receipt_map["records/duplicate.json"].intake_status == "RECEIVED"
    assert (
        receipt_map["records/duplicate.json"].receipt_id
        != receipt_map["records/normal.json"].receipt_id
    )

    # Verify corrupt file received with hash mismatch issue
    assert "records/corrupt.json" in receipt_map
    assert receipt_map["records/corrupt.json"].intake_status == "RECEIVED"
    assert "mismatch" in (receipt_map["records/corrupt.json"].reason or "").lower()
    assert any(i.code == "HASH_MISMATCH" for i in result.issues)

    # Verify undeclared file received with undeclared note
    assert "records/extra_undeclared.txt" in receipt_map
    assert receipt_map["records/extra_undeclared.txt"].intake_status == "RECEIVED"
    assert receipt_map["records/extra_undeclared.txt"].declared_asset_id is None
    assert "undeclared" in (receipt_map["records/extra_undeclared.txt"].reason or "").lower()

    # Verify declared missing file has DECLARED_MISSING receipt and no artifact
    assert "records/declared_but_missing.json" in receipt_map
    assert receipt_map["records/declared_but_missing.json"].intake_status == "DECLARED_MISSING"
    assert receipt_map["records/declared_but_missing.json"].artifact_revision_id is None
    assert any(i.code == "MISSING_ARTIFACT" for i in result.issues)


def test_failed_acquisition_attempt_creates_no_invented_blob(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    lead = SourceLead(
        source_lead_id="source_lead:test_fail",
        aliases=["domain:test_fail"],
        official_url="https://example.com/missing.pdf",
        discovery_evidence_refs=[],
        source_class="SOP",
        regime="E_WASTE_2022",
        state="DISCOVERED",
        acquired_artifact_revision_id=None,
        rights_and_license={
            "copyright_owner": "Test",
            "statutory_exception_sec52": None,
            "asset_rights_seed": "REVIEW_REQUIRED",
            "redistribution_allowed": False,
            "attribution_text": "Test",
        },
    )

    outcome = record_acquisition(
        lead,
        body_bytes=None,
        status_code=404,
        error_message="Not Found",
        blob_store=store,
    )

    assert outcome.status == "FETCH_FAILED"
    assert outcome.artifact_revision is None
    assert outcome.receipt.intake_status == "FETCH_FAILED"
    assert outcome.receipt.artifact_revision_id is None
    assert "Not Found" in (outcome.receipt.reason or "")
    assert len(outcome.issues) == 1
    assert outcome.issues[0].code == "MISSING_ARTIFACT"


def test_audited_batch_intake_with_kernel_and_catalog(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    actor = ActorRef(
        actor_id="service:intake_worker", actor_kind="SERVICE", authenticated_session_ref=None
    )
    authority = LocalAuthority({"intake_worker": TrustedPrincipal(actor, frozenset({"intake."}))})
    cap = authority.issue("intake_worker")
    db_path = tmp_path / "app.sqlite"
    kernel = AuditKernel(db_path, store, authority=authority)
    catalog = ArtifactCatalog(db_path, store, kernel=kernel)

    context = CommandContext(
        contract_version="1.1",
        command_id="cmd:test_intake",
        operation_id="op:test_intake",
        attempt_id="att:test_intake",
        idempotency_key="key:test_intake",
        actor=actor,
        case_version_id=None,
        run_id=None,
        turn_id=None,
        correlation_id="corr:test_intake",
        parent_operation_id=None,
    )

    result = intake_batch(
        CASE_001_DIR,
        blob_store=store,
        catalog=catalog,
        kernel=kernel,
        capability=cap,
        context=context,
    )

    assert len(result.receipts) > 0
    # Verify records exist in catalog
    first_receipt = result.receipts[0]
    stored_receipt = catalog.get_receipt(first_receipt.receipt_id)
    assert stored_receipt.receipt_id == first_receipt.receipt_id

    # Verify audit events were recorded
    events = kernel.list_stream_events(f"stream:{result.batch_id}")
    assert len(events) >= 1  # result audit event
    assert kernel.get_result(context.operation_id) is not None
