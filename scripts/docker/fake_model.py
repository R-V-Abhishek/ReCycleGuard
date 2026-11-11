"""Pipeline check without a GPU: a fixed-reply server shaped like llama-server. Not evidence.

Writes a synthetic provenance folder and configuration whose model id starts with ``fixture/``, so
run_trials.py labels the session as fixture output. No weights are involved.
"""

import hashlib
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmarks.evaluation.trial_fixture import FakeModel  # noqa: E402
from recycleguard.local_model import (  # noqa: E402
    FIXTURE_MODEL_PREFIX,
    LLAMA_SERVER_FLAGS,
    LocalModelConfig,
)

PROVENANCE = Path("/models/provenance/fixture")
BUILD = "b12033"


def write_provenance():
    PROVENANCE.mkdir(parents=True, exist_ok=True)
    tokenizer = PROVENANCE / "tokenizer.json"
    tokenizer.write_text(
        json.dumps(
            {
                "model": {"type": "BPE"},
                "pre_tokenizer": {"type": "Sequence", "pretokenizers": [{"type": "ByteLevel"}]},
            }
        )
    )
    template = PROVENANCE / "chat_template.jinja"
    template.write_text("Synthetic fixture template; no model is loaded.")
    manifest = PROVENANCE / "download-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "model_id": FIXTURE_MODEL_PREFIX + "not-a-model",
                "revision": "0" * 40,
                "quantization": "none",
                "runtime": {"llama.cpp": BUILD},
                "files": [
                    {
                        "path": path.name,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "bytes": path.stat().st_size,
                    }
                    for path in (tokenizer, template)
                ],
            }
        )
    )
    lock = PROVENANCE / "runtime-lock.env"
    lock.write_text("LLAMA_BUILD=fixture\n")
    config = LocalModelConfig(
        configuration_id="configuration:docker_fixture",
        backend="llama_cpp",
        model_id=FIXTURE_MODEL_PREFIX + "not-a-model",
        model_path=PROVENANCE,
        model_revision="0" * 40,
        weights_manifest_path=manifest,
        weights_manifest_digest=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        runtime_lock_path=lock,
        runtime_lock_digest=hashlib.sha256(lock.read_bytes()).hexdigest(),
        runtime_version=BUILD,
        endpoint="http://127.0.0.1:8766/v1/completions",
        max_output_tokens=1024,
        max_total_tokens=32768,
        timeout_seconds=60.0,
        server_flags=LLAMA_SERVER_FLAGS,
    )
    (PROVENANCE / "server-session.json").write_text(
        json.dumps({"server_flags": LLAMA_SERVER_FLAGS})
    )
    (PROVENANCE / "local-model.json").write_text(config.model_dump_json(indent=2))


class Handler(BaseHTTPRequestHandler):
    fake = FakeModel()

    def log_message(self, format, *args):
        pass

    def send(self, value):
        payload = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self.send(
            {
                "object": "list",
                "data": [
                    {"id": str(PROVENANCE), "object": "model", "created": 1, "owned_by": "fixture"}
                ],
                "models": [],
            }
        )

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.send(
            {
                "id": "cmpl-fixture",
                "object": "text_completion",
                "created": 1,
                "model": request["model"],
                "system_fingerprint": f"{BUILD}-fixture",
                "choices": [
                    {
                        "index": 0,
                        "logprobs": None,
                        "finish_reason": "stop",
                        "text": json.dumps(self.fake.reply(request["prompt"])),
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 80,
                    "total_tokens": 180,
                    "prompt_tokens_details": {"cached_tokens": 0},
                },
                "timings": {"predicted_ms": 1.0},
            }
        )


if __name__ == "__main__":
    write_provenance()
    ThreadingHTTPServer(("127.0.0.1", 8766), Handler).serve_forever()
