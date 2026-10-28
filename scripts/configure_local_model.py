"""Write explicit machine-local inference configuration after the pinned download."""

import hashlib
from pathlib import Path

from recycleguard.local_model import LocalModelConfig

ROOT = Path(__file__).resolve().parents[1]


def main():
    model = ROOT / ".recycleguard/models/qwen3.5-9b-4bit"
    manifest = model / "download-manifest.json"
    lock = ROOT / "tools/local-model/uv.lock"
    config = LocalModelConfig(
        model_id="mlx-community/Qwen3.5-9B-4bit",
        model_path=model,
        model_revision="8b2b98c00a6b4d291155e4890773ca8f769aee53",
        weights_manifest_path=manifest,
        weights_manifest_digest=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        runtime_lock_path=lock,
        runtime_lock_digest=hashlib.sha256(lock.read_bytes()).hexdigest(),
        endpoint="http://127.0.0.1:8766/v1/completions",
        max_output_tokens=1024,
        max_total_tokens=32768,
        timeout_seconds=180.0,
    )
    target = ROOT / ".recycleguard/local-model.json"
    target.write_text(config.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Wrote explicit local backend configuration: {target}")


if __name__ == "__main__":
    main()
