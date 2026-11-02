"""Optional loopback server that keeps every reply viable for its JSON Schema. Off by default.

Started only by ``serve.py --constrained``, and the pin records that flag, so a constrained run can
never pass for an unconstrained one. It answers the same two routes the application uses and the
same response shape as ``mlx_lm server``. A request without ``response_schema`` is refused rather
than decoded freely. One request at a time, as the pinned server flags require.

Written without access to MLX: its first run on the Mac is its first real test.
"""

import json
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from constrained_json import SchemaMatcher, choose_token

_MAX_REQUEST_BYTES = 8_000_000
_CANDIDATES = 2048


def constraint_processor(matcher, tokenizer, prompt_length, stop_tokens):
    """An mlx-lm logits processor: everything but the chosen token becomes impossible."""
    import mlx.core as mx

    def decode(token):
        return tokenizer.decode([token])

    def process(tokens, logits):
        generated = tokens[prompt_length:].tolist()
        text = tokenizer.decode(generated) if generated else ""
        ranked = mx.argsort(-logits, axis=-1).reshape(-1)[:_CANDIDATES].tolist()
        # Stop tokens may rank below the candidate cut, so they are always considered.
        ranked += [token for token in sorted(stop_tokens) if token not in ranked]
        chosen = choose_token(matcher, text, ranked, decode, stop_tokens)
        if chosen is None:
            # Nothing can continue the reply: stop, and let the application's validation fail it.
            chosen = min(stop_tokens)
        mask = mx.full(logits.shape, float("-inf"))
        mask[..., chosen] = 0.0
        return logits + mask

    return process


def stop_token_ids(tokenizer, stop_sequences):
    ids = {tokenizer.eos_token_id} if tokenizer.eos_token_id is not None else set()
    for sequence in stop_sequences:
        encoded = tokenizer.encode(sequence, add_special_tokens=False)
        if len(encoded) == 1:
            ids.add(encoded[0])
    if not ids:
        raise ValueError("no stop token could be resolved")
    return ids


def generate(model, tokenizer, request, runtime_version):
    from mlx_lm import stream_generate
    from mlx_lm.sample_utils import make_sampler

    schema = request.get("response_schema")
    if not isinstance(schema, dict):
        raise ValueError("constrained server requires response_schema")
    prompt = tokenizer.encode(request["prompt"], add_special_tokens=False)
    stop_tokens = stop_token_ids(tokenizer, request.get("stop") or [])
    processor = constraint_processor(SchemaMatcher(schema), tokenizer, len(prompt), stop_tokens)
    text, completion_tokens, finish = "", 0, "length"
    for piece in stream_generate(
        model,
        tokenizer,
        prompt,
        max_tokens=request["max_tokens"],
        sampler=make_sampler(temp=0.0),
        logits_processors=[processor],
    ):
        completion_tokens = piece.generation_tokens
        if piece.token in stop_tokens:
            finish = "stop"
            break
        text += piece.text
    return {
        "id": f"cmpl-{uuid.uuid4().hex}",
        "object": "text_completion",
        "created": int(time.time()),
        "model": request["model"],
        "system_fingerprint": f"{runtime_version}-constrained",
        "choices": [{"index": 0, "finish_reason": finish, "text": text}],
        "usage": {
            "prompt_tokens": len(prompt),
            "completion_tokens": completion_tokens,
            "total_tokens": len(prompt) + completion_tokens,
        },
    }


def main(model_path, port, runtime_version):
    from mlx_lm import load

    model, tokenizer = load(model_path)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def _send(self, status, value):
            payload = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path != "/v1/models":
                self._send(404, {"error": "not found"})
                return
            self._send(
                200,
                {
                    "object": "list",
                    "data": [{"id": model_path, "object": "model", "created": int(time.time())}],
                },
            )

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            if self.path != "/v1/completions" or length > _MAX_REQUEST_BYTES:
                self._send(404, {"error": "not found"})
                return
            request = json.loads(self.rfile.read(length))
            if not lock.acquire(blocking=False):
                self._send(429, {"error": "one request at a time"})
                return
            try:
                self._send(200, generate(model, tokenizer, request, runtime_version))
            except (KeyError, TypeError, ValueError) as exc:
                self._send(400, {"error": str(exc)})
            finally:
                lock.release()

    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), sys.argv[3])
