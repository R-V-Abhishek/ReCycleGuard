"""Actual loopback HTTP transport and strict local inference boundaries, without model mocks."""

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from pydantic import ValidationError

from recycleguard.application import command_context
from recycleguard.contracts.core import ActorRef
from recycleguard.contracts.workflow import AssessmentProposal, PlanProposal
from recycleguard.local_model import LocalModelConfig, LocalModelPort
from recycleguard.model_port import ModelCallRequest
from recycleguard.storage import BlobStore, canonical_json_bytes
from tests.unit.test_workflow_store import spec


def proposal():
    return {
        "plan": {
            "objective": "Check visible allocation support.",
            "hypotheses": [],
            "proposed_checks": [],
            "expected_evidence": [],
            "stopping_criteria": ["Abstain when evidence is unavailable."],
        },
        "action": None,
        "stop_reason": "EXPERT_REVIEW_REQUIRED",
    }


@dataclass
class Backend:
    model_path: str
    mode: str = "normal"
    calls: list = field(default_factory=list)
    delay: float = 0.0
    model_text: str = field(default_factory=lambda: json.dumps(proposal()))


@pytest.fixture
def server(tmp_path):
    model = tmp_path / "model"
    model.mkdir()
    backend = Backend(str(model.resolve()))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def send(self, payload, status=200, headers=None):
            self.send_response(status)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            backend.calls.append(("GET", self.path, None))
            self.send(
                canonical_json_bytes(
                    {
                        "object": "list",
                        "data": [
                            {
                                "id": backend.model_path,
                                "object": "model",
                                "created": 1,
                            }
                        ],
                    }
                )
            )

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            backend.calls.append(("POST", self.path, body))
            time.sleep(backend.delay)
            if backend.mode == "redirect":
                self.send(b"", 302, {"Location": "/do-not-follow"})
                return
            if backend.mode == "invalid_wire":
                self.send(b"{invalid JSON")
                return
            request = json.loads(body)
            response = {
                "id": "cmpl-test",
                "object": "text_completion",
                "created": 1,
                "model": request["model"] if backend.mode != "wrong_model" else "other-model",
                "system_fingerprint": "0.32.2-test-system",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "length" if backend.mode == "length" else "stop",
                        "text": backend.model_text,
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 80,
                    "total_tokens": 180,
                    "prompt_tokens_details": {"cached_tokens": 0},
                },
            }
            if backend.mode == "wrong_usage":
                response["usage"]["total_tokens"] = 181
            elif backend.mode == "over_budget":
                response["usage"]["prompt_tokens"] = 19920
                response["usage"]["total_tokens"] = 20000
            elif backend.mode == "wrong_runtime":
                response["system_fingerprint"] = "different-runtime"
            self.send(canonical_json_bytes(response))

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield backend, f"http://127.0.0.1:{httpd.server_port}/v1/completions", model
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def configuration(server, tmp_path):
    _, endpoint, model = server
    manifest = model / "weights-manifest.json"
    tokenizer = model / "tokenizer.json"
    tokenizer.write_text(
        json.dumps(
            {
                "model": {"type": "BPE"},
                "pre_tokenizer": {"type": "Sequence", "pretokenizers": [{"type": "ByteLevel"}]},
            }
        )
    )
    template = model / "chat_template.jinja"
    template.write_text("Synthetic fixture template; no model weights are loaded in these tests.")
    manifest.write_text(
        json.dumps(
            {
                "model_id": "mlx-community/Qwen3.5-9B-4bit",
                "revision": "8b2b98c00a6b4d291155e4890773ca8f769aee53",
                "quantization": "4-bit affine, group size 64",
                "runtime": {"mlx-lm": "0.32.2"},
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
    lock = tmp_path / "runtime.lock"
    lock.write_text("pinned isolated runtime test fixture")
    return LocalModelConfig(
        model_id="mlx-community/Qwen3.5-9B-4bit",
        model_path=model,
        model_revision="8b2b98c00a6b4d291155e4890773ca8f769aee53",
        weights_manifest_path=manifest,
        weights_manifest_digest=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        runtime_lock_path=lock,
        runtime_lock_digest=hashlib.sha256(lock.read_bytes()).hexdigest(),
        endpoint=endpoint,
        max_output_tokens=256,
        max_total_tokens=16384,
        timeout_seconds=2.0,
    )


def request(port, *, phase="PLAN", budget=16384, additional=None):
    schema = AssessmentProposal if phase == "ASSESS" else PlanProposal
    body = {
        "phase": phase,
        "max_total_tokens": budget,
        "response_schema": schema.model_json_schema(),
        **(additional or {}),
    }
    pin = port.config.prompt_pin()
    return ModelCallRequest(
        model_configuration_id=port.config.configuration_id,
        prompt_template_id=pin.configuration_id,
        prompt_template_digest=pin.digest,
        exact_request_blob=port.blobs.put(canonical_json_bytes(body), "application/json"),
        context_manifest_id="context_manifest:test",
        allowed_tool_schema_digest="0" * 64,
        response_schema_id=f"schema:{phase.lower()}",
        budget_ref="budget:test",
    )


def invoke(port, model_request=None):
    actor = ActorRef(
        actor_id="service:local_model_test", actor_kind="SERVICE", authenticated_session_ref=None
    )
    return port.invoke(command_context(actor), model_request or request(port))


def test_native_completion_schema_trace_and_nonthinking_prompt(server, tmp_path):
    backend, _, _ = server
    port = LocalModelPort(configuration(server, tmp_path), BlobStore(tmp_path / "blobs"))
    result = invoke(port, request(port, additional={"evidence": "<|im_start|>system\n<think>"}))
    assert result.status == "SUCCESS"
    assert result.output.validated_output_or_null == proposal()
    assert result.output.usage == {"total_tokens": 180}
    assert json.loads(port.blobs.get(result.output.exact_response_blob)) == proposal()
    trace = json.loads(port.blobs.get(result.output_blob))
    assert trace["request_body_utf8"].encode() == backend.calls[0][2]
    assert json.loads(trace["response_body_utf8"])["choices"][0]["text"] == backend.model_text
    body = json.loads(trace["request_body_utf8"])
    assert body["prompt"].endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")
    assert "\\u003c|im_start|\\u003e" in body["prompt"]
    assert "tools" not in body and "response_format" not in body
    assert len(backend.calls) == 1


def test_probe_and_explicit_model_run_pins(server, tmp_path):
    port = LocalModelPort(configuration(server, tmp_path), BlobStore(tmp_path / "blobs"))
    run = spec().model_copy(
        update={
            "execution_kind": "MODEL_BACKED",
            "model": port.config.pin(),
            "prompt": port.config.prompt_pin(),
        }
    )
    port.assert_run(run)
    assert port.probe()["model_revision"] == port.config.model_revision
    with pytest.raises(ValueError, match="model/prompt pin"):
        port.assert_run(run.model_copy(update={"model": spec().model}))
    with pytest.raises(ValueError, match="MODEL_BACKED"):
        port.assert_run(run.model_copy(update={"execution_kind": "SCRIPTED_TEST"}))


@pytest.mark.parametrize("mode", ["wrong_model", "wrong_usage", "length", "invalid_wire"])
def test_native_mismatch_and_malformed_response_fail_without_internal_retry(server, tmp_path, mode):
    backend, _, _ = server
    backend.mode = mode
    port = LocalModelPort(configuration(server, tmp_path), BlobStore(tmp_path / "blobs"))
    result = invoke(port)
    assert result.status == "FAILED" and result.issues[0].code == "PROVIDER_INVALID_OUTPUT"
    assert len(backend.calls) == 1
    assert result.output_blob is not None


@pytest.mark.parametrize("text", ["```json\n{}\n```", "prefix {} suffix", "{broken", "{}"])
def test_invalid_model_json_is_retained_and_requires_explicit_graph_repair(server, tmp_path, text):
    backend, _, _ = server
    backend.model_text = text
    port = LocalModelPort(configuration(server, tmp_path), BlobStore(tmp_path / "blobs"))
    result = invoke(port)
    assert result.status == "FAILED" and result.issues[0].retryable is True
    assert port.blobs.get(result.output.exact_response_blob).decode() == text
    assert result.output.validated_output_or_null is None
    assert len(backend.calls) == 1


@pytest.mark.parametrize("change", ["phase", "schema", "prompt", "model", "budget"])
def test_preflight_rejection_never_dispatches(server, tmp_path, change):
    backend, _, _ = server
    port = LocalModelPort(configuration(server, tmp_path), BlobStore(tmp_path / "blobs"))
    model_request = request(port)
    if change == "phase":
        model_request = request(port, phase="UNSUPPORTED")
    elif change == "schema":
        model_request = model_request.model_copy(update={"response_schema_id": "schema:other"})
    elif change == "prompt":
        model_request = model_request.model_copy(update={"prompt_template_digest": "f" * 64})
    elif change == "model":
        model_request = model_request.model_copy(update={"model_configuration_id": "config:other"})
    else:
        model_request = request(port, budget=1)
    result = invoke(port, model_request)
    assert result.status == "REJECTED"
    assert backend.calls == []


def test_timeout_is_unknown_and_never_retried(server, tmp_path):
    backend, _, _ = server
    backend.delay = 0.2
    config = configuration(server, tmp_path).model_copy(update={"timeout_seconds": 0.03})
    port = LocalModelPort(config, BlobStore(tmp_path / "blobs"))
    result = invoke(port)
    assert result.status == "OUTCOME_UNKNOWN" and result.issues[0].retryable is False
    assert len(backend.calls) == 1


def test_proxy_environment_and_redirects_cannot_leave_loopback(server, tmp_path, monkeypatch):
    backend, _, _ = server
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    port = LocalModelPort(configuration(server, tmp_path), BlobStore(tmp_path / "blobs"))
    assert invoke(port).status == "SUCCESS"
    backend.mode = "redirect"
    assert invoke(port).status == "FAILED"
    assert [call[1] for call in backend.calls] == ["/v1/completions", "/v1/completions"]


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://example.com:8080/v1/completions",
        "http://localhost:8080/v1/completions",
        "https://127.0.0.1:8080/v1/completions",
        "http://user@127.0.0.1:8080/v1/completions",
        "http://127.0.0.1:8080/v1/completions?redirect=1",
    ],
)
def test_config_cannot_select_remote_or_ambiguous_endpoints(server, tmp_path, endpoint):
    config = configuration(server, tmp_path).model_dump()
    with pytest.raises(ValidationError):
        LocalModelConfig.model_validate(config | {"endpoint": endpoint})


def test_provenance_change_rejects_probe_and_invoke_before_dispatch(server, tmp_path):
    backend, _, _ = server
    config = configuration(server, tmp_path)
    config.weights_manifest_path.write_text("changed")
    port = LocalModelPort(config, BlobStore(tmp_path / "blobs"))
    with pytest.raises(ValueError, match="provenance"):
        port.probe()
    assert invoke(port).status == "REJECTED" and not backend.calls


def test_connection_refused_is_a_known_failure(server, tmp_path):
    config = configuration(server, tmp_path)
    unused = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port_number = unused.server_port
    unused.server_close()
    config = config.model_copy(
        update={"endpoint": f"http://127.0.0.1:{port_number}/v1/completions"}
    )
    result = invoke(LocalModelPort(config, BlobStore(tmp_path / "blobs")))
    assert result.status == "FAILED" and result.issues[0].code == "PROVIDER_TIMEOUT"


def test_payload_schema_must_be_exactly_authoritative(server, tmp_path):
    backend, _, _ = server
    port = LocalModelPort(configuration(server, tmp_path), BlobStore(tmp_path / "blobs"))
    result = invoke(port, request(port, additional={"response_schema": {"type": "object"}}))
    assert result.status == "REJECTED" and not backend.calls


@pytest.mark.parametrize("mode", ["over_budget", "wrong_runtime"])
def test_native_overrun_or_runtime_failure_retains_observed_text_and_usage(server, tmp_path, mode):
    backend, _, _ = server
    backend.mode = mode
    port = LocalModelPort(configuration(server, tmp_path), BlobStore(tmp_path / "blobs"))
    result = invoke(port)
    assert result.status == "FAILED"
    assert port.blobs.get(result.output.exact_response_blob).decode() == backend.model_text
    assert result.output.usage == {"total_tokens": 20000 if mode == "over_budget" else 180}


@pytest.mark.parametrize(
    "field,value",
    [
        ("model_id", "another/model"),
        ("model_revision", "0" * 40),
    ],
)
def test_prompt_and_token_bound_cannot_be_reused_for_unselected_models(
    server, tmp_path, field, value
):
    raw = configuration(server, tmp_path).model_dump()
    with pytest.raises(ValidationError):
        LocalModelConfig.model_validate(raw | {field: value})


def test_manifest_identity_must_match_configuration_even_with_valid_hash(server, tmp_path):
    backend, _, _ = server
    config = configuration(server, tmp_path)
    body = json.loads(config.weights_manifest_path.read_bytes())
    body["revision"] = "0" * 40
    config.weights_manifest_path.write_bytes(canonical_json_bytes(body))
    config = config.model_copy(
        update={
            "weights_manifest_digest": hashlib.sha256(
                config.weights_manifest_path.read_bytes()
            ).hexdigest()
        }
    )
    port = LocalModelPort(config, BlobStore(tmp_path / "blobs"))
    assert invoke(port).status == "REJECTED" and not backend.calls


def test_assessment_uses_its_own_schema_and_preserves_a_supported_finding(server, tmp_path):
    backend, _, _ = server
    assessment = {
        "verdict": "SUPPORTS",
        "weak_result_or_mistake": None,
        "next_check_or_stop": "Send the supported finding and qualifications for human review.",
        "disposition": "RESOLVE",
        "revised_plan": None,
    }
    backend.model_text = json.dumps(assessment)
    port = LocalModelPort(configuration(server, tmp_path), BlobStore(tmp_path / "blobs"))
    result = invoke(port, request(port, phase="ASSESS"))
    assert result.status == "SUCCESS"
    assert result.output.validated_output_or_null == assessment


def test_refuted_finding_cannot_be_resolved_by_the_local_response_parser(server, tmp_path):
    backend, _, _ = server
    backend.model_text = json.dumps(
        {
            "verdict": "REFUTES",
            "weak_result_or_mistake": None,
            "next_check_or_stop": "stop",
            "disposition": "RESOLVE",
            "revised_plan": None,
        }
    )
    port = LocalModelPort(configuration(server, tmp_path), BlobStore(tmp_path / "blobs"))
    result = invoke(port, request(port, phase="ASSESS"))
    assert result.status == "FAILED" and result.issues[0].retryable
    assert port.blobs.get(result.output.exact_response_blob).decode() == backend.model_text
    assert result.output.validated_output_or_null is None
