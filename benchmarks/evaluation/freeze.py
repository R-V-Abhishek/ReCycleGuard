"""CP5 freeze manifest: digest everything an experiment depends on, then verify it later.

Evaluator-side and read-only with respect to the code it measures. A freeze records file and
directory digests, literal values supplied by the caller (for example the prompt pin) and the Git
commit. ``verify_freeze`` recomputes every digest, so a changed byte is reported by name.
"""

import hashlib
import json
import subprocess
from pathlib import Path

IGNORED = {"__pycache__", ".DS_Store", ".pytest_cache", ".ruff_cache"}
FORMAT = "recycleguard-freeze-v1"


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(root: Path) -> str:
    """Digest of every file's relative path and bytes, in sorted order, ignoring caches."""
    if not root.is_dir():
        raise FileNotFoundError(f"not a directory: {root}")
    lines = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in IGNORED for part in relative.parts) or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError(f"symlink inside a frozen tree: {relative}")
        if path.is_file():
            lines.append(f"{relative.as_posix()}\0{file_digest(path)}\n")
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def git_state(repository: Path) -> dict:
    def run(*arguments):
        done = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )
        return done.stdout.strip() if done.returncode == 0 else None

    status = run("status", "--porcelain", "--untracked-files=no")
    return {"commit": run("rev-parse", "HEAD"), "dirty": None if status is None else bool(status)}


def build_freeze(repository: Path, spec: dict) -> dict:
    """``spec`` has ``scope``, ``files`` and ``trees`` (repository-relative) and ``values``."""
    if spec.get("scope") not in {"INCLUDES_REAL_MODEL", "NON_MODEL_ONLY"}:
        raise ValueError("scope must be INCLUDES_REAL_MODEL or NON_MODEL_ONLY")
    files = {name: file_digest(repository / name) for name in sorted(spec.get("files", []))}
    trees = {name: tree_digest(repository / name) for name in sorted(spec.get("trees", []))}
    values = dict(sorted(spec.get("values", {}).items()))
    for key, value in values.items():
        if not isinstance(value, (str, int, float, bool, type(None), list, dict)):
            raise ValueError(f"value {key!r} is not JSON-serialisable")
    return {
        "format": FORMAT,
        "scope": spec["scope"],
        "git": git_state(repository),
        "files": files,
        "trees": trees,
        "values": values,
    }


def freeze_bytes(freeze: dict) -> bytes:
    return (json.dumps(freeze, indent=2, sort_keys=True) + "\n").encode("utf-8")


def freeze_digest(freeze: dict) -> str:
    return hashlib.sha256(freeze_bytes(freeze)).hexdigest()


def verify_freeze(repository: Path, freeze: dict, *, strict_commit: bool = False) -> list[str]:
    """Return every problem found; an empty list means the frozen inputs are unchanged."""
    problems = []
    if freeze.get("format") != FORMAT:
        return [f"unsupported freeze format: {freeze.get('format')!r}"]
    for name, expected in freeze["files"].items():
        path = repository / name
        if not path.is_file():
            problems.append(f"missing file: {name}")
        elif file_digest(path) != expected:
            problems.append(f"changed file: {name}")
    for name, expected in freeze["trees"].items():
        try:
            actual = tree_digest(repository / name)
        except (FileNotFoundError, ValueError) as exc:
            problems.append(f"unreadable tree {name}: {exc}")
            continue
        if actual != expected:
            problems.append(f"changed tree: {name}")
    recorded = freeze["git"]
    current = git_state(repository)
    if recorded.get("dirty"):
        problems.append("freeze was recorded from a dirty working tree")
    if strict_commit and current["commit"] != recorded.get("commit"):
        problems.append(f"HEAD {current['commit']} is not the frozen commit {recorded['commit']}")
    return problems
