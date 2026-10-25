"""V02 SQLite registry for artifact revisions, receipts and snapshots.

Every catalog write enforces blob-before-reference: the BlobRef must be retrievable from the
BlobStore before the catalog row is committed.  This prevents orphan references.

Frozen snapshots retain missing/failed receipts as well as received evidence.
Membership and coverage blobs must exist in the store.

This module does not implement C05 approval workflow; approval state changes are made through
the AuditKernel which requires an intent/result pair.
"""

import sqlite3
from pathlib import Path

from recycleguard.contracts.artifacts import ArtifactRevision, AssetReceipt, FrozenSnapshot

from .audit_kernel import AuditKernel
from .blob_store import BlobStore, canonical_json_bytes

_CATALOG_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS artifact_revisions (
    artifact_revision_id TEXT PRIMARY KEY,
    artifact_id          TEXT NOT NULL,
    blob_sha256          TEXT NOT NULL,
    revision_json        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS intake_receipts (
    receipt_id       TEXT PRIMARY KEY,
    batch_id         TEXT NOT NULL,
    intake_status    TEXT NOT NULL,
    receipt_json     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_receipts_batch ON intake_receipts (batch_id);
CREATE INDEX IF NOT EXISTS idx_receipts_status ON intake_receipts (intake_status);

CREATE TABLE IF NOT EXISTS frozen_snapshots (
    snapshot_id      TEXT PRIMARY KEY,
    snapshot_kind    TEXT NOT NULL,
    membership_sha   TEXT NOT NULL,
    review_state     TEXT NOT NULL,
    snapshot_json    TEXT NOT NULL
);
"""


class CatalogError(ValueError):
    """Raised when a catalog invariant is violated."""


class ArtifactCatalog:
    """SQLite-backed artifact catalog with blob-before-reference enforcement.

    All writes require an active shared AuditKernel transaction.
    Reads may use a standalone connection. Re-inserting the same serialized record
    is a no-op; re-inserting with a different serialisation raises CatalogError.
    """

    def __init__(
        self, database: str | Path, blob_store: BlobStore, *, kernel: AuditKernel | None = None
    ) -> None:
        self.blob_store = blob_store
        if kernel is not None:
            self.kernel = kernel
            self.connection = kernel.connection
            actual = self.connection.execute("PRAGMA database_list").fetchone()[2]
            if Path(actual).resolve() != Path(database).resolve():
                raise CatalogError("catalog and kernel must use the same database")
            self._owns_connection = False
        else:
            self.kernel = None
            self.connection = sqlite3.connect(database)
            self.connection.row_factory = sqlite3.Row
            self._owns_connection = True
        if self.connection.in_transaction:
            raise CatalogError("catalog must be opened before an audited transaction")
        self.connection.executescript(_CATALOG_SCHEMA)

    def close(self) -> None:
        if self._owns_connection:
            self.connection.close()

    def _require_write(self, prefixes):
        if (
            self.kernel is None
            or self.kernel.active_intent is None
            or not self.connection.in_transaction
        ):
            raise CatalogError("catalog writes require the shared audited transaction")
        if not any(self.kernel.active_intent.event_type.startswith(p) for p in prefixes):
            raise CatalogError("active operation does not permit this catalog mutation")

    # ------------------------------------------------------------------
    # Artifact revisions
    # ------------------------------------------------------------------

    def put_artifact_revision(self, revision: ArtifactRevision) -> ArtifactRevision:
        """Store an artifact revision after verifying its blob exists.

        Idempotent: returns the stored revision if an identical record already exists.
        Raises CatalogError if the same ID is reused with different content.
        """
        self._require_write(("intake.", "extraction.", "normalization."))
        # blob-before-reference: raises FileNotFoundError / BlobIntegrityError on failure
        self.blob_store.get(revision.blob)

        encoded = canonical_json_bytes(revision.model_dump(mode="json")).decode()
        existing = self.connection.execute(
            "SELECT revision_json FROM artifact_revisions WHERE artifact_revision_id = ?",
            (revision.artifact_revision_id,),
        ).fetchone()
        if existing is not None:
            if existing["revision_json"] != encoded:
                raise CatalogError(
                    f"artifact_revision_id already exists with different content: "
                    f"{revision.artifact_revision_id}"
                )
            return ArtifactRevision.model_validate_json(existing["revision_json"])

        self.connection.execute(
            "INSERT INTO artifact_revisions VALUES (?, ?, ?, ?)",
            (revision.artifact_revision_id, revision.artifact_id, revision.blob.sha256, encoded),
        )
        return revision

    def get_artifact_revision(self, artifact_revision_id: str) -> ArtifactRevision:
        row = self.connection.execute(
            "SELECT revision_json FROM artifact_revisions WHERE artifact_revision_id = ?",
            (artifact_revision_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"artifact revision not found: {artifact_revision_id}")
        return ArtifactRevision.model_validate_json(row["revision_json"])

    def list_revisions_for_artifact(self, artifact_id: str) -> list[ArtifactRevision]:
        rows = self.connection.execute(
            "SELECT revision_json FROM artifact_revisions WHERE artifact_id = ?",
            (artifact_id,),
        ).fetchall()
        return [ArtifactRevision.model_validate_json(r["revision_json"]) for r in rows]

    # ------------------------------------------------------------------
    # Intake receipts
    # ------------------------------------------------------------------

    def put_receipt(self, receipt: AssetReceipt) -> AssetReceipt:
        """Persist an intake receipt.

        For RECEIVED status the receipt's artifact_revision_id must already be in the catalog
        so the receipt → revision → blob chain is consistent.

        Idempotent: same content → same stored receipt.
        Raises CatalogError for ID collision with different content.
        """
        self._require_write(("intake.",))
        if receipt.intake_status == "RECEIVED":
            if receipt.artifact_revision_id is None:
                raise CatalogError("RECEIVED receipt must have artifact_revision_id")
            # Ensure the referenced revision already exists in the catalog
            self.get_artifact_revision(receipt.artifact_revision_id)

        encoded = canonical_json_bytes(receipt.model_dump(mode="json")).decode()
        existing = self.connection.execute(
            "SELECT receipt_json FROM intake_receipts WHERE receipt_id = ?",
            (receipt.receipt_id,),
        ).fetchone()
        if existing is not None:
            if existing["receipt_json"] != encoded:
                raise CatalogError(
                    f"receipt_id already exists with different content: {receipt.receipt_id}"
                )
            return AssetReceipt.model_validate_json(existing["receipt_json"])

        self.connection.execute(
            "INSERT INTO intake_receipts VALUES (?, ?, ?, ?)",
            (receipt.receipt_id, receipt.batch_id, receipt.intake_status, encoded),
        )
        return receipt

    def get_receipt(self, receipt_id: str) -> AssetReceipt:
        row = self.connection.execute(
            "SELECT receipt_json FROM intake_receipts WHERE receipt_id = ?",
            (receipt_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"receipt not found: {receipt_id}")
        return AssetReceipt.model_validate_json(row["receipt_json"])

    def list_receipts_for_batch(self, batch_id: str) -> list[AssetReceipt]:
        rows = self.connection.execute(
            "SELECT receipt_json FROM intake_receipts WHERE batch_id = ?",
            (batch_id,),
        ).fetchall()
        return [AssetReceipt.model_validate_json(r["receipt_json"]) for r in rows]

    # ------------------------------------------------------------------
    # Frozen snapshots
    # ------------------------------------------------------------------

    def put_snapshot(self, snapshot: FrozenSnapshot) -> FrozenSnapshot:
        """Store a frozen snapshot after verifying membership and coverage blobs exist.

        Every source receipt ID must exist, including missing/failed dispositions.
        Idempotent: same content → same stored snapshot.
        Raises CatalogError on ID collision with different content.
        """
        self._require_write(("snapshot.", "review."))
        if snapshot.review_state != "DRAFT" and not self.kernel.active_intent.event_type.startswith(
            "review."
        ):
            raise CatalogError("snapshot approval requires a trusted review operation")
        # blob-before-reference for both membership and coverage blobs
        self.blob_store.get(snapshot.membership_blob)
        self.blob_store.get(snapshot.coverage_blob)

        # Missing/failed receipts are evidence and remain in frozen membership.
        # Only an absent receipt ID is invalid; downstream coverage controls conclusions.
        for rid in snapshot.source_receipt_ids:
            self.get_receipt(rid)

        # Membership digest must match the declared value on the model
        if snapshot.membership_blob.sha256 != snapshot.membership_digest:
            raise CatalogError(
                "snapshot membership_blob sha256 does not match declared membership_digest"
            )

        encoded = canonical_json_bytes(snapshot.model_dump(mode="json")).decode()
        existing = self.connection.execute(
            "SELECT snapshot_json FROM frozen_snapshots WHERE snapshot_id = ?",
            (snapshot.snapshot_id,),
        ).fetchone()
        if existing is not None:
            if existing["snapshot_json"] != encoded:
                raise CatalogError(
                    f"snapshot_id already exists with different content: {snapshot.snapshot_id}"
                )
            return FrozenSnapshot.model_validate_json(existing["snapshot_json"])

        self.connection.execute(
            "INSERT INTO frozen_snapshots VALUES (?, ?, ?, ?, ?)",
            (
                snapshot.snapshot_id,
                snapshot.snapshot_kind,
                snapshot.membership_blob.sha256,
                snapshot.review_state,
                encoded,
            ),
        )
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> FrozenSnapshot:
        row = self.connection.execute(
            "SELECT snapshot_json FROM frozen_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"snapshot not found: {snapshot_id}")
        return FrozenSnapshot.model_validate_json(row["snapshot_json"])

    def list_snapshots(
        self, *, kind: str | None = None, review_state: str | None = None
    ) -> list[FrozenSnapshot]:
        query = "SELECT snapshot_json FROM frozen_snapshots WHERE 1=1"
        params: list[str] = []
        if kind is not None:
            query += " AND snapshot_kind = ?"
            params.append(kind)
        if review_state is not None:
            query += " AND review_state = ?"
            params.append(review_state)
        rows = self.connection.execute(query, params).fetchall()
        return [FrozenSnapshot.model_validate_json(r["snapshot_json"]) for r in rows]

    def update_snapshot_review_state(self, snapshot_id: str, new_state: str) -> FrozenSnapshot:
        raise CatalogError("frozen snapshots are immutable; create a reviewed child revision")
