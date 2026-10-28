"""Fetch a pinned, data-only model into the ignored project-local model store."""

import hashlib
import json
import os
import platform
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL_ID = "mlx-community/Qwen3.5-9B-4bit"
REVISION = "8b2b98c00a6b4d291155e4890773ca8f769aee53"
MODEL_ROOT = ROOT / ".recycleguard/models/qwen3.5-9b-4bit"


def main():
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("This inference runtime requires Apple Silicon macOS.")
    os.environ["HF_HOME"] = str(ROOT / ".recycleguard/model-download-cache")
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from huggingface_hub import snapshot_download

    snapshot_download(
        MODEL_ID,
        revision=REVISION,
        local_dir=MODEL_ROOT,
        allow_patterns=["*.json", "*.safetensors", "*.jinja", "README.md"],
        max_workers=3,
    )
    records = []
    for path in sorted(MODEL_ROOT.iterdir()):
        if path.is_file() and path.name not in {"download-manifest.json", "server-session.json"}:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            records.append(
                {"path": path.name, "sha256": digest.hexdigest(), "bytes": path.stat().st_size}
            )
    manifest = {
        "model_id": MODEL_ID,
        "revision": REVISION,
        "quantization": "4-bit affine, group size 64",
        "files": records,
        "runtime": {name: version(name) for name in ("mlx", "mlx-lm", "transformers")},
    }
    (MODEL_ROOT / "download-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"model_root": str(MODEL_ROOT), "bytes": sum(r["bytes"] for r in records)}))


if __name__ == "__main__":
    main()
