"""Measure prompt bytes for V1 and V2 over the development cases against a loopback fake.

No model and no weights: the fake server returns fixed JSON, so this says nothing about model
quality. Held-out cases are never rendered or run. V2 walks a worst-case path that inspects the
whole dossier. Exits non-zero when a run does not reach review or a prompt nears the bound.

    uv run scripts/measure_prompts.py <fresh-data-root> <output.json>
"""

import json
import secrets
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from trial_child import caller, prepare_dossier, run_variant

from benchmarks.evaluation.trial_fixture import FakeModel, serve
from benchmarks.generator.pilot_cases import DEV, build_pilot_cases
from recycleguard.api import ApiOptions, create_app
from recycleguard.config import Settings
from recycleguard.local_model import LocalModelConfig
from tests.unit.test_local_model import configuration


def main():
    data_root, output = Path(sys.argv[1]), Path(sys.argv[2])
    if data_root.exists():
        raise SystemExit("data root must be fresh")
    fake = FakeModel()
    with tempfile.TemporaryDirectory() as temporary:
        scratch = Path(temporary)
        model = scratch / "model"
        model.mkdir()
        httpd = serve(fake, str(model.resolve()))
        endpoint = f"http://127.0.0.1:{httpd.server_port}/v1/completions"
        config = configuration((None, endpoint, model), scratch).model_copy(
            update={
                "max_output_tokens": LocalModelConfig.model_fields["max_output_tokens"].default,
                "max_total_tokens": LocalModelConfig.model_fields["max_total_tokens"].default,
                "timeout_seconds": 60.0,
            }
        )
        config_path = scratch / "config.json"
        config_path.write_text(config.model_dump_json(), "utf-8")
        limit = config.max_total_tokens - config.max_output_tokens
        password, token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        app = create_app(
            ApiOptions(
                settings=Settings(data_root=data_root), token=token, model_config_path=config_path
            )
        )
        rows = []
        with TestClient(app) as client:
            client.headers["Authorization"] = "Bearer " + token
            call = caller(client)
            call(
                "POST",
                "/reviewer",
                {"actor_id": "human:prompt_fixture", "password": password},
                201,
            )
            for case in build_pilot_cases():
                if case.split != DEV:
                    continue
                fixture = f"case_{case.world.case_tag}"
                row = {"fixture": fixture}
                rows.append(row)
                try:
                    dossier = prepare_dossier(call, fixture, password)
                    for variant in ("FIXED_RETRIEVAL", "ADAPTIVE"):
                        fake.sizes = []
                        run_id, view = run_variant(call, dossier, variant)
                        row[variant] = {
                            "status": view["state"]["status"],
                            "stop_reason": view["state"]["stop_reason"],
                            "model_calls": view["state"]["budget"]["model_calls"],
                            "tool_calls": view["state"]["budget"]["tool_calls"],
                            "largest_prompt_bytes": max(fake.sizes, default=0),
                            # A prompt over the bound is rejected before it reaches the fake.
                            "issue_codes": sorted(
                                {
                                    issue["code"]
                                    for event in call("GET", f"/runs/{run_id}/trace")["events"]
                                    for issue in event.get("issues") or []
                                }
                            ),
                        }
                except Exception as exc:  # recorded; one bad case must not hide the others
                    row["error"] = f"{type(exc).__name__}: {exc}"[:500]
                print(json.dumps(row), flush=True)
        httpd.shutdown()
        httpd.server_close()
    results = [row[v] for row in rows for v in ("FIXED_RETRIEVAL", "ADAPTIVE") if v in row]
    largest = max((r["largest_prompt_bytes"] for r in results), default=0)
    # Preflight legitimately blocks a dossier with declared pages missing, before any model call.
    blocked = [r for r in results if r["status"] == "BLOCKED_INPUT" and r["model_calls"] == 0]
    passed = (
        len(results) == 2 * len(rows)
        and all(r["status"] == "AWAITING_REVIEW" or r in blocked for r in results)
        and largest <= limit
    )
    summary = {
        "scope": "Loopback fake only; prompt sizes and completion, not model quality.",
        "prompt_byte_limit": limit,
        "largest_prompt_bytes": largest,
        "blocked_before_model_runs": len(blocked),
        "passed": passed,
        "cases": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n", "utf-8")
    print(
        json.dumps({k: summary[k] for k in ("prompt_byte_limit", "largest_prompt_bytes", "passed")})
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
