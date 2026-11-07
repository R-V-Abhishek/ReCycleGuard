"""Run one trial through the real API. Imports only the installed application.

No evaluator code may be reachable here: the coordinator copies this file next to the case and,
for real-model runs, starts it with the wheel's Python inside the sandbox. The fixture reviewer
is synthetic: its decisions are test scaffolding, never team approvals.
"""

import argparse
import json
import re
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


def application_options(variant, runtime, visible, config, token, ablated=False):
    """Test adapters exist only for controls, and a control never receives a model config.

    An ablated model run is an evaluation: the server holds it to the frozen budget.
    """
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
            settings=Settings(
                data_root=runtime / "root", mode="evaluation" if ablated else "runtime"
            ),
            model_config_path=config,
            **shared,
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


_CODE = re.compile(r'"code":\s*"([A-Z][A-Z0-9_]+)"')
_TEXT_LIMIT = 300


def _text(value):
    return None if value is None else str(value)[:_TEXT_LIMIT]


def _shown(request):
    """What the model was shown: counts, flags and issue codes, never the evidence itself."""
    if request.get("phase") == "PLAN":
        return {
            "pending_findings": len(request.get("pending_findings") or []),
            "inspectable_observations": len(request.get("inspectable_observation_ids") or []),
            "inspectable_total": request.get("inspectable_observations_total"),
            "prior_observations": len(request.get("prior_stage_observations") or []),
            "previous_plans": len(request.get("previous_plans") or []),
            "previous_rejection": "previous_rejection" in request,
        }
    if request.get("phase") == "BRIEF":
        finding = request.get("finding") or {}
        return {
            "issue_type": finding.get("issue_type"),
            "citable_evidence_ids": len(request.get("citable_evidence_ref_ids") or []),
            "evidence_items": len(request.get("evidence") or []),
            "figures": len(request.get("figures_shown_by_code") or []),
        }
    stage = (request.get("observation") or {}).get("stage_output") or {}
    decision = stage.get("concise_decision")
    evidence = decision.get("evidence_data") if isinstance(decision, dict) else None
    raw = decision.get("evidence_data_json") if isinstance(decision, dict) else None
    # Cut evidence stays a JSON string; search it as sent, not re-escaped.
    text = json.dumps(evidence) if evidence is not None else (raw or "")
    return {
        "tool": (request.get("action") or {}).get("allowed_operation"),
        "disposition": stage.get("disposition"),
        "citable_evidence_ids": len(stage.get("evidence_ref_ids") or []),
        "evidence_refs_total": stage.get("evidence_refs_total"),
        "citable_calculation_ids": len(stage.get("calculation_ids") or []),
        "evidence_truncated": bool(
            isinstance(decision, dict) and decision.get("evidence_truncated")
        ),
        "evidence_chars": len(json.dumps(evidence)) if evidence is not None else len(raw or ""),
        "evidence_keys": sorted(evidence) if isinstance(evidence, dict) else None,
        "visible_issue_codes": sorted(set(_CODE.findall(text))),
    }


def _reply(response):
    output = (response or {}).get("validated_output_or_null")
    if not isinstance(output, dict):
        return None
    if "what_to_check" in output:  # the brief text itself is kept in the trial's briefs
        return {
            "brief_chars": {
                key: len(str(output.get(key) or ""))
                for key in ("what_to_check", "explanation", "evidence_request")
            },
            "cited_ids": len(output.get("evidence_ref_ids") or []),
        }
    if "verdict" in output:
        proposal = output.get("finding_proposal") or None
        return {
            "verdict": output.get("verdict"),
            "disposition": output.get("disposition"),
            "next_check_or_stop": _text(output.get("next_check_or_stop")),
            "weak_result_or_mistake": _text(output.get("weak_result_or_mistake")),
            "proposal": None
            if proposal is None
            else {
                "issue_type": proposal.get("issue_type"),
                "advisory_status": proposal.get("advisory_status"),
                "cited_ids": len(proposal.get("evidence_ref_ids") or []),
                "abstention_reason": proposal.get("abstention_reason"),
                "withheld_claim_scopes": proposal.get("withheld_claim_scopes"),
                "basis": _text(proposal.get("basis")),
            },
        }
    plan, action = output.get("plan") or {}, output.get("action") or None
    return {
        "objective": _text(plan.get("objective")),
        "hypotheses": [_text(h) for h in (plan.get("hypotheses") or [])[:5]],
        "proposed_checks": (plan.get("proposed_checks") or [])[:8],
        "operation": None if action is None else action.get("allowed_operation"),
        "argument_keys": None if action is None else sorted(action.get("typed_arguments") or {}),
        "concise_reason": None if action is None else _text(action.get("concise_reason")),
        "stop_reason": output.get("stop_reason"),
    }


def _transport(trace):
    """Finish reason and token counts from the provider's own reply."""
    try:
        body = json.loads((trace or {}).get("response_body_utf8") or "")
    except ValueError:
        return {"finish_reason": None, "prompt_tokens": None, "completion_tokens": None}
    choice = (body.get("choices") or [{}])[0]
    usage = body.get("usage") or {}
    thinking = (trace or {}).get("thinking")
    return {
        "finish_reason": choice.get("finish_reason"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "elapsed_seconds": (trace or {}).get("elapsed_seconds"),
        # A thinking call reasons first; its reasoning text stays in model-calls.jsonl only.
        **(
            {}
            if thinking is None
            else {
                "thinking_finish": thinking.get("finish_reason"),
                "thinking_tokens": thinking.get("completion_tokens"),
            }
        ),
    }


def decision_trace(events):
    """Per model call: what it was shown, what it replied and why it said so, in its own words.

    The model's short text fields are kept, capped; tool evidence and prompts are not. The exact
    transport stays in the runtime folder (``model-calls.jsonl``) and is never sealed or exported.
    """
    rows, shown = [], None
    for event in events:
        if event.get("kind") == "PROMPT_PREPARED":
            shown = {"phase": event.get("phase"), **_shown(event.get("request") or {})}
        elif event.get("kind") == "MODEL_RESULT":
            rows.append(
                {
                    "operation_id": event["operation_id"],
                    "attempt_id": event.get("attempt_id"),
                    "status": event.get("status"),
                    "issue_codes": sorted({issue["code"] for issue in event.get("issues") or []}),
                    "shown": shown,
                    "reply": _reply(event.get("response")),
                    "transport": _transport(event.get("provider_trace")),
                }
            )
    return rows


def _reasoning(trace):
    """The thinking request's exact exchange, when the call thought before answering."""
    thinking = (trace or {}).get("thinking")
    if thinking is None:
        return {}
    return {
        "thinking_request_body_utf8": thinking.get("request_body_utf8"),
        "thinking_response_body_utf8": thinking.get("response_body_utf8"),
    }


def model_calls(events):
    """Exact request and reply bodies, kept beside the trial for diagnostic replay only."""
    return [
        {
            "operation_id": event["operation_id"],
            "attempt_id": event.get("attempt_id"),
            "request_body_utf8": (event.get("provider_trace") or {}).get("request_body_utf8"),
            "response_body_utf8": (event.get("provider_trace") or {}).get("response_body_utf8"),
            **_reasoning(event.get("provider_trace")),
        }
        for event in events
        if event.get("kind") == "MODEL_RESULT" and event.get("provider_trace")
    ]


def census(root, report):
    """Record kinds and check states behind each calculation: counts only, no record contents.

    It shows why a deterministic family did or did not fire: whether the records it needs were
    extracted at all, and what state each reconciliation check reached.
    """
    from collections import Counter

    from recycleguard.contracts.core import BlobRef
    from recycleguard.storage import BlobStore

    try:
        blobs = BlobStore(root)

        def load(ref):
            return json.loads(blobs.get(BlobRef.model_validate(ref)))

        records, dispositions, checks, priority, eligibility = (Counter() for _ in range(5))
        for calculation in ((report or {}).get("report") or {}).get("calculations") or []:
            membership = load(calculation["analyzed_input_membership_blob"])
            records.update(member["record_type"] for member in membership["members"])
            dispositions.update(
                f"{item['record_type']}:{item['state']}"
                for item in load(calculation["quantity_dispositions_blob"])
            )
            derivation = load(calculation["derivation_blob"])
            checks.update(
                f"{c['rule']}:{c['state']}:{c.get('code')}" for c in derivation["allocation_checks"]
            )
            priority.update(c["state"] for c in derivation["priority_checks"])
            eligibility.update(
                f"{o['condition']}:{o['testability']}:{o['state']}"
                for o in derivation["eligibility"]
            )
        return {
            "records": dict(sorted(records.items())),
            "dispositions": dict(sorted(dispositions.items())),
            "allocation_checks": dict(sorted(checks.items())),
            "priority_checks": dict(sorted(priority.items())),
            "eligibility": dict(sorted(eligibility.items())),
        }
    except Exception as exc:  # diagnostic only: never fail a trial over it
        return {"error": f"{type(exc).__name__}: {exc}"[:300]}


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
            # The API's own error code and message, so the runtime log says why; capped.
            raise RuntimeError(f"{method} {path}: {response.status_code} {response.text[:300]}")
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


def run_variant(call, dossier, variant, deadline_seconds=600, budgets=None, ablated=None):
    """Start one run and wait for its job to end; returns (run_id, view)."""
    body = {"dossier_id": dossier, **trial_body(variant)}
    if budgets is not None:
        body["budgets"] = budgets
    if ablated:
        body["ablated_families"] = ablated
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
    parser.add_argument("--container", action="store_true")
    parser.add_argument("--budgets", type=json.loads)
    parser.add_argument("--ablate", type=json.loads, help="JSON list of families switched off")
    arguments = parser.parse_args()

    if arguments.container:
        from recycleguard.isolated_runtime import probe_trial_boundary

        probe_trial_boundary(
            arguments.visible,
            Path(__file__).resolve().parent,
            arguments.runtime,
            arguments.runtime / "isolation-evidence-real.json",
        )

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
            arguments.variant,
            arguments.runtime,
            arguments.visible,
            arguments.config,
            token,
            ablated=bool(arguments.ablate),
        )
    )
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + token
        call = caller(client)
        call("POST", "/reviewer", {"actor_id": "human:trial_fixture", "password": password}, 201)
        dossier = prepare_dossier(call, arguments.case, password)
        run_id, view = run_variant(
            call, dossier, arguments.variant, budgets=arguments.budgets, ablated=arguments.ablate
        )
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
            # Model briefs (gated, or dropped with a reason) and template briefs, per finding.
            "briefs": None,
            "calls": None,
            "decisions": None,
            "census": None,
            "rejected_actions": None,
            # The trace endpoint verifies the run's whole audit hash chain before it answers.
            "audit_chain": "UNVERIFIED",
        }
        response = client.get(f"{BASE}/runs/{run_id}/report")
        if response.status_code == 200:
            result["report"] = response.json()
            result["census"] = census(arguments.runtime / "root", result["report"])
        response = client.get(f"{BASE}/runs/{run_id}/briefs")
        if response.status_code == 200:
            result["briefs"] = response.json()
        response = client.get(f"{BASE}/runs/{run_id}/trace")
        if response.status_code == 200:
            events = response.json()["events"]
            result["calls"], result["rejected_actions"] = call_summary(events)
            result["decisions"] = decision_trace(events)
            result["audit_chain"] = "VERIFIED"
            with (arguments.runtime / "model-calls.jsonl").open("w", encoding="utf-8") as stream:
                for call_record in model_calls(events):
                    stream.write(json.dumps(call_record, sort_keys=True) + "\n")
    (arguments.runtime / "result.json").write_text(
        json.dumps(result, sort_keys=True, indent=1) + "\n", "utf-8"
    )


if __name__ == "__main__":
    main()
