"""Verify the pinned weights, record the session, then become llama-server. Stdlib only."""

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

WEIGHTS = Path("/models/weights")
PROVENANCE = Path("/models/provenance")
SERVER = "/app/llama-server"
PORT = "8766"
# Keep equal to recycleguard.local_model.LLAMA_SERVER_FLAGS and CONSTRAINED_FLAG.
FLAGS = [
    "--ctx-size",
    "32768",
    "--parallel",
    "1",
    "--n-gpu-layers",
    "999",
    "--n-predict",
    "1024",
    "--no-cache-prompt",
]
CONSTRAINED_FLAG = "--constrained-json"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    root = PROVENANCE / os.environ["MODEL_SLUG"]
    manifest_path = root / "download-manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    if manifest["runtime"]["llama.cpp"] != os.environ["LLAMA_BUILD"]:
        raise SystemExit("Model manifest was recorded for a different llama.cpp build.")
    gguf = None
    for entry in manifest["files"]:
        is_weights = entry["path"].endswith(".gguf")
        path = (WEIGHTS if is_weights else root) / entry["path"]
        if path.stat().st_size != entry["bytes"] or sha256(path) != entry["sha256"]:
            raise SystemExit(f"Model file differs from its manifest: {entry['path']}")
        gguf = path if is_weights else gguf
    if gguf is None:
        raise SystemExit("Model manifest names no GGUF file.")
    # The constrained mode is chosen per request; the flag only records it in the session and pin.
    constrained = os.environ.get("CONSTRAINED") == "1"
    session = {
        "started_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "model_id": manifest["model_id"],
        "revision": manifest["revision"],
        "manifest_sha256": sha256(manifest_path),
        "runtime_lock_sha256": sha256(root / "runtime-lock.env"),
        "server_flags": [*FLAGS, *([CONSTRAINED_FLAG] if constrained else [])],
    }
    (root / "server-session.json").write_text(json.dumps(session, indent=2) + "\n", "utf-8")
    sys.stdout.flush()
    # The alias makes the served identity the provenance path that clients pin.
    command = [
        SERVER,
        "--model",
        str(gguf),
        "--alias",
        str(root),
        "--host",
        "127.0.0.1",
        "--port",
        PORT,
        *FLAGS,
    ]
    os.execv(SERVER, command)


if __name__ == "__main__":
    main()
