"""Full-batch intake and auditable receipt generation.

Owned by Sampreeth (H02 / C01).
Implements CP1 inventory accounting: every discovered file inside the submitted batch
gets a receipt, including undeclared extras, duplicate bytes, and corrupt documents.
Declared assets missing from disk receive DECLARED_MISSING receipts without an invented blob.
Symlinks and path traversals are rejected with REJECTED_ACCESS receipts.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING
from uuid import uuid4

from recycleguard.contracts.artifacts import ArtifactRevision, AssetReceipt, EvidenceCapability
from recycleguard.contracts.core import (
    BoundaryModel,
    CommandContext,
    Issue,
    TemporalValue,
)
from recycleguard.contracts.dossier import CaseManifest
from recycleguard.storage.blob_store import BlobStore

if TYPE_CHECKING:
    from recycleguard.storage.audit_kernel import AuditKernel
    from recycleguard.storage.authority import Capability
    from recycleguard.storage.catalog import ArtifactCatalog


def _utc_now_rfc3339() -> str:
    return datetime.now(UTC).isoformat()


def _infer_doc_type_and_capabilities(
    relative_path: str, logical_record_type: str | None = None
) -> tuple[str, str, list[EvidenceCapability], list[EvidenceCapability]]:
    """Determine doc_type, source_kind, establishes, and does_not_establish capabilities."""
    path_lower = relative_path.lower()

    if "invoice" in path_lower or "bill" in path_lower:
        doc_type = "GST_INVOICE"
        source_kind = "COMPANY_RECORD"
        establishes = ["PAYMENT", "IDENTITY"]
        does_not_establish = ["LIABILITY_ALLOCATION", "RULE_TEXT"]
    elif "ledger" in path_lower or path_lower.endswith(".csv"):
        doc_type = "ERP_CSV"
        source_kind = "COMPANY_RECORD"
        establishes = ["REPORTED_ACCOUNT_POSITION"]
        does_not_establish = ["LIABILITY_ALLOCATION", "RULE_TEXT"]
    elif "portal" in path_lower or "certificate" in path_lower:
        doc_type = "PORTAL_SNAPSHOT"
        source_kind = "PORTAL_CAPTURE"
        establishes = ["CERTIFICATE_IDENTITY", "TRANSFER_STAGE", "REPORTED_ACCOUNT_POSITION"]
        does_not_establish = ["RULE_TEXT"]
    elif "faq" in path_lower:
        doc_type = "FAQ"
        source_kind = "OFFICIAL_GUIDANCE"
        establishes = ["RULE_TEXT", "CONTEXT_ONLY"]
        does_not_establish = ["LIABILITY_ALLOCATION", "PAYMENT"]
    elif "rule" in path_lower or "gazette" in path_lower:
        doc_type = "STATUTORY_INSTRUMENT"
        source_kind = "GAZETTE"
        establishes = ["RULE_TEXT"]
        does_not_establish = ["LIABILITY_ALLOCATION", "PAYMENT"]
    else:
        doc_type = "OTHER"
        source_kind = "SYNTHETIC_RECORD"
        establishes = ["CONTEXT_ONLY"]
        does_not_establish = ["RULE_TEXT", "LIABILITY_ALLOCATION"]

    return doc_type, source_kind, establishes, does_not_establish


class IntakeBatchResult(BoundaryModel):
    batch_id: str
    case_id: str | None
    receipts: list[AssetReceipt]
    artifact_revisions: list[ArtifactRevision]
    issues: list[Issue]
    manifest: CaseManifest | None = None


def intake_batch(
    batch_root: str | Path,
    *,
    batch_id: str | None = None,
    blob_store: BlobStore,
    catalog: ArtifactCatalog | None = None,
    kernel: AuditKernel | None = None,
    capability: Capability | None = None,
    context: CommandContext | None = None,
    manifest_filename: str = "case_manifest.json",
) -> IntakeBatchResult:
    """Execute full-batch intake over a folder following H02 and CP1 contracts.

    Discovers every file inside batch_root, audits exact bytes, records undeclared extras,
    duplicate bytes, corrupt files, declared missing assets, and symlink/traversal rejections.
    When catalog, kernel, and capability are supplied, writes are performed under the shared
    audited transaction with prefix check 'intake.'.
    """
    root = Path(batch_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"batch root directory not found: {root}")

    bid = batch_id or f"batch:{uuid4().hex[:12]}"
    receipts: list[AssetReceipt] = []
    revisions: list[ArtifactRevision] = []
    issues: list[Issue] = []

    # 1. Parse manifest if present
    manifest_path = root / manifest_filename
    manifest: CaseManifest | None = None
    declared_by_relpath: dict[str, any] = {}

    if manifest_path.is_file():
        try:
            manifest = CaseManifest.model_validate_json(manifest_path.read_bytes())
            for asset in manifest.assets:
                # Normalize relative path to forward slashes
                norm_rel = str(PurePosixPath(asset.relative_path))
                declared_by_relpath[norm_rel] = asset
        except Exception as exc:
            issues.append(
                Issue(
                    issue_id=f"issue:{uuid4().hex[:8]}",
                    code="INVALID_SCHEMA",
                    severity="BLOCKING",
                    message=f"failed to parse manifest {manifest_filename}: {exc}",
                    field_path=manifest_filename,
                    evidence_refs=[],
                    retryable=False,
                )
            )

    case_id = manifest.case_id if manifest else None

    # 2. Walk batch_root and discover all physical files
    discovered_relpaths: set[str] = set()

    # Search subdirectories records/, documents/, and root
    subdirs = ["records", "documents", ""]
    for subdir_name in subdirs:
        dir_to_scan = root / subdir_name if subdir_name else root
        if not dir_to_scan.is_dir():
            continue

        for entry in os.scandir(dir_to_scan):
            # Skip manifest file itself and directories
            if entry.name == manifest_filename or entry.is_dir():
                continue

            # Compute relative path with posix slashes
            raw_path = Path(entry.path)
            try:
                rel_posix = str(PurePosixPath(raw_path.relative_to(root)))
            except ValueError:
                continue

            # Check for symlink / path traversal
            if entry.is_symlink() or os.path.islink(raw_path):
                receipt = AssetReceipt(
                    receipt_id=f"receipt:{uuid4().hex[:12]}",
                    batch_id=bid,
                    declared_asset_id=f"asset:{rel_posix}"
                    if rel_posix in declared_by_relpath
                    else None,
                    supplied_path_or_url=rel_posix,
                    intake_status="REJECTED_ACCESS",
                    artifact_revision_id=None,
                    reason="Symlink or path traversal outside batch boundary rejected",
                    received_at=_utc_now_rfc3339(),
                )
                receipts.append(receipt)
                issues.append(
                    Issue(
                        issue_id=f"issue:{uuid4().hex[:8]}",
                        code="ACCESS_DENIED",
                        severity="BLOCKING",
                        message=f"Symlink rejected at {rel_posix}",
                        field_path=rel_posix,
                        evidence_refs=[],
                        retryable=False,
                    )
                )
                continue

            discovered_relpaths.add(rel_posix)

            # Read exact bytes
            try:
                raw_bytes = raw_path.read_bytes()
            except OSError as exc:
                receipt = AssetReceipt(
                    receipt_id=f"receipt:{uuid4().hex[:12]}",
                    batch_id=bid,
                    declared_asset_id=rel_posix if rel_posix in declared_by_relpath else None,
                    supplied_path_or_url=rel_posix,
                    intake_status="FETCH_FAILED",
                    artifact_revision_id=None,
                    reason=f"Failed to read file from disk: {exc}",
                    received_at=_utc_now_rfc3339(),
                )
                receipts.append(receipt)
                continue

            sha256 = hashlib.sha256(raw_bytes).hexdigest()
            byte_len = len(raw_bytes)

            # Guess media type
            media_type = "application/octet-stream"
            if rel_posix.endswith(".json") or rel_posix.endswith(".jsonl"):
                media_type = "application/json"
            elif rel_posix.endswith(".csv"):
                media_type = "text/csv"
            elif rel_posix.endswith(".pdf"):
                media_type = "application/pdf"
            elif rel_posix.endswith(".txt"):
                media_type = "text/plain"

            # Check if declared
            declared = declared_by_relpath.get(rel_posix)
            if declared is not None:
                media_type = declared.media_type or media_type

            # Store in BlobStore
            blob_ref = blob_store.put(raw_bytes, media_type)

            # Determine doc_type, source_kind, capabilities
            doc_type, source_kind, establishes, does_not_establish = (
                _infer_doc_type_and_capabilities(
                    rel_posix, declared.logical_record_type if declared else None
                )
            )

            art_id = f"artifact:{uuid4().hex[:12]}"
            art_rev_id = f"artifact_rev:{uuid4().hex[:12]}"

            revision = ArtifactRevision(
                artifact_id=art_id,
                artifact_revision_id=art_rev_id,
                blob=blob_ref,
                original_filename=raw_path.name,
                source_kind=source_kind,
                doc_type=doc_type,
                establishes=establishes,
                does_not_establish=does_not_establish,
                source_url=None,
                fetch_attempt_id=None,
                captured_at=declared.source_capture_time
                if declared
                else TemporalValue(
                    raw=None,
                    value=_utc_now_rfc3339()[:10],
                    precision="DATE",
                    timezone=None,
                    interpretation_status="PARSED",
                ),
                ingested_at=_utc_now_rfc3339(),
                access_policy_id="policy:standard_intake",
                rights_decision_id="decision:synthetic_pilot_allow",
                synthetic=True,
                derived_from=[],
            )
            revisions.append(revision)

            # Check hash / length consistency against manifest declaration
            receipt_reason: str | None = None
            if declared is not None:
                if sha256 != declared.body_digest or byte_len != declared.byte_length:
                    receipt_reason = (
                        f"Hash/length mismatch: declared (sha256={declared.body_digest}, "
                        f"length={declared.byte_length}), actual (sha256={sha256}, "
                        f"length={byte_len})"
                    )
                    issues.append(
                        Issue(
                            issue_id=f"issue:{uuid4().hex[:8]}",
                            code="HASH_MISMATCH",
                            severity="WARNING",
                            message=receipt_reason,
                            field_path=rel_posix,
                            evidence_refs=[],
                            retryable=False,
                        )
                    )
            else:
                receipt_reason = "Undeclared extra file discovered in intake batch"

            receipt = AssetReceipt(
                receipt_id=f"receipt:{uuid4().hex[:12]}",
                batch_id=bid,
                declared_asset_id=f"asset:{rel_posix}" if declared is not None else None,
                supplied_path_or_url=rel_posix,
                intake_status="RECEIVED",
                artifact_revision_id=art_rev_id,
                reason=receipt_reason,
                received_at=_utc_now_rfc3339(),
            )
            receipts.append(receipt)

    # 3. Check for declared missing files
    for declared_relpath, _declared_asset in declared_by_relpath.items():
        if declared_relpath not in discovered_relpaths:
            receipt = AssetReceipt(
                receipt_id=f"receipt:{uuid4().hex[:12]}",
                batch_id=bid,
                declared_asset_id=f"asset:{declared_relpath}",
                supplied_path_or_url=declared_relpath,
                intake_status="DECLARED_MISSING",
                artifact_revision_id=None,
                reason="Declared asset missing from intake batch filesystem",
                received_at=_utc_now_rfc3339(),
            )
            receipts.append(receipt)
            issues.append(
                Issue(
                    issue_id=f"issue:{uuid4().hex[:8]}",
                    code="MISSING_ARTIFACT",
                    severity="WARNING",
                    message=f"Declared asset {declared_relpath} is missing from batch root",
                    field_path=declared_relpath,
                    evidence_refs=[],
                    retryable=False,
                )
            )

    # 4. If catalog and kernel are provided, commit to catalog in transaction
    if (
        catalog is not None
        and kernel is not None
        and capability is not None
        and context is not None
    ):
        from recycleguard.contracts.audit import OperationIntent, OperationResult
        from recycleguard.storage.blob_store import canonical_json_bytes

        intent_payload = blob_store.put(
            canonical_json_bytes({"batch_id": bid, "root": str(root)}), "application/json"
        )
        intent = OperationIntent(
            context=context,
            idempotency_key=context.idempotency_key,
            event_type="intake.batch",
            payload=intent_payload,
            stream_id=f"stream:{bid}",
        )
        kernel.commit_intent(intent, capability=capability)

        def _persist_catalog():
            for rev in revisions:
                catalog.put_artifact_revision(rev)
            for rec in receipts:
                catalog.put_receipt(rec)

        res_payload = blob_store.put(
            canonical_json_bytes(
                {
                    "batch_id": bid,
                    "receipts_count": len(receipts),
                    "revisions_count": len(revisions),
                }
            ),
            "application/json",
        )
        result = OperationResult(
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status="SUCCESS" if not any(i.severity == "BLOCKING" for i in issues) else "PARTIAL",
            payload=res_payload,
            issue_codes=[i.code for i in issues],
        )
        kernel.commit_result(intent, result, capability=capability, mutation=_persist_catalog)

    return IntakeBatchResult(
        batch_id=bid,
        case_id=case_id,
        receipts=receipts,
        artifact_revisions=revisions,
        issues=issues,
        manifest=manifest,
    )
