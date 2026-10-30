"""Export the frontend contract without creating a runtime data root or serving a UI."""

import json
import tempfile
from pathlib import Path

import typer
from fastapi.testclient import TestClient

from recycleguard.api import ApiOptions, create_app
from recycleguard.config import Settings


def main(check: bool = False):
    with tempfile.TemporaryDirectory() as temporary:
        application = create_app(
            ApiOptions(
                settings=Settings(data_root=Path(temporary)),
                token="schema-export-only-not-a-server-token",
            )
        )
        with TestClient(application):
            expected = json.dumps(application.openapi(), indent=2, ensure_ascii=False) + "\n"
    path = Path(__file__).resolve().parents[1] / "docs/api/openapi.json"
    if check:
        if not path.exists() or path.read_text(encoding="utf-8") != expected:
            raise typer.BadParameter("OpenAPI drift: regenerate docs/api/openapi.json")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(expected)
    typer.echo("Checked API contract" if check else "Exported API contract")


if __name__ == "__main__":
    typer.run(main)
