"""Proposed common boundary subset from CONTRACTS sections 1–3.

A02 must review these models with all four producer/consumer handoffs before freeze.
"""

import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

PROTOCOL_VERSION = "1.1"


def decimal_string(value: str) -> str:
    if type(value) is not str or not re.fullmatch(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?", value):
        raise ValueError("quantity must be a plain decimal JSON string")
    integral, _, fractional = value.lstrip("-").partition(".")
    if len(integral) > 18 or len(fractional) > 8:
        raise ValueError("decimal exceeds 18 integral or 8 fractional digits")
    return value


def utc_timestamp(value: str) -> str:
    if type(value) is not str or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)", value
    ):
        raise ValueError("runtime timestamp requires RFC 3339 UTC")
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


Timestamp = Annotated[
    str,
    BeforeValidator(utc_timestamp),
    Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)$"),
]


DecimalString = Annotated[
    str, BeforeValidator(decimal_string), Field(pattern=r"^-?(0|[1-9][0-9]{0,17})(\.[0-9]{1,8})?$")
]
ID = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*:[^\s]+$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Nonempty = Annotated[str, Field(min_length=1)]
Status = Literal["SUCCESS", "PARTIAL", "FAILED", "REJECTED", "CANCELLED", "OUTCOME_UNKNOWN"]
ErrorCode = Literal[
    "INVALID_SCHEMA",
    "ACCESS_DENIED",
    "HASH_MISMATCH",
    "MISSING_ARTIFACT",
    "INCOMPLETE_COVERAGE",
    "EXTRACTION_FAILED",
    "UNCONFIRMED_IDENTIFIER",
    "AMBIGUOUS_IDENTITY",
    "AMBIGUOUS_EVENT",
    "DIMENSION_MISMATCH",
    "NUMERIC_PRECISION_EXCEEDED",
    "EARLIER_LIABILITY_UNMET",
    "LIABILITY_PRIORITY_UNRESOLVED",
    "UNSUPPORTED_PROFILE",
    "UNAPPROVED_PROFILE",
    "APPLICABILITY_UNRESOLVED",
    "RULE_CONFLICT",
    "SOURCE_INCOMPLETE",
    "STALE_SNAPSHOT",
    "BUDGET_EXHAUSTED",
    "CYCLE_DETECTED",
    "PROVIDER_TIMEOUT",
    "PROVIDER_INVALID_OUTPUT",
    "AUDIT_UNAVAILABLE",
    "CONCURRENT_MODIFICATION",
    "STALE_REVIEW",
    "EXPORT_RESTRICTED",
    "PROHIBITED_VERDICT",
    "CANCELLED",
    "INTEGRITY_FAILED",
    "OVER_ALLOCATION",
    "UNSUPPORTED_FEATURE",
    "CREDIT_EXPIRED",
    "CREDIT_CANCELLED",
    "CAPABILITY_MISMATCH",
    "WEIGHT_BASIS_CONFLICT",
]


class BoundaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class ActorRef(BoundaryModel):
    actor_id: ID
    actor_kind: Literal["HUMAN", "SERVICE", "MODEL_PROPOSAL", "EVALUATOR"]
    authenticated_session_ref: ID | None


class CommandContext(BoundaryModel):
    contract_version: Literal["1.1"]
    command_id: ID
    operation_id: ID
    attempt_id: ID
    idempotency_key: Nonempty
    actor: ActorRef
    case_version_id: ID | None
    run_id: ID | None
    turn_id: ID | None
    correlation_id: ID
    parent_operation_id: ID | None

    @model_validator(mode="after")
    def pinned_run(self):
        if self.run_id is not None and self.case_version_id is None:
            raise ValueError("run calls must pin case_version_id")
        if self.turn_id is not None and self.run_id is None:
            raise ValueError("turn_id requires run_id")
        return self


class BlobRef(BoundaryModel):
    sha256: Digest
    byte_length: Annotated[int, Field(ge=0)]
    media_type: Nonempty


class Locator(BoundaryModel):
    kind: Literal["PDF_PAGE", "PDF_CELL", "CSV_ROW", "JSON_POINTER", "TEXT_SPAN", "DB_RECORD"]
    page_index_1based: Annotated[int, Field(ge=1)] | None
    printed_page_label: str | None
    row_index_1based: Annotated[int, Field(ge=1)] | None
    column_name: str | None
    json_pointer: str | None
    text_start: Annotated[int, Field(ge=0)] | None
    text_end: Annotated[int, Field(ge=0)] | None
    table_id: ID | None
    cell_row: Annotated[int, Field(ge=1)] | None
    cell_column: Annotated[int, Field(ge=1)] | None

    @model_validator(mode="after")
    def required_coordinates(self):
        if self.kind in {"PDF_PAGE", "PDF_CELL"} and self.page_index_1based is None:
            raise ValueError("PDF locator requires physical page")
        if self.kind == "PDF_CELL" and any(
            v is None for v in (self.table_id, self.cell_row, self.cell_column)
        ):
            raise ValueError("PDF cell requires table and cell coordinates")
        if self.kind == "CSV_ROW" and self.row_index_1based is None:
            raise ValueError("CSV locator requires data-row index")
        if self.kind == "JSON_POINTER" and (
            self.json_pointer is None or not re.fullmatch(r"(/([^~]|~[01])*)*", self.json_pointer)
        ):
            raise ValueError("invalid RFC 6901 pointer")
        if self.kind == "TEXT_SPAN" and (
            self.text_start is None or self.text_end is None or self.text_end <= self.text_start
        ):
            raise ValueError("text locator requires nonempty half-open span")
        return self


class EvidenceRef(BoundaryModel):
    ref_kind: Literal["ARTIFACT", "OBSERVATION", "RECORD", "PROVISION", "CALCULATION", "FINDING"]
    ref_id: ID
    artifact_revision_id: ID | None
    locator: Locator | None


class Quantity(BoundaryModel):
    decimal: DecimalString
    unit: Literal["KG", "TONNE", "INR", "UNIT_COUNT"]
    dimension: Literal["METAL_MASS", "EQUIPMENT_MASS", "MONEY", "COUNT"]
    metal: Literal["AU", "CU", "AL", "FE"] | None

    @model_validator(mode="after")
    def compatible_units(self):
        if (self.dimension == "METAL_MASS") != (self.metal is not None):
            raise ValueError("metal required iff METAL_MASS")
        units = {
            "METAL_MASS": {"KG", "TONNE"},
            "EQUIPMENT_MASS": {"KG", "TONNE"},
            "MONEY": {"INR"},
            "COUNT": {"UNIT_COUNT"},
        }
        if self.unit not in units[self.dimension]:
            raise ValueError("unit incompatible with dimension")
        if self.dimension == "COUNT" and Decimal(self.decimal) % 1 != 0:
            raise ValueError("COUNT must be integral")
        return self


class TemporalValue(BoundaryModel):
    raw: str | None
    value: str | None
    precision: Literal["INSTANT", "DATE", "MONTH", "YEAR", "UNKNOWN"]
    timezone: str | None
    interpretation_status: Literal["PARSED", "REVIEWED", "AMBIGUOUS", "UNKNOWN"]

    @model_validator(mode="after")
    def preserve_precision(self):
        if self.timezone is not None:
            try:
                ZoneInfo(self.timezone)
            except ZoneInfoNotFoundError as exc:
                raise ValueError("timezone must be an IANA name") from exc
        if self.value is None:
            if self.interpretation_status in {"PARSED", "REVIEWED"}:
                raise ValueError("parsed/reviewed time requires value")
            return self
        if self.precision == "UNKNOWN":
            raise ValueError("unknown precision cannot assert a normalized value")
        patterns = {"DATE": r"\d{4}-\d{2}-\d{2}", "MONTH": r"\d{4}-\d{2}", "YEAR": r"\d{4}"}
        if self.precision == "INSTANT":
            if not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})", self.value
            ):
                raise ValueError("instant requires RFC 3339 offset")
            datetime.fromisoformat(self.value.replace("Z", "+00:00"))
        else:
            if not re.fullmatch(patterns[self.precision], self.value):
                raise ValueError("value must match source precision")
            suffix = {"DATE": "", "MONTH": "-01", "YEAR": "-01-01"}[self.precision]
            datetime.fromisoformat(self.value + suffix)
        return self


class Issue(BoundaryModel):
    issue_id: ID
    code: ErrorCode
    severity: Literal["INFO", "WARNING", "BLOCKING"]
    message: Nonempty
    field_path: str | None
    evidence_refs: list[EvidenceRef]
    retryable: bool


T = TypeVar("T")


class ServiceResult(BoundaryModel, Generic[T]):
    contract_version: Literal["1.1"]
    operation_id: ID
    attempt_id: ID
    status: Status
    output: T | None
    output_blob: BlobRef | None
    issues: list[Issue]
    dependencies: list[EvidenceRef]
    audit_event_ids: list[ID]

    @model_validator(mode="after")
    def explicit_incompleteness(self):
        if self.status == "SUCCESS" and any(i.severity == "BLOCKING" for i in self.issues):
            raise ValueError("SUCCESS cannot contain blocking issues")
        if self.status != "SUCCESS" and not self.issues:
            raise ValueError("non-success requires explicit issues")
        return self
