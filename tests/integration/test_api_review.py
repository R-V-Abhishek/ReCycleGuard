"""Regression checks for the S_ui integration's authoritative HTTP boundaries."""

import time
from dataclasses import replace

from recycleguard.api.trace import trace_events
from recycleguard.investigation import InvestigationService
from tests.integration.test_a05_baseline import approved_foundation as approved_foundation
from tests.integration.test_a06_workflow import workflow as workflow
from tests.integration.test_api import BASE, PASSWORD, checked
from tests.integration.test_api import api as api
from tests.support.workflow import assess, plan


def ready_run(api):
    dossier = checked(api.post(BASE + "/dossiers/select", json={"fixture_id": "case_001"}), 201)
    path = BASE + "/dossiers/" + dossier["dossier_id"]
    draft = checked(api.post(path + "/prepare"))
    checked(
        api.post(BASE + "/reviewer", json={"actor_id": "human:api_review", "password": PASSWORD}),
        201,
    )
    checked(
        api.post(
            path + "/review-foundation",
            json={
                "password": PASSWORD,
                "candidate_digest": draft["candidate_digest"],
                "accepted_qualifications": "Synthetic UI integration review; uncertainty retained.",
            },
        )
    )
    run = checked(
        api.post(
            BASE + "/runs",
            json={
                "dossier_id": dossier["dossier_id"],
                "mode": "SCRIPTED_TEST",
                "budgets": {"max_model_calls": 7},
            },
        ),
        202,
    )
    route = BASE + "/runs/" + run["run_id"]
    for _ in range(200):
        current = checked(api.get(route))
        if current["job"]["status"] not in {"RUNNING", "QUEUED"}:
            assert current["state"]["status"] == "AWAITING_REVIEW", current
            return dossier, route, current
        time.sleep(0.05)
    raise AssertionError("scripted API fixture failed to pause")


def test_openapi_has_response_contracts_for_every_json_route(api):
    schema = checked(api.get("/openapi.json"))
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            if method not in {"get", "post"}:
                continue
            for status, response in operation["responses"].items():
                if not status.startswith("2"):
                    continue
                for content_type, content in response.get("content", {}).items():
                    if content_type == "application/json":
                        assert content["schema"], f"untyped response: {method} {path}"


def test_run_configuration_and_listing_survive_client_memory_loss(api):
    dossier, route, current = ready_run(api)
    configuration = current["configuration"]
    assert configuration["execution_kind"] == "SCRIPTED_TEST"
    assert configuration["budgets"]["max_model_calls"] == 7
    assert configuration["budgets"]["tools_per_finding"] == 8
    assert configuration["case_snapshot"]["membership_digest"]
    assert configuration["model_configuration_id"] and configuration["prompt_configuration_id"]
    listed = checked(api.get(BASE + "/runs", params={"dossier_id": dossier["dossier_id"]}))
    assert listed["runs"] == [checked(api.get(route))]
    assert (
        checked(api.get(BASE + "/runs"))["runs"][0]["state"]["run_id"] == current["state"]["run_id"]
    )
    assert api.get(BASE + "/runs", params={"dossier_id": "unknown"}).status_code == 404


def test_committed_review_recovers_after_projection_response_failure(api, monkeypatch):
    _, route, _ = ready_run(api)
    packet = checked(api.post(route + "/packet"))
    original = InvestigationService.project_review
    interrupted = []

    def fail_once(self, context, packet_id):
        if not interrupted:
            interrupted.append(True)
            raise RuntimeError("simulated response interruption after decision commit")
        return original(self, context, packet_id)

    monkeypatch.setattr(InvestigationService, "project_review", fail_once)
    response = api.post(
        route + "/review",
        json={
            "password": PASSWORD,
            "packet_id": packet["packet_id"],
            "expected_dependency_digest": packet["review_dependency_digest"],
            "decision": "APPROVE",
            "reason": "Qualified synthetic paper accepted.",
        },
    )
    assert response.status_code == 500
    recovered = checked(api.get(route))
    assert recovered["state"]["status"] == "COMPLETED"
    assert recovered["state"]["review_outcome"] == "APPROVED"
    assert recovered["job"]["detail"] == "COMPLETED"
    assert checked(api.get(route))["state"] == recovered["state"]


def test_cancel_control_plane_does_not_rebuild_model_or_index(api, monkeypatch):
    _, route, _ = ready_run(api)

    def unavailable(*_args, **_kwargs):
        raise AssertionError("cancellation must not construct a model-backed runner")

    monkeypatch.setattr(InvestigationService, "runner", unavailable)
    checked(api.post(route + "/cancel"), 202)
    cancelled = checked(api.get(route))
    assert cancelled["state"]["status"] == "CANCELLED"
    assert cancelled["job"]["detail"] == "CANCELLED"


def test_trace_reports_exact_retry_attempt_before_and_after_terminal_result(workflow):
    with workflow([replace(plan(), status="FAILED", retryable=True), plan(), assess()]) as env:

        class Service:
            store = env.runner.store
            blobs = env.cases.kernel.blob_store
            kernel = env.cases.kernel

        seen_during_retry = []
        original = env.port.invoke

        def observe_retry(context, request):
            if len(env.port.calls) == 1:
                seen_during_retry.extend(trace_events(Service(), env.spec.run_id))
            return original(context, request)

        env.port.invoke = observe_retry
        state = env.drive(env.start())
        assert state.status == "AWAITING_REVIEW"
        earlier = [event for event in seen_during_retry if event["kind"] == "MODEL_RESULT"]
        assert len(earlier) == 1 and earlier[0]["status"] == "FAILED"
        final = [
            event
            for event in trace_events(Service(), env.spec.run_id)
            if event["event_type"] == "graph.model.plan.result"
        ]
        assert [event["status"] for event in final] == ["FAILED", "SUCCESS"]
        assert final[0]["operation_id"] == final[1]["operation_id"]
        assert final[0]["attempt_id"] != final[1]["attempt_id"]
        assert final[0]["issues"] and final[1]["issues"] == []


def test_busy_redraft_is_rejected_before_human_decision_commits(api, monkeypatch):
    from concurrent.futures import Future

    _, route, _ = ready_run(api)
    packet = checked(api.post(route + "/packet"))
    body = {
        "password": PASSWORD,
        "packet_id": packet["packet_id"],
        "expected_dependency_digest": packet["review_dependency_digest"],
        "decision": "REQUEST_CHANGES",
        "reason": "Please clarify the unresolved scope.",
    }
    # Simulate the finished worker still tearing down its resources. No graph
    # mutation is active, but the executor cannot yet accept the redraft.
    with monkeypatch.context() as patch:
        patch.setattr(Future, "done", lambda _self: False)
        rejected = api.post(route + "/review", json=body)
        assert rejected.status_code == 409, rejected.text
    unchanged = checked(api.get(route))
    assert unchanged["state"]["review_outcome"] == "PENDING"
    assert unchanged["state"]["status"] == "AWAITING_REVIEW"
    approved = checked(api.post(route + "/review", json={**body, "decision": "APPROVE"}))
    assert approved["review_outcome"] == "APPROVED"
