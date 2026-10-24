"""V02 storage tests — immutable blob store, artifact catalog and audited commit kernel.

Tests are grouped by the plan's required verification points:
  1. Blob/catalog round-trips
  2. Intent-before-write ordering
  3. Atomic result/event commits
  4. Idempotency
  5. Failure handling (crashes, corrupt blobs, permission violations, missing refs)

Each test uses real SQLite and real filesystem blobs in tmp_path; no mocks.
"""

import hashlib
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from recycleguard.contracts import BlobRef, CommandContext
from recycleguard.contracts.artifacts import ArtifactRevision, AssetReceipt, FrozenSnapshot
from recycleguard.contracts.audit import OperationIntent, OperationResult
from recycleguard.contracts.core import ActorRef, TemporalValue
from recycleguard.storage import ArtifactCatalog, AuditKernel, BlobIntegrityError, BlobStore
from recycleguard.storage import canonical_json_bytes
from recycleguard.storage.catalog import CatalogError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _actor(kind: str = "SERVICE") -> ActorRef:
    return ActorRef(
        actor_id="service:test",
        actor_kind=kind,
        authenticated_session_ref=None,
    )


def _context(
    suffix: str = "t1",
    *,
    actor_kind: str = "SERVICE",
    case_version_id: str | None = "case_version:v1",
    run_id: str | None = "run:r1",
) -> CommandContext:
    return CommandContext(
        contract_version="1.1",
        command_id=f"command:{suffix}",
        operation_id=f"operation:{suffix}",
        attempt_id=f"attempt:{suffix}",
        idempotency_key=suffix,
        actor=_actor(actor_kind),
        case_version_id=case_version_id,
        run_id=run_id,
        turn_id=None,
        correlation_id=f"correlation:{suffix}",
        parent_operation_id=None,
    )


def _intent(
    store: BlobStore,
    ctx: CommandContext,
    event_type: str = "intake.import",
    payload_bytes: bytes = b"{}",
) -> OperationIntent:
    ref = store.put(payload_bytes, "application/json")
    return OperationIntent(
        context=ctx,
        idempotency_key=ctx.idempotency_key,
        event_type=event_type,
        payload=ref,
        stream_id="stream:test",
    )


def _success_result(ctx: CommandContext, payload: BlobRef) -> OperationResult:
    return OperationResult(
        operation_id=ctx.operation_id,
        attempt_id=ctx.attempt_id,
        status="SUCCESS",
        payload=payload,
    )


def _failed_result(ctx: CommandContext) -> OperationResult:
    return OperationResult(
        operation_id=ctx.operation_id,
        attempt_id=ctx.attempt_id,
        status="FAILED",
        payload=None,
        issue_codes=["MISSING_ARTIFACT"],
    )


def _artifact_revision(
    store: BlobStore,
    body: bytes = b"test artifact body",
    artifact_id: str = "artifact:a1",
    revision_suffix: str = "r1",
) -> ArtifactRevision:
    ref = store.put(body, "application/octet-stream")
    return ArtifactRevision(
        artifact_id=artifact_id,
        artifact_revision_id=f"artifact_revision:{artifact_id.split(':')[1]}_{revision_suffix}",
        blob=ref,
        original_filename="test.bin",
        source_kind="SYNTHETIC_RECORD",
        doc_type="OTHER",
        establishes=[],
        does_not_establish=[],
        source_url=None,
        fetch_attempt_id=None,
        captured_at=TemporalValue(
            raw="2024-04-01",
            value="2024-04-01",
            precision="DATE",
            timezone=None,
            interpretation_status="PARSED",
        ),
        ingested_at=_now(),
        access_policy_id="policy:default",
        rights_decision_id="rights:default",
        synthetic=True,
        derived_from=[],
    )


def _receipt(
    revision_id: str | None,
    receipt_id: str = "receipt:r1",
    batch_id: str = "batch:b1",
    status: str = "RECEIVED",
) -> AssetReceipt:
    return AssetReceipt(
        receipt_id=receipt_id,
        batch_id=batch_id,
        declared_asset_id=None,
        supplied_path_or_url="/test/path",
        intake_status=status,
        artifact_revision_id=revision_id,
        reason=None if status == "RECEIVED" else "fetch failed",
        received_at=_now(),
    )


# ===========================================================================
# 1. BLOB / CATALOG ROUND-TRIPS
# ===========================================================================


class TestBlobRoundTrip:
    def test_put_and_get_binary(self, tmp_path):
        store = BlobStore(tmp_path)
        data = b"\x00\x01\x02\x03" * 256
        ref = store.put(data, "application/octet-stream")
        assert store.get(ref) == data

    def test_put_and_get_json(self, tmp_path):
        store = BlobStore(tmp_path)
        payload = canonical_json_bytes({"key": "value", "number": 42})
        ref = store.put(payload, "application/json")
        assert store.get(ref) == payload

    def test_put_is_idempotent(self, tmp_path):
        store = BlobStore(tmp_path)
        data = b"idempotent"
        ref1 = store.put(data, "text/plain")
        ref2 = store.put(data, "text/plain")
        assert ref1 == ref2

    def test_put_stores_in_sharded_path(self, tmp_path):
        store = BlobStore(tmp_path)
        data = b"shard test"
        ref = store.put(data, "text/plain")
        expected_path = store.objects / ref.sha256[:2] / ref.sha256
        assert expected_path.is_file()
        assert expected_path.read_bytes() == data

    def test_empty_blob_round_trips(self, tmp_path):
        store = BlobStore(tmp_path)
        ref = store.put(b"", "application/octet-stream")
        assert ref.byte_length == 0
        assert store.get(ref) == b""

    def test_large_blob_round_trips(self, tmp_path):
        store = BlobStore(tmp_path)
        data = b"x" * 1_000_000
        ref = store.put(data, "application/octet-stream")
        assert store.get(ref) == data

    def test_corrupt_blob_is_detected_on_get(self, tmp_path):
        store = BlobStore(tmp_path)
        ref = store.put(b"original", "text/plain")
        blob_path = store.objects / ref.sha256[:2] / ref.sha256
        blob_path.write_bytes(b"tampered")
        with pytest.raises(BlobIntegrityError, match="digest mismatch"):
            store.get(ref)

    def test_length_mismatch_is_detected_on_get(self, tmp_path):
        store = BlobStore(tmp_path)
        data = b"length check"
        ref = store.put(data, "text/plain")
        blob_path = store.objects / ref.sha256[:2] / ref.sha256
        # Write bytes with correct hash prefix but wrong length by appending
        blob_path.write_bytes(data + b"\x00")
        with pytest.raises(BlobIntegrityError, match="length mismatch"):
            store.get(ref)

    def test_missing_blob_raises_file_not_found(self, tmp_path):
        store = BlobStore(tmp_path)
        fake_digest = "a" * 64
        ref = BlobRef(sha256=fake_digest, byte_length=5, media_type="text/plain")
        with pytest.raises(FileNotFoundError):
            store.get(ref)

    def test_corrupt_existing_blob_blocks_re_put(self, tmp_path):
        store = BlobStore(tmp_path)
        data = b"original"
        ref = store.put(data, "text/plain")
        blob_path = store.objects / ref.sha256[:2] / ref.sha256
        blob_path.write_bytes(b"different")
        with pytest.raises(BlobIntegrityError):
            store.put(data, "text/plain")


class TestArtifactCatalogRoundTrip:
    def test_put_and_get_artifact_revision(self, tmp_path):
        store = BlobStore(tmp_path)
        catalog = ArtifactCatalog(tmp_path / "catalog.sqlite", store)
        rev = _artifact_revision(store)
        stored = catalog.put_artifact_revision(rev)
        assert stored == rev
        assert catalog.get_artifact_revision(rev.artifact_revision_id) == rev
        catalog.close()

    def test_put_artifact_idempotent(self, tmp_path):
        store = BlobStore(tmp_path)
        catalog = ArtifactCatalog(tmp_path / "catalog.sqlite", store)
        rev = _artifact_revision(store)
        r1 = catalog.put_artifact_revision(rev)
        r2 = catalog.put_artifact_revision(rev)
        assert r1 == r2 == rev
        catalog.close()

    def test_artifact_id_collision_with_different_content_raises(self, tmp_path):
        store = BlobStore(tmp_path)
        catalog = ArtifactCatalog(tmp_path / "catalog.sqlite", store)
        rev = _artifact_revision(store)
        catalog.put_artifact_revision(rev)
        # Build a different revision with the same ID (different blob)
        other_body = b"different body"
        other_ref = store.put(other_body, "application/octet-stream")
        # Manually build another revision that would have the same artifact_revision_id
        # but different content — easiest via model_copy
        different = rev.model_copy(
            update={"blob": other_ref, "original_filename": "different.bin"}
        )
        with pytest.raises(CatalogError, match="different content"):
            catalog.put_artifact_revision(different)
        catalog.close()

    def test_artifact_blob_must_exist_before_catalog_write(self, tmp_path):
        store = BlobStore(tmp_path)
        catalog = ArtifactCatalog(tmp_path / "catalog.sqlite", store)
        fake_ref = BlobRef(sha256="b" * 64, byte_length=10, media_type="application/octet-stream")
        rev = ArtifactRevision(
            artifact_id="artifact:missing",
            artifact_revision_id="artifact_revision:missing_r1",
            blob=fake_ref,
            original_filename=None,
            source_kind="SYNTHETIC_RECORD",
            doc_type="OTHER",
            establishes=[],
            does_not_establish=[],
            source_url=None,
            fetch_attempt_id=None,
            captured_at=TemporalValue(
                raw=None, value=None, precision="UNKNOWN",
                timezone=None, interpretation_status="UNKNOWN"
            ),
            ingested_at=_now(),
            access_policy_id="policy:default",
            rights_decision_id="rights:default",
            synthetic=True,
            derived_from=[],
        )
        with pytest.raises(FileNotFoundError):
            catalog.put_artifact_revision(rev)
        catalog.close()

    def test_list_revisions_for_artifact(self, tmp_path):
        store = BlobStore(tmp_path)
        catalog = ArtifactCatalog(tmp_path / "catalog.sqlite", store)
        r1 = _artifact_revision(store, b"body1", "artifact:multi", "v1")
        r2 = _artifact_revision(store, b"body2", "artifact:multi", "v2")
        catalog.put_artifact_revision(r1)
        catalog.put_artifact_revision(r2)
        listed = catalog.list_revisions_for_artifact("artifact:multi")
        assert len(listed) == 2
        assert {r.artifact_revision_id for r in listed} == {
            r1.artifact_revision_id, r2.artifact_revision_id
        }
        catalog.close()

    def test_get_missing_artifact_raises_key_error(self, tmp_path):
        store = BlobStore(tmp_path)
        catalog = ArtifactCatalog(tmp_path / "catalog.sqlite", store)
        with pytest.raises(KeyError, match="not found"):
            catalog.get_artifact_revision("artifact_revision:nonexistent_r1")
        catalog.close()


class TestReceiptCatalogRoundTrip:
    def test_received_receipt_requires_prior_revision(self, tmp_path):
        store = BlobStore(tmp_path)
        catalog = ArtifactCatalog(tmp_path / "catalog.sqlite", store)
        # Cannot put a RECEIVED receipt without the revision already in catalog
        with pytest.raises(KeyError):
            catalog.put_receipt(_receipt("artifact_revision:missing_r1"))
        catalog.close()

    def test_put_received_receipt_after_revision(self, tmp_path):
        store = BlobStore(tmp_path)
        catalog = ArtifactCatalog(tmp_path / "catalog.sqlite", store)
        rev = _artifact_revision(store)
        catalog.put_artifact_revision(rev)
        r = _receipt(rev.artifact_revision_id)
        stored = catalog.put_receipt(r)
        assert stored == r
        assert catalog.get_receipt(r.receipt_id) == r
        catalog.close()

    def test_failed_receipt_needs_no_revision(self, tmp_path):
        store = BlobStore(tmp_path)
        catalog = ArtifactCatalog(tmp_path / "catalog.sqlite", store)
        r = _receipt(
            revision_id=None,
            status="FETCH_FAILED",
            receipt_id="receipt:fail1",
        )
        stored = catalog.put_receipt(r)
        assert stored.intake_status == "FETCH_FAILED"
        catalog.close()

    def test_receipt_idempotent(self, tmp_path):
        store = BlobStore(tmp_path)
        catalog = ArtifactCatalog(tmp_path / "catalog.sqlite", store)
        rev = _artifact_revision(store)
        catalog.put_artifact_revision(rev)
        r = _receipt(rev.artifact_revision_id)
        r1 = catalog.put_receipt(r)
        r2 = catalog.put_receipt(r)
        assert r1 == r2
        catalog.close()

    def test_list_receipts_for_batch(self, tmp_path):
        store = BlobStore(tmp_path)
        catalog = ArtifactCatalog(tmp_path / "catalog.sqlite", store)
        rev1 = _artifact_revision(store, b"body1", "artifact:a1", "r1")
        rev2 = _artifact_revision(store, b"body2", "artifact:a2", "r1")
        catalog.put_artifact_revision(rev1)
        catalog.put_artifact_revision(rev2)
        r1 = _receipt(rev1.artifact_revision_id, "receipt:r1", "batch:b1")
        r2 = _receipt(rev2.artifact_revision_id, "receipt:r2", "batch:b1")
        catalog.put_receipt(r1)
        catalog.put_receipt(r2)
        listed = catalog.list_receipts_for_batch("batch:b1")
        assert len(listed) == 2
        catalog.close()


class TestSnapshotCatalogRoundTrip:
    def _make_snapshot(
        self, store: BlobStore, catalog: ArtifactCatalog, snapshot_id: str = "snapshot:s1"
    ) -> FrozenSnapshot:
        # Create and register a revision + receipt
        rev = _artifact_revision(store)
        catalog.put_artifact_revision(rev)
        r = _receipt(rev.artifact_revision_id, "receipt:sr1")
        catalog.put_receipt(r)

        membership_data = canonical_json_bytes({"member": "artifact:a1"})
        membership_ref = store.put(membership_data, "application/json")
        coverage_data = canonical_json_bytes({"coverage": "100%"})
        coverage_ref = store.put(coverage_data, "application/json")

        return FrozenSnapshot(
            snapshot_id=snapshot_id,
            snapshot_kind="CASE",
            schema_version="1.0",
            parent_snapshot_id=None,
            membership_blob=membership_ref,
            membership_digest=membership_ref.sha256,
            coverage_blob=coverage_ref,
            created_at=_now(),
            created_by="service:test",
            source_receipt_ids=["receipt:sr1"],
            review_state="DRAFT",
        )

    def test_put_and_get_snapshot(self, tmp_path):
        store = BlobStore(tmp_path)
        catalog = ArtifactCatalog(tmp_path / "catalog.sqlite", store)
        snapshot = self._make_snapshot(store, catalog)
        stored = catalog.put_snapshot(snapshot)
        assert stored == snapshot
        assert catalog.get_snapshot(snapshot.snapshot_id) == snapshot
        catalog.close()

    def test_snapshot_membership_blob_must_exist(self, tmp_path):
        store = BlobStore(tmp_path)
        catalog = ArtifactCatalog(tmp_path / "catalog.sqlite", store)
        snapshot = self._make_snapshot(store, catalog)
        # Replace with non-existent blob
        fake = BlobRef(sha256="c" * 64, byte_length=5, media_type="application/json")
        bad = snapshot.model_copy(update={"membership_blob": fake, "membership_digest": "c" * 64})
        with pytest.raises(FileNotFoundError):
            catalog.put_snapshot(bad)
        catalog.close()

    def test_snapshot_requires_received_receipts(self, tmp_path):
        store = BlobStore(tmp_path)
        catalog = ArtifactCatalog(tmp_path / "catalog.sqlite", store)
        snapshot = self._make_snapshot(store, catalog)

        # Add a failed receipt and reference it from the snapshot
        failed_r = _receipt(None, "receipt:fail1", status="FETCH_FAILED")
        catalog.put_receipt(failed_r)
        bad = snapshot.model_copy(
            update={"source_receipt_ids": ["receipt:sr1", "receipt:fail1"]}
        )
        with pytest.raises(CatalogError, match="non-RECEIVED"):
            catalog.put_snapshot(bad)
        catalog.close()

    def test_snapshot_membership_digest_mismatch_raises(self, tmp_path):
        store = BlobStore(tmp_path)
        catalog = ArtifactCatalog(tmp_path / "catalog.sqlite", store)
        snapshot = self._make_snapshot(store, catalog)
        bad = snapshot.model_copy(update={"membership_digest": "a" * 64})
        with pytest.raises(CatalogError, match="membership_digest"):
            catalog.put_snapshot(bad)
        catalog.close()

    def test_snapshot_idempotent(self, tmp_path):
        store = BlobStore(tmp_path)
        catalog = ArtifactCatalog(tmp_path / "catalog.sqlite", store)
        snapshot = self._make_snapshot(store, catalog)
        s1 = catalog.put_snapshot(snapshot)
        s2 = catalog.put_snapshot(snapshot)
        assert s1 == s2
        catalog.close()

    def test_list_snapshots_by_kind_and_review_state(self, tmp_path):
        store = BlobStore(tmp_path)
        catalog = ArtifactCatalog(tmp_path / "catalog.sqlite", store)
        s1 = self._make_snapshot(store, catalog, "snapshot:s1")
        catalog.put_snapshot(s1)
        listed = catalog.list_snapshots(kind="CASE", review_state="DRAFT")
        assert len(listed) == 1
        assert listed[0].snapshot_id == "snapshot:s1"
        catalog.close()

    def test_update_snapshot_review_state(self, tmp_path):
        store = BlobStore(tmp_path)
        catalog = ArtifactCatalog(tmp_path / "catalog.sqlite", store)
        snapshot = self._make_snapshot(store, catalog)
        catalog.put_snapshot(snapshot)
        updated = catalog.update_snapshot_review_state(snapshot.snapshot_id, "APPROVED")
        assert updated.review_state == "APPROVED"
        fetched = catalog.get_snapshot(snapshot.snapshot_id)
        assert fetched.review_state == "APPROVED"
        catalog.close()


# ===========================================================================
# 2. INTENT-BEFORE-WRITE ORDERING
# ===========================================================================


class TestIntentBeforeWrite:
    def test_result_without_prior_intent_raises(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        ctx = _context("no_intent")
        intent = _intent(store, ctx)
        result = _success_result(ctx, intent.payload)
        # Never commit the intent
        with pytest.raises(ValueError, match="intent-before-write"):
            kernel.commit_result(intent, result)
        kernel.close()

    def test_different_intent_content_blocks_result(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        ctx = _context("mismatched")
        intent = _intent(store, ctx)
        kernel.commit_intent(intent)
        # Forge a different intent with same operation_id
        forged = intent.model_copy(update={"event_type": "intake.forged"})
        result = _success_result(ctx, intent.payload)
        with pytest.raises(ValueError, match="intent-before-write"):
            kernel.commit_result(forged, result)
        kernel.close()

    def test_input_blob_must_exist_before_intent_commit(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        ctx = _context("missing_blob")
        fake_ref = BlobRef(sha256="d" * 64, byte_length=5, media_type="application/json")
        intent = OperationIntent(
            context=ctx,
            idempotency_key=ctx.idempotency_key,
            event_type="intake.import",
            payload=fake_ref,
            stream_id="stream:test",
        )
        with pytest.raises(FileNotFoundError):
            kernel.commit_intent(intent)
        kernel.close()

    def test_output_blob_must_exist_before_result_commit(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        ctx = _context("missing_output")
        intent = _intent(store, ctx)
        kernel.commit_intent(intent)
        fake_ref = BlobRef(sha256="e" * 64, byte_length=5, media_type="application/json")
        result = OperationResult(
            operation_id=ctx.operation_id,
            attempt_id=ctx.attempt_id,
            status="SUCCESS",
            payload=fake_ref,
        )
        with pytest.raises(FileNotFoundError):
            kernel.commit_result(intent, result)
        kernel.close()

    def test_capability_check_blocks_wrong_actor(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        # review.* events require HUMAN; SERVICE should be rejected
        ctx = _context("wrong_actor", actor_kind="SERVICE")
        intent = _intent(store, ctx, event_type="review.decision")
        with pytest.raises(ValueError, match="actor_kind"):
            kernel.commit_intent(intent)
        kernel.close()

    def test_capability_check_allows_correct_actor(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        ctx = _context("correct_actor", actor_kind="HUMAN", run_id=None, case_version_id=None)
        intent = _intent(store, ctx, event_type="review.decision")
        stored = kernel.commit_intent(intent)
        assert stored.idempotency_key == ctx.idempotency_key
        kernel.close()


# ===========================================================================
# 3. ATOMIC RESULT / EVENT COMMITS
# ===========================================================================


class TestAtomicCommits:
    def test_result_and_event_committed_atomically(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        ctx = _context("atomic")
        intent = _intent(store, ctx)
        kernel.commit_intent(intent)
        event = kernel.commit_result(intent, _success_result(ctx, intent.payload))
        assert kernel.get_result(ctx.operation_id) is not None
        assert kernel.get_event(event.event_id) is not None
        kernel.close()

    def test_audit_event_insert_failure_rolls_back_result(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        ctx = _context("rollback")
        intent = _intent(store, ctx)
        kernel.commit_intent(intent)
        kernel.connection.execute(
            "CREATE TRIGGER fail_event BEFORE INSERT ON audit_events "
            "BEGIN SELECT RAISE(ABORT, 'injected audit failure'); END"
        )
        with pytest.raises(sqlite3.IntegrityError, match="injected audit failure"):
            kernel.commit_result(intent, _success_result(ctx, intent.payload))
        # Result must also have been rolled back
        assert kernel.get_result(ctx.operation_id) is None
        # Intent must still be present (not rolled back)
        assert kernel.get_intent(ctx.operation_id) is not None
        kernel.close()

    def test_chain_of_two_events_links_hashes(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        ctx1 = _context("chain1")
        ctx2 = _context("chain2")
        i1 = _intent(store, ctx1)
        i2 = _intent(store, ctx2, payload_bytes=b'{"step":2}')

        kernel.commit_intent(i1)
        e1 = kernel.commit_result(i1, _success_result(ctx1, i1.payload))
        kernel.commit_intent(i2)
        e2 = kernel.commit_result(i2, _success_result(ctx2, i2.payload))

        assert e1.previous_event_hash is None
        assert e2.previous_event_hash == e1.event_hash
        assert e1.sequence == 1
        assert e2.sequence == 2

    def test_event_hash_covers_all_fields(self, tmp_path):
        """Verify the stored event_hash matches a freshly computed digest."""
        import hashlib
        from recycleguard.storage import canonical_json_bytes

        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        ctx = _context("hash_check")
        intent = _intent(store, ctx)
        kernel.commit_intent(intent)
        event = kernel.commit_result(intent, _success_result(ctx, intent.payload))

        computed = hashlib.sha256(
            canonical_json_bytes(event.model_dump(mode="json", exclude={"event_hash"}))
        ).hexdigest()
        assert computed == event.event_hash
        kernel.close()

    def test_failed_result_stored_with_issue_codes(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        ctx = _context("fail_result")
        intent = _intent(store, ctx)
        kernel.commit_intent(intent)
        result = _failed_result(ctx)
        event = kernel.commit_result(intent, result)
        stored = kernel.get_result(ctx.operation_id)
        assert stored.status == "FAILED"
        assert "MISSING_ARTIFACT" in stored.issue_codes
        assert event.event_type == "intake.import.result"
        kernel.close()

    def test_outcome_unknown_result_persists_correctly(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        ctx = _context("unknown_outcome")
        intent = _intent(store, ctx)
        kernel.commit_intent(intent)
        result = OperationResult(
            operation_id=ctx.operation_id,
            attempt_id=ctx.attempt_id,
            status="OUTCOME_UNKNOWN",
            payload=None,
            issue_codes=["AUDIT_UNAVAILABLE"],
        )
        event = kernel.commit_result(intent, result)
        stored = kernel.get_result(ctx.operation_id)
        assert stored.status == "OUTCOME_UNKNOWN"
        assert "AUDIT_UNAVAILABLE" in stored.issue_codes
        kernel.close()

    def test_multi_stream_sequences_are_independent(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)

        def _commit_on_stream(suffix: str, stream: str):
            ctx = _context(suffix)
            payload = store.put(f"{{\"s\":\"{stream}\"}}".encode(), "application/json")
            intent = OperationIntent(
                context=ctx,
                idempotency_key=ctx.idempotency_key,
                event_type="intake.import",
                payload=payload,
                stream_id=stream,
            )
            kernel.commit_intent(intent)
            result = _success_result(ctx, payload)
            return kernel.commit_result(intent, result)

        e_a1 = _commit_on_stream("a1", "stream:alpha")
        e_b1 = _commit_on_stream("b1", "stream:beta")
        e_a2 = _commit_on_stream("a2", "stream:alpha")

        assert e_a1.sequence == 1 and e_a1.stream_id == "stream:alpha"
        assert e_b1.sequence == 1 and e_b1.stream_id == "stream:beta"
        assert e_a2.sequence == 2 and e_a2.stream_id == "stream:alpha"
        assert e_a2.previous_event_hash == e_a1.event_hash
        assert e_b1.previous_event_hash is None
        kernel.close()


# ===========================================================================
# 4. IDEMPOTENCY
# ===========================================================================


class TestIdempotency:
    def test_intent_idempotent_with_same_payload(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        ctx = _context("idem_intent")
        intent = _intent(store, ctx)
        i1 = kernel.commit_intent(intent)
        i2 = kernel.commit_intent(intent)
        assert i1 == i2
        kernel.close()

    def test_intent_conflict_on_same_key_different_content(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        ctx = _context("idem_conflict")
        intent = _intent(store, ctx)
        kernel.commit_intent(intent)
        other_payload = store.put(b'{"v":2}', "application/json")
        different = intent.model_copy(update={"payload": other_payload, "event_type": "intake.other"})
        with pytest.raises(ValueError, match="different intent"):
            kernel.commit_intent(different)
        kernel.close()

    def test_result_idempotent_with_same_outcome(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        ctx = _context("idem_result")
        intent = _intent(store, ctx)
        kernel.commit_intent(intent)
        result = _success_result(ctx, intent.payload)
        e1 = kernel.commit_result(intent, result)
        e2 = kernel.commit_result(intent, result)
        assert e1 == e2
        kernel.close()

    def test_result_conflict_on_different_outcome(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        ctx = _context("idem_result_conflict")
        intent = _intent(store, ctx)
        kernel.commit_intent(intent)
        result1 = _success_result(ctx, intent.payload)
        kernel.commit_result(intent, result1)
        result2 = _failed_result(ctx)
        with pytest.raises(ValueError, match="different terminal result"):
            kernel.commit_result(intent, result2)
        kernel.close()

    def test_result_mismatch_on_attempt_id_raises(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        ctx = _context("attempt_mismatch")
        intent = _intent(store, ctx)
        kernel.commit_intent(intent)
        wrong = OperationResult(
            operation_id=ctx.operation_id,
            attempt_id="attempt:wrong",
            status="SUCCESS",
            payload=intent.payload,
        )
        with pytest.raises(ValueError, match="operation/attempt"):
            kernel.commit_result(intent, wrong)
        kernel.close()

    def test_kernel_survives_reopen(self, tmp_path):
        store = BlobStore(tmp_path)
        db = tmp_path / "audit.sqlite"
        kernel = AuditKernel(db, store)
        ctx = _context("reopen")
        intent = _intent(store, ctx)
        kernel.commit_intent(intent)
        event = kernel.commit_result(intent, _success_result(ctx, intent.payload))
        kernel.close()

        kernel2 = AuditKernel(db, store)
        assert kernel2.get_result(ctx.operation_id).status == "SUCCESS"
        # Idempotent after reopen
        event2 = kernel2.commit_result(intent, _success_result(ctx, intent.payload))
        assert event2 == event
        kernel2.close()

    def test_attempt_recording_is_idempotent(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        ctx = _context("attempt_record")
        intent = _intent(store, ctx)
        kernel.commit_intent(intent)
        kernel.record_attempt(intent)
        kernel.record_attempt(intent)  # second call must not raise
        attempts = kernel.list_attempts(ctx.operation_id)
        assert len(attempts) == 1
        kernel.close()


# ===========================================================================
# 5. FAILURE HANDLING
# ===========================================================================


class TestFailureHandling:
    def test_forged_result_without_intent_is_rejected(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        ctx = _context("forged")
        intent = _intent(store, ctx)
        # Commit the intent but create a completely different forged intent
        kernel.commit_intent(intent)
        forged_payload = store.put(b'{"forged":true}', "application/json")
        forged_intent = OperationIntent(
            context=ctx,
            idempotency_key=ctx.idempotency_key,
            event_type="intake.forged",
            payload=forged_payload,
            stream_id="stream:test",
        )
        result = OperationResult(
            operation_id=ctx.operation_id,
            attempt_id=ctx.attempt_id,
            status="SUCCESS",
            payload=forged_payload,
        )
        with pytest.raises(ValueError, match="intent-before-write"):
            kernel.commit_result(forged_intent, result)
        kernel.close()

    def test_corrupt_input_blob_detected_at_intent_commit(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        ctx = _context("corrupt_input")
        intent = _intent(store, ctx)
        # Corrupt the payload blob
        blob_path = store.objects / intent.payload.sha256[:2] / intent.payload.sha256
        blob_path.write_bytes(b"corrupted")
        with pytest.raises(BlobIntegrityError):
            kernel.commit_intent(intent)
        kernel.close()

    def test_stream_head_reflects_latest_event(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        assert kernel.stream_head("stream:test") is None

        ctx1 = _context("head1")
        i1 = _intent(store, ctx1)
        kernel.commit_intent(i1)
        e1 = kernel.commit_result(i1, _success_result(ctx1, i1.payload))
        seq, h = kernel.stream_head("stream:test")
        assert seq == 1 and h == e1.event_hash

        ctx2 = _context("head2")
        i2 = _intent(store, ctx2, payload_bytes=b'{"n":2}')
        kernel.commit_intent(i2)
        e2 = kernel.commit_result(i2, _success_result(ctx2, i2.payload))
        seq, h = kernel.stream_head("stream:test")
        assert seq == 2 and h == e2.event_hash
        kernel.close()

    def test_non_success_result_requires_issue_codes(self):
        """Verify contract: non-success OperationResult without issues raises at model validation."""
        with pytest.raises(Exception):
            OperationResult(
                operation_id="operation:t",
                attempt_id="attempt:t",
                status="FAILED",
                payload=None,
                issue_codes=[],
            )

    def test_list_stream_events_returns_ordered_chain(self, tmp_path):
        store = BlobStore(tmp_path)
        kernel = AuditKernel(tmp_path / "audit.sqlite", store)
        for i in range(1, 4):
            ctx = _context(f"chain{i}")
            intent = _intent(store, ctx, payload_bytes=f'{{"n":{i}}}'.encode())
            kernel.commit_intent(intent)
            kernel.commit_result(intent, _success_result(ctx, intent.payload))

        events = kernel.list_stream_events("stream:test")
        assert len(events) == 3
        assert [e.sequence for e in events] == [1, 2, 3]
        # Hash chain integrity
        for prev, curr in zip(events, events[1:]):
            assert curr.previous_event_hash == prev.event_hash
        kernel.close()

    def test_catalog_survives_reopen(self, tmp_path):
        store = BlobStore(tmp_path)
        db = tmp_path / "catalog.sqlite"
        catalog = ArtifactCatalog(db, store)
        rev = _artifact_revision(store)
        catalog.put_artifact_revision(rev)
        catalog.close()

        catalog2 = ArtifactCatalog(db, store)
        assert catalog2.get_artifact_revision(rev.artifact_revision_id) == rev
        catalog2.close()
