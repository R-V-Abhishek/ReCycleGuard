"""Four-workstream CP0 acceptance checks; no provider, acquisition or C08 tool is invoked."""

import csv
import hashlib
import json
import sqlite3
from pathlib import Path

import pdfplumber
import pytest

from benchmarks.evaluation.cp0_reference import reference_amounts
from benchmarks.generator.starter_world import build_case_001
from recycleguard.contracts import BlobRef, CommandContext
from recycleguard.contracts.artifacts import ArtifactRevision
from recycleguard.contracts.audit import AuditEvent, OperationIntent, OperationResult
from recycleguard.contracts.domain import RECORD_ADAPTER
from recycleguard.contracts.dossier import CaseManifest
from recycleguard.contracts.extraction import Observation
from recycleguard.storage import BlobIntegrityError, BlobStore, CommitBoundary, canonical_json_bytes

FIXTURES = Path(__file__).parents[1] / "fixtures"
CASE = FIXTURES / "visible/case_001"


def load_rows(name):
    return [json.loads(line) for line in (CASE / f"records/{name}.jsonl").read_text().splitlines()]


def test_every_visible_asset_roundtrips_through_v01_blob_store(tmp_path):
    store = BlobStore(tmp_path)
    manifest = CaseManifest.model_validate_json((CASE / "case_manifest.json").read_bytes())
    for asset in manifest.assets:
        body = (CASE / asset.relative_path).read_bytes()
        ref = store.put(body, asset.media_type)
        assert type(ref) is BlobRef
        assert (ref.sha256, ref.byte_length) == (asset.body_digest, asset.byte_length)
        assert store.get(ref) == body
        assert store.put(body, asset.media_type) == ref


def test_every_normalized_observation_ref_resolves_to_visible_original():
    observations = {
        v["observation_id"]: Observation.model_validate(v)
        for name in ("observations", "certificate_observations")
        for v in load_rows(name)
    }
    artifacts = {
        v["artifact_revision_id"]: ArtifactRevision.model_validate(v)
        for v in load_rows("artifacts")
    }
    for name in (
        "entities",
        "registrations",
        "obligations",
        "certificates",
        "certificate_events",
        "allocations",
        "commercial_records",
        "account_balances",
    ):
        for row in load_rows(name):
            record = RECORD_ADAPTER.validate_json(json.dumps(row))
            for oid in record.observation_refs:
                observation = observations[oid]
                artifact = artifacts[observation.artifact_revision_id]
                body = (CASE / "documents" / artifact.original_filename).read_bytes()
                assert hashlib.sha256(body).hexdigest() == artifact.blob.sha256
                loc = observation.locator
                if loc.kind == "JSON_POINTER":
                    value = json.loads(body)
                    for part in loc.json_pointer.strip("/").split("/"):
                        if part.isdigit():
                            value = value[int(part)]
                        else:
                            value = value[part.replace("~1", "/").replace("~0", "~")]
                    assert value == observation.raw_fields
                elif loc.kind == "CSV_ROW":
                    rows = list(csv.DictReader(body.decode().splitlines()))
                    assert rows[loc.row_index_1based - 1] == observation.raw_fields
                else:
                    pytest.fail(f"unexpected starter observation locator {loc.kind}")


def test_f02_has_matching_visible_external_event_identity_and_f03_is_distinct():
    first, second = load_rows("certificate_observations")
    event = load_rows("certificate_events")[0]
    assert first["raw_fields"]["Transaction_ID"] == second["raw_fields"]["transaction_id"]
    assert event["external_event_ref"] == first["raw_fields"]["Transaction_ID"]
    assert event["supporting_observations"] == [first["observation_id"], second["observation_id"]]
    # Sharing a certificate alone does not prove equivalence: a changed transaction is distinct.
    distinct = {**second["raw_fields"], "transaction_id": "TXN-2024-999"}
    assert first["raw_fields"]["Transaction_ID"] != distinct["transaction_id"]
    assert first["parsed_fields"]["certificate_id"] == second["parsed_fields"]["certificate_id"]


def test_independent_reference_and_pending_do_not_inflate_supported():
    expected = json.loads((FIXTURES / "expected/case_001_expected.json").read_text())
    balance = expected["expected_balances"][0]
    for key, value in reference_amounts().items():
        assert balance[key] == value
    allocation = load_rows("allocations")[0]
    assert allocation["state"] == "SUPPORTED" and allocation["quantity"]["decimal"] == "55.0000"
    commercial = load_rows("commercial_records")[0]
    assert commercial["credit_quantity"]["decimal"] == "25.0000"
    assert commercial["linked_credit_refs"] == []
    assert len(load_rows("allocations")) == 1


def test_renderer_reproduces_the_frozen_visible_pack(tmp_path):
    build_case_001(tmp_path)
    for original in CASE.rglob("*"):
        if original.is_file():
            assert (
                tmp_path / "visible/case_001" / original.relative_to(CASE)
            ).read_bytes() == original.read_bytes()


def make_operation(store, context_payload, suffix="sample"):
    context = CommandContext.model_validate(
        {
            **context_payload,
            "operation_id": f"operation:{suffix}",
            "attempt_id": f"attempt:{suffix}",
            "idempotency_key": suffix,
        }
    )
    payload = store.put(canonical_json_bytes(context.model_dump(mode="json")), "application/json")
    intent = OperationIntent(
        context=context, idempotency_key=suffix, event_type="cp0.fixture", payload=payload
    )
    result = OperationResult(
        operation_id=context.operation_id,
        attempt_id=context.attempt_id,
        status="SUCCESS",
        payload=payload,
    )
    return intent, result


def test_a01_context_v01_commit_and_chain_survive_reopen(tmp_path, context_payload):
    store = BlobStore(tmp_path)
    kernel = CommitBoundary(tmp_path / "audit.sqlite", store)
    intent, result = make_operation(store, context_payload)
    assert kernel.commit_intent(intent) == intent
    event = kernel.commit_result(intent, result)
    assert AuditEvent.model_validate_json(event.model_dump_json()) == event
    assert kernel.commit_result(intent, result) == event
    second, second_result = make_operation(store, context_payload, "second")
    kernel.commit_intent(second)
    next_event = kernel.commit_result(second, second_result)
    assert next_event.previous_event_hash == event.event_hash
    assert next_event.sequence == 2
    assert (
        hashlib.sha256(
            canonical_json_bytes(next_event.model_dump(mode="json", exclude={"event_hash"}))
        ).hexdigest()
        == next_event.event_hash
    )
    kernel.close()
    reopened = CommitBoundary(tmp_path / "audit.sqlite", store)
    assert reopened.commit_result(intent, result) == event
    reopened.close()


def test_reused_key_or_forged_intent_cannot_rebind_result(tmp_path, context_payload):
    store = BlobStore(tmp_path)
    kernel = CommitBoundary(tmp_path / "audit.sqlite", store)
    intent, result = make_operation(store, context_payload)
    kernel.commit_intent(intent)
    changed = intent.model_copy(update={"event_type": "forged"})
    with pytest.raises(ValueError, match="different input/context"):
        kernel.commit_intent(changed)
    with pytest.raises(ValueError, match="exact intent"):
        kernel.commit_result(changed, result)
    mismatch = result.model_copy(update={"attempt_id": "attempt:other"})
    with pytest.raises(ValueError, match="operation/attempt"):
        kernel.commit_result(intent, mismatch)
    kernel.close()


def test_terminal_result_and_event_roll_back_together(tmp_path, context_payload):
    store = BlobStore(tmp_path)
    kernel = CommitBoundary(tmp_path / "audit.sqlite", store)
    intent, result = make_operation(store, context_payload)
    kernel.commit_intent(intent)
    kernel.connection.execute(
        "CREATE TRIGGER fail_event BEFORE INSERT ON audit_events "
        "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
        kernel.commit_result(intent, result)
    assert kernel.connection.execute("SELECT count(*) FROM operation_results").fetchone()[0] == 0
    assert kernel.connection.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 0
    assert kernel.connection.execute("SELECT count(*) FROM operation_intents").fetchone()[0] == 1
    kernel.close()


def test_faq_example_is_supported_by_the_supplied_original():
    root = FIXTURES / "visible/h01"
    observation = Observation.model_validate_json((root / "observation_sample.json").read_bytes())
    with pdfplumber.open(root / "acquired_originals/cpcb_faq_20240123.pdf") as pdf:
        page = pdf.pages[observation.locator.page_index_1based - 1]
        normalized = " ".join(page.extract_text().split())
        assert observation.raw_fields["answer"] in normalized


def test_credit_lot_capacity_and_allocation_share_the_same_typed_identity():
    from recycleguard.contracts.domain import CreditLot

    lot = CreditLot.model_validate_json((FIXTURES / "expected/cp0_credit_lot.json").read_bytes())
    event = load_rows("certificate_events")[0]
    allocation = load_rows("allocations")[0]
    certificate = load_rows("certificates")[0]
    assert lot.credit_lot_id == event["credit_lot_id"] == allocation["credit_lot_id"]
    assert lot.certificate_id == certificate["certificate_id"] == event["certificate_id"]
    assert lot.supported_capacity.decimal == certificate["face_quantity"]["decimal"]
    assert lot.supported_capacity.decimal == allocation["quantity"]["decimal"]


def test_corrupted_or_absent_original_cannot_be_silently_read(tmp_path):
    store = BlobStore(tmp_path)
    ref = store.put(b"original", "text/plain")
    file = store.objects / ref.sha256[:2] / ref.sha256
    file.write_bytes(b"modified")
    with pytest.raises(BlobIntegrityError):
        store.get(ref)
    with pytest.raises(BlobIntegrityError):
        store.put(b"original", "text/plain")
    file.unlink()
    with pytest.raises(FileNotFoundError):
        store.get(ref)
