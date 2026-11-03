"""Enforced networkless Docker boundary for the explicit scripted investigator.

The host launcher validates exact mounts and never passes host environment values.
The wheel image excludes source-control, test and evaluator trees. Container entry
records real OS-boundary probes before dispatching the installed investigation CLI.
This is a trusted-application sandbox, not protection against a hostile Docker host.
"""

import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from recycleguard.isolation import FORBIDDEN_ENV_PREFIXES, FORBIDDEN_PATH_PATTERNS

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


_SECURITY_FLAGS = (
    "--read-only",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges",
)
TRIAL_USER = 10001
TRIAL_LABEL = "recycleguard.trial=1"
# Parallel coordinators clean up only their own session's containers.
TRIAL_SESSION_KEY = "recycleguard.session"
TRIAL_NO_NETWORK = "none"
API_PORT = 8000
_TRIAL_MOUNT_MODES = {"/visible": True, "/program": True, "/runtime": False}
PROVENANCE_TARGET = "/models/provenance"
_SYSTEM_MOUNTS = {"/", "/etc/hosts", "/etc/hostname", "/etc/resolv.conf", "/tmp"}
_SYSTEM_MOUNT_ROOTS = ("/proc", "/dev", "/sys")
_ABSENT_FROM_TRIALS = (
    "/repo",
    "/work",
    "/evaluator",
    "/models/weights",
    "/var/run/docker.sock",
    "/run/docker.sock",
)


def _volume_mount(volume: str, target: str, subpath: str | None, readonly: bool) -> str:
    fields = [f"type=volume,source={volume},target={target}"]
    if subpath is not None:
        fields.append(f"volume-subpath={subpath}")
    if readonly:
        fields.append("readonly")
    return ",".join(fields)


def trial_container_arguments(
    name: str,
    image: str,
    network: str,
    trial_volume: str,
    attempt_subpath: str,
    provenance_volume: str | None,
    arguments: list[str],
    *,
    docker: str = "docker",
    session: str | None = None,
) -> list[str]:
    """``docker create`` for one trial. Volumes only: evaluator data is simply never mounted."""
    if not image or image.startswith("-") or not name or name.startswith("-"):
        raise ValueError("trial container needs a name and an image")
    if session is not None and not re.fullmatch(r"[0-9a-f]{16}", session):
        raise ValueError("trial session label must be 16 hex characters")
    if "," in attempt_subpath or "\n" in attempt_subpath or ".." in attempt_subpath.split("/"):
        raise ValueError("attempt path cannot be used as a volume subpath")
    command = [
        docker,
        "create",
        "--name",
        name,
        "--label",
        TRIAL_LABEL,
        *([] if session is None else ["--label", f"{TRIAL_SESSION_KEY}={session}"]),
        *_SECURITY_FLAGS,
        "--network",
        network,
        "--pids-limit",
        "512",
        "--memory",
        "8g",
        "--cpus",
        "8",
        "--user",
        f"{TRIAL_USER}:{TRIAL_USER}",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=256m",
    ]
    for target, readonly in _TRIAL_MOUNT_MODES.items():
        command += [
            "--mount",
            _volume_mount(trial_volume, target, f"{attempt_subpath}{target}", readonly),
        ]
    if provenance_volume is not None:
        command += ["--mount", _volume_mount(provenance_volume, PROVENANCE_TARGET, None, True)]
    return [*command, image, *arguments]


def verify_trial_inspection(
    inspection: dict, network: str, volumes: set[str], session: str | None = None
) -> list[str]:
    """Check what Docker will actually start, before it starts. Returns every problem found."""
    host, config = inspection["HostConfig"], inspection["Config"]
    problems = []
    if session is not None and (config.get("Labels") or {}).get(TRIAL_SESSION_KEY) != session:
        problems.append("container does not carry its session label")
    if host.get("Privileged"):
        problems.append("container is privileged")
    if not host.get("ReadonlyRootfs"):
        problems.append("root filesystem is writable")
    if "ALL" not in (host.get("CapDrop") or []) or host.get("CapAdd"):
        problems.append("capabilities are not all dropped")
    if host.get("Binds"):
        problems.append("container has host bind mounts")
    if host.get("Devices"):
        problems.append("container has host devices")
    if host.get("NetworkMode") != network:
        problems.append(f"network mode is {host.get('NetworkMode')}, expected {network}")
    if str(config.get("User", "")).split(":")[0] in {"", "0", "root"}:
        problems.append("container runs as root")
    names = [item.split("=", 1)[0].upper() for item in config.get("Env") or []]
    if any(name.startswith(FORBIDDEN_ENV_PREFIXES) for name in names):
        problems.append("container environment holds an evaluator key")
    expected = dict(_TRIAL_MOUNT_MODES)
    if network != TRIAL_NO_NETWORK:
        expected[PROVENANCE_TARGET] = True
    mounts = {mount["Target"]: mount for mount in host.get("Mounts") or []}
    if set(mounts) != set(expected):
        problems.append(f"mounts are {sorted(mounts)}, expected {sorted(expected)}")
    for target, mount in mounts.items():
        if mount.get("Type") != "volume" or mount.get("Source") not in volumes:
            problems.append(f"{target} is not an allowed volume")
        if bool(mount.get("ReadOnly")) != expected.get(target, True):
            problems.append(f"{target} has the wrong read-only mode")
    return problems


def _denied_when_raising(action: str, target: str, operation) -> dict:
    record = {"action": action, "target": target, "denied": False, "errno": None}
    try:
        operation()
    except OSError as exc:
        record.update(denied=True, errno=exc.errno)
    return record


def _connect(address: tuple[str, int]) -> None:
    with socket.create_connection(address, timeout=2):
        pass


def _mount_points(mountinfo: Path = Path("/proc/self/mountinfo")) -> list[str]:
    return [line.split()[4] for line in mountinfo.read_text("utf-8").splitlines()]


def probe_trial_boundary(visible: Path, program: Path, runtime: Path, evidence: Path) -> list[dict]:
    """Evidence from inside a trial container, recorded before any investigation starts.

    Evaluator paths are not mounted here, so there is nothing to be refused. For those, the evidence
    is that they do not exist and that the mount table holds nothing else.
    """
    records = [
        {
            "action": "absent",
            "target": target,
            "denied": not os.path.lexists(target),
            "errno": None,
        }
        for target in _ABSENT_FROM_TRIALS
    ]
    allowed = {str(visible), str(program), str(runtime), PROVENANCE_TARGET, *_SYSTEM_MOUNTS}
    for point in _mount_points():
        if not point.startswith(_SYSTEM_MOUNT_ROOTS):
            records.append(
                {"action": "mount", "target": point, "denied": point in allowed, "errno": None}
            )
    writes = [visible / ".forbidden-write", program / ".forbidden-write", Path("/opt/forbidden")]
    if Path(PROVENANCE_TARGET).exists():
        writes.append(Path(PROVENANCE_TARGET) / ".forbidden-write")
    for target in writes:
        records.append(
            _denied_when_raising(
                "write", str(target), lambda t=target: t.write_text("probe", encoding="utf-8")
            )
        )
    records.append(
        _denied_when_raising("connect", "external-network", lambda: _connect(("198.51.100.1", 443)))
    )
    records.append(
        _denied_when_raising(
            "connect", "api-on-loopback", lambda: _connect(("127.0.0.1", API_PORT))
        )
    )
    records.append(
        {
            "action": "import",
            "target": "benchmarks",
            "denied": importlib.util.find_spec("benchmarks") is None,
            "errno": None,
        }
    )
    records.append(
        {
            "action": "environment",
            "target": "evaluator keys",
            "denied": not [
                name for name in os.environ if name.upper().startswith(FORBIDDEN_ENV_PREFIXES)
            ],
            "errno": None,
        }
    )
    records.append({"action": "uid", "target": "root", "denied": os.getuid() != 0, "errno": None})
    evidence.write_text(
        json.dumps(
            {"recorded_at": datetime.now(UTC).isoformat(), "probes": records},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        "utf-8",
    )
    if not all(record["denied"] for record in records):
        raise RuntimeError("isolation probe was not denied; investigator was not started")
    return records


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
        *_SECURITY_FLAGS[:1],
        "--network",
        "none",
        *_SECURITY_FLAGS[1:],
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
