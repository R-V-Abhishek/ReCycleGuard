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
    """Start one model-backed run and wait for its job to end; returns (run_id, view)."""
    body = {"dossier_id": dossier, "mode": "MODEL_BACKED", "variant": variant}
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
    parser.add_argument("--config", type=Path, required=True)
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

    from recycleguard.api import ApiOptions, create_app
    from recycleguard.config import Settings

    password, token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    originals = arguments.visible / "originals"
    app = create_app(
        ApiOptions(
            settings=Settings(data_root=arguments.runtime / "root"),
            token=token,
            model_config_path=arguments.config,
            fixture_root=arguments.visible / "fixtures",
            r02_path=originals / "e-waste_rules_2022.pdf",
            r08_path=originals / "cpcb_faq_20240123.pdf",
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
        }
        response = client.get(f"{BASE}/runs/{run_id}/report")
        if response.status_code == 200:
            result["report"] = response.json()
    (arguments.runtime / "result.json").write_text(
        json.dumps(result, sort_keys=True, indent=1) + "\n", "utf-8"
    )


if __name__ == "__main__":
    main()
