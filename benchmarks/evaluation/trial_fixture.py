"""Loopback fake backend for dry runs. Fixed JSON; it says nothing about model quality."""

import json
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

USER, END = "<|im_start|>user\n", "<|im_end|>\n<|im_start|>assistant"
ADAPTIVE_CHECKS = (
    ("compute_reconciliation", {"bucket_ids": []}),
    ("inspect_evidence", {"observation_ids": []}),
    ("search_rules", {"query": "extended producer responsibility certificate"}),
)


class FakeModel:
    """Serial fixture backend that records the byte size of every exact prompt."""

    def __init__(self):
        self.sizes, self.plans, self.lock = [], Counter(), threading.Lock()

    def reply(self, prompt):
        with self.lock:
            self.sizes.append(len(prompt.encode("utf-8")))
            payload = json.loads(prompt[prompt.index(USER) + len(USER) : prompt.index(END)])
            if payload["phase"] == "ASSESS":
                return {
                    "verdict": "UNKNOWN",
                    "weak_result_or_mistake": "Fixture assessment only.",
                    "next_check_or_stop": "continue",
                    "disposition": "CONTINUE",
                    "revised_plan": None,
                }
            step = self.plans[payload["run_id"]]
            self.plans[payload["run_id"]] += 1
            draft = {
                "objective": "Fixture plan.",
                "hypotheses": ["Fixture hypothesis."],
                "proposed_checks": ["Fixture check."],
                "expected_evidence": ["Fixture evidence."],
                "stopping_criteria": ["Fixture stop."],
            }
            if step >= len(ADAPTIVE_CHECKS):
                return {"plan": draft, "action": None, "stop_reason": "NO_NEW_EVIDENCE"}
            operation, arguments = ADAPTIVE_CHECKS[step]
            return {
                "plan": draft,
                "action": {
                    "action_kind": "CHECK",
                    "allowed_operation": operation,
                    "typed_arguments": arguments,
                    "finding_id": payload["pending_findings"][0],
                    "concise_reason": "Fixture reason.",
                    "evidence_refs": [],
                },
                "stop_reason": None,
            }


def serve(fake, model_path):
    class Handler(BaseHTTPRequestHandler):
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
                {"object": "list", "data": [{"id": model_path, "object": "model", "created": 1}]}
            )

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send(
                {
                    "id": "cmpl-fixture",
                    "object": "text_completion",
                    "created": 1,
                    "model": request["model"],
                    "system_fingerprint": "0.32.2-fixture",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "text": json.dumps(fake.reply(request["prompt"])),
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 80,
                        "total_tokens": 180,
                        "prompt_tokens_details": {"cached_tokens": 0},
                    },
                }
            )

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
