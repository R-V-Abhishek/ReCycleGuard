"""Every-file intake with exact bytes, conservative capabilities and audited replay."""

import hashlib
import mimetypes
import os
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from pydantic import ValidationError

from recycleguard.contracts.artifacts import ArtifactRevision, AssetReceipt
from recycleguard.contracts.audit import OperationIntent, OperationResult
from recycleguard.contracts.core import BoundaryModel, CommandContext, Issue, TemporalValue
from recycleguard.contracts.dossier import AssetEntry, CaseManifest
from recycleguard.storage import ArtifactCatalog, AuditKernel, BlobStore, canonical_json_bytes
from recycleguard.storage.authority import Capability


def _now():
    return datetime.now(UTC).isoformat()


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
    audited = any(value is not None for value in (catalog, kernel, capability, context))
    if audited:
        if any(value is None for value in (catalog, kernel, capability, context)):
            raise ValueError(
                "audited intake requires catalog, kernel, capability and context together"
            )
        if catalog.kernel is not kernel or kernel.blob_store is not blob_store:
            raise ValueError("intake must share the catalog, kernel and blob store")
        kernel.authority.check(capability, context.actor, "intake.batch")
    root = Path(batch_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"batch root directory not found: {root}")
    if PurePosixPath(manifest_filename).name != manifest_filename:
        raise ValueError("manifest filename must be a local basename")
    bid = batch_id or (
        f"batch:{context.operation_id.split(':', 1)[1]}" if audited else f"batch:{uuid4().hex}"
    )
    intent = None
    if audited:
        payload = blob_store.put(
            canonical_json_bytes(
                {
                    "batch_id": bid,
                    "root": str(root),
                    "manifest_filename": manifest_filename,
                }
            ),
            "application/json",
        )
        intent = OperationIntent(
            context=context,
            idempotency_key=context.idempotency_key,
            event_type="intake.batch",
            payload=payload,
            stream_id=f"stream:{bid}",
        )
        kernel.commit_intent(intent, capability=capability)
        previous = kernel.get_result(context.operation_id)
        if previous is not None:
            return IntakeBatchResult.model_validate_json(blob_store.get(previous.payload))

    receipts, revisions, issues = [], [], []
    declared: dict[str, AssetEntry] = {}
    manifest = None
    manifest_path = root / manifest_filename
    if manifest_path.is_file() and not manifest_path.is_symlink():
        try:
            manifest = CaseManifest.model_validate_json(manifest_path.read_bytes())
            for asset in manifest.assets:
                rel = str(PurePosixPath(asset.relative_path))
                if rel in declared:
                    raise ValueError(f"duplicate declared path: {rel}")
                declared[rel] = asset
        except (ValidationError, ValueError, OSError) as exc:
            issues.append(_issue("INVALID_SCHEMA", str(exc), manifest_filename, "BLOCKING"))

    seen: set[str] = set()

    def receipt(rel, status, revision_id=None, reason=None):
        # AssetEntry has no asset_id: retain a safe stable path identity, not raw whitespace.
        asset_id = "asset:" + hashlib.sha256(rel.encode()).hexdigest() if rel in declared else None
        receipts.append(
            AssetReceipt(
                receipt_id=f"receipt:{uuid4().hex}",
                batch_id=bid,
                declared_asset_id=asset_id,
                supplied_path_or_url=rel,
                intake_status=status,
                artifact_revision_id=revision_id,
                reason=reason,
                received_at=_now(),
            )
        )

    def scan(directory):
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                path = Path(entry.path)
                rel = path.relative_to(root).as_posix()
                if entry.is_symlink():
                    seen.add(rel)
                    receipt(rel, "REJECTED_ACCESS", reason="Symlink is outside the intake boundary")
                    issues.append(_issue("ACCESS_DENIED", "Symlink rejected", rel, "BLOCKING"))
                elif entry.is_dir(follow_symlinks=False):
                    scan(path)
                elif entry.is_file(follow_symlinks=False):
                    seen.add(rel)
                    try:
                        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                        with os.fdopen(os.open(path, flags), "rb") as stream:
                            data = stream.read()
                    except OSError as exc:
                        receipt(rel, "FETCH_FAILED", reason=str(exc))
                        issues.append(_issue("MISSING_ARTIFACT", str(exc), rel))
                        continue
                    asset = declared.get(rel)
                    media = (
                        asset.media_type
                        if asset
                        else mimetypes.guess_type(rel)[0] or "application/octet-stream"
                    )
                    if rel.endswith(".jsonl"):
                        media = "application/x-ndjson"
                    blob = blob_store.put(data, media)
                    name = path.name.lower()
                    doc_type = (
                        "GST_INVOICE"
                        if "invoice" in name
                        else "ERP_CSV"
                        if name.endswith(".csv")
                        else "OTHER"
                    )
                    unknown_time = TemporalValue(
                        raw=None,
                        value=None,
                        precision="UNKNOWN",
                        timezone=None,
                        interpretation_status="UNKNOWN",
                    )
                    revision = ArtifactRevision(
                        artifact_id=f"artifact:{uuid4().hex}",
                        artifact_revision_id=f"artifact_rev:{uuid4().hex}",
                        blob=blob,
                        original_filename=path.name,
                        source_kind="SYNTHETIC_RECORD",
                        doc_type=doc_type,
                        establishes=["CONTEXT_ONLY"],
                        does_not_establish=["RULE_TEXT", "LIABILITY_ALLOCATION", "PAYMENT"],
                        source_url=None,
                        fetch_attempt_id=None,
                        captured_at=asset.source_capture_time if asset else unknown_time,
                        ingested_at=_now(),
                        access_policy_id="policy:local_intake",
                        rights_decision_id="decision:review_required",
                        synthetic=manifest.synthetic if manifest else False,
                        derived_from=[],
                    )
                    revisions.append(revision)
                    reason = None
                    if asset is not None and (
                        blob.sha256 != asset.body_digest or blob.byte_length != asset.byte_length
                    ):
                        reason = "Hash/length mismatch against declared manifest"
                        issues.append(_issue("HASH_MISMATCH", reason, rel))
                    elif asset is None and rel != manifest_filename:
                        reason = "Undeclared extra file retained"
                    receipt(rel, "RECEIVED", revision.artifact_revision_id, reason)

    scan(root)
    for rel in declared:
        if rel not in seen:
            unsafe = PurePosixPath(rel).is_absolute() or ".." in PurePosixPath(rel).parts
            receipt(
                rel,
                "REJECTED_ACCESS" if unsafe else "DECLARED_MISSING",
                reason="Unsafe path" if unsafe else "Declared file missing",
            )
            issues.append(
                _issue(
                    "ACCESS_DENIED" if unsafe else "MISSING_ARTIFACT",
                    "Declared file unavailable",
                    rel,
                )
            )
    output = IntakeBatchResult(
        batch_id=bid,
        case_id=None if manifest is None else manifest.case_id,
        receipts=receipts,
        artifact_revisions=revisions,
        issues=issues,
        manifest=manifest,
    )
    if audited:
        payload = blob_store.put(
            canonical_json_bytes(output.model_dump(mode="json")), "application/json"
        )
        result = OperationResult(
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status="PARTIAL" if issues else "SUCCESS",
            payload=payload,
            issue_codes=[issue.code for issue in issues],
        )

        def persist():
            for revision in revisions:
                catalog.put_artifact_revision(revision)
            for item in receipts:
                catalog.put_receipt(item)

        kernel.commit_result(intent, result, capability=capability, mutation=persist)
    return output


def _issue(code, message, path, severity="WARNING"):
    return Issue(
        issue_id=f"issue:{uuid4().hex}",
        code=code,
        severity=severity,
        message=message,
        field_path=path,
        evidence_refs=[],
        retryable=False,
    )
