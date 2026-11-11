"""Server and disk failures over the loopback fixture. Each ends in a recorded outcome, never a
blind retry of a request the server may have acted on. No weights and no quality claim."""

import errno
import json

import pytest

from benchmarks.evaluation.trials import Coordinator, Ledger, TrialOutcome, build_schedule
from recycleguard.application import command_context
from recycleguard.investigation import evaluation_budgets
from recycleguard.reporting.baseline import MODEL_LOOP_LIMITATION
from recycleguard.storage import BlobStore
from tests.integration.test_a05_baseline import approved_foundation as approved_foundation
from tests.integration.test_model_investigation import native as native
from tests.integration.test_v1_fixed_plan import run
from tests.support.workflow import assess
from tests.unit.test_local_model import server as server


def posts(backend):
    return [call for call in backend.calls if call[0] == "POST"]


def trace_issue_codes(service, spec):
    codes = set()
    for event in service.kernel.list_stream_events(f"stream:{spec.run_id}"):
        if event.event_type.startswith("graph.model.") and event.event_type.endswith(".result"):
            record = json.loads(service.blobs.get(event.payload_blob))
            codes |= {issue["code"] for issue in record["issues"]}
    return codes


def test_server_dying_mid_call_fails_the_run_without_a_second_dispatch(native, monkeypatch):
    backend = native[5]
    backend.mode = "drop"
    spec, state, _, _ = run(native, monkeypatch, lambda _: assess().output)
    assert state.status == "FAILED"
    assert len(posts(backend)) == 1
    assert trace_issue_codes(native[0], spec) == {"PROVIDER_TIMEOUT"}


def test_malformed_wire_reply_is_retried_once_and_then_recorded(native, monkeypatch):
    backend = native[5]
    backend.mode = "invalid_wire"
    spec, state, _, _ = run(native, monkeypatch, lambda _: assess().output)
    assert state.stop_reason == "PROVIDER_FAILURE" and state.budget.retries == 1
    assert len(posts(backend)) == 2
    assert trace_issue_codes(native[0], spec) == {"PROVIDER_INVALID_OUTPUT"}
    # The known-invalid reply ends the investigation, not the run: the deterministic report
    # is still drafted and says why.
    assert state.status == "AWAITING_REVIEW"
    report = native[0].latest_report(spec.run_id).report
    assert MODEL_LOOP_LIMITATION in [claim.template_or_text for claim in report.claims]


def test_full_disk_during_a_call_never_redispatches_on_resume(native, monkeypatch):
    service, context, capability, request, config, backend = native
    request = request.model_copy(update={"budgets": evaluation_budgets(config)})
    spec = service.prepare(context, request)
    runner = service.runner(spec)
    real_put = BlobStore.put
    full = {"on": False}

    def put(store, data, media_type):
        if full["on"]:
            raise OSError(errno.ENOSPC, "No space left on device")
        return real_put(store, data, media_type)

    monkeypatch.setattr(BlobStore, "put", put)

    def http(port_http):
        def wrapped(port, method, path, body=None):
            answer = port_http(port, method, path, body)
            if method == "POST":
                full["on"] = True
            return answer

        return wrapped

    from recycleguard.local_model import LocalModelPort

    monkeypatch.setattr(LocalModelPort, "_http", http(LocalModelPort._http))
    try:
        state = runner.start_run(context, spec, capability=capability)
        with pytest.raises(OSError, match="No space left"):
            for _ in range(16):
                state = runner.advance(
                    command_context(context.actor),
                    spec.run_id,
                    state.version,
                    capability=capability,
                )
        sent = len(posts(backend))
        assert sent == 1
        full["on"] = False
        current = service.store.load(spec.run_id)
        for _ in range(16):
            if current.status in {"FAILED", "AWAITING_REVIEW"}:
                break
            current = runner.advance(
                command_context(context.actor),
                spec.run_id,
                current.version,
                capability=capability,
            )
    finally:
        runner.close()
    assert current.status == "FAILED"
    assert len(posts(backend)) == sent


def test_full_disk_on_the_ledger_leaves_a_resumable_trial_not_a_lost_one(tmp_path):
    schedule = build_schedule(["a"], ("V1", "V2"), 1)
    ledger = Ledger(tmp_path / "ledger.jsonl")
    original = ledger.append

    def no_space(row):
        if row["status"] == "SUCCESS":
            raise OSError(errno.ENOSPC, "No space left on device")
        original(row)

    ledger.append = no_space
    with pytest.raises(OSError, match="No space left"):
        Coordinator(
            schedule, ledger, lambda _: TrialOutcome(status="SUCCESS"), tmp_path / "K"
        ).run()
    assert [row["status"] for row in ledger.rows()] == ["STARTED"]

    resumed = Ledger(tmp_path / "ledger.jsonl")
    Coordinator(schedule, resumed, lambda _: TrialOutcome(status="SUCCESS"), tmp_path / "K").run()
    statuses = [row["status"] for row in resumed.rows()]
    assert "INTERRUPTED" in statuses and resumed.terminal() == {s.trial_id for s in schedule}


def test_repeated_infrastructure_failures_stop_the_schedule(tmp_path):
    schedule = build_schedule(["a", "b", "c"], ("V1", "V2"), 1)
    ledger = Ledger(tmp_path / "ledger.jsonl")

    def server_gone(_):
        raise ConnectionRefusedError("model server is not running")

    summary = Coordinator(schedule, ledger, server_gone, tmp_path / "K").run()
    assert summary.stopped_because == "INFRASTRUCTURE_FAILURES" and summary.completed == 3
    assert {row["status"] for row in ledger.rows()} == {"STARTED", "INFRA_FAILED"}
