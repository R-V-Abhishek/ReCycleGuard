"""A03 internal snapshot persistence slice, built on the V02 audited coordinator.

This is not the complete C05 facade: profile policy persistence, ServiceResult CLI
handlers and trusted login/session establishment remain to be integrated.
"""

from datetime import UTC, datetime

from recycleguard.contracts import CommandContext
from recycleguard.contracts.artifacts import FrozenSnapshot
from recycleguard.contracts.audit import OperationIntent, OperationResult
from recycleguard.contracts.snapshots import SnapshotPublication, SnapshotReview
from recycleguard.storage import ArtifactCatalog, AuditKernel, Capability, canonical_json_bytes
from recycleguard.storage.catalog import CatalogError


class SnapshotStore:
    def __init__(self, kernel: AuditKernel, catalog: ArtifactCatalog):
        if catalog.kernel is not kernel:
            raise ValueError("snapshot store must share its catalog's audit coordinator")
        self.kernel = kernel
        self.catalog = catalog
        if kernel.connection.in_transaction:
            raise ValueError("initialize snapshot storage before dispatching operations")
        kernel.connection.execute("""
            CREATE TABLE IF NOT EXISTS snapshot_heads (
                scope_id TEXT PRIMARY KEY,
                snapshot_id TEXT NOT NULL REFERENCES frozen_snapshots(snapshot_id)
            )
        """)

    def head(self, scope_id: str) -> FrozenSnapshot | None:
        row = self.kernel.connection.execute(
            "SELECT snapshot_id FROM snapshot_heads WHERE scope_id=?", (scope_id,)
        ).fetchone()
        return None if row is None else self.catalog.get_snapshot(row["snapshot_id"])

    def _begin(self, context, request, event_type, capability):
        self.kernel.authority.check(capability, context.actor, event_type)
        payload = self.kernel.blob_store.put(
            canonical_json_bytes(request.model_dump(mode="json")), "application/json"
        )
        intent = OperationIntent(
            context=context,
            idempotency_key=context.idempotency_key,
            event_type=event_type,
            payload=payload,
            stream_id=f"stream:{request.scope_id}",
        )
        self.kernel.commit_intent(intent, capability=capability)
        result = self.kernel.get_result(context.operation_id)
        if result is not None:
            if result.status != "SUCCESS" or result.payload is None:
                raise CatalogError("operation already ended without a snapshot")
            return intent, FrozenSnapshot.model_validate_json(
                self.kernel.blob_store.get(result.payload)
            )
        return intent, None

    def _reject(self, intent, capability, message, code):
        payload = self.kernel.blob_store.put(
            canonical_json_bytes({"message": message}), "application/json"
        )
        result = OperationResult(
            operation_id=intent.context.operation_id,
            attempt_id=intent.context.attempt_id,
            status="REJECTED",
            payload=payload,
            issue_codes=[code],
        )
        self.kernel.commit_result(intent, result, capability=capability)

    def _persist(self, request, snapshot, intent, capability):
        payload = self.kernel.blob_store.put(
            canonical_json_bytes(snapshot.model_dump(mode="json")), "application/json"
        )
        result = OperationResult(
            operation_id=intent.context.operation_id,
            attempt_id=intent.context.attempt_id,
            status="SUCCESS",
            payload=payload,
        )

        def mutation():
            current = self.head(request.scope_id)
            actual = None if current is None else current.snapshot_id
            if actual != request.expected_head:
                raise CatalogError("CONCURRENT_MODIFICATION: snapshot head changed")
            if current is not None and current.snapshot_kind != snapshot.snapshot_kind:
                raise CatalogError("snapshot scope kind cannot change")
            if snapshot.parent_snapshot_id != actual:
                raise CatalogError("snapshot parent must be the exact expected revision")
            self.catalog.put_snapshot(snapshot)
            self.kernel.connection.execute(
                "INSERT INTO snapshot_heads VALUES (?,?) ON CONFLICT(scope_id) "
                "DO UPDATE SET snapshot_id=excluded.snapshot_id",
                (request.scope_id, snapshot.snapshot_id),
            )

        try:
            self.kernel.commit_result(intent, result, capability=capability, mutation=mutation)
        except CatalogError as exc:
            code = (
                "CONCURRENT_MODIFICATION"
                if str(exc).startswith("CONCURRENT_MODIFICATION")
                else "INVALID_SCHEMA"
            )
            self._reject(intent, capability, str(exc), code)
            raise
        return snapshot

    def publish(
        self, context: CommandContext, request: SnapshotPublication, *, capability: Capability
    ):
        intent, replay = self._begin(context, request, "snapshot.publish", capability)
        if replay is not None:
            return replay
        snapshot = FrozenSnapshot(
            snapshot_id=request.snapshot_id,
            snapshot_kind=request.snapshot_kind,
            schema_version="1.0",
            parent_snapshot_id=request.expected_head,
            membership_blob=request.membership_blob,
            membership_digest=request.membership_digest,
            coverage_blob=request.coverage_blob,
            created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            created_by=context.actor.actor_id,
            source_receipt_ids=request.source_receipt_ids,
            review_state="DRAFT",
        )
        return self._persist(request, snapshot, intent, capability)

    def review(self, context: CommandContext, request: SnapshotReview, *, capability: Capability):
        intent, replay = self._begin(context, request, "review.snapshot", capability)
        if replay is not None:
            return replay
        try:
            target = self.catalog.get_snapshot(request.target_snapshot_id)
        except KeyError:
            self._reject(intent, capability, "review target is missing", "MISSING_ARTIFACT")
            raise
        if target.membership_digest != request.target_membership_digest:
            self._reject(
                intent, capability, "membership digest does not match target", "STALE_REVIEW"
            )
            raise CatalogError("STALE_REVIEW: membership digest does not match target")
        if target.review_state != "DRAFT":
            self._reject(
                intent, capability, "review target must be a draft revision", "STALE_REVIEW"
            )
            raise CatalogError("review target must be a draft revision")
        child = target.model_copy(
            update={
                "snapshot_id": request.new_snapshot_id,
                "parent_snapshot_id": target.snapshot_id,
                "review_state": "APPROVED" if request.decision == "APPROVE" else "REJECTED",
                "created_by": context.actor.actor_id,
                "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
        )
        return self._persist(request, child, intent, capability)
