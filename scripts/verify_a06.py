"""Reproduce an explicitly scripted A06 graph over actual approved synthetic inputs.

This standalone script bootstraps fresh evidence through verify_cp2, then exercises
the graph boundary. It does not select a provider or measure actual model quality.
"""

import hashlib
import json
from collections import deque
from pathlib import Path
from typing import Annotated

import typer
from verify_cp2 import require, save
from verify_cp2 import run as bootstrap

from recycleguard.application import command_context, local_application
from recycleguard.config import Settings
from recycleguard.contracts.artifacts import ProfileRef, SnapshotRef
from recycleguard.contracts.core import BoundaryModel, EvidenceRef, ServiceResult
from recycleguard.contracts.workflow import (
    ActionDraft,
    AssessmentProposal,
    BudgetLimits,
    ConfigurationPin,
    PlanDraft,
    PlanProposal,
    RunSpec,
    StageOutcome,
)
from recycleguard.model_port import ModelCallResult
from recycleguard.storage import canonical_json_bytes
from recycleguard.workflow import ToolBinding, WorkflowRunner, WorkflowStages

DISCLAIMER = (
    "SCRIPTED SYNTHETIC A06 DEMONSTRATION ONLY. No actual model, retrieval-quality "
    "evaluation, team checkpoint approval or legal conclusion is asserted. "
    "Tool observations and stage decisions are scripted; production integration is A07."
)


class Query(BoundaryModel):
    query: str


def pin(name: str) -> ConfigurationPin:
    return ConfigurationPin(
        configuration_id=f"configuration:a06_demo_{name}",
        digest=hashlib.sha256(f"scripted-demo:{name}".encode()).hexdigest(),
    )


def source_revision() -> str:
    root = Path(__file__).resolve().parents[1]
    paths = sorted((root / "src/recycleguard").rglob("*.py")) + [Path(__file__).resolve()]
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode())
        # Git can check out CRLF on Windows; this pin describes source text.
        digest.update(path.read_text(encoding="utf-8").encode())
    return f"source-sha256:{digest.hexdigest()}"


def plan(exact=False):
    return PlanDraft(
        objective="Inspect an exact clause locator" if exact else "Investigate weak evidence",
        hypotheses=["A broad query may lack exact source support"],
        proposed_checks=["Inspect the frozen synthetic evidence"],
        expected_evidence=["Exact locator support"],
        stopping_criteria=["Resolve within the scripted scope or abstain"],
    )


class ScriptedPort:
    def __init__(self, settings, blobs):
        require(
            settings.mode == "test" and settings.enable_test_adapters,
            "scripted port requires explicit test mode",
        )
        self.blobs, self.exchanges = blobs, []
        self.steps = deque()
        for exact in (False, True):
            self.steps.append(
                (
                    "PLAN",
                    PlanProposal(
                        plan=plan(exact),
                        action=ActionDraft(
                            action_kind="REFORMULATE" if exact else "CHECK",
                            allowed_operation="search_rules",
                            typed_arguments={
                                "query": "exact clause locator" if exact else "allocation"
                            },
                            finding_id="finding:a06_demo",
                            concise_reason="Scripted locator investigation",
                            evidence_refs=[],
                        ),
                        stop_reason=None,
                    ),
                )
            )
            self.steps.append(
                (
                    "ASSESS",
                    AssessmentProposal(
                        verdict="SUPPORTS" if exact else "WEAK",
                        weak_result_or_mistake=None
                        if exact
                        else "Broad query returned weak locator support",
                        next_check_or_stop="Resolve scripted finding"
                        if exact
                        else "Reformulate locator query",
                        disposition="RESOLVE" if exact else "CONTINUE",
                        revised_plan=None if exact else plan(True),
                    ),
                )
            )

    def invoke(self, context, request):
        require(bool(self.steps), "script exhausted; no provider fallback exists")
        phase, proposal = self.steps.popleft()
        exact_request = json.loads(self.blobs.get(request.exact_request_blob))
        require(exact_request["phase"] == phase, "scripted model phase mismatch")
        response = proposal.model_dump(mode="json")
        response_blob = self.blobs.put(canonical_json_bytes(response), "application/json")
        self.exchanges.append(
            {
                "context": context.model_dump(mode="json"),
                "request": exact_request,
                "response": response,
            }
        )
        return ServiceResult[ModelCallResult](
            contract_version="1.1",
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status="SUCCESS",
            output=ModelCallResult(
                model_call_id=f"model_call:a06_scripted_{len(self.exchanges)}",
                provider_request_ref=None,
                exact_response_blob=response_blob,
                validated_output_or_null=response,
                validation_issues=[],
                usage=None,
                timing={},
                outcome="SUCCESS",
            ),
            output_blob=None,
            issues=[],
            dependencies=[],
            audit_event_ids=[],
        )


def run(
    data_root: Annotated[Path, typer.Option(help="New synthetic evidence root; must not exist.")],
    output: Annotated[Path, typer.Option(help="New verification output directory.")],
):
    data_root, output = data_root.resolve(), output.resolve()
    bootstrap(data_root=data_root, output=output)
    settings = Settings(data_root=data_root, mode="test", enable_test_adapters=True)
    with local_application(settings) as (cases, context, capability):
        snapshot = cases.snapshots.catalog.get_snapshot("snapshot:cp2_demo_support_approved")
        corpus = cases.snapshots.catalog.get_snapshot("snapshot:cp2_demo_corpus_approved")
        membership = json.loads(cases.kernel.blob_store.get(snapshot.membership_blob))
        spec = RunSpec(
            run_id="run:a06_scripted_demo",
            case_snapshot=SnapshotRef(
                snapshot_id=snapshot.snapshot_id, membership_digest=snapshot.membership_digest
            ),
            corpus_snapshot=SnapshotRef(
                snapshot_id=corpus.snapshot_id, membership_digest=corpus.membership_digest
            ),
            profile=ProfileRef.model_validate(membership["profile"]),
            index=pin("index"),
            code_revision=source_revision(),
            dependency_lock_digest=hashlib.sha256(
                (Path(__file__).resolve().parents[1] / "uv.lock").read_bytes()
            ).hexdigest(),
            adapters=pin("adapters"),
            tools=pin("tools"),
            prompt=pin("prompt"),
            model=pin("model"),
            retrieval_policy=pin("retrieval"),
            audit_policy=pin("audit"),
            security_policy=pin("security"),
            execution_kind="SCRIPTED_TEST",
            experiment_variant="SCRIPTED_DEMO_ONLY",
            finding_ids=["finding:a06_demo"],
            budgets=BudgetLimits(),
        )
        port = ScriptedPort(settings, cases.kernel.blob_store)
        calls = []

        def result(ctx, decision):
            return ServiceResult[StageOutcome](
                contract_version="1.1",
                operation_id=ctx.operation_id,
                attempt_id=ctx.attempt_id,
                status="SUCCESS",
                output=StageOutcome(
                    disposition="QUALIFIED",
                    evidence_refs=[
                        EvidenceRef(
                            ref_kind="ARTIFACT",
                            ref_id=snapshot.snapshot_id,
                            artifact_revision_id=None,
                            locator=None,
                        )
                    ],
                    output_blob=None,
                    concise_decision=decision,
                ),
                output_blob=None,
                issues=[],
                dependencies=[],
                audit_event_ids=[],
            )

        def stage(ctx, pinned_spec):
            cases.snapshots.get(pinned_spec.case_snapshot)
            cases.snapshots.get(pinned_spec.corpus_snapshot)
            cases.profiles.get(pinned_spec.profile, require_approved=True)
            return result(ctx, DISCLAIMER)

        def lookup(ctx, query):
            calls.append(query.query)
            return result(
                ctx,
                "Scripted exact locator support"
                if len(calls) == 2
                else "Scripted weak locator result",
            )

        runner = WorkflowRunner(
            cases,
            settings,
            model_port=port,
            tools={"search_rules": ToolBinding(Query, lookup)},
            stages=WorkflowStages(stage, stage, stage),
            checkpoint_path=data_root / "workflow-cache.sqlite",
        )
        try:
            state = runner.start_run(context, spec, capability=capability)
            transitions = [state.model_dump(mode="json")]
            for _ in range(20):
                if state.status == "AWAITING_REVIEW":
                    break
                require(
                    state.status not in {"FAILED", "BLOCKED_INPUT", "BLOCKED_OUTPUT", "CANCELLED"},
                    f"scripted workflow stopped unexpectedly: {state.status}",
                )
                state = runner.advance(
                    command_context(context.actor),
                    state.run_id,
                    state.version,
                    capability=capability,
                )
                transitions.append(state.model_dump(mode="json"))
            require(
                state.status == "AWAITING_REVIEW" and state.review_outcome == "PENDING",
                "scripted demo must pause for human review without approving itself",
            )
            require(
                state.resolved_finding_ids == ["finding:a06_demo"]
                and not state.pending_finding_ids,
                "scripted finding was not resolved within scope",
            )
            require(
                state.budget.model_calls == 4
                and state.budget.tool_calls == 2
                and state.budget.finding_reformulations == {"finding:a06_demo": 1},
                "bounded adaptive trace counters differ from scripted sequence",
            )
            require(
                state.budget.observed_tokens is None and state.budget.observed_cost_usd is None,
                "scripted execution cannot assert measured provider usage or cost",
            )
            events = cases.kernel.list_stream_events(f"stream:{spec.run_id}")
            turns = runner.store.list_turns(spec.run_id)
            save(output / "a06-run-spec.json", spec.model_dump(mode="json"))
            save(output / "a06-state.json", state.model_dump(mode="json"))
            save(output / "a06-transitions.json", transitions)
            save(output / "a06-turns.json", [turn.model_dump(mode="json") for turn in turns])
            save(output / "a06-audit.json", [event.model_dump(mode="json") for event in events])
            save(output / "a06-scripted-exchanges.json", port.exchanges)
            save(
                output / "a06-summary.json",
                {
                    "disclaimer": DISCLAIMER,
                    "execution_kind": spec.execution_kind,
                    "code_revision": spec.code_revision,
                    "dependency_lock_digest": spec.dependency_lock_digest,
                    "state": state.status,
                    "review_outcome": state.review_outcome,
                    "model_calls": state.budget.model_calls,
                    "tool_calls": state.budget.tool_calls,
                    "query_sequence": calls,
                    "reformulations": state.budget.finding_reformulations,
                    "observed_tokens": None,
                    "observed_cost_usd": None,
                    "turn_count": len(turns),
                    "audit_event_count": len(events),
                    "actual_model_evaluation": False,
                    "checkpoint_approved": False,
                },
            )
        finally:
            runner.close()
    typer.echo(f"Scripted-only A06 verification passed: {output / 'a06-summary.json'}")


if __name__ == "__main__":
    typer.run(run)
