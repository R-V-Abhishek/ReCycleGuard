"""Explicit HTTP response contracts shared with OpenAPI consumers."""

from typing import Literal

from pydantic import ConfigDict, Field, JsonValue

from recycleguard.contracts.artifacts import ArtifactRevision, ProfileRef, SnapshotRef
from recycleguard.contracts.core import BlobRef, BoundaryModel
from recycleguard.contracts.extraction import Observation
from recycleguard.contracts.foundation import FoundationResult
from recycleguard.contracts.workflow import BudgetLimits, ConfigurationPin, RunState


class HealthResponse(BoundaryModel):
    status: Literal["OK"]
    model_configured: bool
    model_probed: bool
    concurrency: int
    ui_implemented: bool
    available_modes: list[Literal["MODEL_BACKED", "SCRIPTED_TEST"]]


class AgentResponse(BoundaryModel):
    configured: bool
    model_id: str | None
    prompt_pin: ConfigurationPin | None
    system_template: str
    phase_rules: dict[str, str]
    response_schemas: dict[str, JsonValue]
    note: str


class FixtureResponse(BoundaryModel):
    fixture_id: str
    case_id: str
    fiscal_year: str
    synthetic: bool


class DossierResponse(BoundaryModel):
    dossier_id: str
    name: str
    status: Literal["UPLOADED", "DRAFT", "APPROVED"]
    synthetic: bool
    case_id: str
    candidate_digest: str | None = None
    foundation: FoundationResult | None = None
    foundation_blob: BlobRef | None = None


class CatalogueResponse(BoundaryModel):
    fixtures: list[FixtureResponse]
    dossiers: list[DossierResponse]


class EnrollmentResponse(BoundaryModel):
    status: Literal["ENROLLED"]


class EvidenceResponse(BoundaryModel):
    snapshot: SnapshotRef
    records: list[dict[str, JsonValue]]
    observations: list[Observation]
    originals: list[ArtifactRevision]


class JobResponse(BoundaryModel):
    run_id: str
    dossier_id: str
    status: Literal["QUEUED", "RUNNING", "STOPPED", "FAILED", "INTERRUPTED"]
    detail: str | None
    cancel_requested: int


class RunConfigurationResponse(BoundaryModel):
    execution_kind: Literal["MODEL_BACKED", "SCRIPTED_TEST"]
    budgets: BudgetLimits
    model_configuration_id: str
    prompt_configuration_id: str
    case_snapshot: SnapshotRef
    corpus_snapshot: SnapshotRef
    profile: ProfileRef
    index: ConfigurationPin


class RunResponse(BoundaryModel):
    state: RunState
    job: JobResponse
    configuration: RunConfigurationResponse


class RunListResponse(BoundaryModel):
    runs: list[RunResponse]


class StartedRunResponse(BoundaryModel):
    run_id: str
    status: Literal["QUEUED"]
    mode: Literal["MODEL_BACKED", "SCRIPTED_TEST"]


class QueuedRunResponse(BoundaryModel):
    run_id: str
    status: Literal["QUEUED"]


class CancellationResponse(BoundaryModel):
    run_id: str
    cancellation_requested: bool
    note: str


class TraceEventResponse(BoundaryModel):
    """Stable event identity with version-extensible, JSON-only payload fields."""

    model_config = ConfigDict(extra="allow", frozen=True)
    __pydantic_extra__: dict[str, JsonValue] = Field(init=False)
    sequence: int
    event_id: str
    operation_id: str
    turn_id: str | None
    attempt_id: str
    event_type: str
    payload_ref: BlobRef
    kind: Literal[
        "PROMPT_PREPARED",
        "PLAN",
        "TOOL_PROPOSED",
        "ASSESSMENT",
        "MODEL_RESULT",
        "TOOL_OR_STAGE_RESULT",
        "AUDIT",
    ]


class TraceResponse(BoundaryModel):
    run_id: str
    events: list[TraceEventResponse]
    last_sequence: int
