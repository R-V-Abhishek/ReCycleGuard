"""Read-only A01 CLI; operational commands follow their checkpoint dependencies."""

import json
import sqlite3
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from recycleguard import __version__
from recycleguard.config import Settings
from recycleguard.contracts import PROTOCOL_VERSION, CommandContext, Quantity

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


if __name__ == "__main__":
    app()
