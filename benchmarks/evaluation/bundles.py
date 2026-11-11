"""A trial's whole audit root as one sealed file, so ``recorded_port`` can replay its model calls.

Evaluator-only. Data stays on the machine: bundles live beside the sealed results in the trial
output and are never committed. A replay is not a new trial and is not evidence of model quality.
"""

import hashlib
import shutil
import zipfile
from pathlib import Path


def write_bundle(root: Path, bundles: Path) -> str:
    """Seal ``root`` as ``bundles/<sha256>.zip``. Entries are sorted, so the order is stable."""
    bundles.mkdir(parents=True, exist_ok=True)
    partial = bundles / "partial.zip"
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())
    digest = hashlib.sha256(partial.read_bytes()).hexdigest()
    partial.replace(bundles / f"{digest}.zip")
    return digest


def open_bundle(output: Path, digest: str, into: Path) -> Path:
    """Unpack a verified bundle into a fresh directory; the sealed file itself is never touched."""
    stored = output / "bundles" / f"{digest}.zip"
    if hashlib.sha256(stored.read_bytes()).hexdigest() != digest:
        raise ValueError(f"sealed bundle changed: {digest}")
    if into.exists():
        raise ValueError("bundle target must be a fresh directory")
    into.mkdir(parents=True)
    try:
        with zipfile.ZipFile(stored) as archive:
            for member in archive.namelist():
                target = (into / member).resolve()
                if into.resolve() not in target.parents:
                    raise ValueError("bundle entry escapes its directory")
            archive.extractall(into)
    except Exception:
        shutil.rmtree(into, ignore_errors=True)
        raise
    return into
