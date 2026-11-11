"""Run a frozen trial protocol: one process and one fresh set of roots per attempt.

Evaluator-only. Rerunning with the same output directory resumes; a different protocol is refused.
Creating ``<output>/KILL`` stops the schedule before the next trial. Development cases only, unless
``--held-out`` names a freeze manifest that verifies against this exact code and protocol.

    uv run scripts/run_trials.py <protocol.json> <output-dir> --config <...> --venv <wheel-venv>
    uv run scripts/run_trials.py <protocol.json> <output-dir> --config <...> --isolation-disclosed
    python scripts/run_trials.py <protocol.json> /work/<name> --config <...> --docker  # in `trials`
    uv run scripts/run_trials.py <protocol.json> <output-dir> --fixture-model   # dry run, no model
    uv run scripts/run_trials.py <protocol.json> <output-dir> --config <...> --venv <wheel-venv> \
        --held-out <freeze.json>

Protocol: {"protocol_version": "...", "case_ids": ["case_..."], "repeats": 1,
"variants": ["FIXED_RETRIEVAL", "ADAPTIVE"], "wall_seconds": 25200, "tokens": 2000000}
Optional: "controls": ["V0", "SC"] (one deterministic run per case) and "canaries": ["case_..."]
(development cases run at both ends of the session, compared by score_trials and never scored).
Optional, evaluation only: "ablated_families": ["F02_...", ...] switches off those families'
deterministic findings in every trial of the session, controls included.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))  # evaluator code is not part of the installed wheel

from benchmarks.evaluation.bundles import write_bundle  # noqa: E402
from benchmarks.evaluation.freeze import verify_freeze  # noqa: E402
from benchmarks.evaluation.trials import (  # noqa: E402
    CANARY,
    CONTROLS,
    Caps,
    Coordinator,
    Ledger,
    TrialOutcome,
    protocol_schedule,
    verify_seals,
)

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
RUN_BLOCKED = {"BLOCKED_OUTPUT"}
FIXTURE, DISCLOSED, SANDBOXED, DOCKERED, DOCKER_FIXTURE = (
    "FIXTURE_NOT_EVIDENCE",
    "LOCAL_MODEL_COOPERATIVE_ISOLATION",
    "LOCAL_MODEL_SANDBOXED",
    "LOCAL_MODEL_DOCKER",
    "FIXTURE_NOT_EVIDENCE_DOCKER",
)
CONTAINER_BACKENDS = {DOCKERED, DOCKER_FIXTURE}
# Names fixed in deploy/compose.yaml. Paths are inside the `trials` container.
TRIAL_ROOT = Path("/work")
TRIAL_VOLUME = "recycleguard-trial-data"
PROVENANCE_VOLUME = "recycleguard-model-provenance"
MODEL_CONTAINER = "recycleguard-model"
API_CONTAINER = "recycleguard-api"
INVESTIGATOR_IMAGE = "recycleguard-investigator:local"


@dataclass(frozen=True)
class Launch:
    """How each child starts. ``python`` is the wheel venv's interpreter when sandboxed."""

    backend: str
    config_path: Path
    python: Path | None = None
    fixtures: Path = VISIBLE_FIXTURES


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


def held_out_case_ids():
    from benchmarks.generator.pilot_cases import DEV, build_pilot_cases

    return {f"case_{case.world.case_tag}" for case in build_pilot_cases() if case.split != DEV}


def require_verified_freeze(freeze_path, protocol_path):
    """Refuse everything but an exact, committed, approved freeze. Returns the held-out root."""
    freeze = json.loads(freeze_path.read_bytes())
    problems = verify_freeze(REPOSITORY, freeze, strict_commit=True)
    values = freeze.get("values", {})
    if freeze.get("scope") != "INCLUDES_REAL_MODEL":
        problems.append("freeze scope does not include the real model")
    if values.get("protocol_sha256") != hashlib.sha256(protocol_path.read_bytes()).hexdigest():
        problems.append("freeze does not name this exact protocol")
    # A relative root is inside this checkout, so one freeze verifies on the laptop and the cloud.
    root = values.get("held_out_visible_root")
    if not root or not (REPOSITORY / root).is_dir():
        problems.append("freeze does not name an existing held-out visible root")
    if problems:
        raise SystemExit("held-out run refused: " + "; ".join(problems))
    return (REPOSITORY / root).resolve()


def require_held_out_cases(case_ids):
    unknown = sorted(set(case_ids) - held_out_case_ids())
    if unknown:
        raise SystemExit(f"not held-out cases: {unknown}")


def prepare_attempt(spec, attempt, fixtures=VISIBLE_FIXTURES):
    """A visible root holding only this case and the two public originals."""
    visible, runtime, program = attempt / "visible", attempt / "runtime", attempt / "program"
    # A canary is always a development case, whichever cases the session scores.
    source = VISIBLE_FIXTURES if spec.role == CANARY else fixtures
    shutil.copytree(source / spec.case_id, visible / "fixtures" / spec.case_id, symlinks=False)
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
    # The configuration and runtime lock are single files. Granting their directories would expose
    # everything beside them: the data root and the local-model tooling.
    return (
        python.parent.parent.resolve(),
        home.resolve(),
        config_path.resolve(),
        config.model_path.resolve(),
        config.runtime_lock_path.resolve(),
    ), urlsplit(config.endpoint).port


def forbidden_paths(output=None):
    """Existing evaluator paths the probes must be refused. A missing one would prove nothing.

    Each evaluator tree has its own probe, and so do this session's results: a later trial must
    not read an earlier one.
    """
    candidates = [
        REPOSITORY / "benchmarks",
        REPOSITORY / "benchmarks/evaluation",
        REPOSITORY / "benchmarks/generator",
        REPOSITORY / "benchmarks/heldout",
        REPOSITORY / "benchmarks/hidden",
        REPOSITORY / "benchmarks/pilot",
        REPOSITORY / "docs/evaluation",
        REPOSITORY / "docs/checkpoints",
        REPOSITORY / "scripts",
        REPOSITORY / "tests",
        REPOSITORY / "tests/fixtures/expected",
        REPOSITORY / ".git",
    ]
    if output is not None:
        candidates += [output / "ledger.jsonl", output / "results", output / "bundles"]
    return [path for path in candidates if path.exists()]


def require_separate_grants(reads, forbidden):
    """A read grant holding or held by an evaluator path would make its probe fail or lie."""
    for grant in reads:
        for path in forbidden:
            path = path.resolve()
            if grant == path or grant in path.parents or path in grant.parents:
                raise SystemExit(f"sandbox read grant {grant} overlaps evaluator path {path}")


def _ablation(ablated):
    """The same switch reaches every variant, controls included, so SC stays the zero line."""
    return ["--ablate", json.dumps(sorted(ablated))] if ablated else []


def child_command(launch, spec, attempt, budgets=None, output=None, ablated=None):
    visible, runtime, program = prepare_attempt(spec, attempt, launch.fixtures)
    arguments = [] if budgets is None else ["--budgets", json.dumps(budgets)]
    arguments += _ablation(ablated)
    arguments += [
        "--case",
        spec.case_id,
        "--variant",
        spec.variant,
        "--visible",
        str(visible.resolve()),
        "--runtime",
        str(runtime.resolve()),
    ]
    # A control has no model, so it is never told where one is.
    if spec.variant not in CONTROLS:
        arguments += ["--config", str(launch.config_path)]
    if launch.backend != SANDBOXED:
        environment = {k: v for k, v in os.environ.items() if k.upper() in KEPT_ENVIRONMENT}
        return [sys.executable, str(program), *arguments], environment, runtime

    from recycleguard.host_sandbox import sandbox_command, sandbox_environment, sandbox_profile

    reads, port = sandbox_reads(launch.config_path, launch.python)
    forbidden = forbidden_paths(output)
    require_separate_grants(reads, forbidden)
    profile = attempt / "sandbox.sb"
    profile.write_text(
        sandbox_profile(visible, runtime, (program.parent.resolve(), *reads), model_port=port),
        "utf-8",
    )
    for path in forbidden:
        arguments += ["--forbidden", str(path)]
    arguments.append("--sandboxed")
    return (
        sandbox_command(profile, launch.python, program, arguments),
        sandbox_environment(runtime.resolve()),
        runtime,
    )


def session_id(output):
    """Labels this coordinator's containers, so parallel sessions never remove each other's."""
    return hashlib.sha256(output.resolve().as_posix().encode()).hexdigest()[:16]


def container_command(
    launch, spec, attempt, budgets=None, root=TRIAL_ROOT, session=None, ablated=None
):
    """``docker create`` for one trial, with the paths the investigator sees inside it."""
    from recycleguard.isolated_runtime import (
        TRIAL_NO_NETWORK,
        TRIAL_USER,
        trial_container_arguments,
    )

    visible, runtime, program = prepare_attempt(spec, attempt, launch.fixtures)
    if hasattr(os, "geteuid") and os.geteuid() == 0:  # the investigator is not root
        os.chown(runtime, TRIAL_USER, TRIAL_USER)
    control = spec.variant in CONTROLS
    arguments = ["-I", f"/program/{program.name}"]
    arguments += [] if budgets is None else ["--budgets", json.dumps(budgets)]
    arguments += _ablation(ablated)
    arguments += ["--case", spec.case_id, "--variant", spec.variant]
    arguments += ["--visible", "/visible", "--runtime", "/runtime", "--container"]
    if not control:
        arguments += ["--config", launch.config_path.as_posix()]
    subpath = attempt.resolve().relative_to(root).as_posix()
    network = TRIAL_NO_NETWORK if control else f"container:{MODEL_CONTAINER}"
    name = "recycleguard-trial-" + hashlib.sha256(subpath.encode()).hexdigest()[:16]
    command = trial_container_arguments(
        name,
        INVESTIGATOR_IMAGE,
        network,
        TRIAL_VOLUME,
        subpath,
        None if control else PROVENANCE_VOLUME,
        arguments,
        session=session,
    )
    return command, name, network, runtime


def run_container(command, name, network, attempt, log, session=None):
    """Create, check what Docker will start, then start. The container never outlives this call."""
    from recycleguard.isolated_runtime import verify_trial_inspection

    created = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    if created.returncode != 0:
        return created
    try:
        inspected = subprocess.run(
            ["docker", "inspect", name], capture_output=True, check=True, timeout=60
        )
        (attempt / "isolation-inspect.json").write_bytes(inspected.stdout)
        expected = network
        if network.startswith("container:"):
            # Docker records the joined container by id, which also pins the running server.
            model = subprocess.run(
                ["docker", "inspect", network.split(":", 1)[1]],
                capture_output=True,
                check=True,
                timeout=60,
            )
            expected = "container:" + json.loads(model.stdout)[0]["Id"]
        problems = verify_trial_inspection(
            json.loads(inspected.stdout)[0], expected, {TRIAL_VOLUME, PROVENANCE_VOLUME}, session
        )
        if problems:
            raise SystemExit("trial container refused: " + "; ".join(problems))
        return subprocess.run(
            ["docker", "start", "--attach", name],
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=CHILD_TIMEOUT_SECONDS,
            check=False,
        )
    finally:
        subprocess.run(["docker", "rm", "--force", name], capture_output=True, check=False)


def prepare_docker_session(output):
    """A killed coordinator can leave a trial running. Evidence holds only this session's work.

    Only this session's containers are removed: other sessions may be running beside it.
    """
    from recycleguard.isolated_runtime import TRIAL_LABEL, TRIAL_SESSION_KEY

    if not output.is_relative_to(TRIAL_ROOT):
        raise SystemExit(f"--docker output must be under {TRIAL_ROOT}, in the trial volume")
    running = subprocess.run(
        ["docker", "ps", "--quiet", "--filter", f"name=^{API_CONTAINER}$"],
        capture_output=True,
        text=True,
        check=True,
    )
    if running.stdout.strip():
        raise SystemExit("stop the demo API first: it shares the model's network with trials")
    stale = subprocess.run(
        [
            "docker",
            "ps",
            "--all",
            "--quiet",
            "--filter",
            f"label={TRIAL_LABEL}",
            "--filter",
            f"label={TRIAL_SESSION_KEY}={session_id(output)}",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    if stale:
        subprocess.run(["docker", "rm", "--force", *stale], capture_output=True, check=True)


def seal(result_path, results):
    # Content-addressed, so a later change to a sealed result cannot go unnoticed.
    raw = result_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    (results / f"{digest}.json").write_bytes(raw)
    return digest, json.loads(raw)


def trial_runner(output, launch, budgets=None, ablated=None):
    results = output / "results"
    results.mkdir(exist_ok=True)
    session = session_id(output)

    def run(spec):
        trial_dir = output / "trials" / f"t{spec.position:04d}"
        trial_dir.mkdir(parents=True, exist_ok=True)
        attempt = trial_dir / f"attempt-{sum(1 for _ in trial_dir.iterdir()) + 1}"
        attempt.mkdir()
        if launch.backend in CONTAINER_BACKENDS:
            command, name, network, runtime = container_command(
                launch, spec, attempt, budgets, session=session, ablated=ablated
            )
            with (attempt / "child.log").open("wb") as log:
                done = run_container(command, name, network, attempt, log, session)
        else:
            command, environment, runtime = child_command(
                launch, spec, attempt, budgets, output, ablated=ablated
            )
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
        detail = f"{result['status']}/{result['stop_reason']}"
        try:
            bundle = write_bundle(runtime / "root", output / "bundles")
        except OSError as exc:  # the sealed result stands; only its replay material is missing
            bundle, detail = None, f"{detail}; bundle not written: {type(exc).__name__}"
        return TrialOutcome(
            status="FAILED"
            if result["status"] in RUN_FAILED
            else "BLOCKED"
            if result["status"] in RUN_BLOCKED
            else "SUCCESS",
            tokens=result["budget"]["observed_tokens"],
            detail=detail,
            result_digest=digest,
            bundle_digest=bundle,
        )

    return run


def coordinate(protocol_path, output, launch, *, held_out=None):
    output = output.resolve()
    if launch.backend in CONTAINER_BACKENDS:
        prepare_docker_session(output)
    protocol = freeze(protocol_path, output)
    require_development_cases(protocol.get("canaries", ()))
    if held_out is None:
        require_development_cases(protocol["case_ids"])
    else:
        launch = replace(launch, fixtures=require_verified_freeze(held_out, protocol_path))
        require_held_out_cases(protocol["case_ids"])
        (output / "freeze.json").write_bytes(held_out.read_bytes())
    schedule = protocol_schedule(protocol)
    # Result files carry the runtime's variant label even on the fake, so record the backend here.
    (output / "backend.txt").write_text(launch.backend + "\n", "utf-8")
    summary = Coordinator(
        schedule,
        Ledger(output / "ledger.jsonl"),
        trial_runner(output, launch, protocol.get("budgets"), protocol.get("ablated_families")),
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
    parser.add_argument("--docker", action="store_true", help="one fresh container per trial")
    parser.add_argument("--fixture-model", action="store_true")
    parser.add_argument("--held-out", type=Path, help="verified CP5 freeze manifest")
    arguments = parser.parse_args()
    if arguments.fixture_model:
        if arguments.held_out is not None:
            parser.error("a fixture dry run can never use held-out cases")
        with_fixture_model(arguments.protocol, arguments.output)
    elif arguments.config is None:
        parser.error("give --config or --fixture-model")
    elif arguments.docker:
        from recycleguard.local_model import FIXTURE_MODEL_PREFIX, LocalModelConfig

        config = LocalModelConfig.model_validate_json(arguments.config.read_bytes())
        fixture = config.model_id.startswith(FIXTURE_MODEL_PREFIX)
        if fixture and arguments.held_out is not None:
            parser.error("a fixture dry run can never use held-out cases")
        launch = Launch(DOCKER_FIXTURE if fixture else DOCKERED, arguments.config.resolve())
        coordinate(arguments.protocol, arguments.output, launch, held_out=arguments.held_out)
    elif arguments.isolation_disclosed:
        from recycleguard.local_model import FIXTURE_MODEL_PREFIX, LocalModelConfig

        config = LocalModelConfig.model_validate_json(arguments.config.read_bytes())
        if config.model_id.startswith(FIXTURE_MODEL_PREFIX) and arguments.held_out is not None:
            parser.error("a fixture dry run can never use held-out cases")
        launch = Launch(DISCLOSED, arguments.config.resolve())
        coordinate(arguments.protocol, arguments.output, launch, held_out=arguments.held_out)
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
        coordinate(arguments.protocol, arguments.output, launch, held_out=arguments.held_out)


if __name__ == "__main__":
    main()
