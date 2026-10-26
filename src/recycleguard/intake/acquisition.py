"""Auditable acquisition for regulatory leads and primary source instruments.

Owned by Sampreeth (H02 / C01).
Implements acquisition attempts: records requested URL, fetch attempts, exact bytes,
and produces AssetReceipt and ArtifactRevision.
A failed fetch creates a receipt with intake_status='FETCH_FAILED', artifact_revision_id=None,
and an explicit failure reason, never an invented blob or hash.
"""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from recycleguard.contracts.artifacts import ArtifactRevision, AssetReceipt
from recycleguard.contracts.audit import OperationIntent, OperationResult
from recycleguard.contracts.core import BoundaryModel, CommandContext, Issue, TemporalValue
from recycleguard.contracts.sources import SourceLead
from recycleguard.storage import AuditKernel, canonical_json_bytes
from recycleguard.storage.authority import Capability
from recycleguard.storage.blob_store import BlobStore
from recycleguard.storage.catalog import ArtifactCatalog


def _utc_now_rfc3339() -> str:
    return datetime.now(UTC).isoformat()


class AcquisitionOutcome(BoundaryModel):
    source_lead_id: str
    url: str
    status: str
    receipt: AssetReceipt
    artifact_revision: ArtifactRevision | None
    issues: list[Issue]


def _prepare_acquisition(
    lead: SourceLead,
    *,
    body_bytes: bytes | None,
    media_type: str = "application/pdf",
    status_code: int = 200,
    error_message: str | None = None,
    blob_store: BlobStore,
    batch_id: str | None = None,
    catalog: ArtifactCatalog | None = None,
) -> AcquisitionOutcome:
    """Record the result of an acquisition attempt.

    If body_bytes is provided and status_code is 200, stores the exact bytes into
    BlobStore, creates an ArtifactRevision and an AssetReceipt with intake_status='RECEIVED'.
    If body_bytes is None or an error occurred, creates an AssetReceipt with
    intake_status='FETCH_FAILED' and no artifact revision.
    """
    bid = batch_id or f"batch:acq_{uuid4().hex[:8]}"
    receipt_id = f"receipt:{uuid4().hex[:12]}"
    issues: list[Issue] = []

    if body_bytes is None or status_code >= 400 or error_message:
        reason = (
            error_message or f"HTTP {status_code} when attempting to fetch from {lead.official_url}"
        )
        receipt = AssetReceipt(
            receipt_id=receipt_id,
            batch_id=bid,
            declared_asset_id=lead.source_lead_id,
            supplied_path_or_url=lead.official_url,
            intake_status="FETCH_FAILED",
            artifact_revision_id=None,
            reason=reason,
            received_at=_utc_now_rfc3339(),
        )
        issues.append(
            Issue(
                issue_id=f"issue:{uuid4().hex[:8]}",
                code="MISSING_ARTIFACT",
                severity="WARNING",
                message=reason,
                field_path=lead.official_url,
                evidence_refs=[],
                retryable=True,
            )
        )
        return AcquisitionOutcome(
            source_lead_id=lead.source_lead_id,
            url=lead.official_url,
            status="FETCH_FAILED",
            receipt=receipt,
            artifact_revision=None,
            issues=issues,
        )

    # Success: store raw bytes in BlobStore
    blob_ref = blob_store.put(body_bytes, media_type)
    art_id = f"artifact:{lead.source_lead_id.replace('source_lead:', '')}"
    art_rev_id = lead.acquired_artifact_revision_id or f"artifact_rev:{uuid4().hex[:12]}"

    source_kind = "GAZETTE" if lead.source_class == "GAZETTE_RULE" else "OFFICIAL_GUIDANCE"
    doc_type = (
        "STATUTORY_INSTRUMENT"
        if lead.source_class == "GAZETTE_RULE"
        else ("FAQ" if lead.source_class == "FAQ" else "TECHNICAL_FRAMEWORK")
    )

    revision = ArtifactRevision(
        artifact_id=art_id,
        artifact_revision_id=art_rev_id,
        blob=blob_ref,
        original_filename=Path(lead.official_url.split("?")[0]).name or "acquired_document",
        source_kind=source_kind,
        doc_type=doc_type,
        establishes=["RULE_TEXT", "CONTEXT_ONLY"],
        does_not_establish=["LIABILITY_ALLOCATION", "PAYMENT"],
        source_url=lead.official_url,
        fetch_attempt_id=f"attempt:{uuid4().hex[:8]}",
        captured_at=TemporalValue(
            raw=None,
            value=_utc_now_rfc3339()[:10],
            precision="DATE",
            timezone=None,
            interpretation_status="PARSED",
        ),
        ingested_at=_utc_now_rfc3339(),
        access_policy_id="policy:regulatory_source",
        rights_decision_id="decision:fair_dealing_sec52",
        synthetic=False,
        derived_from=[],
    )

    receipt = AssetReceipt(
        receipt_id=receipt_id,
        batch_id=bid,
        declared_asset_id=lead.source_lead_id,
        supplied_path_or_url=lead.official_url,
        intake_status="RECEIVED",
        artifact_revision_id=art_rev_id,
        reason=None,
        received_at=_utc_now_rfc3339(),
    )

    return AcquisitionOutcome(
        source_lead_id=lead.source_lead_id,
        url=lead.official_url,
        status="RECEIVED",
        receipt=receipt,
        artifact_revision=revision,
        issues=[],
    )


def record_acquisition(
    lead: SourceLead,
    *,
    body_bytes: bytes | None,
    media_type: str = "application/pdf",
    status_code: int = 200,
    error_message: str | None = None,
    blob_store: BlobStore,
    batch_id: str | None = None,
    catalog: ArtifactCatalog | None = None,
    kernel: AuditKernel | None = None,
    capability: Capability | None = None,
    context: CommandContext | None = None,
) -> AcquisitionOutcome:
    """Prepare an outcome or atomically persist it with a complete trusted dispatcher."""
    audited = any(value is not None for value in (catalog, kernel, capability, context))
    if audited:
        if any(value is None for value in (catalog, kernel, capability, context)):
            raise ValueError("audited acquisition requires the complete dispatcher")
        if catalog.kernel is not kernel or kernel.blob_store is not blob_store:
            raise ValueError("acquisition must use the shared coordinator")
        kernel.authority.check(capability, context.actor, "intake.acquisition")
        request = {
            "lead": lead.model_dump(mode="json"),
            "body_digest": None if body_bytes is None else hashlib.sha256(body_bytes).hexdigest(),
            "media_type": media_type,
            "status_code": status_code,
            "error_message": error_message,
            "batch_id": batch_id,
        }
        payload = blob_store.put(canonical_json_bytes(request), "application/json")
        intent = OperationIntent(
            context=context,
            idempotency_key=context.idempotency_key,
            event_type="intake.acquisition",
            payload=payload,
            stream_id=f"stream:{lead.source_lead_id}",
        )
        kernel.commit_intent(intent, capability=capability)
        existing = kernel.get_result(context.operation_id)
        if existing is not None:
            return AcquisitionOutcome.model_validate_json(blob_store.get(existing.payload))
    output = _prepare_acquisition(
        lead,
        body_bytes=body_bytes,
        media_type=media_type,
        status_code=status_code,
        error_message=error_message,
        blob_store=blob_store,
        batch_id=batch_id,
    )
    if audited:
        payload = blob_store.put(
            canonical_json_bytes(output.model_dump(mode="json")), "application/json"
        )
        result = OperationResult(
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status="SUCCESS" if output.status == "RECEIVED" else "PARTIAL",
            payload=payload,
            issue_codes=[issue.code for issue in output.issues],
        )

        def persist():
            if output.artifact_revision is not None:
                catalog.put_artifact_revision(output.artifact_revision)
            catalog.put_receipt(output.receipt)

        kernel.commit_result(intent, result, capability=capability, mutation=persist)
    return output
