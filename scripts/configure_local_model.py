"""Write explicit machine-local inference configuration after the pinned download.

``--constrained`` writes a separate configuration whose pin records the constrained server mode.
``--llama-cpp <model-root>`` configures the Docker backend from what ``model-download`` recorded.
"""

import hashlib
import json
import sys
from pathlib import Path

from recycleguard.local_model import (
    CONSTRAINED_FLAG,
    LLAMA_CPP,
    LLAMA_SERVER_FLAGS,
    SERVER_FLAGS,
    LocalModelConfig,
)

ROOT = Path(__file__).resolve().parents[1]
LLAMA_ENDPOINT = "http://127.0.0.1:8766/v1/completions"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def llama_cpp_config(model, constrained):
    manifest_path = model / "download-manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    lock = model / "runtime-lock.env"
    return LocalModelConfig(
        configuration_id="configuration:pc_llama_cpp",
        backend=LLAMA_CPP,
        model_id=manifest["model_id"],
        model_path=model,
        model_revision=manifest["revision"],
        weights_manifest_path=manifest_path,
        weights_manifest_digest=digest(manifest_path),
        runtime_lock_path=lock,
        runtime_lock_digest=digest(lock),
        runtime_version=manifest["runtime"]["llama.cpp"],
        endpoint=LLAMA_ENDPOINT,
        max_output_tokens=1024,
        max_total_tokens=32768,
        timeout_seconds=180.0,
        server_flags=[*LLAMA_SERVER_FLAGS, *([CONSTRAINED_FLAG] if constrained else [])],
    )


def mlx_config(constrained):
    model = ROOT / ".recycleguard/models/qwen3.5-9b-4bit"
    manifest = model / "download-manifest.json"
    lock = ROOT / "tools/local-model/uv.lock"
    return LocalModelConfig(
        model_id="mlx-community/Qwen3.5-9B-4bit",
        model_path=model,
        model_revision="8b2b98c00a6b4d291155e4890773ca8f769aee53",
        weights_manifest_path=manifest,
        weights_manifest_digest=digest(manifest),
        runtime_lock_path=lock,
        runtime_lock_digest=digest(lock),
        endpoint="http://127.0.0.1:8766/v1/completions",
        max_output_tokens=1024,
        max_total_tokens=32768,
        timeout_seconds=180.0,
        server_flags=[*SERVER_FLAGS, *([CONSTRAINED_FLAG] if constrained else [])],
    )


def main():
    arguments = sys.argv[1:]
    constrained = "--constrained" in arguments
    arguments = [argument for argument in arguments if argument != "--constrained"]
    name = "local-model-constrained.json" if constrained else "local-model.json"
    if len(arguments) == 2 and arguments[0] == "--llama-cpp":
        model = Path(arguments[1])
        config, target = llama_cpp_config(model, constrained), model / name
    elif not arguments:
        config, target = mlx_config(constrained), ROOT / ".recycleguard" / name
    else:
        raise SystemExit("usage: configure_local_model.py [--constrained] [--llama-cpp <root>]")
    target.write_text(config.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Wrote explicit local backend configuration: {target}")


if __name__ == "__main__":
    main()
