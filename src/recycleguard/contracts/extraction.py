"""Extraction, coverage, and observation boundary models from CONTRACTS section 3.3.

Owned by Sampreeth (H01/H03). Reviewed by A02 before freeze.
"""

from typing import Literal

from pydantic import JsonValue, model_validator

from .core import ID, BlobRef, BoundaryModel, Digest, Issue, Locator, TemporalValue, Timestamp

ExtractionStatus = Literal["COMPLETE", "PARTIAL", "FAILED"]
CoverageDisposition = Literal["PARSED", "QUARANTINED", "EXCLUDED", "FAILED", "NOT_APPLICABLE"]
ExtractionMethod = Literal["CSV", "JSON", "PDF_TEXT", "PDF_TABLE", "OCR", "HUMAN_ASSERTION"]
ValidationState = Literal["VALID", "REVIEW_REQUIRED", "INVALID"]


class CoverageItem(BoundaryModel):
    """Page or row disposition record guaranteeing intake accounting (CONTRACTS §3.3)."""

    coverage_item_id: ID
    artifact_revision_id: ID
    locator: Locator
    disposition: CoverageDisposition
    reason_code: str
    child_observation_ids: list[ID]


class Observation(BoundaryModel):
    """Raw and parsed observation with extraction provenance and temporal triad (CONTRACTS §3.3)."""

    observation_id: ID
    extraction_id: ID
    artifact_revision_id: ID
    locator: Locator
    observation_type: str
    raw_fields: dict[str, JsonValue]
    parsed_fields: dict[str, JsonValue]
    validation_state: ValidationState
    extraction_method: ExtractionMethod
    field_quality: dict[str, JsonValue]
    event_time: TemporalValue
    source_capture_time: TemporalValue
    ingestion_time: Timestamp


class ExtractionResult(BoundaryModel):
    """Structured extraction outcome with terminal coverage and raw text reference."""

    extraction_id: ID
    artifact_revision_id: ID
    adapter_id: str
    adapter_version: str
    configuration_digest: Digest
    text_blob: BlobRef | None
    observations_blob: BlobRef
    coverage_blob: BlobRef
    status: ExtractionStatus
    issues: list[Issue]

    @model_validator(mode="after")
    def explicit_issues(self):
        if self.status == "COMPLETE" and any(i.severity == "BLOCKING" for i in self.issues):
            raise ValueError("complete extraction cannot contain blocking issues")
        if self.status != "COMPLETE" and not self.issues:
            raise ValueError("non-complete extraction requires explicit issues")
        return self
