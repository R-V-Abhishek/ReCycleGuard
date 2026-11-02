"""Verify the pinned local files, then start a single-worker loopback MLX server."""

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from importlib.metadata import version

from download import MODEL_ID, MODEL_ROOT, REVISION, ROOT


def main():
    manifest_path = MODEL_ROOT / "download-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["model_id"] != MODEL_ID or manifest["revision"] != REVISION:
        raise SystemExit("Local model manifest differs from the pinned repository revision.")
    for entry in manifest["files"]:
        path = MODEL_ROOT / entry["path"]
        if path.parent != MODEL_ROOT or path.is_symlink():
            raise SystemExit("Unexpected file path in model manifest.")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if path.stat().st_size != entry["bytes"] or digest.hexdigest() != entry["sha256"]:
            raise SystemExit(f"Model integrity check failed: {entry['path']}")
    for package, expected in manifest["runtime"].items():
        if version(package) != expected:
            raise SystemExit(f"Runtime version drift: {package}")
    os.environ["HF_HOME"] = str(ROOT / ".recycleguard/model-download-cache")
    (ROOT / ".recycleguard/model-download-cache/hub").mkdir(parents=True, exist_ok=True)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    session = {
        "pid": os.getpid(),
        "started_at": datetime.now(UTC).isoformat(),
        "model_id": MODEL_ID,
        "revision": REVISION,
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "runtime_lock_sha256": hashlib.sha256(
            (ROOT / "tools/local-model/uv.lock").read_bytes()
        ).hexdigest(),
        "endpoint": "http://127.0.0.1:8766/v1/completions",
    }
    (MODEL_ROOT / "server-session.json").write_text(
        json.dumps(session, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "Verified local model; serving on 127.0.0.1:8766. Ctrl-C releases model memory.", flush=True
    )
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "mlx_lm",
            "server",
            "--model",
            str(MODEL_ROOT),
            "--host",
            "127.0.0.1",
            "--port",
            "8766",
            "--decode-concurrency",
            "1",
            "--prompt-concurrency",
            "1",
            "--prompt-cache-size",
            "1",
            "--prefill-step-size",
            "256",
            "--max-tokens",
            "1024",
            "--log-level",
            "WARNING",
            "--allowed-origins",
            "http://127.0.0.1:8766",
        ],
    )


if __name__ == "__main__":
    main()
