"""Local HTTP boundary with real intake/review/audit and server-owned test exchanges."""

import io
import threading
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from recycleguard.api import ApiOptions, create_app
from recycleguard.config import Settings
from recycleguard.contracts.workflow import PlanDraft, PlanProposal
from recycleguard.investigation import ScriptedExchange, ScriptedInvestigator

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/visible"
TOKEN = "api-integration-test-bearer-token-32"
PASSWORD = "reviewer-integration-secret-42"
BASE = "/api/v1"


@pytest.fixture
def api(tmp_path):
    proposal = PlanProposal(
        plan=PlanDraft(
            objective="Preserve unresolved applicability for human review",
            hypotheses=["Source applicability requires qualified review"],
            proposed_checks=["Retain deterministic preflight evidence"],
            expected_evidence=["Frozen original records"],
            stopping_criteria=["Human expertise is required"],
        ),
        action=None,
        stop_reason="EXPERT_REVIEW_REQUIRED",
    )
    options = ApiOptions(
        settings=Settings(data_root=tmp_path, mode="test", enable_test_adapters=True),
        token=TOKEN,
        test_exchanges=(ScriptedExchange(phase="PLAN", response=proposal.model_dump(mode="json")),),
    )
    with TestClient(create_app(options), raise_server_exceptions=False) as client:
        client.headers["Authorization"] = "Bearer " + TOKEN
        yield client


def checked(response, code=200):
    assert response.status_code == code, response.text
    return response.json()


def test_bearer_and_client_control_boundaries(api):
    assert api.get(BASE + "/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
    anonymous = TestClient(api.app, raise_server_exceptions=False)
    assert anonymous.get(BASE + "/health").status_code == 401
    assert checked(api.get(BASE + "/health"))["ui_implemented"] is False
    agent = checked(api.get(BASE + "/agent"))
    assert agent["configured"] is False and agent["model_id"] is None
    assert set(agent["response_schemas"]) == {"PLAN", "ASSESS"}
    assert agent["response_schemas"]["PLAN"] == PlanProposal.model_json_schema()

    assert (
        api.post(BASE + "/dossiers/select", json={"fixture_id": "../../outside"}).status_code == 404
    )
    for extra in (
        {"actor": {"actor_id": "human:spoof"}},
        {"local_model_config": {"endpoint": "http://remote.invalid"}},
        {"scripted_exchanges": []},
    ):
        response = api.post(
            BASE + "/runs", json={"dossier_id": "dossier:any", "mode": "SCRIPTED_TEST", **extra}
        )
        assert response.status_code == 422, response.text


def test_safe_zip_upload_rejects_traversal_and_oversize(api):
    bad = io.BytesIO()
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("../outside.txt", "untrusted")
    response = api.post(
        BASE + "/dossiers", content=bad.getvalue(), headers={"Content-Type": "application/zip"}
    )
    assert response.status_code == 422, response.text
    assert "unsafe" in response.text.lower()
    oversized = api.post(
        BASE + "/dossiers",
        content=b"0" * (25 * 1024 * 1024 + 1),
        headers={"Content-Type": "application/zip"},
    )
    assert oversized.status_code == 413, oversized.text
    good = io.BytesIO()
    with zipfile.ZipFile(good, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((FIXTURES / "case_001").rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(FIXTURES / "case_001"))
    uploaded = checked(
        api.post(
            BASE + "/dossiers", content=good.getvalue(), headers={"Content-Type": "application/zip"}
        ),
        201,
    )
    assert uploaded["status"] == "UPLOADED"
    assert checked(api.get(BASE + "/dossiers/" + uploaded["dossier_id"]))["status"] == "UPLOADED"


def test_prepare_authenticated_exact_review_background_trace_report_and_decision(api):
    fixtures = checked(api.get(BASE + "/dossiers"))["fixtures"]
    assert "case_001" in {item["fixture_id"] for item in fixtures}
    selected = checked(api.post(BASE + "/dossiers/select", json={"fixture_id": "case_001"}), 201)
    path = BASE + "/dossiers/" + selected["dossier_id"]
    draft = checked(api.post(path + "/prepare"))
    assert draft["status"] == "DRAFT"
    unapproved_run = api.post(
        BASE + "/runs", json={"dossier_id": selected["dossier_id"], "mode": "SCRIPTED_TEST"}
    )
    assert unapproved_run.status_code == 409, unapproved_run.text
    checked(
        api.post(BASE + "/reviewer", json={"actor_id": "human:api_test", "password": PASSWORD}), 201
    )
    body = {
        "password": PASSWORD,
        "candidate_digest": draft["candidate_digest"],
        "accepted_qualifications": (
            "Synthetic review only; unknown applicability remains unresolved."
        ),
    }
    malformed = api.post(path + "/review-foundation", json={**body, "candidate_digest": "bad"})
    assert malformed.status_code == 422
    assert PASSWORD not in malformed.text
    stale = api.post(path + "/review-foundation", json={**body, "candidate_digest": "0" * 64})
    assert stale.status_code == 409, stale.text
    wrong = api.post(path + "/review-foundation", json={**body, "password": "incorrect-secret"})
    assert wrong.status_code in {401, 403, 409}, wrong.text
    assert "incorrect-secret" not in wrong.text
    assert checked(api.get(path))["status"] == "DRAFT"
    approved = checked(api.post(path + "/review-foundation", json=body))
    assert approved["status"] == "APPROVED"
    assert approved["foundation"]["case_snapshot"]["review_state"] == "APPROVED"
    evidence = checked(api.get(path + "/evidence"))
    original = next(
        item for item in evidence["originals"] if item["original_filename"] == "case_manifest.json"
    )
    downloaded = api.get(path + "/artifacts/" + original["artifact_revision_id"])
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == (FIXTURES / "case_001/case_manifest.json").read_bytes()
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert api.get(path + "/artifacts/artifact:unknown").status_code == 404
    observations = {item["observation_id"]: item for item in evidence["observations"]}
    assertions = []
    for record in evidence["records"]:
        if record["record_type"] not in {"Certificate", "CertificateEvent", "Allocation"}:
            continue
        observation = next(
            observations[key]
            for key in record["observation_refs"]
            if observations[key]["parsed_fields"].get("record_type") == record["record_type"]
        )
        assertions.append(
            {
                "target_record_revision_id": record["record_revision_id"],
                "evidence_refs": [
                    {
                        "ref_kind": "OBSERVATION",
                        "ref_id": observation["observation_id"],
                        "artifact_revision_id": observation["artifact_revision_id"],
                        "locator": observation["locator"],
                    }
                ],
                "reason": "Synthetic human review of the exact original record observation.",
            }
        )
    support_body = {
        "password": PASSWORD,
        "snapshot_digest": evidence["snapshot"]["membership_digest"],
        "assertions": assertions,
        "reason": "Synthetic test review; legal applicability remains unresolved.",
    }
    stale_support = api.post(
        path + "/support-review", json={**support_body, "snapshot_digest": "0" * 64}
    )
    assert stale_support.status_code == 409, stale_support.text
    supported = checked(api.post(path + "/support-review", json=support_body))
    assert supported["status"] == "APPROVED"
    refreshed = checked(api.get(path + "/evidence"))
    assert refreshed["snapshot"]["membership_digest"] != evidence["snapshot"]["membership_digest"]
    started = checked(
        api.post(
            BASE + "/runs", json={"dossier_id": selected["dossier_id"], "mode": "SCRIPTED_TEST"}
        ),
        202,
    )
    run_path = BASE + "/runs/" + started["run_id"]
    deadline = time.monotonic() + 60
    while True:
        run = checked(api.get(run_path))
        if run["job"]["status"] not in {"QUEUED", "RUNNING"}:
            break
        assert time.monotonic() < deadline, run
        time.sleep(0.05)
    assert run["job"]["status"] == "STOPPED", run
    assert run["state"]["status"] == "AWAITING_REVIEW", run
    trace = checked(api.get(run_path + "/trace"))
    assert trace["events"]
    kinds = {event["kind"] for event in trace["events"]}
    assert {"PROMPT_PREPARED", "MODEL_RESULT", "PLAN"} <= kinds
    assert all(
        item["system_template"] is None
        for item in trace["events"]
        if item["kind"] == "PROMPT_PREPARED"
    )
    cursor = trace["events"][0]["sequence"]
    assert all(
        event["sequence"] > cursor
        for event in checked(api.get(run_path + "/trace", params={"after": cursor}))["events"]
    )
    events = api.get(run_path + "/events")
    assert events.status_code == 200, events.text
    assert events.headers["content-type"].startswith("text/event-stream")
    assert "event: trace" in events.text and "event: stopped" in events.text
    assert api.get(run_path + "/events", headers={"Last-Event-ID": "invalid"}).status_code == 422
    report = checked(api.get(run_path + "/report"))
    assert report["report"]["revision"]["run_id"] == started["run_id"]
    audited = checked(api.get(run_path + "/audit"))
    assert audited["verification_status"] == "VERIFIED_INTEGRITY"
    assert audited["runtime_metadata"]["execution_kind"] == "SCRIPTED_TEST"
    assert api.post(run_path + "/resume").status_code == 409
    packet = checked(api.post(run_path + "/packet"))
    decision = {
        "password": PASSWORD,
        "packet_id": packet["packet_id"],
        "expected_dependency_digest": packet["review_dependency_digest"],
        "decision": "APPROVE",
        "reason": "Synthetic test review; retained qualifications acknowledged.",
    }
    rejected = api.post(
        run_path + "/review", json={**decision, "expected_dependency_digest": "0" * 64}
    )
    assert rejected.status_code == 409, rejected.text
    reviewed = checked(api.post(run_path + "/review", json=decision))
    assert reviewed["status"] == "COMPLETED", reviewed


def test_concurrent_run_and_turn_boundary_cancellation(api, monkeypatch):
    selected = checked(api.post(BASE + "/dossiers/select", json={"fixture_id": "case_001"}), 201)
    path = BASE + "/dossiers/" + selected["dossier_id"]
    draft = checked(api.post(path + "/prepare"))
    checked(
        api.post(BASE + "/reviewer", json={"actor_id": "human:cancel_test", "password": PASSWORD}),
        201,
    )
    checked(
        api.post(
            path + "/review-foundation",
            json={
                "password": PASSWORD,
                "candidate_digest": draft["candidate_digest"],
                "accepted_qualifications": (
                    "Synthetic cancellation test; applicability is unresolved."
                ),
            },
        )
    )
    entered, release = threading.Event(), threading.Event()
    original = ScriptedInvestigator.invoke

    def blocked_invoke(self, context, request):
        entered.set()
        assert release.wait(15), "test model was not released"
        return original(self, context, request)

    monkeypatch.setattr(ScriptedInvestigator, "invoke", blocked_invoke)
    body = {"dossier_id": selected["dossier_id"], "mode": "SCRIPTED_TEST"}
    try:
        started = checked(api.post(BASE + "/runs", json=body), 202)
        run_path = BASE + "/runs/" + started["run_id"]
        assert entered.wait(15), "background run did not reach the test model"
        concurrent = api.post(BASE + "/runs", json=body)
        assert concurrent.status_code == 409, concurrent.text
        assert api.post(run_path + "/resume").status_code == 409
        requested = checked(api.post(run_path + "/cancel"), 202)
        assert requested["cancellation_requested"] is True
    finally:
        release.set()
    deadline = time.monotonic() + 30
    while True:
        run = checked(api.get(run_path))
        if run["job"]["status"] not in {"RUNNING", "QUEUED"}:
            break
        assert time.monotonic() < deadline, run
        time.sleep(0.05)
    assert run["job"]["status"] == "STOPPED", run
    assert run["state"]["status"] == "CANCELLED", run
    assert run["state"]["budget"]["model_calls"] == 1
    assert api.post(run_path + "/resume").status_code == 409
    assert api.post(run_path + "/cancel").status_code == 409
