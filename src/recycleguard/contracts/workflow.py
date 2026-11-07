"""C09 bounded workflow boundaries. Test traces never establish real-model performance."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, JsonValue, model_validator

from .artifacts import ProfileRef, SnapshotRef
from .core import ID, BlobRef, BoundaryModel, Digest, EvidenceRef, Nonempty, Timestamp
from .results import AbstentionReason, CalculationValueRef, FaultFamily

RunStatus = Literal[
    "CREATED",
    "PREFLIGHT",
    "INVESTIGATING",
    "DRAFTING",
    "VERIFYING",
    "BRIEFING",
    "AWAITING_REVIEW",
    "COMPLETED",
    "BLOCKED_INPUT",
    "BLOCKED_OUTPUT",
    "FAILED",
    "CANCELLED",
]
StopReason = Literal[
    "RESOLVED_WITHIN_SCOPE",
    "NO_NEW_EVIDENCE",
    "EXPERT_REVIEW_REQUIRED",
    "BUDGET_EXHAUSTED",
    "CYCLE_DETECTED",
    "PROVIDER_FAILURE",
    "AUDIT_FAILURE",
    "REVIEW_REJECTED",
    "CHANGES_REQUESTED",
    "MANUAL_CLOSURE",
]
Count = Annotated[int, Field(ge=0)]

ReviewOutcome = Literal[
    "NOT_REQUESTED",
    "PENDING",
    "APPROVED",
    "REJECTED",
    "CHANGES_REQUESTED",
    "ESCALATED",
    "CLOSED_WITHOUT_DECISION",
]


class ConfigurationPin(BoundaryModel):
    configuration_id: ID
    digest: Digest


class CancellationRequest(BoundaryModel):
    run_id: ID
    expected_version: Annotated[int, Field(ge=1)]
    reason: Nonempty


class BudgetLimits(BoundaryModel):
    max_case_actions: Annotated[int, Field(ge=1)] = 64
    max_model_calls: Annotated[int, Field(ge=1)] = 24
    max_total_tokens: Annotated[int, Field(ge=1)] = 49152
    tokens_per_model_call: Annotated[int, Field(ge=1)] = 2048
    max_wall_seconds: Annotated[int, Field(ge=1)] = 300
    tools_per_finding: Annotated[int, Field(ge=1, le=8)] = 8
    reformulations_per_finding: Annotated[int, Field(ge=0, le=2)] = 2
    retries_per_operation: Annotated[int, Field(ge=0, le=1)] = 1
    report_repairs: Annotated[int, Field(ge=0, le=1)] = 1
    preflight_actions: Annotated[int, Field(ge=1)] = 1
    verification_actions: Annotated[int, Field(ge=1)] = 2
    cost_ceiling_usd: None = None


class BudgetUsage(BoundaryModel):
    actions: Count = 0
    model_calls: Count = 0
    tool_calls: Count = 0
    retries: Count = 0
    reserved_tokens: Count = 0
    observed_tokens: Count | None = None
    observed_cost_usd: str | None = None
    usage_known_calls: Count = 0
    cost_known_calls: Count = 0
    preflight_actions: Count = 0
    verification_actions: Count = 0
    report_repairs: Count = 0
    finding_actions: dict[str, Count] = Field(default_factory=dict)
    finding_reformulations: dict[str, Count] = Field(default_factory=dict)


class RunSpec(BoundaryModel):
    run_id: ID
    case_snapshot: SnapshotRef
    corpus_snapshot: SnapshotRef
    profile: ProfileRef
    index: ConfigurationPin
    code_revision: Nonempty
    dependency_lock_digest: Digest
    adapters: ConfigurationPin
    tools: ConfigurationPin
    prompt: ConfigurationPin
    model: ConfigurationPin
    retrieval_policy: ConfigurationPin
    audit_policy: ConfigurationPin
    security_policy: ConfigurationPin
    topology: Literal["SINGLE_INVESTIGATOR"] = "SINGLE_INVESTIGATOR"
    execution_kind: Literal["SCRIPTED_TEST", "MODEL_BACKED"] = "SCRIPTED_TEST"
    experiment_variant: Nonempty
    finding_ids: list[ID] = Field(min_length=1)
    budgets: BudgetLimits
    parent_run_id: ID | None = None
    runtime_configuration: BlobRef | None = None

    @model_validator(mode="after")
    def unique_findings(self):
        if len(self.finding_ids) != len(set(self.finding_ids)):
            raise ValueError("finding queue must be unique")
        return self


class PlanDraft(BoundaryModel):
    objective: Nonempty
    hypotheses: list[Nonempty]
    proposed_checks: list[Nonempty]
    expected_evidence: list[Nonempty]
    stopping_criteria: list[Nonempty] = Field(min_length=1)


class ActionDraft(BoundaryModel):
    action_kind: Literal["CHECK", "REFORMULATE"]
    allowed_operation: Nonempty
    typed_arguments: dict[str, JsonValue]
    finding_id: ID
    concise_reason: Nonempty
    evidence_refs: list[EvidenceRef]


class PlanProposal(BoundaryModel):
    model_config = ConfigDict(
        json_schema_extra={
            "oneOf": [
                {"properties": {"action": {"type": "object"}, "stop_reason": {"type": "null"}}},
                {
                    "properties": {
                        "action": {"type": "null"},
                        "stop_reason": {"enum": ["NO_NEW_EVIDENCE", "EXPERT_REVIEW_REQUIRED"]},
                    }
                },
            ]
        }
    )
    plan: PlanDraft
    action: ActionDraft | None
    # Review outcomes and technical budget/failure decisions are trusted handlers'
    # responsibility. The investigator may only request abstention/escalation.
    stop_reason: Literal["NO_NEW_EVIDENCE", "EXPERT_REVIEW_REQUIRED"] | None

    @model_validator(mode="after")
    def action_or_stop(self):
        if (self.action is None) == (self.stop_reason is None):
            raise ValueError("choose exactly one action or stop")
        return self


class PlanRecord(PlanDraft):
    plan_id: ID
    revision: Annotated[int, Field(ge=1)]
    previous_plan_ref: ID | None
    triggering_operation_ref: ID | None
    finding_id: ID


class ActionProposal(ActionDraft):
    plan_ref: ID


class FindingProposal(BoundaryModel):
    """A model's suggested finding. It reaches a report only through the deterministic gate.

    References and scopes stay loose here so a bad citation is a retained gate rejection,
    not a failed assessment.
    """

    issue_type: FaultFamily
    advisory_status: Literal[
        "RECONCILED_WITHIN_SCOPE",
        "DISCREPANCY_DETECTED",
        "PENDING_VERIFICATION",
        "REQUIRES_EXPERT_REVIEW",
    ]
    basis: Nonempty
    evidence_ref_ids: list[str]
    abstention_reason: AbstentionReason | None = None
    withheld_claim_scopes: list[str] = Field(default_factory=list)
    next_action_kind: Literal["INVESTIGATE", "REQUEST_EVIDENCE", "ESCALATE", "NO_FURTHER_ACTION"]
    next_action_text: Nonempty


class AssessmentProposal(BoundaryModel):
    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"disposition": {"const": "RESOLVE"}}},
                    "then": {"properties": {"verdict": {"const": "SUPPORTS"}}},
                },
                {
                    "if": {"properties": {"revised_plan": {"type": "object"}}},
                    "then": {
                        "properties": {
                            "verdict": {"enum": ["WEAK", "REFUTES", "NO_PROGRESS", "UNKNOWN"]}
                        }
                    },
                },
            ]
        }
    )
    verdict: Literal["SUPPORTS", "REFUTES", "WEAK", "NO_PROGRESS", "UNKNOWN"]
    weak_result_or_mistake: str | None
    next_check_or_stop: Nonempty
    disposition: Literal["CONTINUE", "RESOLVE", "ABSTAIN"]
    revised_plan: PlanDraft | None
    finding_proposal: FindingProposal | None = None

    @model_validator(mode="after")
    def revision_has_trigger(self):
        if self.disposition == "RESOLVE" and self.verdict != "SUPPORTS":
            raise ValueError("resolution requires a supported assessment")
        if self.revised_plan is not None and self.verdict not in {
            "WEAK",
            "REFUTES",
            "NO_PROGRESS",
            "UNKNOWN",
        }:
            raise ValueError("plan revision requires an adverse or uncertain observation")
        return self


class BriefProposal(BoundaryModel):
    """A model's draft reviewer brief for one verified finding.

    Text only, in words: code adds every number. Lengths and references are checked by the brief
    gate, so a bad draft is a retained rejection rather than a failed call.
    """

    what_to_check: Nonempty
    explanation: Nonempty
    evidence_request: Nonempty
    evidence_ref_ids: list[str]


class BriefFigure(BoundaryModel):
    """One number shown with a brief, copied by code from the authoritative calculation."""

    label: Nonempty
    value: Nonempty
    value_ref: CalculationValueRef


class ReviewerBrief(BoundaryModel):
    """Advisory reading aid for one finding of one report revision. It changes nothing.

    A model brief that fails the gate, or whose call did not complete, is kept with its reason
    and no text. A template brief is built by code from the finding alone.
    """

    brief_id: ID
    run_id: ID
    report_revision_id: ID
    finding_revision_id: ID
    issue_type: FaultFamily
    source: Literal["MODEL", "TEMPLATE"]
    status: Literal["ACCEPTED", "REJECTED", "DROPPED"]
    reason: str | None
    what_to_check: str | None
    explanation: str | None
    evidence_request: str | None
    evidence_refs: list[EvidenceRef]
    figures: list[BriefFigure]
    label: Nonempty
    model_operation_ref: ID | None
    proposal: BriefProposal | None = None

    @model_validator(mode="after")
    def outcome_shape(self):
        texts = (self.what_to_check, self.explanation, self.evidence_request)
        if self.status == "ACCEPTED":
            if any(text is None for text in texts) or self.reason is not None:
                raise ValueError("an accepted brief has its text and no rejection reason")
        elif any(text is not None for text in texts) or not self.reason:
            raise ValueError("a rejected or dropped brief has a reason and no text")
        if self.source == "TEMPLATE" and (
            self.status != "ACCEPTED" or self.model_operation_ref is not None
        ):
            raise ValueError("a template brief is always built and involves no model call")
        return self


class ObservationAssessment(BoundaryModel):
    assessment_id: ID
    operation_ref: ID
    plan_ref: ID
    observation_refs: list[EvidenceRef]
    verdict: Literal["SUPPORTS", "REFUTES", "WEAK", "NO_PROGRESS", "UNKNOWN"]
    weak_result_or_mistake: str | None
    next_check_or_stop: Nonempty
    revised_plan_ref: ID | None
    disposition: Literal["CONTINUE", "RESOLVE", "ABSTAIN"]
    finding_proposal: FindingProposal | None = None


class RunState(BoundaryModel):
    run_id: ID
    version: Annotated[int, Field(ge=1)]
    status: RunStatus
    current_turn: int
    pending_finding_ids: list[ID]
    resolved_finding_ids: list[ID]
    abstained_finding_ids: list[ID]
    budget: BudgetUsage
    created_at: Timestamp
    updated_at: Timestamp
    stop_reason: StopReason | None
    review_outcome: ReviewOutcome
    plan_refs: list[ID]
    assessment_refs: list[ID]
    result_refs: list[BlobRef]
    action_fingerprints: list[Digest]
    search_queries: dict[str, list[Digest]] = Field(default_factory=dict)
    review_record_refs: list[ID] = Field(default_factory=list)
    last_audit_sequence: int
    pending_operation_id: ID | None
    pending_attempt_id: ID | None = None
    active_turn_input: BlobRef | None
    last_checkpoint_ref: BlobRef | None


class StageOutcome(BoundaryModel):
    service_operation_ids: list[ID] = Field(default_factory=list)
    retrieval_attempt_ids: list[ID] = Field(default_factory=list)
    calculation_ids: list[ID] = Field(default_factory=list)
    finding_revision_ids: list[ID] = Field(default_factory=list)
    disposition: Literal["PASS", "QUALIFIED", "BLOCKED"]
    evidence_refs: list[EvidenceRef]
    output_blob: BlobRef | None
    concise_decision: Nonempty


class ContextManifest(BoundaryModel):
    context_manifest_id: ID
    run_id: ID
    phase: Literal["PLAN", "ASSESS", "BRIEF"]
    exact_request_blob: BlobRef
    allowed_tool_schema_digest: Digest
    max_total_tokens: int


class TurnManifest(BoundaryModel):
    turn_id: ID
    run_id: ID
    turn_index: Annotated[int, Field(ge=1)]
    previous_turn_id: ID | None
    input_state_blob: BlobRef
    output_state_blob: BlobRef | None
    pinned_membership_refs: list[ID]
    operation_ids_in_order: list[ID]
    context_manifest_ids: list[ID]
    retrieval_attempt_ids: list[ID]
    calculation_ids: list[ID]
    finding_revision_ids: list[ID]
    plan_refs: list[ID]
    observation_assessment_refs: list[ID]
    plan_revised: bool
    coverage_summary_blob: BlobRef
    budget_before: BudgetUsage
    budget_after: BudgetUsage
    turn_status: Literal["STARTED", "COMPLETED", "FAILED", "CANCELLED"]
    concise_decision: str | None
    stop_reason: StopReason | None
    first_event_sequence: int
    last_event_sequence: int
