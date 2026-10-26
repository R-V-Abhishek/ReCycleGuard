"""Auditable acquisition for regulatory leads and primary source instruments.

Owned by Sampreeth (H02 / C01).
Implements acquisition attempts: records requested URL, fetch attempts, exact bytes,
and produces AssetReceipt and ArtifactRevision.
A failed fetch creates a receipt with intake_status='FETCH_FAILED', artifact_revision_id=None,
and an explicit failure reason, never an invented blob or hash.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from recycleguard.contracts.artifacts import ArtifactRevision, AssetReceipt
from recycleguard.contracts.core import BoundaryModel, Issue, TemporalValue
from recycleguard.contracts.sources import SourceLead
from recycleguard.storage.blob_store import BlobStore

if TYPE_CHECKING:
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
