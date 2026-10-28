"""Actual local inference over synthetic evidence; compatibility smoke, not a benchmark."""

import hashlib
import json
import time
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer
from verify_cp2 import request_for, require, save
from verify_cp2 import run as bootstrap

from recycleguard.application import command_context, local_application
from recycleguard.baseline import BaselineOutput, BaselineService
from recycleguard.config import Settings
from recycleguard.contracts.artifacts import ProfileRef, SnapshotRef
from recycleguard.contracts.core import BlobRef, BoundaryModel, EvidenceRef, ServiceResult
from recycleguard.contracts.workflow import BudgetLimits, ConfigurationPin, RunSpec, StageOutcome
from recycleguard.local_model import LocalModelConfig, LocalModelPort
from recycleguard.model_port import ModelCallResult
from recycleguard.reporting import ReportVerifier
from recycleguard.storage import canonical_json_bytes
from recycleguard.workflow import ToolBinding, WorkflowRunner, WorkflowStages

DISCLAIMER = (
    "ACTUAL LOCAL MODEL ON SYNTHETIC INPUTS. This is a C09/C10 compatibility smoke, "
    "not held-out quality evaluation, MG1 approval, CP3 approval or completed A07 wiring. "
    "Arithmetic, report drafting and report verification remain deterministic. "
    "Human review remains required; temporal applicability and deadline qualifications remain."
)


class Calculate(BoundaryModel):
    """Compute exact balances from the approved case. No caller-supplied quantities or arguments."""


def pin(name):
    return ConfigurationPin(
        configuration_id=f"configuration:u01_smoke_{name}",
        digest=hashlib.sha256(f"local-model-smoke:{name}".encode()).hexdigest(),
    )


def child_context(context):
    key = f"{context.operation_id}:deterministic_baseline"
    return context.model_copy(
        update={
            "command_id": f"command:{key}",
            "operation_id": f"operation:{key}",
            "attempt_id": f"attempt:{context.attempt_id}:deterministic_baseline",
            "idempotency_key": key,
            "parent_operation_id": context.operation_id,
        }
    )


def run(
    config: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    data_root: Annotated[Path, typer.Option(help="Fresh synthetic evidence root; must not exist.")],
    output: Annotated[Path, typer.Option(help="Fresh smoke output directory.")],
):
    model_config = LocalModelConfig.model_validate_json(config.read_bytes())
    require(
        model_config.max_total_tokens >= 32768,
        "smoke config must permit the explicitly reserved 32768 tokens per call",
    )
    data_root, output = data_root.resolve(), output.resolve()
    bootstrap(data_root=data_root, output=output)
    settings = Settings(data_root=data_root)
    started = time.perf_counter()
    root = Path(__file__).resolve().parents[1]
    source_manifest = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [
            Path(__file__).resolve(),
            root / "src/recycleguard/local_model.py",
            root / "src/recycleguard/workflow/runner.py",
            root / "src/recycleguard/workflow/store.py",
        ]
    }
    save(output / "local-source-digests.json", source_manifest)
    save(output / "local-model-config.json", model_config.model_dump(mode="json"))
    with local_application(settings) as (cases, context, capability):
        blobs = cases.kernel.blob_store
        snapshot = cases.snapshots.catalog.get_snapshot("snapshot:cp2_demo_support_approved")
        corpus = cases.snapshots.catalog.get_snapshot("snapshot:cp2_demo_corpus_approved")
        membership = json.loads(blobs.get(snapshot.membership_blob))
        spec = RunSpec(
            run_id="run:u01_real_local_synthetic_smoke",
            case_snapshot=SnapshotRef(
                snapshot_id=snapshot.snapshot_id, membership_digest=snapshot.membership_digest
            ),
            corpus_snapshot=SnapshotRef(
                snapshot_id=corpus.snapshot_id, membership_digest=corpus.membership_digest
            ),
            profile=ProfileRef.model_validate(membership["profile"]),
            index=pin("no_retrieval_index"),
            code_revision="source-sha256:"
            + hashlib.sha256(canonical_json_bytes(source_manifest)).hexdigest(),
            dependency_lock_digest=hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest(),
            adapters=pin("actual_local_mlx"),
            tools=pin("deterministic_reconciliation"),
            prompt=model_config.prompt_pin(),
            model=model_config.pin(),
            retrieval_policy=pin("not_exercised"),
            audit_policy=pin("application_ledger"),
            security_policy=pin("local_read_only_tools"),
            execution_kind="MODEL_BACKED",
            experiment_variant="REAL_LOCAL_MODEL_ON_SYNTHETIC_INPUTS_NOT_BENCHMARK",
            finding_ids=["finding:check_supported_allocation_gap"],
            budgets=BudgetLimits(
                max_model_calls=8,
                tokens_per_model_call=32768,
                max_total_tokens=262144,
                max_wall_seconds=600,
            ),
        )
        actual_tools, outputs = [], []

        def stage_result(ctx, disposition, decision, *, blob=None, refs=()):
            return ServiceResult[StageOutcome](
                contract_version="1.1",
                operation_id=ctx.operation_id,
                attempt_id=ctx.attempt_id,
                status="SUCCESS",
                output=StageOutcome(
                    disposition=disposition,
                    evidence_refs=list(refs),
                    output_blob=blob,
                    concise_decision=decision,
                ),
                output_blob=None,
                issues=[],
                dependencies=[],
                audit_event_ids=[],
            )

        def preflight(ctx, pinned):
            cases.snapshots.get(pinned.case_snapshot)
            cases.snapshots.get(pinned.corpus_snapshot)
            cases.profiles.get(pinned.profile, require_approved=True)
            return stage_result(ctx, "QUALIFIED", DISCLAIMER)

        def calculate(ctx, arguments):
            before = time.perf_counter()
            calculated = BaselineService(cases).run(
                child_context(ctx), request_for(cases, snapshot), capability=capability
            )
            require(
                calculated.output is not None and calculated.status in {"SUCCESS", "PARTIAL"},
                f"actual deterministic calculation failed: {calculated.status}",
            )
            actual = calculated.output
            outputs.append(actual)
            evidence = [
                EvidenceRef(
                    ref_kind="CALCULATION",
                    ref_id=actual.calculation.calculation_id,
                    artifact_revision_id=None,
                    locator=None,
                )
            ]
            decision = {
                "source_snapshot": snapshot.snapshot_id,
                "calculation_id": actual.calculation.calculation_id,
                "coverage": actual.calculation.coverage,
                "buckets": [
                    bucket.model_dump(mode="json") for bucket in actual.calculation.bucket_results
                ],
                "qualifications": [issue.message for issue in calculated.issues],
                "scope": "Investigate allocation gap; no legal conclusion or automatic approval.",
            }
            actual_tools.append(
                {
                    "operation_id": ctx.operation_id,
                    "child_operation_id": calculated.operation_id,
                    "elapsed_seconds": time.perf_counter() - before,
                    "envelope": calculated.model_dump(mode="json"),
                }
            )
            return ServiceResult[StageOutcome](
                contract_version="1.1",
                operation_id=ctx.operation_id,
                attempt_id=ctx.attempt_id,
                status=calculated.status,
                output=StageOutcome(
                    disposition="QUALIFIED",
                    evidence_refs=evidence,
                    output_blob=calculated.output_blob,
                    concise_decision=json.dumps(decision),
                ),
                output_blob=None,
                issues=calculated.issues,
                dependencies=calculated.dependencies,
                audit_event_ids=calculated.audit_event_ids,
            )

        def draft(ctx, pinned):
            if not outputs:
                return stage_result(ctx, "BLOCKED", "No actual deterministic tool result exists.")
            report = outputs[-1].report
            return stage_result(
                ctx,
                "QUALIFIED",
                "Deterministic qualified baseline report; human review pending.",
                blob=blobs.put(report.model_dump_json().encode(), "application/json"),
            )

        def verify(ctx, pinned):
            if not outputs:
                return stage_result(
                    ctx, "BLOCKED", "No authoritative calculation for report verification."
                )
            actual = BaselineOutput.model_validate_json(outputs[-1].model_dump_json())
            checked = ReportVerifier().verify(
                actual.report, authoritative_calculations=[actual.calculation]
            )
            disposition = "BLOCKED" if checked.verdict == "BLOCKED" else "QUALIFIED"
            return stage_result(
                ctx,
                disposition,
                f"Deterministic verifier: {checked.verdict}. {DISCLAIMER}",
                blob=blobs.put(checked.model_dump_json().encode(), "application/json"),
            )

        port = LocalModelPort(model_config, blobs)
        runner = WorkflowRunner(
            cases,
            settings,
            model_port=port,
            tools={"compute_reconciliation": ToolBinding(Calculate, calculate)},
            stages=WorkflowStages(preflight, draft, verify),
            checkpoint_path=data_root / "local-model-workflow-cache.sqlite",
            model_run_validator=port.assert_run,
        )
        try:
            state = runner.start_run(context, spec, capability=capability)
            transitions = [state.model_dump(mode="json")]
            for _ in range(24):
                if state.status in {
                    "AWAITING_REVIEW",
                    "COMPLETED",
                    "FAILED",
                    "BLOCKED_INPUT",
                    "BLOCKED_OUTPUT",
                    "CANCELLED",
                }:
                    break
                state = runner.advance(
                    command_context(context.actor),
                    state.run_id,
                    state.version,
                    capability=capability,
                )
                transitions.append(state.model_dump(mode="json"))
            events = cases.kernel.list_stream_events(f"stream:{spec.run_id}")
            model_calls = []
            for event in events:
                if event.event_type.startswith("graph.model.") and event.event_type.endswith(
                    ".result"
                ):
                    call = json.loads(blobs.get(event.payload_blob))
                    trace = None
                    if call["model_output"] is not None:
                        raw = ServiceResult[ModelCallResult].model_validate_json(
                            blobs.get(BlobRef.model_validate(call["raw_result_blob"]))
                        )
                        if raw.output_blob is not None:
                            trace = json.loads(blobs.get(raw.output_blob))
                    model_calls.append(
                        {
                            "operation_id": event.operation_id,
                            "status": call["status"],
                            "output": call["model_output"],
                            "raw_result_blob": call["raw_result_blob"],
                            "issues": call["issues"],
                            "provider_trace": trace,
                        }
                    )
            save(output / "local-run-spec.json", spec.model_dump(mode="json"))
            save(output / "local-state.json", state.model_dump(mode="json"))
            save(output / "local-transitions.json", transitions)
            save(
                output / "local-turns.json",
                [turn.model_dump(mode="json") for turn in runner.store.list_turns(spec.run_id)],
            )
            save(output / "local-audit.json", [event.model_dump(mode="json") for event in events])
            save(output / "local-model-calls.json", model_calls)
            save(output / "local-actual-tools.json", actual_tools)
            child_events = []
            for identifier in sorted(
                {
                    identifier
                    for tool in actual_tools
                    for identifier in tool["envelope"]["audit_event_ids"]
                }
            ):
                event = cases.kernel.get_event(identifier)
                require(event is not None, "actual deterministic tool audit event is missing")
                child_events.append(event.model_dump(mode="json"))
            save(output / "local-tool-audit.json", child_events)
            summary = {
                "disclaimer": DISCLAIMER,
                "execution_kind": spec.execution_kind,
                "state": state.status,
                "stop_reason": state.stop_reason,
                "review_outcome": state.review_outcome,
                "budget": state.budget.model_dump(mode="json"),
                "actual_tool_calls": len(actual_tools),
                "plan_count": len(state.plan_refs),
                "assessment_count": len(state.assessment_refs),
                "model_id": model_config.model_id,
                "model_revision": model_config.model_revision,
                "runtime_version": model_config.runtime_version,
                "prompt_pin": spec.prompt.model_dump(mode="json"),
                "weights_manifest_digest": model_config.weights_manifest_digest,
                "local_runtime_lock_digest": model_config.runtime_lock_digest,
                "elapsed_workflow_seconds": time.perf_counter() - started,
                "benchmark_quality_measured": False,
                "MG1_approved": False,
                "CP3_approved": False,
            }
            if outputs:
                bucket = outputs[-1].calculation.bucket_results[0]
                summary["actual_quantities"] = {
                    field: bucket.model_dump(mode="json")[field]
                    for field in ("required", "supported", "signed_gap", "pending")
                }
                require(
                    tuple(
                        Decimal(value.decimal)
                        for value in (
                            bucket.required,
                            bucket.supported,
                            bucket.signed_gap,
                            bucket.pending,
                        )
                    )
                    == (100, 55, 45, 25),
                    "actual deterministic fixture quantities changed",
                )
                (output / "local-working-paper.md").write_text(
                    outputs[-1].report.rendered_markdown, encoding="utf-8"
                )
            save(output / "local-summary.json", summary)
            require(
                state.status == "AWAITING_REVIEW"
                and state.review_outcome == "PENDING"
                and bool(actual_tools)
                and bool(state.plan_refs)
                and bool(state.assessment_refs),
                f"local model compatibility smoke did not complete: {state.status}; "
                "inspect saved trace",
            )
        finally:
            runner.close()
    typer.echo(
        f"Actual local-model synthetic compatibility smoke passed: {output / 'local-summary.json'}"
    )


if __name__ == "__main__":
    typer.run(run)
