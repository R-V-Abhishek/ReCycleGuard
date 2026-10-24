"""Generate/check the A01 proposal schemas from runtime models."""

import json
from pathlib import Path
from typing import Annotated

import typer

from recycleguard.contracts import (
    ActorRef,
    BlobRef,
    CommandContext,
    EvidenceRef,
    Issue,
    Locator,
    Quantity,
    ServiceResult,
    TemporalValue,
)
from recycleguard.model_port import ModelCallRequest, ModelCallResult

MODELS = [
    ActorRef,
    BlobRef,
    CommandContext,
    EvidenceRef,
    Issue,
    Locator,
    Quantity,
    TemporalValue,
    ModelCallRequest,
    ModelCallResult,
    ServiceResult[Quantity],
]
app = typer.Typer()


@app.command()
def export(check: Annotated[bool, typer.Option("--check")] = False):
    root = Path(__file__).resolve().parents[1] / "schemas/v1"
    root.mkdir(parents=True, exist_ok=True)
    for model in MODELS:
        name = model.__name__.replace("[", "_").replace("]", "")
        path = root / f"{name}.json"
        expected = json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False) + "\n"
        if check:
            if not path.exists() or path.read_text() != expected:
                raise typer.BadParameter(f"schema drift: {path.name}; regenerate schemas")
        else:
            path.write_text(expected)
    typer.echo(f"{'Checked' if check else 'Generated'} {len(MODELS)} proposal schemas")


if __name__ == "__main__":
    app()
