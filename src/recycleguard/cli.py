"""Local CLI with read-only diagnostics and trusted C05 publication/review."""

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from recycleguard import __version__
from recycleguard.application import command_context, local_application, local_review_application
from recycleguard.baseline import BaselineService
from recycleguard.config import Settings
from recycleguard.contracts import PROTOCOL_VERSION, ActorRef, CommandContext, Quantity
from recycleguard.contracts.baseline import BaselineRequest, RecordSupportReview
from recycleguard.contracts.bundles import ReplayRequest
from recycleguard.contracts.foundation import FoundationApproval, FoundationRequest
from recycleguard.contracts.profiles import ProfilePublication, ProfileReview
from recycleguard.contracts.snapshots import CaseReopen, SnapshotPublication, SnapshotReview
from recycleguard.exports.service import ExportService
from recycleguard.foundation import FoundationService
from recycleguard.foundation_review import FoundationReviewer
from recycleguard.local_session import initialize_reviewer
from recycleguard.storage import canonical_json_bytes
from recycleguard.support_review import SupportReviewer

app = typer.Typer(no_args_is_help=True, help="ReCycleGuard local application scaffold.")


def version(value: bool):
    if value:
        typer.echo(f"recycleguard {__version__} (protocol {PROTOCOL_VERSION})")
        raise typer.Exit()


@app.callback()
def main(
    show_version: Annotated[
        bool, typer.Option("--version", callback=version, is_eager=True)
    ] = False,
):
    """Local evidence workflow with explicitly configured inference backends."""


@app.command()
def doctor():
    """Check configuration and SQLite/FTS5 without creating runtime files."""
    try:
        settings = Settings.from_environment()
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE VIRTUAL TABLE capability_probe USING fts5(body)")
    except (ValueError, sqlite3.Error) as exc:
        typer.echo(f"preflight failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        json.dumps(
            {
                "status": "SCAFFOLD_READY",
                "protocol_version": PROTOCOL_VERSION,
                "sqlite_fts5": True,
                "model_gateway": "LOCAL_CONFIGURED_UNVERIFIED"
                if settings.local_model_config is not None
                else "UNAVAILABLE",
                "mode": settings.mode,
                "test_adapters": settings.enable_test_adapters,
                "roots": {
                    key: str(value.resolve())
                    for key, value in settings.model_dump().items()
                    if key.endswith("_root")
                },
            },
            sort_keys=True,
        )
    )


model_app = typer.Typer(help="Inspect an explicitly configured local model; no automatic fallback.")
app.add_typer(model_app, name="model")


@model_app.command("probe")
def model_probe(config: Annotated[Path | None, typer.Option()] = None):
    """Verify local model pins and its loopback endpoint without generating text."""
    from recycleguard.local_model import LocalModelConfig, LocalModelPort
    from recycleguard.storage import BlobStore

    settings = Settings.from_environment()
    selected = config or settings.local_model_config
    if selected is None:
        typer.echo("Pass --config or set RECYCLEGUARD_LOCAL_MODEL_CONFIG.", err=True)
        raise typer.Exit(1)
    try:
        configuration = LocalModelConfig.model_validate_json(selected.read_bytes())
        result = LocalModelPort(configuration, BlobStore(settings.data_root)).probe()
    except (OSError, ValueError) as exc:
        typer.echo(f"Local model unavailable: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(result, sort_keys=True))


@app.command("validate")
def validate_fixture(
    kind: Annotated[str, typer.Argument(help="command-context or quantity")],
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
):
    """Validate a local development fixture; this does not import or approve evidence."""
    models = {"command-context": CommandContext, "quantity": Quantity}
    if kind not in models:
        raise typer.BadParameter("choose command-context or quantity")
    try:
        result = models[kind].model_validate_json(path.read_bytes())
    except (ValidationError, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(result.model_dump_json())


reviewer_app = typer.Typer(help="Local owner enrollment; internal review only.")
snapshot_app = typer.Typer(help="Publish and review immutable snapshot revisions.")
profile_app = typer.Typer(help="Publish and review immutable calculation profiles.")
app.add_typer(reviewer_app, name="reviewer")
app.add_typer(snapshot_app, name="snapshot")
app.add_typer(profile_app, name="profile")
foundation_app = typer.Typer(help="Build the A04 evidence foundation for human review.")
app.add_typer(foundation_app, name="foundation")


@foundation_app.command("build")
def foundation_build(path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]):
    """Build audited case/corpus/profile drafts. This does not approve CP1."""
    try:
        request = FoundationRequest.model_validate_json(path.read_bytes())
        with local_application(Settings.from_environment()) as (cases, context, capability):
            output = FoundationService(cases).build(context, request, capability=capability)
            typer.echo(output.model_dump_json())
            if output.status != "SUCCESS":
                raise typer.Exit(1)
    except (ValueError, OSError, sqlite3.Error) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@reviewer_app.command("init")
def reviewer_init(
    actor_id: Annotated[str, typer.Argument(help="Local reviewer ID, e.g. human:lead")],
):
    """Enroll the data-root owner once; never replace existing credentials."""
    password = typer.prompt("New reviewer password", hide_input=True, confirmation_prompt=True)
    try:
        initialize_reviewer(Settings.from_environment().data_root, actor_id, password)
    except (ValueError, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo("Local reviewer enrolled. Internal review does not confer portal authority.")


def _dispatch(path: Path, model, method: str, *, review=False):
    try:
        settings = Settings.from_environment()
        request = model.model_validate_json(path.read_bytes())
        password = None
        if review:
            password = typer.prompt("Reviewer password", hide_input=True, err=True)
        with local_application(settings, password) as (service, context, capability):
            # Fixed dispatcher mapping, never a method name supplied by request JSON.
            handlers = {
                "publish_snapshot": service.publish_snapshot,
                "review_snapshot": service.review_snapshot,
                "publish_profile": service.publish_profile,
                "review_profile": service.review_profile,
                "reopen_case": service.reopen_case,
            }
            result = handlers[method](context, request, capability=capability)
            typer.echo(result.model_dump_json())
            if result.status != "SUCCESS":
                raise typer.Exit(1)
    except (ValueError, OSError, sqlite3.Error) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@snapshot_app.command("publish")
def snapshot_publish(path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]):
    """Publish a draft from existing membership and coverage blobs."""
    _dispatch(path, SnapshotPublication, "publish_snapshot")


@snapshot_app.command("reopen")
def snapshot_reopen(path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]):
    """Publish revised CASE membership against an exact parent."""
    _dispatch(path, CaseReopen, "reopen_case")


@snapshot_app.command("review")
def snapshot_review(path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]):
    """Reauthenticate and create a version-bound approval or rejection child."""
    _dispatch(path, SnapshotReview, "review_snapshot", review=True)


@profile_app.command("publish")
def profile_publish(path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]):
    """Publish a draft after policy and exact source-dependency checks."""
    _dispatch(path, ProfilePublication, "publish_profile")


@profile_app.command("review")
def profile_review(path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]):
    """Reauthenticate and review the exact profile ID, version and digest."""
    _dispatch(path, ProfileReview, "review_profile", review=True)


baseline_app = typer.Typer(help="Deterministic calculation, verified report and audit inspection.")
app.add_typer(baseline_app, name="baseline")


@baseline_app.command("run")
def baseline_run(path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]):
    """Run against exact approved stored inputs. PARTIAL remains visible with exit code 2."""
    try:
        request = BaselineRequest.model_validate_json(path.read_bytes())
        with local_application(Settings.from_environment()) as (cases, context, capability):
            result = BaselineService(cases).run(context, request, capability=capability)
            typer.echo(result.model_dump_json())
            if result.status != "SUCCESS":
                raise typer.Exit(2 if result.status == "PARTIAL" else 1)
    except (ValueError, OSError, sqlite3.Error) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@baseline_app.command("audit")
def baseline_audit(operation_id: Annotated[str, typer.Argument()]):
    """Inspect the archived baseline result and hash-chain event references."""
    try:
        with local_application(Settings.from_environment()) as (cases, _, _):
            intent = cases.kernel.get_intent(operation_id)
            result = cases.kernel.get_result(operation_id)
            if intent is None:
                raise ValueError("unknown operation")
            events = cases.kernel.list_stream_events(intent.stream_id)
            previous = None
            for sequence, event in enumerate(events, 1):
                digest = hashlib.sha256(
                    canonical_json_bytes(event.model_dump(mode="json", exclude={"event_hash"}))
                ).hexdigest()
                if (
                    event.sequence != sequence
                    or event.previous_event_hash != previous
                    or event.event_hash != digest
                ):
                    raise ValueError("audit hash chain failed verification")
                for ref in [event.payload_blob, *event.input_refs, *event.output_refs]:
                    cases.kernel.blob_store.get(ref)
                previous = digest
            typer.echo(
                json.dumps(
                    {
                        "audit_valid": True,
                        "intent": intent.model_dump(mode="json"),
                        "result": None if result is None else result.model_dump(mode="json"),
                        "events": [e.model_dump(mode="json") for e in events],
                    }
                )
            )
    except (ValueError, OSError, sqlite3.Error) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@baseline_app.command("support-review")
def support_review(path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]):
    """Authenticate a human and publish exact evidence-bound support revisions."""
    try:
        request = RecordSupportReview.model_validate_json(path.read_bytes())
        password = typer.prompt("Reviewer password", hide_input=True, err=True)
        with local_review_application(Settings.from_environment(), password) as args:
            cases, context, human_cap, actor, service_cap = args
            result = SupportReviewer(
                cases, service_actor=actor, service_capability=service_cap
            ).approve(context, request, capability=human_cap)
            typer.echo(result.model_dump_json())
    except (ValueError, KeyError, OSError, sqlite3.Error) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@foundation_app.command("review")
def foundation_review(path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]):
    """Accept exact foundation inputs and qualifications after human authentication."""
    try:
        request = FoundationApproval.model_validate_json(path.read_bytes())
        password = typer.prompt("Reviewer password", hide_input=True, err=True)
        with local_review_application(Settings.from_environment(), password) as args:
            cases, context, human_cap, actor, service_cap = args
            result = FoundationReviewer(
                cases, service_actor=actor, service_capability=service_cap
            ).approve(context, request, capability=human_cap)
            typer.echo(result.model_dump_json())
    except (ValueError, KeyError, OSError, sqlite3.Error) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


investigation_app = typer.Typer(
    help="Bounded real-service investigation; scripted C10 is test-only."
)
app.add_typer(investigation_app, name="investigation")


@investigation_app.command("start")
def investigation_start(path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]):
    from recycleguard.investigation import InvestigationRequest, InvestigationService

    try:
        settings = Settings.from_environment()
        request = InvestigationRequest.model_validate_json(path.read_bytes())
        with local_application(settings) as (cases, context, capability):
            service = InvestigationService(cases, settings, capability=capability)
            spec = service.prepare(context, request)
            runner = service.runner(spec)
            try:
                state = runner.start_run(context, spec, capability=capability)
                typer.echo(state.model_dump_json())
            finally:
                runner.close()
    except (ValueError, OSError, sqlite3.Error) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


def _investigation_action(run_id, action, expected_version=None, reason=None, max_steps=64):
    from recycleguard.investigation import InvestigationService

    try:
        settings = Settings.from_environment()
        with local_application(settings) as (cases, context, capability):
            service = InvestigationService(cases, settings, capability=capability)
            state = service.recover_reviews(context, run_id)
            spec = service.store.spec(run_id)
            if action == "status":
                output = state
            elif action == "report":
                output = service.latest_report(run_id)
            elif action == "packet":
                output = service.packet(context, spec)
            else:
                runner = service.runner(spec)
                try:
                    if action == "advance":
                        output = runner.advance(
                            context, run_id, expected_version, capability=capability
                        )
                    elif action == "resume":
                        output = runner.resume(context, run_id, capability=capability)
                    elif action == "cancel":
                        output = runner.cancel(
                            context, run_id, expected_version, reason, capability=capability
                        )
                    else:
                        for _ in range(max_steps):
                            if state.status in {
                                "AWAITING_REVIEW",
                                "COMPLETED",
                                "FAILED",
                                "CANCELLED",
                                "BLOCKED_INPUT",
                                "BLOCKED_OUTPUT",
                            }:
                                break
                            state = runner.advance(
                                context, run_id, state.version, capability=capability
                            )
                        output = state
                finally:
                    runner.close()
            typer.echo(output.model_dump_json())
    except (ValueError, OSError, sqlite3.Error, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@investigation_app.command("status")
def investigation_status(run_id: str):
    _investigation_action(run_id, "status")


@investigation_app.command("advance")
def investigation_advance(run_id: str, expected_version: Annotated[int, typer.Option(min=1)]):
    _investigation_action(run_id, "advance", expected_version)


@investigation_app.command("run")
def investigation_run(run_id: str, max_steps: Annotated[int, typer.Option(min=1, max=128)] = 64):
    _investigation_action(run_id, "run", max_steps=max_steps)


@investigation_app.command("resume")
def investigation_resume(run_id: str):
    _investigation_action(run_id, "resume")


@investigation_app.command("cancel")
def investigation_cancel(
    run_id: str,
    expected_version: Annotated[int, typer.Option(min=1)],
    reason: Annotated[str, typer.Option()],
):
    if not reason.strip():
        raise typer.BadParameter("cancellation requires a reason")
    _investigation_action(run_id, "cancel", expected_version, reason)


@investigation_app.command("report")
def investigation_report(run_id: str):
    _investigation_action(run_id, "report")


@investigation_app.command("packet")
def investigation_packet(run_id: str):
    _investigation_action(run_id, "packet")


@investigation_app.command("review")
def investigation_review(
    packet_id: str, decision: Annotated[str, typer.Option()], reason: Annotated[str, typer.Option()]
):
    from datetime import UTC, datetime

    from recycleguard.application import command_context
    from recycleguard.contracts.review import ReviewDecision
    from recycleguard.investigation import InvestigationService

    try:
        settings = Settings.from_environment()
        password = typer.prompt("Reviewer password", hide_input=True, err=True)
        with local_review_application(settings, password) as args:
            cases, human_context, human_cap, actor, service_cap = args
            service = InvestigationService(cases, settings, capability=service_cap)
            reviewer = service.review_service()
            packet = reviewer.get_packet(packet_id)
            spec = service.store.spec(packet.run_id)
            service.recover_reviews(command_context(actor), packet.run_id)
            review_decision = ReviewDecision(
                decision=decision,
                authenticated_reviewer_ref=human_context.actor,
                reason=reason,
                recorded_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            )
            result = reviewer.submit_review(
                service.bound(human_context, spec),
                packet_id,
                packet.review_dependency_digest,
                review_decision,
                capability=human_cap,
            )
            if result.status != "SUCCESS":
                typer.echo(result.model_dump_json())
                raise typer.Exit(1)
            state = service.project_review(command_context(actor), packet_id)
            typer.echo(state.model_dump_json())
    except (ValueError, OSError, sqlite3.Error) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@app.command("serve")
def serve_api(
    host: str = "0.0.0.0",
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8000,
    model_config: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
    token_file: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
    cors_origin: Annotated[list[str] | None, typer.Option()] = None,
    fixture_root: Annotated[Path | None, typer.Option(exists=True, file_okay=False)] = None,
):
    """Start one API worker. Frontend assets are served separately."""
    import os

    import uvicorn

    from recycleguard.api import ApiOptions, create_app

    token = os.environ.get("RECYCLEGUARD_API_TOKEN")
    if token_file is not None:
        token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise typer.BadParameter("Set RECYCLEGUARD_API_TOKEN or provide --token-file")
    settings = Settings.from_environment()
    application = create_app(
        ApiOptions(
            settings=settings,
            token=token,
            model_config_path=model_config,
            cors_origins=tuple(cors_origin or ()),
            # An installed wheel holds no fixtures, so its image names where they are.
            **(
                {}
                if fixture_root is None
                else {
                    "fixture_root": fixture_root,
                    "r02_path": fixture_root / "h04/acquired_originals/e-waste_rules_2022.pdf",
                    "r08_path": fixture_root / "h01/acquired_originals/cpcb_faq_20240123.pdf",
                }
            ),
        )
    )
    uvicorn.run(application, host=host, port=port, workers=1)


audit_app = typer.Typer(help="Audit export and bundle verification.")
app.add_typer(audit_app, name="audit")


@audit_app.command("export")
def audit_export(
    run_id: Annotated[str, typer.Option("--run-id", help="Run ID to export")],
    kind: Annotated[
        str, typer.Option("--kind", help="COMPLETE_LOCAL or QUALIFIED_PUBLIC")
    ] = "COMPLETE_LOCAL",
    output: Annotated[Path | None, typer.Option(file_okay=False)] = None,
):
    """Export an auditable bundle (COMPLETE_LOCAL or QUALIFIED_PUBLIC)."""
    try:
        if kind not in {"COMPLETE_LOCAL", "QUALIFIED_PUBLIC"}:
            raise typer.BadParameter("kind must be COMPLETE_LOCAL or QUALIFIED_PUBLIC")
        bundle_kind = kind
        with local_application(Settings.from_environment()) as (cases, context, capability):
            service = ExportService(cases)
            result = service.export_bundle(
                context, run_id, bundle_kind=bundle_kind, capability=capability
            )
            if result.status == "SUCCESS" and output is not None:
                service.write_package(result.output, output)
            typer.echo(result.model_dump_json())
            if result.status != "SUCCESS":
                raise typer.Exit(1)
    except (ValueError, OSError, sqlite3.Error) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@audit_app.command("verify")
def audit_verify(
    bundle_id: Annotated[str, typer.Option("--bundle-id", help="Bundle ID to verify")],
):
    """Verify bundle object integrity and audit hash-chain continuity."""
    try:
        with local_application(Settings.from_environment()) as (cases, _, _):
            service = ExportService(cases)
            result = service.verify_bundle(bundle_id)
            typer.echo(result.model_dump_json())
            if result.verdict != "PASS":
                raise typer.Exit(1)
    except (ValueError, OSError, sqlite3.Error) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@app.command("replay")
def replay(
    bundle_id: Annotated[str, typer.Option("--bundle-id", help="Bundle ID to replay")],
    mode: Annotated[str, typer.Option("--mode", help="ARTIFACT or RECOMPUTE")] = "ARTIFACT",
):
    """Replay stored artifacts offline; unsupported execution modes fail explicitly."""
    try:
        if mode not in {"ARTIFACT", "RECOMPUTE", "MODEL_RERUN"}:
            raise typer.BadParameter("mode must be ARTIFACT, RECOMPUTE or MODEL_RERUN")
        replay_mode = mode
        request = ReplayRequest(
            bundle_id=bundle_id,
            mode=replay_mode,
            dependency_environment_ref="env:offline_v1",
            access_scope_id="scope:offline",
        )
        with local_application(Settings.from_environment()) as (cases, context, capability):
            service = ExportService(cases)
            result = service.replay_bundle(context, request, capability=capability)
            typer.echo(result.model_dump_json())
            if result.status != "SUCCESS":
                raise typer.Exit(1)
    except (ValueError, OSError, sqlite3.Error) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@audit_app.command("verify-package")
def verify_package(directory: Annotated[Path, typer.Argument(exists=True, file_okay=False)]):
    """Verify a standalone package without a source application database."""
    try:
        service, manifest = ExportService.open_package(directory)
        result = service.verify_bundle(manifest)
        typer.echo(result.model_dump_json())
        if result.verdict != "PASS":
            raise typer.Exit(1)
    except (ValueError, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@app.command("replay-package")
def replay_package(directory: Annotated[Path, typer.Argument(exists=True, file_okay=False)]):
    """Inspect verified frozen artifacts offline; do not execute tools or restore a live DB."""
    try:
        service, manifest = ExportService.open_package(directory)
        context = command_context(
            ActorRef(
                actor_id="service:offline_artifact_inspector",
                actor_kind="SERVICE",
                authenticated_session_ref=None,
            )
        )
        result = service.replay_bundle(
            context,
            ReplayRequest(
                bundle_id=manifest.bundle_id,
                mode="ARTIFACT",
                dependency_environment_ref="env:offline_artifact_inspection",
                access_scope_id="scope:package_read_only",
            ),
        )
        typer.echo(result.model_dump_json())
        if result.status != "SUCCESS":
            raise typer.Exit(1)
    except (ValueError, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@app.command(
    "isolated-investigation",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def isolated_investigation(
    context: typer.Context,
    image: Annotated[str, typer.Option()],
    visible_root: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    runtime_root: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    arguments: Annotated[list[str], typer.Argument()],
    user_id: Annotated[int, typer.Option(min=1)] = 10001,
):
    """Run the investigator in the fixed nonroot, networkless Docker boundary."""
    import subprocess

    from recycleguard.isolated_runtime import run_isolated

    try:
        result = run_isolated(
            image, visible_root, runtime_root, [*arguments, *context.args], user_id=user_id
        )
        if result.stdout:
            typer.echo(result.stdout, nl=False)
        if result.stderr:
            typer.echo(result.stderr, nl=False, err=True)
        if result.returncode:
            raise typer.Exit(1)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


if __name__ == "__main__":
    app()
