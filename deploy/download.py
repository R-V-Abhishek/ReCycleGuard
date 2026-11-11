"""Fetch the pinned GGUF and tokenizer files, then record their digests. Stdlib plus the HF client.

Weights and provenance go to separate volumes, so a trial can read the second without the first.
"""

import hashlib
import json
import os
import shutil
from pathlib import Path

from huggingface_hub import hf_hub_download

WEIGHTS = Path("/models/weights")
PROVENANCE = Path("/models/provenance")
TOKENIZER_FILES = ("tokenizer.json", "chat_template.jinja")


def record(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": path.name, "sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def main():
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    settings = {
        line.split("=", 1)[0]: line.split("=", 1)[1].strip()
        for line in Path("/deploy/model.env").read_text("utf-8").splitlines()
        if line and not line.startswith("#")
    }
    root = PROVENANCE / settings["MODEL_SLUG"]
    root.mkdir(parents=True, exist_ok=True)
    gguf = Path(
        hf_hub_download(
            settings["MODEL_REPO"],
            settings["MODEL_FILE"],
            revision=settings["MODEL_REVISION"],
            local_dir=WEIGHTS,
        )
    )
    files = [record(gguf)]
    for name in TOKENIZER_FILES:
        hf_hub_download(
            settings["TOKENIZER_REPO"],
            name,
            revision=settings["TOKENIZER_REVISION"],
            local_dir=root,
        )
        files.append(record(root / name))
    shutil.rmtree(root / ".cache", ignore_errors=True)
    shutil.copyfile("/deploy/model.env", root / "runtime-lock.env")
    manifest = {
        "model_id": settings["MODEL_REPO"],
        "revision": settings["MODEL_REVISION"],
        "quantization": settings["MODEL_QUANTIZATION"],
        "tokenizer_source": settings["TOKENIZER_REPO"],
        "tokenizer_revision": settings["TOKENIZER_REVISION"],
        "files": files,
        "runtime": {"llama.cpp": settings["LLAMA_BUILD"]},
    }
    (root / "download-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"provenance": str(root), "bytes": sum(item["bytes"] for item in files)}))


if __name__ == "__main__":
    main()
