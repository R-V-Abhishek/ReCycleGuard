"""Run one trial through the real API. Imports only the installed application.

No evaluator code may be reachable here: the coordinator copies this file next to the case and,
for real-model runs, starts it with the wheel's Python inside the sandbox. The fixture reviewer
is synthetic: its decisions are test scaffolding, never team approvals.
"""

import argparse
import json
import secrets
import time
from pathlib import Path

from recycleguard.contracts.core import EvidenceRef

BASE = "/api/v1"
TERMINAL = {"STOPPED", "FAILED"}
REVIEW_NOTE = "Synthetic fixture review for a trial."
REAL_MODEL_VARIANTS = {"FIXED_RETRIEVAL", "ADAPTIVE"}
CONTROL_FINDING = "finding:control"
_CONTROL_PLAN = {
    "objective": "Scripted control.",
    "hypotheses": [],
    "proposed_checks": ["compute_reconciliation"],
    "expected_evidence": ["Deterministic reconciliation output"],
    "stopping_criteria": ["The scripted control ends after its step"],
}
# V0 runs no check, so its report holds only the deterministic pipeline's own output. SC runs the
# real tools through the graph with fixed replies, so it can never be read as model performance.
CONTROL_EXCHANGES = {
    "V0": [
        (
            "PLAN",
            {"plan": _CONTROL_PLAN, "action": None, "stop_reason": "NO_NEW_EVIDENCE"},
        )
    ],
    "SC": [
        (
            "PLAN",
            {
                "plan": _CONTROL_PLAN,
                "action": {
                    "action_kind": "CHECK",
                    "allowed_operation": "compute_reconciliation",
                    "typed_arguments": {"bucket_ids": []},
                    "finding_id": CONTROL_FINDING,
                    "concise_reason": "Scripted control step.",
                    "evidence_refs": [],
                },
                "stop_reason": None,
            },
        ),
        (
            "ASSESS",
            {
                "verdict": "UNKNOWN",
                "weak_result_or_mistake": None,
                "next_check_or_stop": "stop",
                "disposition": "ABSTAIN",
                "revised_plan": None,
                "finding_proposal": None,
            },
        ),
    ],
}


def application_options(variant, runtime, visible, config, token):
    """Test adapters exist only for controls, and a control never receives a model config."""
    from recycleguard.api import ApiOptions
    from recycleguard.config import Settings
    from recycleguard.investigation import ScriptedExchange

    originals = visible / "originals"
    shared = {
        "token": token,
        "fixture_root": visible / "fixtures",
        "r02_path": originals / "e-waste_rules_2022.pdf",
        "r08_path": originals / "cpcb_faq_20240123.pdf",
    }
    if variant in REAL_MODEL_VARIANTS:
        if config is None:
            raise ValueError("a real-model variant needs its model configuration")
        return ApiOptions(
            settings=Settings(data_root=runtime / "root"), model_config_path=config, **shared
        )
    if variant not in CONTROL_EXCHANGES:
        raise ValueError(f"unknown variant: {variant}")
    return ApiOptions(
        settings=Settings(data_root=runtime / "root", mode="test", enable_test_adapters=True),
        test_exchanges=[
            ScriptedExchange(phase=phase, response=response)
            for phase, response in CONTROL_EXCHANGES[variant]
        ],
        **shared,
    )


def trial_body(variant):
    if variant in REAL_MODEL_VARIANTS:
        return {"mode": "MODEL_BACKED", "variant": variant}
    return {"mode": "SCRIPTED_TEST", "variant": "ADAPTIVE"}


def call_summary(events):
    """Outcome of every recorded call and refused action; codes only, no prompt or model text."""
    calls, rejected = [], []
    for event in events:
        if event["event_type"].endswith(".result") and "kind" in event:
            kinds = {"MODEL_RESULT": "MODEL", "TOOL_OR_STAGE_RESULT": None}
            if event["kind"] in kinds:
                kind = kinds[event["kind"]] or (
                    "TOOL" if event["event_type"].startswith("graph.tool.") else "STAGE"
                )
                calls.append(
                    {
                        "kind": kind,
                        "event_type": event["event_type"],
                        "operation_id": event["operation_id"],
                        "status": event["status"],
                        "issue_codes": sorted({issue["code"] for issue in event["issues"]}),
                    }
                )
        if event["event_type"] == "graph.action_rejected.result":
            rejected.append(event["operation_id"])
    return calls, rejected


def supported_assertions(evidence):
    observations = {o["observation_id"]: o for o in evidence["observations"]}
    assertions = []
    for record in evidence["records"]:
        kind = record["record_type"]
        if kind not in {"Certificate", "CertificateEvent", "Allocation"}:
            continue
        for reference in record["observation_refs"]:
            observation = observations[reference]
            fields = observation["parsed_fields"]
            if (
                fields.get("record_type") != kind
                or (kind == "Allocation" and fields.get("state") != "SUPPORTED")
                or (
                    kind == "CertificateEvent"
                    and (
                        fields.get("assertion_state") != "SUPPORTED"
                        or fields.get("transfer_stage") != "COMPLETED"
                    )
                )
            ):
                continue
            ref = EvidenceRef(
                ref_kind="OBSERVATION",
                ref_id=observation["observation_id"],
                artifact_revision_id=observation["artifact_revision_id"],
                locator=observation["locator"],
            )
            assertions.append(
                {
                    "target_record_revision_id": record["record_revision_id"],
                    "evidence_refs": [ref.model_dump(mode="json")],
                    "reason": REVIEW_NOTE,
                }
            )
            break
    return assertions


def caller(client):
    def call(method, path, body=None, code=200):
        response = client.request(method, BASE + path, json=body)
        if response.status_code != code:
            raise RuntimeError(f"{method} {path}: {response.status_code}")
        return response.json()

    return call


def prepare_dossier(call, fixture, password):
    """Select and fixture-review one dossier; returns its id."""
    dossier = call("POST", "/dossiers/select", {"fixture_id": fixture}, 201)["dossier_id"]
    prepared = call("POST", f"/dossiers/{dossier}/prepare")
    call(
        "POST",
        f"/dossiers/{dossier}/review-foundation",
        {
            "password": password,
            "candidate_digest": prepared["candidate_digest"],
            "accepted_qualifications": REVIEW_NOTE,
        },
    )
    evidence = call("GET", f"/dossiers/{dossier}/evidence")
    call(
        "POST",
        f"/dossiers/{dossier}/support-review",
        {
            "password": password,
            "snapshot_digest": evidence["snapshot"]["membership_digest"],
            "assertions": supported_assertions(evidence),
            "reason": REVIEW_NOTE,
        },
    )
    return dossier


def run_variant(call, dossier, variant, deadline_seconds=600, budgets=None):
    """Start one run and wait for its job to end; returns (run_id, view)."""
    body = {"dossier_id": dossier, **trial_body(variant)}
    if budgets is not None:
        body["budgets"] = budgets
    run_id = call("POST", "/runs", body, 202)["run_id"]
    deadline = time.monotonic() + deadline_seconds
    while True:
        view = call("GET", f"/runs/{run_id}")
        if view["job"]["status"] in TERMINAL:
            return run_id, view
        if time.monotonic() >= deadline:
            raise TimeoutError(f"run {run_id} did not finish within {deadline_seconds} s")
        time.sleep(0.5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--visible", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--forbidden", type=Path, action="append", default=[])
    parser.add_argument("--sandboxed", action="store_true")
    parser.add_argument("--budgets", type=json.loads)
    arguments = parser.parse_args()

    if arguments.sandboxed:
        from recycleguard.host_sandbox import probe_boundary

        (arguments.runtime / "tmp").mkdir(exist_ok=True)
        probe_boundary(
            arguments.forbidden,
            arguments.visible,
            arguments.runtime,
            arguments.runtime / "isolation-evidence-real.json",
        )

    from fastapi.testclient import TestClient

    from recycleguard.api import create_app

    password, token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    app = create_app(
        application_options(
            arguments.variant, arguments.runtime, arguments.visible, arguments.config, token
        )
    )
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + token
        call = caller(client)
        call("POST", "/reviewer", {"actor_id": "human:trial_fixture", "password": password}, 201)
        dossier = prepare_dossier(call, arguments.case, password)
        run_id, view = run_variant(call, dossier, arguments.variant, budgets=arguments.budgets)
        state = view["state"]
        result = {
            "case_id": arguments.case,
            "requested_variant": arguments.variant,
            "experiment_variant": view["configuration"]["experiment_variant"],
            "run_id": run_id,
            "job": view["job"],
            "status": state["status"],
            "stop_reason": state["stop_reason"],
            "budget": state["budget"],
            "report": None,
            "calls": None,
            "rejected_actions": None,
            # The trace endpoint verifies the run's whole audit hash chain before it answers.
            "audit_chain": "UNVERIFIED",
        }
        response = client.get(f"{BASE}/runs/{run_id}/report")
        if response.status_code == 200:
            result["report"] = response.json()
        response = client.get(f"{BASE}/runs/{run_id}/trace")
        if response.status_code == 200:
            result["calls"], result["rejected_actions"] = call_summary(response.json()["events"])
            result["audit_chain"] = "VERIFIED"
    (arguments.runtime / "result.json").write_text(
        json.dumps(result, sort_keys=True, indent=1) + "\n", "utf-8"
    )


if __name__ == "__main__":
    main()
