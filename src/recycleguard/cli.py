"""Local CLI with read-only diagnostics and trusted C05 publication/review."""

import json
import sqlite3
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from recycleguard import __version__
from recycleguard.application import local_application
from recycleguard.config import Settings
from recycleguard.contracts import PROTOCOL_VERSION, CommandContext, Quantity
from recycleguard.contracts.foundation import FoundationRequest
from recycleguard.contracts.profiles import ProfilePublication, ProfileReview
from recycleguard.contracts.snapshots import CaseReopen, SnapshotPublication, SnapshotReview
from recycleguard.foundation import FoundationService
from recycleguard.local_session import initialize_reviewer

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
    """A01 scaffold. No live filing or model gateway is configured."""


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
                "model_gateway": "UNAVAILABLE",
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


if __name__ == "__main__":
    app()
