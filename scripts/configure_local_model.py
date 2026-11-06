"""Write explicit machine-local inference configuration after the pinned download.

``--constrained`` writes a separate configuration whose pin records the constrained server mode.
``--llama-cpp <model-root>`` configures the Docker backend from what ``model-download`` recorded.
``--forced-cap N`` writes a separate configuration capped at N model calls, for the MG1 cap check.
``--prompt <version>`` uses ``docs/checkpoints/mg1/prompts/<version>.json`` instead of v7.
``--slots N`` (llama.cpp only) pins a server started with ``SLOTS=N``, for prompt sweeps.
"""

import hashlib
import json
import sys
from pathlib import Path

from recycleguard.local_model import (
    BUILTIN_PROMPT_VERSION,
    CONSTRAINED_FLAG,
    LLAMA_CPP,
    SERVER_FLAGS,
    LocalModelConfig,
    PromptText,
    llama_server_flags,
)

ROOT = Path(__file__).resolve().parents[1]
PROMPT_DIRS = (ROOT / "docs/checkpoints/mg1/prompts", ROOT / "docs/checkpoints/mg2/prompts")


def prompt_file(name):
    """The prompt file of that version, from the MG1 or the MG2 folder."""
    found = [
        folder / f"{name}.json" for folder in PROMPT_DIRS if (folder / f"{name}.json").is_file()
    ]
    if len(found) != 1:
        raise SystemExit(f"expected exactly one prompt file named {name}, found {len(found)}")
    return found[0]


LLAMA_ENDPOINT = "http://127.0.0.1:8766/v1/completions"
USAGE = (
    "usage: configure_local_model.py [--constrained] [--forced-cap N] [--prompt <version>] "
    "[--slots N] [--llama-cpp <root>]"
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def llama_cpp_config(model, constrained, slots=1):
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
        server_flags=[*llama_server_flags(slots), *([CONSTRAINED_FLAG] if constrained else [])],
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


def config_name(*, constrained=False, cap=None, prompt=None, slots=1):
    """Every option changes the name, so no configuration overwrites another."""
    name = "local-model-constrained" if constrained else "local-model"
    name += "-forced-cap" if cap is not None else ""
    name += f"-{prompt}" if prompt not in (None, BUILTIN_PROMPT_VERSION) else ""
    name += f"-s{slots}" if slots != 1 else ""
    return name + ".json"


def with_options(config, *, cap=None, prompt=None):
    fields = config.model_dump()
    if cap is not None:
        fields["max_model_calls"] = cap
    if prompt not in (None, BUILTIN_PROMPT_VERSION):
        # v7 stays the built-in text, so its configurations keep their usual pins.
        text = PromptText.model_validate_json(prompt_file(prompt).read_bytes())
        fields.update(
            prompt=text,
            prompt_version=text.prompt_version,
            prompt_template_id=f"prompt:u01_qwen_{text.prompt_version.removeprefix('u01_')}",
        )
    return LocalModelConfig.model_validate(fields)


def write_llama_cpp(model, *, constrained=False, cap=None, prompt=None, slots=1):
    config = with_options(llama_cpp_config(model, constrained, slots), cap=cap, prompt=prompt)
    target = model / config_name(constrained=constrained, cap=cap, prompt=prompt, slots=slots)
    target.write_text(config.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return target


def take(arguments, flag):
    if flag not in arguments:
        return None
    index = arguments.index(flag)
    if index + 1 >= len(arguments):
        raise SystemExit(USAGE)
    value = arguments[index + 1]
    del arguments[index : index + 2]
    return value


def main():
    arguments = sys.argv[1:]
    constrained = "--constrained" in arguments
    arguments = [argument for argument in arguments if argument != "--constrained"]
    cap = take(arguments, "--forced-cap")
    cap = None if cap is None else int(cap)
    prompt = take(arguments, "--prompt")
    slots = int(take(arguments, "--slots") or "1")
    if len(arguments) == 2 and arguments[0] == "--llama-cpp":
        target = write_llama_cpp(
            Path(arguments[1]), constrained=constrained, cap=cap, prompt=prompt, slots=slots
        )
    elif not arguments and slots == 1:
        config = with_options(mlx_config(constrained), cap=cap, prompt=prompt)
        target = (
            ROOT / ".recycleguard" / config_name(constrained=constrained, cap=cap, prompt=prompt)
        )
        target.write_text(config.model_dump_json(indent=2) + "\n", encoding="utf-8")
    else:
        raise SystemExit(USAGE)
    print(f"Wrote explicit local backend configuration: {target}")


if __name__ == "__main__":
    main()
