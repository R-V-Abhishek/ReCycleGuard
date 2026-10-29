"""Bounded C09 graph with audited reservations and rebuildable SQLite checkpoints."""

import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import TypedDict

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langsmith.run_helpers import tracing_context
from pydantic import ValidationError

from recycleguard.contracts.artifacts import ProfileRef
from recycleguard.contracts.audit import OperationIntent, OperationResult
from recycleguard.contracts.core import BlobRef, BoundaryModel, Issue, ServiceResult, Status
from recycleguard.contracts.workflow import (
    ActionProposal,
    AssessmentProposal,
    CancellationRequest,
    ContextManifest,
    ObservationAssessment,
    PlanProposal,
    PlanRecord,
    RunSpec,
    RunState,
    StageOutcome,
    TurnManifest,
)
from recycleguard.model_port import ModelCallRequest, ModelCallResult
from recycleguard.storage import canonical_json_bytes
from recycleguard.storage.authority import AuthorizationError

from .ports import OutcomeUnknownError, ToolBinding, WorkflowStages
from .store import GraphStore

_TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "BLOCKED_INPUT", "BLOCKED_OUTPUT"}
_ALLOWED = {
    "inspect_evidence",
    "lookup_locator",
    "trace_certificate",
    "compute_reconciliation",
    "compare_return",
    "search_rules",
}


class GraphInput(TypedDict):
    run_id: str
    expected_version: int
    route: str
    status: str


class CallRecord(BoundaryModel):
    status: Status
    raw_result_blob: BlobRef
    model_output: ModelCallResult | None
    stage_output: StageOutcome | None
    issues: list[Issue]


class ProviderUsage(BoundaryModel):
    total_tokens: int
    cost_usd: str | None = None


class WorkflowStop(ValueError):
    def __init__(self, reason, *, status="DRAFTING"):
        super().__init__(reason)
        self.reason, self.status = reason, status


class WorkflowRunner:
    def __init__(
        self,
        cases,
        settings,
        *,
        model_port,
        tools: dict[str, ToolBinding],
        stages: WorkflowStages,
        checkpoint_path: Path,
        clock: Callable = lambda: datetime.now(UTC),
    ):
        if not set(tools).issubset(_ALLOWED):
            raise ValueError("tool registry contains a prohibited operation")
        self.cases, self.settings, self.port = cases, settings, model_port
        self.tools, self.stages, self.clock = dict(tools), stages, clock
        self.kernel, self.blobs = cases.kernel, cases.kernel.blob_store
        self.store = GraphStore(self.kernel)
        checkpoint_path = Path(checkpoint_path)
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        if checkpoint_path.resolve() == (settings.data_root / "application.sqlite").resolve():
            raise ValueError("workflow cache must be separate from application audit storage")
        self.connection = sqlite3.connect(checkpoint_path, check_same_thread=False)
        self.checkpointer = SqliteSaver(
            self.connection,
            serde=JsonPlusSerializer(
                pickle_fallback=False,
                allowed_json_modules=[],
                allowed_msgpack_modules=[],
            ),
        )
        builder = StateGraph(GraphInput)
        for name in ("preflight", "investigate", "draft", "verify", "sync"):
            builder.add_node(name, self._node)
            builder.add_edge(name, END)
        builder.add_conditional_edges(
            START,
            lambda state: state["route"],
            {name: name for name in ("preflight", "investigate", "draft", "verify", "sync")},
        )
        self.graph = builder.compile(checkpointer=self.checkpointer)
        self._lock = Lock()
        self._active = None

    def close(self):
        self.connection.close()

    def _now(self):
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("workflow clock must be timezone-aware")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _bound(context, spec):
        if context.run_id not in {None, spec.run_id}:
            raise ValueError("context pins a different run")
        if context.case_version_id not in {None, spec.case_snapshot.snapshot_id}:
            raise ValueError("context pins a different case")
        return context.model_copy(
            update={
                "run_id": spec.run_id,
                "case_version_id": spec.case_snapshot.snapshot_id,
            }
        )

    def _authorize(self, context, capability):
        if context.actor.actor_kind != "SERVICE":
            raise AuthorizationError("workflow dispatch requires a trusted SERVICE actor")
        self.kernel.authority.check(capability, context.actor, "graph.dispatch")

    def _ctx(self, root, spec, suffix):
        key = f"{spec.run_id}:turn_{self.store.load(spec.run_id).current_turn + 1}:{suffix}"
        return self._bound(root, spec).model_copy(
            update={
                "command_id": f"command:{spec.run_id}",
                "operation_id": f"operation:{key}",
                "attempt_id": f"attempt:{key}",
                "idempotency_key": key,
                "correlation_id": f"correlation:{spec.run_id}",
                "turn_id": f"turn:{spec.run_id}:{self.store.load(spec.run_id).current_turn + 1}",
                "parent_operation_id": None,
            }
        )

    def _save(self, root, spec, state, suffix, capability):
        context = self._ctx(root, spec, suffix)
        existing = self.kernel.get_intent(context.operation_id)
        if existing is not None and self.kernel.get_result(context.operation_id) is None:
            frozen = json.loads(self.blobs.get(existing.payload))
            if frozen["expected_version"] != state.version:
                raise ValueError("CONCURRENT_MODIFICATION: interrupted state write is stale")
            state = RunState.model_validate_json(canonical_json_bytes(frozen["state"]))
        return self.store.save(
            context,
            state,
            state.version,
            event_type="graph.state",
            capability=capability,
        )

    def start_run(self, context, spec: RunSpec, *, capability):
        from recycleguard.contracts.artifacts import SnapshotRef

        self._authorize(context, capability)
        if spec.execution_kind != "SCRIPTED_TEST":
            raise ValueError("MODEL_BACKED gateway is unavailable; no automatic fallback")
        if self.settings.mode != "test" or not self.settings.enable_test_adapters:
            raise ValueError("scripted workflow requires explicitly enabled test mode")
        case = self.cases.snapshots.get(spec.case_snapshot)
        corpus = self.cases.snapshots.get(spec.corpus_snapshot)
        if case.snapshot_kind != "CASE" or corpus.snapshot_kind != "CORPUS":
            raise ValueError("run requires CASE and CORPUS snapshots")
        if case.review_state != "APPROVED" or corpus.review_state != "APPROVED":
            raise ValueError("run requires approved snapshots")
        membership = json.loads(self.blobs.get(case.membership_blob))
        if ProfileRef.model_validate(membership["profile"]) != spec.profile:
            raise ValueError("run profile differs from the frozen case")
        if SnapshotRef.model_validate(membership["corpus_snapshot"]) != spec.corpus_snapshot:
            raise ValueError("run corpus differs from the frozen case")
        self.cases.profiles.get(spec.profile, require_approved=True)
        if spec.parent_run_id is not None:
            parent = self.store.load(spec.parent_run_id)
            if parent.status not in _TERMINAL:
                raise ValueError("correction parent must be terminal")
        return self.store.start(
            self._bound(context, spec),
            spec,
            capability=capability,
            now=self._now(),
        )

    def advance(self, context, run_id, expected_state_version, *, capability):
        self._authorize(context, capability)
        state = self.store.load(run_id)
        if state.version != expected_state_version:
            raise ValueError("CONCURRENT_MODIFICATION: stale state version")
        if state.status in _TERMINAL or state.status == "AWAITING_REVIEW":
            raise ValueError("paused or terminal run cannot advance")
        spec = self.store.spec(run_id)
        root = self._bound(context, spec)
        if not self._lock.acquire(blocking=False):
            raise ValueError("concurrent dispatcher invocation")
        try:
            self._active = root, capability
            route = {
                "CREATED": "preflight",
                "PREFLIGHT": "preflight",
                "INVESTIGATING": "investigate",
                "DRAFTING": "draft",
                "VERIFYING": "verify",
            }
            with tracing_context(enabled=False):
                self.graph.invoke(
                    {
                        "run_id": run_id,
                        "expected_version": state.version,
                        "route": route[state.status],
                        "status": state.status,
                    },
                    {"configurable": {"thread_id": run_id}, "recursion_limit": 4},
                )
            return self._checkpoint(root, spec, capability)
        finally:
            self._active = None
            self._lock.release()

    def _checkpoint(self, root, spec, capability):
        state = self.store.load(spec.run_id)
        cached = self.graph.get_state({"configurable": {"thread_id": spec.run_id}})
        blob = self.blobs.put(
            canonical_json_bytes(
                {
                    "run_id": spec.run_id,
                    "version": state.version,
                    "state_blob": self.store.state_blob(spec.run_id).model_dump(mode="json"),
                    "checkpoint_id": cached.config["configurable"].get("checkpoint_id"),
                }
            ),
            "application/json",
        )
        if state.status in _TERMINAL:
            return state
        return self._save(
            root,
            spec,
            state.model_copy(update={"last_checkpoint_ref": blob}),
            f"checkpoint_{state.version}",
            capability,
        )

    def resume(self, context, run_id, checkpoint_ref=None, *, capability):
        self._authorize(context, capability)
        state, spec = self.store.load(run_id), self.store.spec(run_id)
        root = self._bound(context, spec)
        if state.status in _TERMINAL:
            raise ValueError("terminal runs require a new parent-linked run")
        if checkpoint_ref is not None:
            if checkpoint_ref != state.last_checkpoint_ref:
                raise ValueError("STALE_SNAPSHOT: checkpoint is not the latest committed reference")
            checkpoint = json.loads(self.blobs.get(checkpoint_ref))
            historical = RunState.model_validate_json(
                self.blobs.get(BlobRef.model_validate(checkpoint["state_blob"]))
            )
            if (
                checkpoint["run_id"] != run_id
                or historical.run_id != run_id
                or checkpoint["version"] != historical.version
                or historical.version > state.version
            ):
                raise ValueError("checkpoint disagrees with authoritative state")
        # Rebuild cache from the application ledger; this route invokes no tools/model.
        if not self._lock.acquire(blocking=False):
            raise ValueError("concurrent dispatcher invocation")
        self._active = root, capability
        try:
            with tracing_context(enabled=False):
                self.graph.invoke(
                    {
                        "run_id": run_id,
                        "expected_version": state.version,
                        "route": "sync",
                        "status": state.status,
                    },
                    {"configurable": {"thread_id": run_id}, "recursion_limit": 4},
                )
            # Do not move the ledger CAS version during an interrupted turn.
            # Its already committed reservation/turn intents retain their exact version.
            if state.active_turn_input is not None:
                return self.store.load(run_id)
            return self._checkpoint(root, spec, capability)
        finally:
            self._active = None
            self._lock.release()

    def cancel(self, context, run_id, expected_version, reason, *, capability):
        self._authorize(context, capability)
        if not self._lock.acquire(blocking=False):
            raise ValueError("concurrent dispatcher invocation")
        try:
            return self._cancel(context, run_id, expected_version, reason, capability)
        finally:
            self._lock.release()

    def _cancel(self, context, run_id, expected_version, reason, capability):
        if not reason.strip():
            raise ValueError("cancellation requires a reason")
        state, spec = self.store.load(run_id), self.store.spec(run_id)
        if state.version != expected_version or state.status in _TERMINAL:
            raise ValueError("stale or terminal cancellation")
        root = self._bound(context, spec)
        self.store.archive(
            root.model_copy(
                update={
                    "command_id": f"{root.command_id}:reason",
                    "operation_id": f"{root.operation_id}:reason",
                    "attempt_id": f"{root.attempt_id}:reason",
                    "idempotency_key": f"{root.idempotency_key}:reason",
                }
            ),
            "graph.cancellation_request",
            CancellationRequest(
                run_id=run_id, expected_version=expected_version, reason=reason.strip()
            ),
            capability=capability,
        )
        updated = state.model_copy(update={"status": "CANCELLED", "updated_at": self._now()})
        return self.store.save(
            self._bound(context, spec),
            updated,
            expected_version,
            event_type="graph.cancel",
            capability=capability,
        )

    def _node(self, graph_input):
        root, cap = self._active
        state, spec = self.store.load(graph_input["run_id"]), self.store.spec(graph_input["run_id"])
        if state.version != graph_input["expected_version"]:
            raise ValueError("CONCURRENT_MODIFICATION: stale graph input")
        if graph_input["route"] == "sync":
            return {"status": state.status}
        if state.active_turn_input is None:
            state = self._save(
                root,
                spec,
                state.model_copy(
                    update={
                        "active_turn_input": self.store.state_blob(spec.run_id),
                    }
                ),
                "turn_start",
                cap,
            )
        initial = RunState.model_validate_json(self.blobs.get(state.active_turn_input))
        turn_context = self._ctx(root, spec, "turn_commit")
        interrupted = self.kernel.get_intent(turn_context.operation_id)
        if interrupted is not None and self.kernel.get_result(turn_context.operation_id) is None:
            frozen = json.loads(self.blobs.get(interrupted.payload))
            output = self.store.finish_turn(
                turn_context,
                RunState.model_validate_json(canonical_json_bytes(frozen["state"])),
                frozen["expected_version"],
                TurnManifest.model_validate_json(canonical_json_bytes(frozen["manifest"])),
                capability=cap,
            )
            return {"status": output.status}
        try:
            self._time(spec, state)
            if initial.status == "CREATED":
                state = state.model_copy(update={"status": "PREFLIGHT"})
            elif initial.status == "PREFLIGHT":
                result = self._stage(root, spec, "preflight", self.stages.preflight, cap)
                state = self.store.load(spec.run_id).model_copy(
                    update={
                        "status": "BLOCKED_INPUT"
                        if result.disposition == "BLOCKED"
                        else "INVESTIGATING",
                    }
                )
            elif initial.status == "INVESTIGATING":
                state = self._investigate(root, spec, initial, cap)
            elif initial.status == "DRAFTING":
                result = self._stage(root, spec, "draft", self.stages.draft, cap)
                state = self.store.load(spec.run_id).model_copy(
                    update={
                        "status": "BLOCKED_OUTPUT"
                        if result.disposition == "BLOCKED"
                        else "VERIFYING",
                    }
                )
            elif initial.status == "VERIFYING":
                result = self._stage(root, spec, "verify", self.stages.verify, cap)
                state = self.store.load(spec.run_id)
                if result.disposition == "BLOCKED":
                    if state.budget.report_repairs < spec.budgets.report_repairs:
                        usage = state.budget.model_copy(
                            update={"report_repairs": state.budget.report_repairs + 1}
                        )
                        state = state.model_copy(update={"status": "DRAFTING", "budget": usage})
                    else:
                        state = state.model_copy(update={"status": "BLOCKED_OUTPUT"})
                else:
                    state = state.model_copy(
                        update={"status": "AWAITING_REVIEW", "review_outcome": "PENDING"}
                    )
        except WorkflowStop as exc:
            state = self.store.load(spec.run_id)
            target = exc.status if initial.status == "INVESTIGATING" else "BLOCKED_OUTPUT"
            state = state.model_copy(
                update={
                    "status": target,
                    "stop_reason": exc.reason,
                    "abstained_finding_ids": list(
                        dict.fromkeys(state.abstained_finding_ids + state.pending_finding_ids)
                    ),
                    "pending_finding_ids": [],
                }
            )
        state = state.model_copy(update={"updated_at": self._now()})
        coverage = self.blobs.put(
            canonical_json_bytes(
                {
                    "resolved": state.resolved_finding_ids,
                    "abstained": state.abstained_finding_ids,
                    "pending": state.pending_finding_ids,
                    "execution_kind": spec.execution_kind,
                }
            ),
            "application/json",
        )
        events = self.kernel.list_stream_events(f"stream:{spec.run_id}")
        current_events = [e for e in events if e.sequence > initial.last_audit_sequence]
        plans = [
            PlanRecord.model_validate_json(self.blobs.get(e.payload_blob))
            for e in current_events
            if e.event_type == "graph.plan.result"
        ]
        assessments = [
            ObservationAssessment.model_validate_json(self.blobs.get(e.payload_blob))
            for e in current_events
            if e.event_type == "graph.assessment.result"
        ]
        state = state.model_copy(
            update={
                "plan_refs": list(dict.fromkeys(initial.plan_refs + [p.plan_id for p in plans])),
                "assessment_refs": list(
                    dict.fromkeys(initial.assessment_refs + [a.assessment_id for a in assessments])
                ),
                "result_refs": initial.result_refs
                + [
                    event.payload_blob
                    for event in current_events
                    if event.event_type.startswith(("graph.tool.", "graph.stage."))
                    and event.event_type.endswith(".result")
                ],
            }
        )
        service_outputs = [
            self.store.read(event.operation_id, CallRecord).stage_output
            for event in current_events
            if event.event_type.startswith(("graph.tool.", "graph.stage."))
            and event.event_type.endswith(".result")
        ]
        manifest = TurnManifest(
            turn_id=f"turn:{spec.run_id}:{initial.current_turn + 1}",
            run_id=spec.run_id,
            turn_index=initial.current_turn + 1,
            previous_turn_id=None
            if initial.current_turn == 0
            else f"turn:{spec.run_id}:{initial.current_turn}",
            input_state_blob=state.active_turn_input,
            output_state_blob=None,
            pinned_membership_refs=[
                spec.case_snapshot.snapshot_id,
                spec.corpus_snapshot.snapshot_id,
                spec.profile.profile_id,
                spec.index.configuration_id,
            ],
            operation_ids_in_order=[e.operation_id for e in current_events],
            context_manifest_ids=[
                ContextManifest.model_validate_json(
                    self.blobs.get(e.payload_blob)
                ).context_manifest_id
                for e in current_events
                if e.event_type == "graph.context.result"
            ],
            retrieval_attempt_ids=list(
                dict.fromkeys(
                    ref
                    for output in service_outputs
                    if output is not None
                    for ref in output.retrieval_attempt_ids
                )
            ),
            calculation_ids=list(
                dict.fromkeys(
                    ref
                    for output in service_outputs
                    if output is not None
                    for ref in output.calculation_ids
                )
            ),
            finding_revision_ids=list(
                dict.fromkeys(
                    ref
                    for output in service_outputs
                    if output is not None
                    for ref in output.finding_revision_ids
                )
            ),
            plan_refs=state.plan_refs[len(initial.plan_refs) :],
            observation_assessment_refs=state.assessment_refs[len(initial.assessment_refs) :],
            plan_revised=any(
                p.previous_plan_ref is not None and p.triggering_operation_ref is not None
                for p in plans
            ),
            coverage_summary_blob=coverage,
            budget_before=initial.budget,
            budget_after=state.budget,
            turn_status="FAILED" if state.status == "FAILED" else "COMPLETED",
            concise_decision=f"{initial.status} to {state.status}",
            stop_reason=state.stop_reason,
            first_event_sequence=initial.last_audit_sequence + 1,
            last_event_sequence=0,
        )
        final = self.store.finish_turn(
            self._ctx(root, spec, "turn_commit"), state, state.version, manifest, capability=cap
        )
        return {"status": final.status}

    def _time(self, spec, state):
        now = datetime.fromisoformat(self._now().replace("Z", "+00:00"))
        started = datetime.fromisoformat(state.created_at.replace("Z", "+00:00"))
        updated = datetime.fromisoformat(state.updated_at.replace("Z", "+00:00"))
        if now < updated:
            raise WorkflowStop("AUDIT_FAILURE", status="FAILED")
        if (now - started).total_seconds() >= spec.budgets.max_wall_seconds:
            raise WorkflowStop("BUDGET_EXHAUSTED")

    def _reserve(
        self,
        root,
        spec,
        kind,
        name,
        operation_id,
        cap,
        *,
        finding=None,
        retry=False,
        reformulate=False,
        attempt_id=None,
    ):
        state = self.store.load(spec.run_id)
        self._time(spec, state)
        usage, limits = state.budget, spec.budgets
        reserve = 2 if kind in {"model", "tool"} else 0
        if usage.actions + 1 + reserve > limits.max_case_actions:
            raise WorkflowStop("BUDGET_EXHAUSTED")
        changes = {"actions": usage.actions + 1, "retries": usage.retries + int(retry)}
        if kind == "model":
            if (
                usage.model_calls >= limits.max_model_calls
                or usage.reserved_tokens + limits.tokens_per_model_call > limits.max_total_tokens
            ):
                raise WorkflowStop("BUDGET_EXHAUSTED")
            changes.update(
                model_calls=usage.model_calls + 1,
                reserved_tokens=usage.reserved_tokens + limits.tokens_per_model_call,
            )
        elif kind == "tool":
            count = usage.finding_actions.get(finding, 0)
            reforms = usage.finding_reformulations.get(finding, 0)
            if count >= limits.tools_per_finding or (
                reformulate and reforms >= limits.reformulations_per_finding
            ):
                raise WorkflowStop("BUDGET_EXHAUSTED")
            changes.update(
                tool_calls=usage.tool_calls + 1,
                finding_actions=usage.finding_actions | {finding: count + 1},
            )
            if reformulate:
                changes["finding_reformulations"] = usage.finding_reformulations | {
                    finding: reforms + 1
                }
        elif name.startswith("preflight_"):
            if usage.preflight_actions >= limits.preflight_actions:
                raise WorkflowStop("BUDGET_EXHAUSTED")
            changes["preflight_actions"] = usage.preflight_actions + 1
        elif name.startswith("verify_"):
            if usage.verification_actions >= limits.verification_actions:
                raise WorkflowStop("BUDGET_EXHAUSTED")
            changes["verification_actions"] = usage.verification_actions + 1
        self._save(
            root,
            spec,
            state.model_copy(
                update={
                    "budget": usage.model_copy(update=changes),
                    "pending_operation_id": operation_id,
                    "pending_attempt_id": attempt_id,
                    "updated_at": self._now(),
                }
            ),
            f"reserve_{name}",
            cap,
        )

    @staticmethod
    def _issue(code, message, retryable=False):
        return Issue(
            issue_id=f"issue:{code.lower()}",
            code=code,
            severity="BLOCKING",
            message=message,
            field_path=None,
            evidence_refs=[],
            retryable=retryable,
        )

    def _external(
        self, root, spec, name, kind, request, handler, cap, *, finding=None, reformulate=False
    ):
        logical = self._ctx(root, spec, name)
        terminal = self.store.read(logical.operation_id, CallRecord)
        if terminal is not None:
            if terminal.status in {"SUCCESS", "PARTIAL"}:
                if kind == "model":
                    self._usage(
                        root,
                        spec,
                        name,
                        self.kernel.get_result(logical.operation_id).attempt_id,
                        terminal,
                        cap,
                    )
                return terminal, logical.operation_id
            raise WorkflowStop("PROVIDER_FAILURE", status="FAILED")
        for attempt in range(spec.budgets.retries_per_operation + 1):
            ctx = logical.model_copy(update={"attempt_id": f"{logical.attempt_id}_{attempt}"})
            old = self.kernel.connection.execute(
                "SELECT result_json FROM attempt_results WHERE attempt_id=?",
                (ctx.attempt_id,),
            ).fetchone()
            if old is not None:
                stored = OperationResult.model_validate_json(old["result_json"])
                record = CallRecord.model_validate_json(self.blobs.get(stored.payload))
            else:
                registered = self.kernel.connection.execute(
                    "SELECT 1 FROM operation_attempts WHERE attempt_id=?",
                    (ctx.attempt_id,),
                ).fetchone()
                if registered is not None:
                    raise WorkflowStop("PROVIDER_FAILURE", status="FAILED")
                current = self.store.load(spec.run_id)
                if current.pending_attempt_id != ctx.attempt_id:
                    self._reserve(
                        root,
                        spec,
                        kind,
                        f"{name}_{attempt}",
                        ctx.operation_id,
                        cap,
                        finding=finding,
                        retry=attempt > 0,
                        reformulate=reformulate and attempt == 0,
                        attempt_id=ctx.attempt_id,
                    )
                payload = self.blobs.put(
                    canonical_json_bytes(request.model_dump(mode="json")),
                    "application/json",
                )
                intent = OperationIntent(
                    context=ctx,
                    idempotency_key=ctx.idempotency_key,
                    event_type=f"graph.{kind}.{name}",
                    payload=payload,
                    stream_id=f"stream:{spec.run_id}",
                )
                admitted = self.store.load(spec.run_id)
                if admitted.status in _TERMINAL:
                    raise WorkflowStop("EXPERT_REVIEW_REQUIRED", status=admitted.status)
                self._time(spec, admitted)
                self.kernel.commit_intent(intent, capability=cap)
                raw_blob, raw = None, None
                try:
                    raw = handler(ctx, request)
                    envelope = (
                        ServiceResult[ModelCallResult]
                        if kind == "model"
                        else ServiceResult[StageOutcome]
                    )
                    raw = envelope.model_validate_json(raw.model_dump_json())
                    raw_blob = self.blobs.put(
                        canonical_json_bytes(raw.model_dump(mode="json")),
                        "application/json",
                    )
                    issues = list(raw.issues)
                    valid = (raw.operation_id, raw.attempt_id) == (ctx.operation_id, ctx.attempt_id)
                    if kind == "model" and raw.output is not None:
                        valid = valid and raw.output.outcome == raw.status
                        valid = (
                            valid
                            and json.loads(self.blobs.get(raw.output.exact_response_blob))
                            == raw.output.validated_output_or_null
                        )
                        if raw.status == "SUCCESS":
                            schema = PlanProposal if name == "plan" else AssessmentProposal
                            schema.model_validate_json(
                                canonical_json_bytes(raw.output.validated_output_or_null)
                            )
                        issues.extend(raw.output.validation_issues)
                    if raw.status == "SUCCESS" and raw.output is None:
                        valid = False
                    if not valid:
                        issues.append(
                            self._issue(
                                "PROVIDER_INVALID_OUTPUT",
                                "response boundary mismatch",
                                True,
                            )
                        )
                    status = raw.status if valid else "FAILED"
                    if status == "SUCCESS" and any(i.severity == "BLOCKING" for i in issues):
                        status = "FAILED"
                    record = CallRecord(
                        status=status,
                        raw_result_blob=raw_blob,
                        model_output=raw.output if kind == "model" else None,
                        stage_output=None if kind == "model" else raw.output,
                        issues=issues,
                    )
                except OutcomeUnknownError as exc:
                    blob = self.blobs.put(
                        canonical_json_bytes({"error": str(exc), "code": exc.code}),
                        "application/json",
                    )
                    record = CallRecord(
                        status="OUTCOME_UNKNOWN",
                        raw_result_blob=blob,
                        model_output=None,
                        stage_output=None,
                        issues=[self._issue(exc.code, str(exc))],
                    )
                except TimeoutError as exc:
                    blob = self.blobs.put(
                        canonical_json_bytes({"error": str(exc)}),
                        "application/json",
                    )
                    record = CallRecord(
                        status="OUTCOME_UNKNOWN",
                        raw_result_blob=blob,
                        model_output=None,
                        stage_output=None,
                        issues=[self._issue("PROVIDER_TIMEOUT", str(exc) or "timeout")],
                    )
                except (ValueError, RuntimeError) as exc:
                    blob = raw_blob or self.blobs.put(
                        canonical_json_bytes({"error": str(exc)}),
                        "application/json",
                    )
                    record = CallRecord(
                        status="FAILED",
                        raw_result_blob=blob,
                        model_output=raw.output if raw is not None and kind == "model" else None,
                        stage_output=raw.output if raw is not None and kind != "model" else None,
                        issues=[self._issue("PROVIDER_INVALID_OUTPUT", str(exc), True)],
                    )
                archived = self.blobs.put(
                    canonical_json_bytes(record.model_dump(mode="json")),
                    "application/json",
                )
                refs = [record.raw_result_blob]
                if raw is not None and raw.output_blob is not None:
                    self.blobs.get(raw.output_blob)
                    refs.append(raw.output_blob)
                if record.model_output is not None:
                    refs.append(record.model_output.exact_response_blob)
                if record.stage_output is not None and record.stage_output.output_blob is not None:
                    refs.append(record.stage_output.output_blob)
                retryable = (
                    record.status == "FAILED"
                    and any(i.retryable for i in record.issues)
                    and attempt < spec.budgets.retries_per_operation
                )
                self.kernel.commit_result(
                    intent,
                    OperationResult(
                        operation_id=ctx.operation_id,
                        attempt_id=ctx.attempt_id,
                        status=record.status,
                        payload=archived,
                        output_refs=refs,
                        issue_codes=[i.code for i in record.issues],
                    ),
                    capability=cap,
                    terminal=not retryable,
                )
            if kind == "model":
                self._usage(root, spec, name, ctx.attempt_id, record, cap)
            self._time(spec, self.store.load(spec.run_id))
            if record.status in {"SUCCESS", "PARTIAL"}:
                return record, ctx.operation_id
            if record.status != "FAILED" or not any(i.retryable for i in record.issues):
                break
        raise WorkflowStop("PROVIDER_FAILURE", status="FAILED")

    def _usage(self, root, spec, name, attempt_id, record, cap):
        suffix = f"usage_{name}_{attempt_id.rsplit('_', 1)[1]}"
        ctx = self._ctx(root, spec, suffix)
        supplied = None if record.model_output is None else record.model_output.usage
        tokens, cost = None, None
        if supplied is not None:
            try:
                metrics = ProviderUsage.model_validate_json(canonical_json_bytes(supplied))
                if metrics.total_tokens < 0:
                    raise ValueError("negative provider usage")
                if metrics.cost_usd is not None:
                    amount = Decimal(metrics.cost_usd)
                    if not amount.is_finite() or amount < 0:
                        raise ValueError("provider cost must be finite and nonnegative")
                tokens, cost = metrics.total_tokens, metrics.cost_usd
            except (ValueError, ArithmeticError) as exc:
                raise WorkflowStop("PROVIDER_FAILURE", status="FAILED") from exc
        if self.store.read(ctx.operation_id, RunState) is not None:
            # Accounting is idempotent; its safety decision must survive a crash
            # after the usage commit but before the enclosing turn was stopped.
            if tokens is not None and tokens > spec.budgets.tokens_per_model_call:
                raise WorkflowStop("BUDGET_EXHAUSTED", status="FAILED")
            return
        state = self.store.load(spec.run_id)
        current = state.budget
        known = current.usage_known_calls + int(tokens is not None)
        known_cost = current.cost_known_calls + int(cost is not None)
        observed = None
        observed_cost = None
        if known == current.model_calls and tokens is not None:
            observed = (current.observed_tokens or 0) + tokens
        if known_cost == current.model_calls and cost is not None:
            try:
                observed_cost = str(Decimal(current.observed_cost_usd or "0") + Decimal(cost))
            except ArithmeticError as exc:
                raise WorkflowStop("PROVIDER_FAILURE", status="FAILED") from exc
        usage = current.model_copy(
            update={
                "observed_tokens": observed,
                "observed_cost_usd": observed_cost,
                "usage_known_calls": known,
                "cost_known_calls": known_cost,
            }
        )
        self._save(root, spec, state.model_copy(update={"budget": usage}), suffix, cap)
        if tokens is not None and tokens > spec.budgets.tokens_per_model_call:
            raise WorkflowStop("BUDGET_EXHAUSTED", status="FAILED")

    def _stage(self, root, spec, name, handler, cap):
        result, _ = self._external(root, spec, name, "stage", spec, handler, cap)
        return result.stage_output

    def _model(self, root, spec, initial, phase, body, cap):
        response_model = PlanProposal if phase == "PLAN" else AssessmentProposal
        blob = self.blobs.put(
            canonical_json_bytes(
                {
                    "phase": phase,
                    "run_id": spec.run_id,
                    "max_total_tokens": spec.budgets.tokens_per_model_call,
                    "response_schema": response_model.model_json_schema(),
                    "allowed_tools": {
                        name: binding.arguments_model.model_json_schema()
                        for name, binding in sorted(self.tools.items())
                    }
                    if phase == "PLAN"
                    else {},
                    **body,
                }
            ),
            "application/json",
        )
        request = ModelCallRequest(
            model_configuration_id=spec.model.configuration_id,
            prompt_template_id=spec.prompt.configuration_id,
            prompt_template_digest=spec.prompt.digest,
            exact_request_blob=blob,
            context_manifest_id=(
                f"context_manifest:{spec.run_id}:{initial.current_turn + 1}:{phase}"
            ),
            allowed_tool_schema_digest=spec.tools.digest,
            response_schema_id=f"schema:{phase.lower()}",
            budget_ref=f"budget:{spec.run_id}",
        )
        manifest = ContextManifest(
            context_manifest_id=request.context_manifest_id,
            run_id=spec.run_id,
            phase=phase,
            exact_request_blob=blob,
            allowed_tool_schema_digest=spec.tools.digest,
            max_total_tokens=spec.budgets.tokens_per_model_call,
        )
        self.store.archive(
            self._ctx(root, spec, f"context_{phase}"), "graph.context", manifest, capability=cap
        )
        result, operation = self._external(
            root, spec, phase.lower(), "model", request, self.port.invoke, cap
        )
        if result.status != "SUCCESS" or result.model_output is None:
            raise WorkflowStop("PROVIDER_FAILURE", status="FAILED")
        model = PlanProposal if phase == "PLAN" else AssessmentProposal
        return model.model_validate_json(
            canonical_json_bytes(result.model_output.validated_output_or_null)
        ), operation

    def _plan(
        self,
        root,
        spec,
        draft,
        initial,
        cap,
        *,
        suffix="plan_record",
        predecessor=None,
        trigger=None,
    ):
        ctx = self._ctx(root, spec, suffix)
        previous = self.store.read(ctx.operation_id, PlanRecord)
        if previous is not None:
            return previous
        prior_id = predecessor or (initial.plan_refs[-1] if initial.plan_refs else None)
        previous_plan = (
            None
            if prior_id is None
            else self._record(spec, prior_id, PlanRecord, "graph.plan.result")
        )
        if previous_plan is not None and previous_plan.finding_id != initial.pending_finding_ids[0]:
            previous_plan, prior_id = None, None
        revision = 1 if previous_plan is None else previous_plan.revision + 1
        if trigger is None and previous_plan is not None and initial.assessment_refs:
            previous_assessment = self._record(
                spec, initial.assessment_refs[-1], ObservationAssessment, "graph.assessment.result"
            )
            assessed_plan = self._record(
                spec, previous_assessment.plan_ref, PlanRecord, "graph.plan.result"
            )
            if assessed_plan.finding_id == initial.pending_finding_ids[0]:
                trigger = previous_assessment.operation_ref
        record = PlanRecord(
            **draft.model_dump(),
            plan_id=f"plan:{ctx.operation_id}",
            revision=revision,
            previous_plan_ref=prior_id,
            triggering_operation_ref=trigger,
            finding_id=initial.pending_finding_ids[0],
        )
        self.store.archive(ctx, "graph.plan", record, capability=cap)
        return record

    def _record(self, spec, reference, model, event_type):
        for event in reversed(self.kernel.list_stream_events(f"stream:{spec.run_id}")):
            if event.event_type == event_type:
                raw = json.loads(self.blobs.get(event.payload_blob))
                key = "plan_id" if model is PlanRecord else "assessment_id"
                if raw[key] == reference:
                    return model.model_validate_json(canonical_json_bytes(raw))
        raise ValueError("missing workflow decision record")

    def _investigate(self, root, spec, initial, cap):
        proposal, _ = self._model(
            root,
            spec,
            initial,
            "PLAN",
            {
                "pending_findings": initial.pending_finding_ids,
                "prior_stage_result_refs": [
                    ref.model_dump(mode="json") for ref in initial.result_refs
                ],
                "previous_assessment_refs": initial.assessment_refs,
                "previous_plan_refs": initial.plan_refs,
                "previous_plans": [
                    self._record(spec, ref, PlanRecord, "graph.plan.result").model_dump(mode="json")
                    for ref in initial.plan_refs[-2:]
                ],
                "previous_assessments": [
                    self._record(
                        spec, ref, ObservationAssessment, "graph.assessment.result"
                    ).model_dump(mode="json")
                    for ref in initial.assessment_refs[-2:]
                ],
            },
            cap,
        )
        if proposal.action is None:
            self._plan(root, spec, proposal.plan, initial, cap)
            raise WorkflowStop(proposal.stop_reason)
        action = proposal.action
        if action.finding_id != initial.pending_finding_ids[0]:
            raise WorkflowStop("EXPERT_REVIEW_REQUIRED", status="BLOCKED_OUTPUT")
        if action.allowed_operation not in self.tools:
            raise WorkflowStop("EXPERT_REVIEW_REQUIRED", status="BLOCKED_OUTPUT")
        binding = self.tools[action.allowed_operation]
        try:
            arguments = binding.arguments_model.model_validate_json(
                canonical_json_bytes(action.typed_arguments)
            )
        except ValidationError as exc:
            raise WorkflowStop("EXPERT_REVIEW_REQUIRED", status="BLOCKED_OUTPUT") from exc
        fingerprint = hashlib.sha256(
            canonical_json_bytes(
                [
                    action.finding_id,
                    action.allowed_operation,
                    arguments.model_dump(mode="json"),
                ]
            )
        ).hexdigest()
        if fingerprint in initial.action_fingerprints:
            raise WorkflowStop("CYCLE_DETECTED")
        queries = dict(initial.search_queries)
        previous_queries = queries.get(action.finding_id, [])
        is_search = action.allowed_operation == "search_rules"
        reformulate = action.action_kind == "REFORMULATE" or (is_search and bool(previous_queries))
        if action.action_kind == "REFORMULATE" and not is_search:
            raise WorkflowStop("EXPERT_REVIEW_REQUIRED", status="BLOCKED_OUTPUT")
        plan = self._plan(root, spec, proposal.plan, initial, cap)
        proposed = ActionProposal(**action.model_dump(), plan_ref=plan.plan_id)
        self.store.archive(
            self._ctx(root, spec, "action"), "graph.action", proposed, capability=cap
        )
        observation, operation = self._external(
            root,
            spec,
            "tool",
            "tool",
            arguments,
            binding.handler,
            cap,
            finding=action.finding_id,
            reformulate=reformulate,
        )
        try:
            assessed, _ = self._model(
                root,
                spec,
                initial,
                "ASSESS",
                {
                    "plan": plan.model_dump(mode="json"),
                    "action": proposed.model_dump(mode="json"),
                    "observation": observation.model_dump(mode="json"),
                },
                cap,
            )
        except WorkflowStop as exc:
            # A completed observation still receives an explicit unknown assessment
            # when the model cannot be called or its result cannot be accepted.
            self.store.archive(
                self._ctx(root, spec, "assessment"),
                "graph.assessment",
                ObservationAssessment(
                    assessment_id=f"assessment:{spec.run_id}:{initial.current_turn + 1}",
                    operation_ref=operation,
                    plan_ref=plan.plan_id,
                    observation_refs=[]
                    if observation.stage_output is None
                    else observation.stage_output.evidence_refs,
                    verdict="UNKNOWN",
                    weak_result_or_mistake="Assessment unavailable within execution bounds.",
                    next_check_or_stop=exc.reason,
                    revised_plan_ref=None,
                    disposition="ABSTAIN",
                ),
                capability=cap,
            )
            raise
        revised = None
        if assessed.revised_plan is not None:
            revised = self._plan(
                root,
                spec,
                assessed.revised_plan,
                initial,
                cap,
                suffix="revised_plan",
                predecessor=plan.plan_id,
                trigger=operation,
            )
        assessment = ObservationAssessment(
            assessment_id=f"assessment:{spec.run_id}:{initial.current_turn + 1}",
            operation_ref=operation,
            plan_ref=plan.plan_id,
            observation_refs=[]
            if observation.stage_output is None
            else observation.stage_output.evidence_refs,
            verdict=assessed.verdict,
            weak_result_or_mistake=assessed.weak_result_or_mistake,
            next_check_or_stop=assessed.next_check_or_stop,
            revised_plan_ref=None if revised is None else revised.plan_id,
            disposition=assessed.disposition,
        )
        self.store.archive(
            self._ctx(root, spec, "assessment"), "graph.assessment", assessment, capability=cap
        )
        state = self.store.load(spec.run_id)
        pending, resolved, abstained = (
            list(initial.pending_finding_ids),
            list(initial.resolved_finding_ids),
            list(initial.abstained_finding_ids),
        )
        if assessed.disposition == "RESOLVE":
            resolved.append(pending.pop(0))
        elif assessed.disposition == "ABSTAIN":
            abstained.append(pending.pop(0))
        if is_search:
            queries[action.finding_id] = previous_queries + [fingerprint]
        return state.model_copy(
            update={
                "status": "INVESTIGATING" if pending else "DRAFTING",
                "stop_reason": None
                if pending
                else ("NO_NEW_EVIDENCE" if abstained else "RESOLVED_WITHIN_SCOPE"),
                "pending_finding_ids": pending,
                "resolved_finding_ids": resolved,
                "abstained_finding_ids": abstained,
                "plan_refs": initial.plan_refs
                + [plan.plan_id]
                + ([] if revised is None else [revised.plan_id]),
                "assessment_refs": initial.assessment_refs + [assessment.assessment_id],
                "action_fingerprints": initial.action_fingerprints + [fingerprint],
                "search_queries": queries,
            }
        )
