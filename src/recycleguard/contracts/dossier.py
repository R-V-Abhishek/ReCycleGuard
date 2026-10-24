"""Visible dossier manifest boundary. Approval is not granted by deserialization."""

from datetime import date
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .core import ID, BoundaryModel, Digest, TemporalValue, Timestamp
from .domain import FiscalYear, Metal


class AssetEntry(BoundaryModel):
    relative_path: str
    media_type: str
    body_digest: Digest
    byte_length: Annotated[int, Field(ge=0)]
    logical_record_type: str
    source_capture_time: TemporalValue
    visibility: Literal["VISIBLE"]

    @model_validator(mode="after")
    def relative_visible_path(self):
        path = PurePosixPath(self.relative_path)
        if path.is_absolute() or ".." in path.parts or "\\" in self.relative_path:
            raise ValueError("asset path must remain relative to the visible case")
        if not path.parts or path.parts[0] not in {"records", "documents"}:
            raise ValueError("asset must be in the visible records/documents boundary")
        return self


class TableDisposition(BoundaryModel):
    table: str
    disposition: Literal["ABSENT", "PRESENT", "UNSUPPORTED"]
    reason: str


class CaseManifest(BoundaryModel):
    schema_version: Literal["1.0"]
    case_id: ID
    synthetic: Literal[True]
    watermark: Literal["SYNTHETIC - NOT A CPCB RECORD"]
    producer_entity_id: ID
    fiscal_year: FiscalYear
    period_start: date
    period_end_exclusive: date
    quarter: Literal["Q1", "Q2", "Q3", "Q4", "ANNUAL"]
    allowed_eee_codes: list[str]
    allowed_metals: list[Metal]
    calculation_profile_id: ID
    business_cutoff: TemporalValue
    knowledge_cutoff: Timestamp
    adapter_versions: dict[str, str]
    evidence_expectations: list[str]
    assets: list[AssetEntry]
    optional_table_dispositions: list[TableDisposition]
    status: Literal["DRAFT", "APPROVED", "REJECTED"]

    @model_validator(mode="after")
    def distinct_assets(self):
        paths = [item.relative_path for item in self.assets]
        if len(paths) != len(set(paths)):
            raise ValueError("manifest asset paths must be unique")
        if self.period_end_exclusive <= self.period_start:
            raise ValueError("invalid case period")
        return self
