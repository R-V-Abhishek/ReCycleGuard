"""Run a frozen trial protocol: one process and one fresh set of roots per attempt.

Evaluator-only. Rerunning with the same output directory resumes; a different protocol is refused.
Creating ``<output>/KILL`` stops the schedule before the next trial. Development cases only.

    uv run scripts/run_trials.py <protocol.json> <output-dir> --config <...> --venv <wheel-venv>
    uv run scripts/run_trials.py <protocol.json> <output-dir> --config <...> --isolation-disclosed
    uv run scripts/run_trials.py <protocol.json> <output-dir> --fixture-model   # dry run, no model

Protocol: {"protocol_version": "...", "case_ids": ["case_..."], "repeats": 1,
"variants": ["FIXED_RETRIEVAL", "ADAPTIVE"], "wall_seconds": 25200, "tokens": 2000000}
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from benchmarks.evaluation.trials import (
    Caps,
    Coordinator,
    Ledger,
    TrialOutcome,
    build_schedule,
    verify_seals,
)

REPOSITORY = Path(__file__).resolve().parents[1]
VISIBLE_FIXTURES = REPOSITORY / "tests/fixtures/visible"
ORIGINALS = (
    VISIBLE_FIXTURES / "h04/acquired_originals/e-waste_rules_2022.pdf",
    VISIBLE_FIXTURES / "h01/acquired_originals/cpcb_faq_20240123.pdf",
)
CHILD = Path(__file__).resolve().with_name("trial_child.py")
CHILD_TIMEOUT_SECONDS = 1200
KEPT_ENVIRONMENT = {"PATH", "PYTHONPATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "VIRTUAL_ENV"}
# A run that stopped itself is a valid result to score; only a crash may be attempted again.
RUN_FAILED = {"FAILED"}
FIXTURE, DISCLOSED, SANDBOXED = (
    "FIXTURE_NOT_EVIDENCE",
    "LOCAL_MODEL_COOPERATIVE_ISOLATION",
    "LOCAL_MODEL_SANDBOXED",
)


@dataclass(frozen=True)
class Launch:
    """How each child starts. ``python`` is the wheel venv's interpreter when sandboxed."""

    backend: str
    config_path: Path
    python: Path | None = None


def freeze(protocol_path, output):
    """Bind the output directory to one exact protocol."""
    raw = protocol_path.read_bytes()
    protocol = json.loads(raw)
    frozen = output / "protocol.json"
    if frozen.exists() and frozen.read_bytes() != raw:
        raise SystemExit("output directory belongs to a different protocol")
    output.mkdir(parents=True, exist_ok=True)
    if not frozen.exists():
        frozen.write_bytes(raw)
    return protocol


def require_development_cases(case_ids):
    from benchmarks.generator.pilot_cases import DEV, build_pilot_cases

    development = {
        f"case_{case.world.case_tag}" for case in build_pilot_cases() if case.split == DEV
    }
    # The MG1 smoke cases come from the separate S06 development set; only its names are read.
    smoke_set = REPOSITORY / "benchmarks/hidden/s06-dev-0.1/clean"
    if smoke_set.is_dir():
        development |= {path.name for path in smoke_set.iterdir()}
    unknown = sorted(set(case_ids) - development)
    if unknown:
        raise SystemExit(f"not development cases: {unknown}")


def prepare_attempt(spec, attempt):
    """A visible root holding only this case and the two public originals."""
    visible, runtime, program = attempt / "visible", attempt / "runtime", attempt / "program"
    shutil.copytree(
        VISIBLE_FIXTURES / spec.case_id, visible / "fixtures" / spec.case_id, symlinks=False
    )
    (visible / "originals").mkdir()
    for original in ORIGINALS:
        shutil.copy2(original, visible / "originals" / original.name)
    runtime.mkdir()
    program.mkdir()
    shutil.copy2(CHILD, program / CHILD.name)
    return visible, runtime, program / CHILD.name


def sandbox_reads(config_path, python):
    """What the investigator must read: its interpreter, the config and the model's provenance."""
    from recycleguard.local_model import LocalModelConfig

    config = LocalModelConfig.model_validate_json(config_path.read_bytes())
    # A venv's python is a link to a managed install, whose whole tree is needed.
    home = Path(
        subprocess.run(
            [str(python), "-I", "-c", "import sys; print(sys.base_prefix)"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    return (
        python.parent.parent.resolve(),
        home.resolve(),
        config_path.parent.resolve(),
        config.model_path.resolve(),
        config.runtime_lock_path.resolve().parent,
    ), urlsplit(config.endpoint).port


def forbidden_paths():
    """Existing evaluator paths the probes must be refused. A missing one would prove nothing."""
    candidates = (
        REPOSITORY / "benchmarks/evaluation",
        REPOSITORY / "benchmarks/hidden",
        REPOSITORY / "tests/fixtures/expected",
        REPOSITORY / ".git",
    )
    return [path for path in candidates if path.exists()]


def child_command(launch, spec, attempt, budgets=None):
    visible, runtime, program = prepare_attempt(spec, attempt)
    arguments = [] if budgets is None else ["--budgets", json.dumps(budgets)]
    arguments += [
        "--case",
        spec.case_id,
        "--variant",
        spec.variant,
        "--visible",
        str(visible.resolve()),
        "--runtime",
        str(runtime.resolve()),
        "--config",
        str(launch.config_path),
    ]
    if launch.backend != SANDBOXED:
        environment = {k: v for k, v in os.environ.items() if k.upper() in KEPT_ENVIRONMENT}
        return [sys.executable, str(program), *arguments], environment, runtime

    from recycleguard.host_sandbox import sandbox_command, sandbox_environment, sandbox_profile

    reads, port = sandbox_reads(launch.config_path, launch.python)
    profile = attempt / "sandbox.sb"
    profile.write_text(
        sandbox_profile(visible, runtime, (program.parent.resolve(), *reads), model_port=port),
        "utf-8",
    )
    for path in forbidden_paths():
        arguments += ["--forbidden", str(path)]
    arguments.append("--sandboxed")
    return (
        sandbox_command(profile, launch.python, program, arguments),
        sandbox_environment(runtime.resolve()),
        runtime,
    )


def seal(result_path, results):
    # Content-addressed, so a later change to a sealed result cannot go unnoticed.
    raw = result_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    (results / f"{digest}.json").write_bytes(raw)
    return digest, json.loads(raw)


def trial_runner(output, launch, budgets=None):
    results = output / "results"
    results.mkdir(exist_ok=True)

    def run(spec):
        trial_dir = output / "trials" / f"t{spec.position:04d}"
        trial_dir.mkdir(parents=True, exist_ok=True)
        attempt = trial_dir / f"attempt-{sum(1 for _ in trial_dir.iterdir()) + 1}"
        attempt.mkdir()
        command, environment, runtime = child_command(launch, spec, attempt, budgets)
        with (attempt / "child.log").open("wb") as log:
            done = subprocess.run(
                command,
                # The sandbox denies the repository, so the child must not start inside it.
                cwd=runtime,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=CHILD_TIMEOUT_SECONDS,
                check=False,
            )
        result_path = runtime / "result.json"
        if done.returncode != 0 or not result_path.is_file():
            return TrialOutcome(status="INFRA_FAILED", detail=f"child exit {done.returncode}")
        digest, result = seal(result_path, results)
        return TrialOutcome(
            status="FAILED" if result["status"] in RUN_FAILED else "SUCCESS",
            tokens=result["budget"]["observed_tokens"],
            detail=f"{result['status']}/{result['stop_reason']}",
            result_digest=digest,
        )

    return run


def coordinate(protocol_path, output, launch):
    output = output.resolve()
    protocol = freeze(protocol_path, output)
    require_development_cases(protocol["case_ids"])
    schedule = build_schedule(
        protocol["case_ids"], tuple(protocol["variants"]), protocol["repeats"]
    )
    # Result files carry the runtime's variant label even on the fake, so record the backend here.
    (output / "backend.txt").write_text(launch.backend + "\n", "utf-8")
    summary = Coordinator(
        schedule,
        Ledger(output / "ledger.jsonl"),
        trial_runner(output, launch, protocol.get("budgets")),
        output / "KILL",
        Caps(wall_seconds=protocol["wall_seconds"], tokens=protocol["tokens"]),
    ).run()
    try:
        seals = verify_seals(output)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        json.dumps(
            {
                "backend": launch.backend,
                "stopped_because": summary.stopped_because,
                "completed_this_run": summary.completed,
                "scheduled": len(schedule),
                "wall_seconds": round(summary.wall_seconds, 1),
                "tokens": summary.tokens,
                "seals_verified": seals,
            }
        )
    )


def with_fixture_model(protocol_path, output):
    from benchmarks.evaluation.trial_fixture import FakeModel, serve
    from recycleguard.local_model import LocalModelConfig
    from tests.unit.test_local_model import configuration

    scratch = Path(tempfile.mkdtemp(prefix="trial-fixture-"))
    try:
        model = scratch / "model"
        model.mkdir()
        httpd = serve(FakeModel(), str(model.resolve()))
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
        coordinate(protocol_path, output, Launch(FIXTURE, config_path))
        httpd.shutdown()
        httpd.server_close()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--venv", type=Path, help="venv holding only the installed wheel")
    parser.add_argument("--isolation-disclosed", action="store_true")
    parser.add_argument("--fixture-model", action="store_true")
    arguments = parser.parse_args()
    if arguments.fixture_model:
        with_fixture_model(arguments.protocol, arguments.output)
    elif arguments.config is None:
        parser.error("give --config or --fixture-model")
    elif arguments.isolation_disclosed:
        launch = Launch(DISCLOSED, arguments.config.resolve())
        coordinate(arguments.protocol, arguments.output, launch)
    else:
        from recycleguard.host_sandbox import SANDBOX_EXEC

        if arguments.venv is None or not Path(SANDBOX_EXEC).exists():
            raise SystemExit(
                "real-model trials need sandbox-exec and --venv; "
                "--isolation-disclosed is the disclosed fallback"
            )
        launch = Launch(
            SANDBOXED, arguments.config.resolve(), arguments.venv.resolve() / "bin/python"
        )
        coordinate(arguments.protocol, arguments.output, launch)


if __name__ == "__main__":
    main()
