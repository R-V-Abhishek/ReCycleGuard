"""Explicit scripted workflow ports and stages. No actual model-quality claims."""

import json
from collections import deque
from dataclasses import dataclass
from typing import Literal

from pydantic import JsonValue

from recycleguard.config import Settings
from recycleguard.contracts.core import BoundaryModel, Issue, ServiceResult
from recycleguard.contracts.workflow import (
    ActionDraft,
    AssessmentProposal,
    PlanDraft,
    PlanProposal,
    StageOutcome,
)
from recycleguard.model_port import ModelCallResult
from recycleguard.storage import canonical_json_bytes


@dataclass(frozen=True)
class ScriptedStep:
    phase: Literal["PLAN", "ASSESS"]
    output: dict[str, JsonValue] | None
    status: str = "SUCCESS"
    retryable: bool = False
    mismatched_operation: bool = False
    exact_output: dict[str, JsonValue] | None = None
    usage: dict[str, JsonValue] | None = None


def issue(status: str, *, retryable: bool = False) -> Issue:
    return Issue(
        issue_id=f"issue:scripted_{status.lower()}",
        code="PROVIDER_TIMEOUT" if status == "FAILED" else "PROVIDER_INVALID_OUTPUT",
        severity="BLOCKING",
        message=f"Scripted test outcome {status}",
        field_path=None,
        evidence_refs=[],
        retryable=retryable,
    )


class ScriptedWorkflowPort:
    def __init__(self, settings: Settings, blobs, steps: list[ScriptedStep]):
        if settings.mode != "test" or not settings.enable_test_adapters:
            raise ValueError("scripted workflow requires explicitly enabled test mode")
        self.blobs = blobs
        self.steps = deque(steps)
        self.calls = []

    def invoke(self, context, request):
        step = self.steps.popleft() if self.steps else None
        if step is None:
            raise RuntimeError("script exhausted; no fallback model exists")
        payload = json.loads(self.blobs.get(request.exact_request_blob))
        if payload["phase"] != step.phase:
            raise ValueError("scripted phase differs from the exact model request")
        self.calls.append((context, request, payload))
        exact = step.output if step.exact_output is None else step.exact_output
        response = self.blobs.put(canonical_json_bytes(exact), "application/json")
        output = ModelCallResult(
            model_call_id=f"model_call:scripted_{len(self.calls)}",
            provider_request_ref=None,
            exact_response_blob=response,
            validated_output_or_null=step.output,
            validation_issues=[],
            usage=step.usage,
            timing={},
            outcome=step.status,
        )
        return ServiceResult[ModelCallResult](
            contract_version="1.1",
            operation_id="operation:wrong" if step.mismatched_operation else context.operation_id,
            attempt_id=context.attempt_id,
            status=step.status,
            output=output,
            output_blob=None,
            issues=[]
            if step.status == "SUCCESS"
            else [issue(step.status, retryable=step.retryable)],
            dependencies=[],
            audit_event_ids=[],
        )


class QueryArguments(BoundaryModel):
    query: str


class RecordingStage:
    """Record real context/argument calls, preserving structured result boundaries."""

    def __init__(self, *, disposition="PASS", statuses=()):
        self.disposition = disposition
        self.statuses = deque(statuses)
        self.calls = []

    def __call__(self, context, arguments):
        self.calls.append((context, arguments))
        status = self.statuses.popleft() if self.statuses else "SUCCESS"
        return ServiceResult[StageOutcome](
            contract_version="1.1",
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status=status,
            output=StageOutcome(
                disposition=self.disposition,
                evidence_refs=[],
                output_blob=None,
                concise_decision="Synthetic stage result only.",
            ),
            output_blob=None,
            issues=[] if status == "SUCCESS" else [issue(status, retryable=True)],
            dependencies=[],
            audit_event_ids=[],
        )


def plan_draft(objective="Inspect the exact allocation evidence") -> PlanDraft:
    return PlanDraft(
        objective=objective,
        hypotheses=["Reported balance may differ from supported allocations"],
        proposed_checks=["Inspect the pinned evidence"],
        expected_evidence=["An exact source observation"],
        stopping_criteria=["Evidence supports resolution or explicit abstention"],
    )


def plan(query="allocation", *, kind="CHECK", operation="search_rules", finding="finding:one"):
    return ScriptedStep(
        "PLAN",
        PlanProposal(
            plan=plan_draft(),
            action=ActionDraft(
                action_kind=kind,
                allowed_operation=operation,
                typed_arguments={"query": query},
                finding_id=finding,
                concise_reason="Inspect exact pinned evidence.",
                evidence_refs=[],
            ),
            stop_reason=None,
        ).model_dump(mode="json"),
    )


def assess(*, verdict="SUPPORTS", disposition="RESOLVE", revised=False):
    return ScriptedStep(
        "ASSESS",
        AssessmentProposal(
            verdict=verdict,
            weak_result_or_mistake=(
                "Weak locator match"
                if verdict in {"WEAK", "REFUTES", "NO_PROGRESS", "UNKNOWN"}
                else None
            ),
            next_check_or_stop="Reformulate the locator query"
            if revised
            else "Resolve within scope",
            disposition=disposition,
            revised_plan=plan_draft("Use an exact clause locator") if revised else None,
        ).model_dump(mode="json"),
    )
