"""macOS ``sandbox-exec`` boundary for real-model trials.

The host launcher builds a deny-by-default profile and a stripped environment. Inside the sandbox
the child attempts real forbidden operations and records them before any investigation starts.
Only the operating system's refusal counts as denial. ``sandbox-exec`` is deprecated by Apple, and
this protects against accidental evaluator access by a trusted application, not a hostile one.
"""

import importlib.util
import json
import os
import socket
from datetime import UTC, datetime
from pathlib import Path

from recycleguard.isolated_runtime import _check_mount

SANDBOX_EXEC = "/usr/bin/sandbox-exec"
SYSTEM_READS = ("/usr/lib", "/usr/share", "/System", "/Library/Frameworks", "/private/var/db/dyld")
EXTERNAL_PROBE = ("198.51.100.1", 443)


def _literal(path: Path | str) -> str:
    text = Path(path).as_posix()
    if any(character in text for character in '"\\\n\x00'):
        raise ValueError("sandbox path contains an unsupported character")
    return f'"{text}"'


def sandbox_profile(
    visible: Path, runtime: Path, reads: tuple[Path, ...], *, model_port: int
) -> str:
    """Deny by default; read only the named trees, write only runtime, connect only to the model."""
    if not 1 <= model_port <= 65535:
        raise ValueError("model port is out of range")
    visible, runtime = _check_mount(visible), _check_mount(runtime)
    if visible == runtime or visible in runtime.parents or runtime in visible.parents:
        raise ValueError("visible and runtime roots must be separate directories")
    readable = [*SYSTEM_READS, visible, runtime, *reads]
    subpaths = "\n".join(f"  (subpath {_literal(path)})" for path in readable)
    return f"""(version 1)
(deny default)
(allow process-fork)
(allow process-exec*)
(allow signal (target self))
(allow sysctl-read)
(allow mach-lookup)
(allow system-socket)
(allow file-read-metadata)
(allow file-read*
{subpaths}
  (literal "/dev/null")
  (literal "/dev/urandom")
  (literal "/dev/random"))
(allow file-write*
  (subpath {_literal(runtime)})
  (literal "/dev/null"))
(allow network-outbound
  (remote ip "localhost:{model_port}")
  (remote unix-socket))
"""


def sandbox_command(profile_path: Path, python: Path, program: Path, arguments: list[str]):
    """``-I`` keeps PYTHONPATH and the working directory out of the import path."""
    return [SANDBOX_EXEC, "-f", str(profile_path), str(python), "-I", str(program), *arguments]


def sandbox_environment(runtime: Path) -> dict[str, str]:
    """Nothing is inherited from the host."""
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(runtime),
        "TMPDIR": str(runtime / "tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    }


def _attempt(action: str, target: str, operation) -> dict:
    record = {"action": action, "target": target, "denied": False, "errno": None}
    try:
        operation()
    except PermissionError as exc:
        record.update(denied=True, errno=exc.errno)
    except OSError as exc:
        # Missing or unreachable is not a refusal, so it proves nothing about the boundary.
        record["errno"] = exc.errno
    return record


def probe_boundary(forbidden: list[Path], visible: Path, runtime: Path, evidence: Path) -> list:
    """Attempt forbidden operations, write the evidence, and refuse to continue on any gap."""
    if not forbidden:
        raise RuntimeError("isolation probes need forbidden host paths to try")
    records = []
    for path in forbidden:
        records.append(_attempt("list", str(path), lambda p=path: list(p.iterdir())))
        records.append(_attempt("read", str(path), lambda p=path: p.read_bytes()))
    for target in (visible / ".forbidden-write", runtime.parent / ".forbidden-write"):
        records.append(
            _attempt("write", str(target), lambda t=target: t.write_text("probe", encoding="utf-8"))
        )

    def connect():
        with socket.create_connection(EXTERNAL_PROBE, timeout=2):
            pass

    records.append(_attempt("connect", "external-network", connect))
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
            "denied": not [name for name in os.environ if _evaluator_key(name)],
            "errno": None,
        }
    )
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


def _evaluator_key(name: str) -> bool:
    from recycleguard.isolation import FORBIDDEN_ENV_PREFIXES

    return name.upper().startswith(FORBIDDEN_ENV_PREFIXES)
