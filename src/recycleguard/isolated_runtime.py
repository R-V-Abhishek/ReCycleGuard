"""Enforced networkless Docker boundary for the explicit scripted investigator.

The host launcher validates exact mounts and never passes host environment values.
The wheel image excludes source-control, test and evaluator trees. Container entry
records real OS-boundary probes before dispatching the installed investigation CLI.
This is a trusted-application sandbox, not protection against a hostile Docker host.
"""

import importlib.util
import json
import os
import shutil
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from recycleguard.isolation import FORBIDDEN_PATH_PATTERNS

ALLOWED_ACTIONS = {"start", "run", "status", "advance", "resume", "cancel", "report", "packet"}
CONTAINER_ENV = {
    "PATH": "/opt/venv/bin:/usr/local/bin:/usr/bin:/bin",
    "HOME": "/runtime",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONUNBUFFERED": "1",
    "RECYCLEGUARD_DATA_ROOT": "/runtime",
    "RECYCLEGUARD_INTAKE_ROOT": "/visible",
    "RECYCLEGUARD_OUTPUT_ROOT": "/runtime/output",
    "RECYCLEGUARD_MODE": "test",
    "RECYCLEGUARD_ENABLE_TEST_ADAPTERS": "true",
}


def _check_arguments(arguments: list[str]) -> None:
    if len(arguments) < 2 or arguments[0] != "investigation" or arguments[1] not in ALLOWED_ACTIONS:
        raise ValueError("isolated runtime permits allowlisted investigation actions only")
    if any("\x00" in argument for argument in arguments):
        raise ValueError("invalid null byte in investigator argument")


def _check_mount(root: Path) -> Path:
    selected = root.resolve(strict=True)
    if any(pattern.search(str(selected)) for pattern in FORBIDDEN_PATH_PATTERNS):
        raise ValueError("mount root matches a forbidden path")
    if not selected.is_dir() or root.is_symlink():
        raise ValueError("mount must be a real dedicated directory")
    if "," in str(selected) or "\n" in str(selected):
        raise ValueError("mount path contains unsupported Docker delimiter")
    for current, directories, files in os.walk(selected, followlinks=False):
        for name in [*directories, *files]:
            entry = Path(current) / name
            relative = entry.relative_to(selected).as_posix()
            if entry.is_symlink() or any(
                pattern.search(relative) for pattern in FORBIDDEN_PATH_PATTERNS
            ):
                raise ValueError("mount contains a forbidden path or symlink")
    return selected


def prepare_build_context(repository: Path, wheel: Path, destination: Path) -> Path:
    """Copy only locked metadata, one wheel and Dockerfile into a fresh context."""
    if destination.exists():
        raise ValueError("build context must be new")
    if wheel.suffix != ".whl" or not wheel.is_file():
        raise ValueError("build requires an existing application wheel")
    destination.mkdir(parents=True)
    (destination / "wheels").mkdir()
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copy2(repository / name, destination / name)
    shutil.copy2(repository / "tools/investigator-runtime/Dockerfile", destination / "Dockerfile")
    shutil.copy2(wheel, destination / "wheels" / wheel.name)
    return destination


def docker_arguments(
    image: str,
    visible_root: Path,
    runtime_root: Path,
    arguments: list[str],
    *,
    docker: str = "docker",
    user_id: int = 10001,
) -> list[str]:
    """Return the fixed security policy; callers cannot add mounts/env/network flags."""
    _check_arguments(arguments)
    if not image or image.startswith("-") or user_id <= 0:
        raise ValueError("image and nonroot user ID are required")
    visible, runtime = _check_mount(visible_root), _check_mount(runtime_root)
    if visible == runtime or visible in runtime.parents or runtime in visible.parents:
        raise ValueError("visible and runtime mounts must be separate directories")
    return [
        docker,
        "run",
        "--rm",
        "--read-only",
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "128",
        "--memory",
        "2g",
        "--cpus",
        "2",
        "--user",
        f"{user_id}:{user_id}",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--mount",
        f"type=bind,source={visible},target=/visible,readonly",
        "--mount",
        f"type=bind,source={runtime},target=/runtime",
        image,
        *arguments,
    ]


def run_isolated(
    image: str,
    visible_root: Path,
    runtime_root: Path,
    arguments: list[str],
    *,
    docker: str = "docker",
    user_id: int = 10001,
) -> subprocess.CompletedProcess:
    """Execute only the installed investigator CLI inside the fixed Docker sandbox."""
    command = docker_arguments(
        image, visible_root, runtime_root, arguments, docker=docker, user_id=user_id
    )
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=900)


def _durable_record(records: list[dict]) -> None:
    path = Path("/runtime/isolation-probes.jsonl")
    with path.open("a", encoding="utf-8") as output:
        for record in records:
            record["recorded_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            output.write(json.dumps(record, sort_keys=True) + "\n")
        output.flush()
        os.fsync(output.fileno())


def probe_boundary() -> list[dict]:
    """Attempt actual reads/listings/writes; the OS denies, not a path helper."""
    records = []
    targets = [
        "/app/benchmarks/evaluation",
        "/app/tests/fixtures/expected",
        "/app/.git",
        "/host/hidden-labels",
        "/visible/../benchmarks/evaluation",
    ]
    for target in targets:
        for action in ("list", "read"):
            try:
                if action == "list":
                    list(Path(target).iterdir())
                else:
                    Path(target).read_bytes()
            except OSError as exc:
                records.append(
                    {"action": action, "target": target, "denied": True, "errno": exc.errno}
                )
            else:
                records.append({"action": action, "target": target, "denied": False})
    for target in ("/opt/forbidden-write", "/visible/.forbidden-write"):
        try:
            Path(target).write_text("probe", encoding="utf-8")
        except OSError as exc:
            records.append(
                {"action": "write", "target": target, "denied": True, "errno": exc.errno}
            )
        else:
            records.append({"action": "write", "target": target, "denied": False})
    records.append(
        {
            "action": "import",
            "target": "benchmarks",
            "denied": importlib.util.find_spec("benchmarks") is None,
        }
    )
    try:
        with socket.create_connection(("198.51.100.1", 443), timeout=0.2):
            records.append({"action": "connect", "target": "external-network", "denied": False})
    except OSError as exc:
        records.append(
            {"action": "connect", "target": "external-network", "denied": True, "errno": exc.errno}
        )
    records.append({"action": "uid", "target": "root", "denied": os.getuid() != 0})
    _durable_record(records)
    if not all(record["denied"] for record in records):
        raise RuntimeError("container boundary probe failed; investigator was not dispatched")
    return records


def container_entry(arguments: list[str]) -> int:
    _check_arguments(arguments)
    os.environ.clear()
    os.environ.update(CONTAINER_ENV)
    probe_boundary()
    result = subprocess.run(
        ["/opt/venv/bin/recycleguard", *arguments], env=CONTAINER_ENV, check=False
    )
    return result.returncode


def main(context: typer.Context, arguments: Annotated[list[str], typer.Argument()]):
    """Internal image entrypoint; host users call the trusted Docker launcher."""
    raise typer.Exit(container_entry([*arguments, *context.args]))


app = typer.Typer()
app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})(main)


if __name__ == "__main__":
    app()
