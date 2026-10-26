"""Extraction service coordinating CSV, JSON, and PDF text extraction.

Owned by Sampreeth (H03 / C03).
Guarantees:
- Produces valid ExtractionResult conforming to CONTRACTS §3.3.
- Writes observations_blob, coverage_blob, and text_blob into BlobStore.
- Enforces explicit issue accounting on partial or failed extractions.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from recycleguard.contracts.artifacts import ArtifactRevision
from recycleguard.contracts.core import BlobRef, Issue
from recycleguard.contracts.extraction import (
    CoverageItem,
    ExtractionResult,
    Observation,
)
from recycleguard.extraction.csv_extractor import extract_csv
from recycleguard.extraction.json_extractor import extract_json
from recycleguard.extraction.pdf_extractor import extract_pdf_pages
from recycleguard.storage.blob_store import BlobStore, canonical_json_bytes

ADAPTER_VERSION = "1.0.0"


def _utc_now_rfc3339() -> str:
    return datetime.now(UTC).isoformat()


def extract_artifact(
    revision: ArtifactRevision,
    blob_store: BlobStore,
    *,
    adapter_id: str = "recycleguard.extraction.standard",
) -> tuple[ExtractionResult, list[Observation], list[CoverageItem]]:
    """Extract an artifact revision and store structured outcomes into BlobStore."""
    ext_id = f"ext:{uuid4().hex[:12]}"
    raw_bytes = blob_store.get(revision.blob)

    filename = (revision.original_filename or "").lower()
    doc_type = revision.doc_type
    media_type = revision.blob.media_type

    observations: list[Observation] = []
    coverage_items: list[CoverageItem] = []
    issues: list[Issue] = []
    text_content: str | None = None

    if media_type == "text/csv" or filename.endswith(".csv") or doc_type == "ERP_CSV":
        observations, coverage_items, issues = extract_csv(
            raw_bytes,
            revision.artifact_revision_id,
            ext_id,
            capture_time=revision.captured_at,
        )
        text_content = raw_bytes.decode("utf-8", errors="replace")
    elif (
        media_type == "application/pdf"
        or filename.endswith(".pdf")
        or doc_type in {"STATUTORY_INSTRUMENT", "FAQ", "SOP", "TECHNICAL_FRAMEWORK", "GST_INVOICE"}
    ):
        observations, coverage_items, text_content, issues = extract_pdf_pages(
            raw_bytes,
            revision.artifact_revision_id,
            ext_id,
            capture_time=revision.captured_at,
        )
    elif (
        media_type == "application/json"
        or filename.endswith(".json")
        or filename.endswith(".jsonl")
    ):
        is_jsonl = filename.endswith(".jsonl")
        observations, coverage_items, issues = extract_json(
            raw_bytes,
            revision.artifact_revision_id,
            ext_id,
            is_jsonl=is_jsonl,
            capture_time=revision.captured_at,
        )
        text_content = raw_bytes.decode("utf-8", errors="replace")
    else:
        # Generic text / unsupported
        text_content = raw_bytes.decode("utf-8", errors="replace")
        issues.append(
            Issue(
                issue_id=f"issue:{uuid4().hex[:8]}",
                code="EXTRACTION_FAILED",
                severity="WARNING",
                message=f"Unsupported artifact media type {media_type} for deep parsing",
                field_path=revision.original_filename,
                evidence_refs=[],
                retryable=False,
            )
        )

    # Serialize observations to JSONL and store in BlobStore
    obs_lines = [
        canonical_json_bytes(obs.model_dump(mode="json")).decode("utf-8") for obs in observations
    ]
    obs_bytes = "\n".join(obs_lines).encode("utf-8") if obs_lines else b""
    obs_blob = blob_store.put(obs_bytes, "application/x-jsonlines")

    # Serialize coverage items to JSONL and store in BlobStore
    cov_lines = [
        canonical_json_bytes(cov.model_dump(mode="json")).decode("utf-8") for cov in coverage_items
    ]
    cov_bytes = "\n".join(cov_lines).encode("utf-8") if cov_lines else b""
    cov_blob = blob_store.put(cov_bytes, "application/x-jsonlines")

    # Text blob
    text_blob: BlobRef | None = None
    if text_content is not None and text_content.strip():
        text_blob = blob_store.put(text_content.encode("utf-8"), "text/plain")

    # Determine status
    if any(i.severity == "BLOCKING" for i in issues):
        status = "FAILED"
    elif issues:
        status = "PARTIAL"
    else:
        status = "COMPLETE"

    # Compute configuration digest
    config_dict = {"adapter_id": adapter_id, "adapter_version": ADAPTER_VERSION}
    config_digest = hashlib.sha256(canonical_json_bytes(config_dict)).hexdigest()

    extraction_result = ExtractionResult(
        extraction_id=ext_id,
        artifact_revision_id=revision.artifact_revision_id,
        adapter_id=adapter_id,
        adapter_version=ADAPTER_VERSION,
        configuration_digest=config_digest,
        text_blob=text_blob,
        observations_blob=obs_blob,
        coverage_blob=cov_blob,
        status=status,
        issues=issues,
    )

    return extraction_result, observations, coverage_items
