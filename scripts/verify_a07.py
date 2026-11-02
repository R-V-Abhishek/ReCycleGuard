"""Fresh-root offline CP3 real services with explicit scripted C10 and fixture review."""

import json
import os
import secrets
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer
from typer.testing import CliRunner
from verify_cp2 import require, save, snapshot_ref
from verify_cp2 import run as bootstrap

from recycleguard.application import local_application
from recycleguard.cli import app
from recycleguard.config import Settings
from recycleguard.contracts.workflow import ActionDraft, AssessmentProposal, PlanDraft, PlanProposal
from recycleguard.investigation import InvestigationRequest, InvestigationService, ScriptedExchange
from recycleguard.local_session import initialize_reviewer

DISCLAIMER = (
    "REAL C07/C08/C12/C13 SERVICES WITH SCRIPTED C10 ONLY. Synthetic fixture review "
    "does not establish team acknowledgement, checkpoint acceptance, model quality "
    "or legal validity."
)


def exchanges():
    plan = PlanDraft(
        objective="Inspect frozen evidence and qualify unresolved claims",
        hypotheses=["A broad query may lack direct support"],
        proposed_checks=["Retrieve a provision", "Reconcile the frozen case"],
        expected_evidence=["Exact source locators and deterministic values"],
        stopping_criteria=["Abstain when authority or applicability is unresolved"],
    )
    steps = []
    for operation, arguments, kind, verdict, disposition in (
        ("search_rules", {"query": "unmatched_phrase_7632"}, "CHECK", "WEAK", "CONTINUE"),
        ("search_rules", {"query": "producer"}, "REFORMULATE", "WEAK", "CONTINUE"),
        ("compute_reconciliation", {"bucket_ids": []}, "CHECK", "UNKNOWN", "ABSTAIN"),
    ):
        proposal = PlanProposal(
            plan=plan,
            action=ActionDraft(
                action_kind=kind,
                allowed_operation=operation,
                typed_arguments=arguments,
                finding_id="finding:a07_demo",
                concise_reason="Scripted bounded evidence inspection",
                evidence_refs=[],
            ),
            stop_reason=None,
        )
        assessment = AssessmentProposal(
            verdict=verdict,
            disposition=disposition,
            weak_result_or_mistake="Evidence does not establish complete temporal applicability",
            next_check_or_stop="Revise query" if disposition == "CONTINUE" else "Retain abstention",
            revised_plan=plan if operation == "search_rules" and kind == "CHECK" else None,
        )
        steps.extend(
            [
                ScriptedExchange(phase="PLAN", response=proposal.model_dump(mode="json")),
                ScriptedExchange(phase="ASSESS", response=assessment.model_dump(mode="json")),
            ]
        )
    return steps


def run(
    data_root: Annotated[Path, typer.Option(help="New data root; must not exist.")],
    output: Annotated[Path, typer.Option(help="New output directory; must not exist.")],
):
    data_root, output = data_root.resolve(), output.resolve()
    bootstrap(data_root=data_root, output=output)
    settings = Settings(data_root=data_root, mode="test", enable_test_adapters=True)
    environment = {
        "RECYCLEGUARD_DATA_ROOT": str(data_root),
        "RECYCLEGUARD_MODE": "test",
        "RECYCLEGUARD_ENABLE_TEST_ADAPTERS": "true",
    }
    # Clear inherited runtime roots from shell configuration; every invocation is explicit.
    environment.update(
        {
            key: value
            for key, value in os.environ.items()
            if key.startswith("RECYCLEGUARD_") and key not in environment
        }
    )
    cli, transcript = CliRunner(), []

    def invoke(arguments, *, password=None):
        result = cli.invoke(
            app, arguments, env=environment, input=None if password is None else password + "\n"
        )
        transcript.append(f"$ recycleguard {' '.join(arguments)}\nexit={result.exit_code}")
        require(result.exit_code == 0, f"CLI {arguments[0:2]} failed: {result.output}")
        # Password prompts go to stderr; result.stdout contains the exact JSON response.
        return json.loads(result.stdout.strip())

    with local_application(settings) as (cases, _, _):
        case = cases.snapshots.catalog.get_snapshot("snapshot:cp2_demo_support_approved")
        corpus = cases.snapshots.catalog.get_snapshot("snapshot:cp2_demo_corpus_approved")
        request = InvestigationRequest(
            run_id="run:a07_integrated_demo",
            case_snapshot=snapshot_ref(case),
            corpus_snapshot=snapshot_ref(corpus),
            finding_ids=["finding:a07_demo"],
            scripted_exchanges=exchanges(),
        )
    request_path = output / "investigation-request.json"
    save(request_path, request.model_dump(mode="json"))
    created = invoke(["investigation", "start", str(request_path)])
    save(output / "a07-created.json", created)
    require(created["status"] == "CREATED", "run did not start at CREATED")
    state = invoke(["investigation", "run", request.run_id])
    save(output / "a07-awaiting-review.json", state)
    require(state["status"] == "AWAITING_REVIEW", f"unexpected graph stop: {state['status']}")
    require(state["abstained_finding_ids"] == request.finding_ids, "unresolved claim was resolved")
    require(
        state["budget"]["tool_calls"] == 3 and state["budget"]["model_calls"] == 6,
        "actual tool/model reservation counts differ",
    )
    require(
        state["budget"]["finding_reformulations"] == {"finding:a07_demo": 1},
        "adaptive reformulation was not retained",
    )
    report = invoke(["investigation", "report", request.run_id])
    save(output / "a07-report.json", report)
    require(report["verification"]["verdict"] == "QUALIFIED", "report lost qualifications")
    bucket = report["report"]["calculations"][0]["bucket_results"][0]
    require(
        {key: Decimal(bucket[key]["decimal"]) for key in ("required", "supported", "pending")}
        == {"required": 100, "supported": 55, "pending": 25},
        "100/55/25 supported arithmetic changed",
    )
    (output / "a07-working-paper.md").write_text(
        report["report"]["rendered_markdown"], encoding="utf-8"
    )
    packet = invoke(["investigation", "packet", request.run_id])
    require(
        invoke(["investigation", "packet", request.run_id]) == packet,
        "repeated packet lookup was not idempotent",
    )
    save(output / "a07-review-packet.json", packet)
    password = secrets.token_urlsafe(32)
    initialize_reviewer(data_root, "human:synthetic_cp3_reviewer", password)
    try:
        reviewed = invoke(
            [
                "investigation",
                "review",
                packet["packet_id"],
                "--decision",
                "APPROVE",
                "--reason",
                "Synthetic fixture working paper accepted with qualifications",
            ],
            password=password,
        )
        require(
            reviewed["status"] == "COMPLETED" and reviewed["review_outcome"] == "APPROVED",
            "authenticated fixture approval did not complete workflow",
        )
        require(
            invoke(["investigation", "status", request.run_id]) == reviewed,
            "review transition did not survive a separate CLI invocation",
        )
        save(output / "a07-reviewed-state.json", reviewed)
    finally:
        (data_root / "reviewer.json").unlink(missing_ok=True)
    with local_application(settings) as (cases, _, cap):
        service = InvestigationService(cases, settings, capability=cap)
        events = cases.kernel.list_stream_events(f"stream:{request.run_id}")
        turns = service.store.list_turns(request.run_id)
        retrieval_ids = [ref for turn in turns for ref in turn.retrieval_attempt_ids]
        calculation_ids = [ref for turn in turns for ref in turn.calculation_ids]
        require(len(retrieval_ids) == 2 and bool(calculation_ids), "turn service lineage missing")
        require(any(turn.plan_revised for turn in turns), "no visible plan revision")
        for event in events:
            for blob in [event.payload_blob, *event.input_refs, *event.output_refs]:
                cases.kernel.blob_store.get(blob)
        save(output / "a07-turns.json", [turn.model_dump(mode="json") for turn in turns])
        save(output / "a07-audit.json", [event.model_dump(mode="json") for event in events])
        save(
            output / "a07-summary.json",
            {
                "disclaimer": DISCLAIMER,
                "execution_kind": "SCRIPTED_TEST",
                "model_quality_evaluated": False,
                "fixture_review_only": True,
                "state": reviewed["status"],
                "review_outcome": reviewed["review_outcome"],
                "tool_calls": state["budget"]["tool_calls"],
                "model_calls": state["budget"]["model_calls"],
                "observed_tokens": state["budget"]["observed_tokens"],
                "reformulations": state["budget"]["finding_reformulations"],
                "turn_count": len(turns),
                "retrieval_attempt_ids": retrieval_ids,
                "calculation_ids": sorted(set(calculation_ids)),
                "audit_event_count": len(events),
                "verification": report["verification"]["verdict"],
                "code_revision": service.store.spec(request.run_id).code_revision,
                "dependency_lock_digest": service.store.spec(request.run_id).dependency_lock_digest,
            },
        )
    (output / "a07-transcript.txt").write_text("\n".join(transcript), encoding="utf-8")
    typer.echo(f"Verified real-service scripted CP3 run: {output / 'a07-summary.json'}")


if __name__ == "__main__":
    typer.run(run)
