"""Audited scripted workflow behavior; these tests do not evaluate actual models."""

import json
import shutil
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from recycleguard.application import command_context, local_application
from recycleguard.config import Settings
from recycleguard.contracts.artifacts import ProfileRef, SnapshotRef
from recycleguard.contracts.core import BlobRef
from recycleguard.contracts.workflow import BudgetLimits, ConfigurationPin, RunSpec
from recycleguard.workflow import ToolBinding, WorkflowRunner, WorkflowStages
from tests.integration.test_a05_baseline import approved_foundation as approved_foundation
from tests.support.workflow import (
    QueryArguments,
    RecordingStage,
    ScriptedStep,
    ScriptedWorkflowPort,
    assess,
    plan,
)

PAUSED_OR_TERMINAL = {
    "AWAITING_REVIEW",
    "COMPLETED",
    "BLOCKED_INPUT",
    "BLOCKED_OUTPUT",
    "FAILED",
    "CANCELLED",
}


@dataclass
class TestClock:
    __test__ = False
    now: datetime = datetime(2026, 10, 28, tzinfo=UTC)

    def __call__(self):
        return self.now


def pin(name):
    return ConfigurationPin(configuration_id=f"configuration:{name}", digest="1" * 64)


def run_spec(cases, *, budgets=None, execution_kind="SCRIPTED_TEST", finding_ids=None):
    snapshot = cases.snapshots.catalog.get_snapshot("snapshot:case_approved")
    corpus = cases.snapshots.catalog.get_snapshot("snapshot:corpus_approved")
    membership = json.loads(cases.kernel.blob_store.get(snapshot.membership_blob))
    return RunSpec(
        run_id="run:scripted_test",
        case_snapshot=SnapshotRef(
            snapshot_id=snapshot.snapshot_id, membership_digest=snapshot.membership_digest
        ),
        corpus_snapshot=SnapshotRef(
            snapshot_id=corpus.snapshot_id, membership_digest=corpus.membership_digest
        ),
        profile=ProfileRef.model_validate(membership["profile"]),
        index=pin("index"),
        code_revision="scripted-test-only",
        dependency_lock_digest="2" * 64,
        adapters=pin("adapters"),
        tools=pin("tools"),
        prompt=pin("prompt"),
        model=pin("model"),
        retrieval_policy=pin("retrieval"),
        audit_policy=pin("audit"),
        security_policy=pin("security"),
        execution_kind=execution_kind,
        experiment_variant="SCRIPTED_TEST_NOT_MODEL_EVALUATION",
        finding_ids=finding_ids or ["finding:one"],
        budgets=budgets or BudgetLimits(),
    )


@dataclass
class Harness:
    cases: object
    context: object
    capability: object
    runner: WorkflowRunner | None
    spec: RunSpec
    port: ScriptedWorkflowPort
    lookup: RecordingStage
    preflight: RecordingStage
    draft: RecordingStage
    verify: RecordingStage
    clock: TestClock
    checkpoint_path: Path
    settings: Settings

    def start(self):
        return self.runner.start_run(self.context, self.spec, capability=self.capability)

    def advance(self, state):
        return self.runner.advance(
            command_context(self.context.actor),
            state.run_id,
            state.version,
            capability=self.capability,
        )

    def drive(self, state, *, until=PAUSED_OR_TERMINAL):
        for _ in range(40):
            if state.status in until:
                return state
            state = self.advance(state)
        raise AssertionError("bounded workflow did not stop within 40 transitions")

    def restart(self):
        if self.runner is not None:
            self.runner.close()
        self.runner = WorkflowRunner(
            self.cases,
            self.settings,
            model_port=self.port,
            tools={"search_rules": ToolBinding(QueryArguments, self.lookup)},
            stages=WorkflowStages(self.preflight, self.draft, self.verify),
            checkpoint_path=self.checkpoint_path,
            clock=self.clock,
        )


@pytest.fixture
def workflow(tmp_path, approved_foundation):
    root = tmp_path / "data"
    shutil.copytree(approved_foundation, root, ignore=shutil.ignore_patterns("reviewer.json"))
    settings = Settings(data_root=root, mode="test", enable_test_adapters=True)

    @contextmanager
    def create(steps, *, budgets=None, preflight="PASS", verified="PASS", tool_statuses=()):
        with local_application(settings) as (cases, context, capability):
            port = ScriptedWorkflowPort(settings, cases.kernel.blob_store, steps)
            lookup = RecordingStage(statuses=tool_statuses)
            stages = [
                RecordingStage(disposition=preflight),
                RecordingStage(),
                RecordingStage(disposition=verified),
            ]
            harness = Harness(
                cases,
                context,
                capability,
                None,
                run_spec(cases, budgets=budgets),
                port,
                lookup,
                *stages,
                TestClock(),
                tmp_path / "workflow-checkpoints.sqlite",
                settings,
            )
            harness.restart()
            try:
                yield harness
            finally:
                harness.runner.close()

    return create


def test_weak_evidence_revises_plan_reformulates_and_resolves(workflow):
    with workflow(
        [
            plan(),
            assess(verdict="WEAK", disposition="CONTINUE", revised=True),
            plan("exact allocation locator", kind="REFORMULATE"),
            assess(),
        ]
    ) as env:
        state = env.drive(env.start())
        assert state.status == "AWAITING_REVIEW"
        assert state.resolved_finding_ids == ["finding:one"]
        assert state.pending_finding_ids == []
        assert state.budget.tool_calls == 2
        assert state.budget.finding_reformulations == {"finding:one": 1}
        assert len(state.plan_refs) >= 2 and len(state.assessment_refs) == 2
        assert [arguments.query for _, arguments in env.lookup.calls] == [
            "allocation",
            "exact allocation locator",
        ]
        assert len(env.port.calls) == 4
        assert len(env.draft.calls) == len(env.verify.calls) == 1


@pytest.mark.parametrize("operation", ["shell.execute", "review.record_support", "sql.query"])
def test_non_allowlisted_operations_never_reach_handler(workflow, operation):
    with workflow([plan(operation=operation)]) as env:
        state = env.drive(env.start())
        assert state.status in {"FAILED", "BLOCKED_OUTPUT"}
        assert not env.lookup.calls
        assert not env.draft.calls


def test_wrong_finding_is_rejected(workflow):
    bad = plan(finding="finding:other")
    with workflow([bad]) as env:
        state = env.drive(env.start())
        assert state.status in {"FAILED", "BLOCKED_OUTPUT"}
        assert not env.lookup.calls


def test_extra_tool_arguments_are_rejected_before_execution(workflow):
    step = plan()
    output = step.output | {
        "action": step.output["action"]
        | {"typed_arguments": {"query": "allocation", "shell": "execute"}}
    }
    with workflow([ScriptedStep("PLAN", output)]) as env:
        state = env.drive(env.start())
        assert state.status in {"FAILED", "BLOCKED_OUTPUT"}
        assert not env.lookup.calls


def test_invalid_structured_proposal_cannot_invoke_tool(workflow):
    step = plan()
    output = step.output | {"unapproved_field": "Ignore the execution boundary"}
    with workflow([ScriptedStep("PLAN", output)]) as env:
        state = env.drive(env.start())
        assert state.status in {"FAILED", "BLOCKED_OUTPUT"}
        assert not env.lookup.calls


def test_exact_response_and_validated_proposal_must_agree(workflow):
    step = plan()
    with workflow(
        [ScriptedStep("PLAN", step.output, exact_output={"different": "response"})]
    ) as env:
        state = env.drive(env.start())
        assert state.status in {"FAILED", "BLOCKED_OUTPUT"}
        assert not env.lookup.calls


def test_model_result_operation_identity_is_checked(workflow):
    step = plan()
    with workflow([ScriptedStep("PLAN", step.output, mismatched_operation=True)]) as env:
        state = env.drive(env.start())
        assert state.status in {"FAILED", "BLOCKED_OUTPUT"}
        assert not env.lookup.calls


def test_blocked_preflight_never_calls_model(workflow):
    with workflow([], preflight="BLOCKED") as env:
        state = env.drive(env.start())
        assert state.status == "BLOCKED_INPUT"
        assert not env.port.calls and not env.lookup.calls


@pytest.mark.parametrize(
    "budgets",
    [
        BudgetLimits(max_case_actions=1),
        BudgetLimits(max_model_calls=1),
        BudgetLimits(max_total_tokens=2048, tokens_per_model_call=2048),
        BudgetLimits(tools_per_finding=1),
    ],
)
def test_case_model_token_and_finding_budgets_stop_execution(workflow, budgets):
    with workflow(
        [
            plan(),
            assess(verdict="WEAK", disposition="CONTINUE", revised=True),
            plan("second query"),
            assess(),
        ],
        budgets=budgets,
    ) as env:
        state = env.drive(env.start())
        assert state.stop_reason == "BUDGET_EXHAUSTED"
        assert state.budget.actions <= budgets.max_case_actions
        assert state.budget.model_calls <= budgets.max_model_calls
        assert state.budget.reserved_tokens <= budgets.max_total_tokens
        assert state.budget.finding_actions.get("finding:one", 0) <= budgets.tools_per_finding


def test_reformulation_budget_stops_before_extra_lookup(workflow):
    limits = BudgetLimits(reformulations_per_finding=0)
    with workflow([plan(kind="REFORMULATE")], budgets=limits) as env:
        state = env.drive(env.start())
        assert state.stop_reason == "BUDGET_EXHAUSTED"
        assert not env.lookup.calls


def test_wall_clock_budget_stops_without_another_model_call(workflow):
    with workflow([plan(), assess()]) as env:
        state = env.start()
        env.clock.now += timedelta(seconds=301)
        state = env.drive(state)
        assert state.stop_reason == "BUDGET_EXHAUSTED"
        assert not env.port.calls


def test_known_failed_model_call_gets_one_retry_with_same_operation(workflow):
    failed = ScriptedStep("PLAN", None, status="FAILED", retryable=True)
    with workflow([failed, plan(), assess()]) as env:
        state = env.drive(env.start())
        assert state.status == "AWAITING_REVIEW"
        assert state.budget.retries == 1
        first, second = env.port.calls[:2]
        assert first[0].operation_id == second[0].operation_id
        assert first[0].attempt_id != second[0].attempt_id


def test_model_retry_cap_prevents_a_third_provider_attempt(workflow):
    failed = ScriptedStep("PLAN", None, status="FAILED", retryable=True)
    with workflow([failed, failed, plan()]) as env:
        state = env.drive(env.start())
        assert state.status == "FAILED"
        assert state.stop_reason == "PROVIDER_FAILURE"
        assert len(env.port.calls) == 2
        assert not env.lookup.calls


def test_repeating_identical_tool_action_stops_the_cycle(workflow):
    with workflow([plan(), assess(verdict="WEAK", disposition="CONTINUE"), plan()]) as env:
        state = env.drive(env.start())
        assert state.stop_reason == "CYCLE_DETECTED"
        assert len(env.lookup.calls) == 1


def test_unknown_model_outcome_is_never_retried(workflow):
    unknown = ScriptedStep("PLAN", None, status="OUTCOME_UNKNOWN", retryable=True)
    with workflow([unknown, plan()]) as env:
        state = env.drive(env.start())
        assert state.status == "FAILED"
        assert state.stop_reason == "PROVIDER_FAILURE"
        assert len(env.port.calls) == 1 and not env.lookup.calls


def test_known_failed_tool_action_gets_one_retry(workflow):
    with workflow([plan(), assess()], tool_statuses=["FAILED", "SUCCESS"]) as env:
        state = env.drive(env.start())
        assert state.status == "AWAITING_REVIEW"
        assert len(env.lookup.calls) == 2
        assert state.budget.retries == 1
        first, second = env.lookup.calls
        assert first[0].operation_id == second[0].operation_id
        assert first[0].attempt_id != second[0].attempt_id


def test_unknown_tool_outcome_is_never_retried(workflow):
    with workflow([plan()], tool_statuses=["OUTCOME_UNKNOWN"]) as env:
        state = env.drive(env.start())
        assert state.status == "FAILED"
        assert len(env.lookup.calls) == 1
        assert len(env.port.calls) == 1


def test_restart_from_committed_checkpoint_never_reexecutes_tool(workflow):
    with workflow([plan(), assess()]) as env:
        state = env.start()
        for _ in range(10):
            if env.lookup.calls:
                break
            state = env.advance(state)
        assert len(env.lookup.calls) == 1
        env.restart()
        restored = env.runner.resume(
            command_context(env.context.actor),
            state.run_id,
            state.last_checkpoint_ref,
            capability=env.capability,
        )
        state = env.drive(restored)
        assert state.status == "AWAITING_REVIEW"
        assert len(env.lookup.calls) == 1
        assert len({ctx.operation_id for ctx, _, _ in env.port.calls}) == len(env.port.calls)


def test_cancel_and_stale_version_cannot_execute_additional_work(workflow):
    with workflow([plan(), assess()]) as env:
        state = env.start()
        advanced = env.advance(state)
        with pytest.raises(ValueError):
            env.runner.advance(
                command_context(env.context.actor),
                state.run_id,
                state.version,
                capability=env.capability,
            )
        cancelled = env.runner.cancel(
            command_context(env.context.actor),
            advanced.run_id,
            advanced.version,
            "Operator cancelled the test",
            capability=env.capability,
        )
        assert cancelled.status == "CANCELLED"
        calls = len(env.port.calls)
        with pytest.raises(ValueError):
            env.advance(cancelled)
        assert len(env.port.calls) == calls


def test_invalid_checkpoint_cannot_replace_authoritative_state(workflow):
    with workflow([plan(), assess()]) as env:
        state = env.start()
        missing = BlobRef(sha256="f" * 64, byte_length=1, media_type="application/json")
        with pytest.raises((ValueError, FileNotFoundError)):
            env.runner.resume(
                command_context(env.context.actor), state.run_id, missing, capability=env.capability
            )


def test_blocked_report_verification_cannot_reach_review(workflow):
    with workflow([plan(), assess()], verified="BLOCKED") as env:
        state = env.drive(env.start())
        assert state.status == "BLOCKED_OUTPUT"
        assert state.review_outcome == "NOT_REQUESTED"


def test_scripted_port_requires_explicit_test_mode(tmp_path):
    for settings in (Settings(data_root=tmp_path), Settings(data_root=tmp_path, mode="test")):
        with pytest.raises(ValueError, match="test mode"):
            ScriptedWorkflowPort(settings, None, [])


def test_runner_rejects_scripted_execution_outside_explicit_test_mode(workflow):
    with workflow([]) as env:
        env.settings = env.settings.model_copy(
            update={"mode": "runtime", "enable_test_adapters": False}
        )
        env.restart()
        with pytest.raises(ValueError):
            env.start()
        assert not env.port.calls and not env.preflight.calls


def test_runner_rejects_unavailable_model_backed_execution(workflow):
    with workflow([]) as env:
        env.spec = env.spec.model_copy(update={"execution_kind": "MODEL_BACKED"})
        with pytest.raises(ValueError):
            env.start()
        assert not env.port.calls


def test_unapproved_case_input_cannot_start(workflow):
    with workflow([]) as env:
        draft = env.cases.snapshots.catalog.get_snapshot("snapshot:case_initial")
        env.spec = env.spec.model_copy(
            update={
                "case_snapshot": SnapshotRef(
                    snapshot_id=draft.snapshot_id, membership_digest=draft.membership_digest
                )
            }
        )
        with pytest.raises(ValueError):
            env.start()
        assert not env.port.calls and not env.preflight.calls


def test_audit_failure_prevents_external_dispatch(workflow):
    with workflow([plan(), assess()]) as env:
        state = env.start()
        env.cases.kernel.connection.execute(
            """CREATE TRIGGER fail_workflow BEFORE INSERT ON audit_events
               WHEN NEW.event_json LIKE '%graph.%'
               BEGIN SELECT RAISE(ABORT,'simulated graph audit failure'); END"""
        )
        with pytest.raises((sqlite3.Error, OSError)):
            env.advance(state)
        assert not env.port.calls and not env.preflight.calls and not env.lookup.calls


def test_old_checkpoint_cannot_roll_authoritative_state_back(workflow):
    with workflow([plan(), assess()]) as env:
        state = env.advance(env.start())
        old_checkpoint = state.last_checkpoint_ref
        assert old_checkpoint is not None
        advanced = env.advance(state)
        with pytest.raises(ValueError):
            env.runner.resume(
                command_context(env.context.actor),
                state.run_id,
                old_checkpoint,
                capability=env.capability,
            )
        resumed = env.runner.resume(
            command_context(env.context.actor),
            state.run_id,
            advanced.last_checkpoint_ref,
            capability=env.capability,
        )
        assert resumed.version >= advanced.version
        assert resumed.status == advanced.status
        assert resumed.budget == advanced.budget
        assert resumed.pending_finding_ids == advanced.pending_finding_ids
        assert not env.port.calls


def test_restart_reuses_reserved_budget_when_external_intent_was_not_written(workflow):
    with workflow([plan(), assess()]) as env:
        state = env.drive(env.start(), until={"INVESTIGATING"})
        env.cases.kernel.connection.execute(
            """CREATE TRIGGER fail_model_intent BEFORE INSERT ON operation_intents
               WHEN NEW.intent_json LIKE '%graph.model.plan%'
               BEGIN SELECT RAISE(ABORT,'crash after reservation before provider intent'); END"""
        )
        with pytest.raises(sqlite3.Error):
            env.advance(state)
        assert not env.port.calls and not env.lookup.calls
        env.cases.kernel.connection.execute("DROP TRIGGER fail_model_intent")
        env.restart()
        restored = env.runner.resume(
            command_context(env.context.actor), state.run_id, None, capability=env.capability
        )
        final = env.drive(restored)
        assert final.status == "AWAITING_REVIEW"
        assert final.budget.model_calls == 2
        assert final.budget.tool_calls == 1
        assert len(env.lookup.calls) == 1


def test_crash_with_unknown_assessment_intent_never_repeats_committed_tool(workflow, monkeypatch):
    with workflow([plan(), assess()]) as env:
        state = env.drive(env.start(), until={"INVESTIGATING"})
        original = env.port.invoke

        def interrupt(context, request):
            payload = json.loads(env.cases.kernel.blob_store.get(request.exact_request_blob))
            if payload["phase"] == "ASSESS":
                raise KeyboardInterrupt("process interrupted after provider intent")
            return original(context, request)

        monkeypatch.setattr(env.port, "invoke", interrupt)
        with pytest.raises(KeyboardInterrupt):
            env.advance(state)
        assert len(env.lookup.calls) == len(env.port.calls) == 1

        monkeypatch.setattr(env.port, "invoke", original)
        env.restart()
        restored = env.runner.resume(
            command_context(env.context.actor), state.run_id, None, capability=env.capability
        )
        final = env.drive(restored)
        assert final.status == "FAILED"
        assert final.stop_reason == "PROVIDER_FAILURE"
        assert len(env.lookup.calls) == len(env.port.calls) == 1


@pytest.mark.parametrize("verdict", ["WEAK", "UNKNOWN", "REFUTES", "NO_PROGRESS"])
def test_uncertain_or_adverse_assessment_cannot_resolve_a_finding(workflow, verdict):
    invalid = assess().output | {
        "verdict": verdict,
        "weak_result_or_mistake": "Evidence remains uncertain",
    }
    with workflow([plan(), ScriptedStep("ASSESS", invalid)]) as env:
        state = env.drive(env.start())
        assert state.status in {"FAILED", "BLOCKED_OUTPUT"}
        assert not state.resolved_finding_ids


def test_reported_model_usage_is_tracked_separately_from_reservations(workflow):
    steps = [
        replace(plan(), usage={"total_tokens": 12}),
        replace(assess(), usage={"total_tokens": 19}),
    ]
    with workflow(steps) as env:
        state = env.drive(env.start())
        assert state.status == "AWAITING_REVIEW"
        assert state.budget.observed_tokens == 31
        assert state.budget.reserved_tokens == 2 * env.spec.budgets.tokens_per_model_call
        assert state.budget.observed_cost_usd is None


def test_unknown_usage_is_not_reported_as_zero_tokens_or_free(workflow):
    with workflow([plan(), assess()]) as env:
        state = env.drive(env.start())
        assert state.budget.observed_tokens is None
        assert state.budget.observed_cost_usd is None


def test_provider_return_after_wall_deadline_cannot_dispatch_a_tool(workflow, monkeypatch):
    with workflow([plan(), assess()]) as env:
        original = env.port.invoke

        def delayed(context, request):
            result = original(context, request)
            env.clock.now += timedelta(seconds=301)
            return result

        monkeypatch.setattr(env.port, "invoke", delayed)
        state = env.drive(env.start())
        assert state.stop_reason == "BUDGET_EXHAUSTED"
        assert not env.lookup.calls


def test_restart_after_committed_calls_before_turn_commit_replays_no_external_actions(workflow):
    with workflow([plan(), assess()]) as env:
        state = env.drive(env.start(), until={"INVESTIGATING"})
        env.cases.kernel.connection.execute(
            """CREATE TRIGGER fail_turn_commit BEFORE INSERT ON audit_events
               WHEN NEW.event_json LIKE '%graph.turn.result%'
               BEGIN SELECT RAISE(ABORT,'crash after calls before turn commit'); END"""
        )
        with pytest.raises(sqlite3.Error):
            env.advance(state)
        assert len(env.port.calls) == 2 and len(env.lookup.calls) == 1
        env.cases.kernel.connection.execute("DROP TRIGGER fail_turn_commit")
        env.clock.now += timedelta(seconds=1)
        env.restart()
        restored = env.runner.resume(
            command_context(env.context.actor), state.run_id, None, capability=env.capability
        )
        final = env.drive(restored)
        assert final.status == "AWAITING_REVIEW"
        assert final.resolved_finding_ids == ["finding:one"]
        assert len(env.port.calls) == 2 and len(env.lookup.calls) == 1


def test_provider_usage_above_reserved_allowance_stops_before_tool_dispatch(workflow):
    with workflow([replace(plan(), usage={"total_tokens": 2049})]) as env:
        state = env.drive(env.start())
        assert state.status == "FAILED"
        assert state.stop_reason == "BUDGET_EXHAUSTED"
        assert state.budget.observed_tokens == 2049
        assert not env.lookup.calls


def test_reserved_operation_expired_during_restart_is_not_dispatched(workflow):
    with workflow([plan(), assess()]) as env:
        state = env.drive(env.start(), until={"INVESTIGATING"})
        env.cases.kernel.connection.execute(
            """CREATE TRIGGER fail_expiring_intent BEFORE INSERT ON operation_intents
               WHEN NEW.intent_json LIKE '%graph.model.plan%'
               BEGIN SELECT RAISE(ABORT,'crash after reservation before provider intent'); END"""
        )
        with pytest.raises(sqlite3.Error):
            env.advance(state)
        env.cases.kernel.connection.execute("DROP TRIGGER fail_expiring_intent")
        env.clock.now += timedelta(seconds=301)
        env.restart()
        restored = env.runner.resume(
            command_context(env.context.actor), state.run_id, None, capability=env.capability
        )
        final = env.drive(restored)
        assert final.stop_reason == "BUDGET_EXHAUSTED"
        assert not env.port.calls and not env.lookup.calls
