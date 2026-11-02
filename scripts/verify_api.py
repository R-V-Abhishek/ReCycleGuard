"""Fresh-root HTTP API demonstration; optional real local inference, no frontend."""

import secrets
import time
from pathlib import Path
from typing import Annotated

import typer
from fastapi.testclient import TestClient
from verify_a07 import exchanges

from recycleguard.api import ApiOptions, create_app
from recycleguard.config import Settings
from recycleguard.contracts.core import EvidenceRef
from recycleguard.storage import canonical_json_bytes

BASE = "/api/v1"
DISCLAIMER = "Synthetic fixture approvals only; no team acknowledgement or legal certification."


def run(
    data_root: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
    model_config: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
):
    if data_root.exists() or output.exists():
        raise typer.BadParameter("data and output roots must be new")
    output.mkdir(parents=True)
    password, token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    mode = "SCRIPTED_TEST" if model_config is None else "MODEL_BACKED"
    settings = Settings(
        data_root=data_root,
        mode="test" if model_config is None else "runtime",
        enable_test_adapters=model_config is None,
    )
    options = ApiOptions(
        settings=settings,
        token=token,
        model_config_path=model_config,
        test_exchanges=tuple(exchanges()) if model_config is None else (),
    )
    application = create_app(options)
    calls = []

    def save(name, value):
        (output / name).write_bytes(canonical_json_bytes(value) + b"\n")

    with TestClient(application) as client:
        client.headers["Authorization"] = "Bearer " + token

        def request(method, path, body=None, code=200):
            response = client.request(method, BASE + path, json=body)
            calls.append({"method": method, "path": path, "status": response.status_code})
            if response.status_code != code:
                raise RuntimeError(f"{method} {path}: {response.status_code} {response.text}")
            return response.json()

        request(
            "POST",
            "/reviewer",
            {"actor_id": "human:api_synthetic_fixture", "password": password},
            201,
        )
        selected = request("POST", "/dossiers/select", {"fixture_id": "case_001"}, 201)
        dossier = selected["dossier_id"]
        prepared = request("POST", f"/dossiers/{dossier}/prepare")
        request(
            "POST",
            f"/dossiers/{dossier}/review-foundation",
            {
                "password": password,
                "candidate_digest": prepared["candidate_digest"],
                "accepted_qualifications": DISCLAIMER + " Applicability remains unknown.",
            },
        )
        evidence = request("GET", f"/dossiers/{dossier}/evidence")
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
            reference = EvidenceRef(
                ref_kind="OBSERVATION",
                ref_id=observation["observation_id"],
                artifact_revision_id=observation["artifact_revision_id"],
                locator=observation["locator"],
            )
            assertions.append(
                {
                    "target_record_revision_id": record["record_revision_id"],
                    "evidence_refs": [reference.model_dump(mode="json")],
                    "reason": DISCLAIMER + " Exact structured support reviewed.",
                }
            )
        request(
            "POST",
            f"/dossiers/{dossier}/support-review",
            {
                "password": password,
                "snapshot_digest": evidence["snapshot"]["membership_digest"],
                "assertions": assertions,
                "reason": DISCLAIMER,
            },
        )
        before = time.monotonic()
        started = request("POST", "/runs", {"dossier_id": dossier, "mode": mode}, 202)
        run_id = started["run_id"]
        deadline = time.monotonic() + 660
        seen = set()
        while time.monotonic() < deadline:
            result = request("GET", f"/runs/{run_id}")
            seen.add(result["state"]["status"])
            if result["job"]["status"] in {"STOPPED", "FAILED"}:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("API investigation did not finish within its verification window")
        save("state.json", result)
        trace = request("GET", f"/runs/{run_id}/trace")
        save("trace.json", trace)
        if result["state"]["status"] != "AWAITING_REVIEW" or result["job"]["status"] == "FAILED":
            raise RuntimeError(f"API investigation did not reach review: {result['job']}")
        report = request("GET", f"/runs/{run_id}/report")
        save("report.json", report)
        audit = request("GET", f"/runs/{run_id}/audit")
        save("audit.json", audit)
        if audit["verification_status"] != "VERIFIED_INTEGRITY":
            raise RuntimeError("Frozen-input audit was not verified")
        wire = [event for event in trace["events"] if event.get("provider_trace") is not None]
        tools = [event for event in trace["events"] if event["kind"] == "TOOL_PROPOSED"]
        if not tools or (model_config is not None and not wire):
            raise RuntimeError("Actual tool reason / exact provider request trace is missing")
        packet = request("POST", f"/runs/{run_id}/packet")
        completed = request(
            "POST",
            f"/runs/{run_id}/review",
            {
                "password": password,
                "packet_id": packet["packet_id"],
                "expected_dependency_digest": packet["review_dependency_digest"],
                "decision": "APPROVE",
                "reason": DISCLAIMER + " Qualified working paper accepted.",
            },
        )
        if completed["status"] != "COMPLETED":
            raise RuntimeError("Authenticated fixture review did not complete the run")
        save(
            "summary.json",
            {
                "disclaimer": DISCLAIMER,
                "mode": mode,
                "state": completed["status"],
                "verification": report["verification"]["verdict"],
                "integrity": audit["verification_status"],
                "tool_calls": result["state"]["budget"]["tool_calls"],
                "model_calls": result["state"]["budget"]["model_calls"],
                "retries": result["state"]["budget"]["retries"],
                "observed_tokens": result["state"]["budget"]["observed_tokens"],
                "wire_exchanges": len(wire),
                "elapsed_seconds": time.monotonic() - before,
                "observed_states": sorted(seen),
                "run_id": run_id,
                "balances": report["report"]["calculations"][0]["bucket_results"],
                "quality_benchmark": False,
            },
        )
    (data_root / "reviewer.json").unlink(missing_ok=True)
    save("http-calls.json", calls)
    typer.echo(f"Verified API {mode}: {output / 'summary.json'}")


if __name__ == "__main__":
    typer.run(run)
