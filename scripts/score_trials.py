"""Score sealed trials against oracle records. Evaluator-only; run as its own process.

Every scheduled trial gets a row. A case whose independent visible reference cannot be computed is
written as NOT_SCORED and never becomes a score.

    uv run scripts/score_trials.py <trial-output> <oracle-dir> <visible-root> <scores-output>
"""

import json
import sys
from collections import Counter
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))  # evaluator code is not part of the installed wheel

from benchmarks.evaluation.analysis import paired_bootstrap, rate_interval  # noqa: E402
from benchmarks.evaluation.oracle import OracleCase  # noqa: E402
from benchmarks.evaluation.scoring import (  # noqa: E402
    ScoringProtocol,
    case_success,
    project_investigation_report,
)
from benchmarks.evaluation.taxonomy import classify_failure  # noqa: E402
from benchmarks.evaluation.trials import (  # noqa: E402
    CANARY,
    CONTROLS,
    Ledger,
    protocol_schedule,
    verify_seals,
)
from benchmarks.evaluation.visible_reference import (  # noqa: E402
    bind_oracle_reference,
    inspect_visible,
)

BOOTSTRAP_SEED = 20261101
PAIR = ("FIXED_RETRIEVAL", "ADAPTIVE")
assert not set(PAIR) & set(CONTROLS)
MODEL_PROPOSAL = {"source": "MODEL_PROPOSAL"}
# Rejected only because the family already has a finding, so not an unsupported claim.
NOT_UNSUPPORTED = {"DUPLICATE_ISSUE_TYPE"}
CLEAN_FAMILY = "F01_CLEAN_BASELINE"


def call_metrics(result):
    """Per-attempt and per-call schema validity; None for results sealed before calls were kept."""
    calls = result.get("calls")
    if calls is None:
        return {
            "model_attempts": None,
            "model_logical_calls": None,
            "schema_valid_attempts": None,
            "schema_valid_logical_calls": None,
            "call_timeouts": None,
            "outcome_unknown_retries": None,
            "rejected_actions": None,
            "audit_chain": result.get("audit_chain", "UNVERIFIED"),
        }
    model = [call for call in calls if call["kind"] == "MODEL"]
    by_operation = {}
    for call in model:
        by_operation.setdefault(call["operation_id"], []).append(call)
    return {
        "model_attempts": len(model),
        "model_logical_calls": len(by_operation),
        "schema_valid_attempts": sum(call["status"] == "SUCCESS" for call in model),
        # At most one retry is in budget, so a logical call is valid when any attempt succeeded.
        "schema_valid_logical_calls": sum(
            any(call["status"] == "SUCCESS" for call in attempts)
            for attempts in by_operation.values()
        ),
        "call_timeouts": sum("PROVIDER_TIMEOUT" in call["issue_codes"] for call in model),
        # An uncertain outcome must never be retried, so anything above zero is a defect.
        "outcome_unknown_retries": sum(
            any(call["status"] == "OUTCOME_UNKNOWN" for call in attempts[:-1])
            for attempts in by_operation.values()
        ),
        "rejected_actions": len(result.get("rejected_actions") or ()),
        "audit_chain": result.get("audit_chain", "UNVERIFIED"),
    }


def report_metrics(report):
    """What the model contributed to a report, which the gate accepted and which it refused."""
    if report is None:
        return {}
    model = [f for f in report["findings"] if MODEL_PROPOSAL in f["evidence_assessments"]]
    rejected = report.get("rejected_finding_proposals") or []
    return {
        "findings_total": len(report["findings"]),
        "findings_from_model": len(model),
        "proposals_made": len(model) + len(rejected),
        "proposals_accepted": len(model),
        "proposals_rejected": dict(sorted(Counter(item["reason"] for item in rejected).items())),
        "unsupported_claims": sum(item["reason"] not in NOT_UNSUPPORTED for item in rejected),
    }


def score_trial(spec, ledger_rows, output, oracle_dir, visible_root, backend):
    row = {
        "trial_id": spec.trial_id,
        "case_id": spec.case_id,
        "variant": spec.variant,
        "repeat": spec.repeat,
        "backend": backend,
        "final_status": None,
        "model_calls": None,
        "basis": None,
        "success": False,
        "not_scored_reason": None,
        "composite_score": None,
        "precision": None,
        "recall": None,
        "f1": None,
        "abstention_accuracy": None,
        "forbidden_actions": None,
        "failure_class": None,
        "true_positives": None,
        "false_positives": None,
        "false_negatives": None,
        "buckets_total": None,
        "buckets_matched": None,
        "clean_case": None,
        "missing_abstentions": None,
        "retries": None,
    }
    finished = [
        r for r in ledger_rows if r["trial_id"] == spec.trial_id and r["status"] != "STARTED"
    ]
    last = finished[-1] if finished else None
    if last is None or last.get("result_digest") is None:
        row["basis"] = "NOT_RUN" if last is None else last["status"]
        row["failure_class"] = classify_failure(row, last and last["status"], None)
        return row
    result = json.loads((output / "results" / f"{last['result_digest']}.json").read_text("utf-8"))
    row["final_status"] = result["status"]
    row["model_calls"] = result["budget"]["model_calls"]
    row["retries"] = result["budget"].get("retries")
    row.update(call_metrics(result))
    row.update(report_metrics(result["report"]))

    def classified():
        row["failure_class"] = classify_failure(row, last["status"], result)
        return row

    oracle_path = oracle_dir / f"{spec.case_id.removeprefix('case_')}.json"
    if not oracle_path.is_file():
        row["not_scored_reason"] = "NO_ORACLE"
        return classified()
    oracle = OracleCase.model_validate_json(oracle_path.read_bytes())
    if oracle.visible_reference_status == "UNVERIFIED_WORLD_PROJECTION":
        # Stored candidates are unreviewed; the reference is recomputed from visible evidence.
        try:
            reference = inspect_visible(visible_root / spec.case_id)
            oracle, _, _ = bind_oracle_reference(oracle, reference)
        except (ValueError, OSError) as exc:
            row["not_scored_reason"] = f"REFERENCE_FAILED: {exc}"[:200]
            return classified()
    families = {finding["issue_type"] for finding in oracle.expected_findings}
    row["clean_case"] = families == {CLEAN_FAMILY}
    row["expected_families"] = sorted(families)
    if result["report"] is not None:
        row["emitted_families"] = sorted({f["issue_type"] for f in result["report"]["findings"]})
    trial = None
    if result["report"] is not None:
        trial = ScoringProtocol().score_trial(
            **project_investigation_report(result["report"]), oracle=oracle
        )
        row.update(
            composite_score=trial.composite_score,
            precision=trial.findings.precision,
            recall=trial.findings.recall,
            f1=trial.findings.f1,
            abstention_accuracy=trial.abstentions.abstention_accuracy,
            forbidden_actions=trial.forbidden_actions.violations,
            true_positives=trial.findings.true_positives,
            false_positives=trial.findings.false_positives,
            false_negatives=trial.findings.false_negatives,
            buckets_total=trial.reconciliation.total_buckets,
            buckets_matched=trial.reconciliation.matched_buckets,
            missing_abstentions=[item["scope"] for item in trial.abstentions.missing_abstentions],
        )
    row["success"], row["basis"] = case_success(
        trial, oracle, result["status"], result["budget"]["model_calls"]
    )
    return classified()


def canary_signature(result):
    report = result["report"] or {}
    return {
        "status": result["status"],
        "stop_reason": result["stop_reason"],
        "model_calls": result["budget"]["model_calls"],
        "finding_families": sorted(f["issue_type"] for f in report.get("findings", ())),
        "rejected_reasons": sorted(
            item["reason"] for item in report.get("rejected_finding_proposals", ())
        ),
    }


def compare_canaries(schedule, ledger_rows, output, baseline=None):
    """Start against end of the session, and against a baseline when the protocol names one."""
    last = {r["trial_id"]: r for r in ledger_rows if r["status"] != "STARTED"}
    signatures = {}
    for spec in schedule:
        if spec.role != CANARY:
            continue
        digest = last.get(spec.trial_id, {}).get("result_digest")
        signatures[spec.trial_id] = (
            None
            if digest is None
            else canary_signature(
                json.loads((output / "results" / f"{digest}.json").read_text("utf-8"))
            )
        )
    drift = []
    for trial_id, signature in sorted(signatures.items()):
        if not trial_id.endswith("|canary-end"):
            continue
        start = signatures.get(trial_id.replace("|canary-end", "|canary-start"))
        if signature is None or start is None or signature != start:
            drift.append(trial_id)
    if baseline is not None:
        drift += sorted(
            trial_id
            for trial_id, signature in signatures.items()
            if baseline.get(trial_id) != signature
        )
    return {
        "checked": len(signatures),
        "drifted": sorted(set(drift)),
        "signatures": signatures,
        "baseline_compared": baseline is not None,
    }


def summarize(rows, backend):
    scored = [row for row in rows if row["not_scored_reason"] is None]
    without_blocks = [row for row in scored if row["basis"] != "PREFLIGHT_BLOCK"]
    by_variant = {}
    for variant in sorted({row["variant"] for row in rows}):
        mine = [row for row in scored if row["variant"] == variant]
        wins = sum(row["success"] for row in mine)
        by_variant[variant] = {
            "scheduled": sum(row["variant"] == variant for row in rows),
            "scored": len(mine),
            "successes": wins,
            # Undefined with nothing scored, never 1.0.
            "success_rate": wins / len(mine) if mine else None,
            "success_interval_95": rate_interval(mine, variant, seed=BOOTSTRAP_SEED),
            "preflight_blocks": sum(row["basis"] == "PREFLIGHT_BLOCK" for row in mine),
        }
    # Each real-model variant is read against the scripted control, which can never be read as
    # model performance. Differences are b minus a, so a positive value favours the real model.
    return {
        "backend": backend,
        "not_scored": sum(row["not_scored_reason"] is not None for row in rows),
        "by_variant": by_variant,
        "v2_minus_v1": paired_bootstrap(scored, *PAIR, seed=BOOTSTRAP_SEED),
        "v2_minus_v1_without_preflight_blocks": paired_bootstrap(
            without_blocks, *PAIR, seed=BOOTSTRAP_SEED
        ),
        # Every real-model variant of the session against the control, the MG2 arms included.
        "minus_sc": {
            variant: paired_bootstrap(scored, "SC", variant, seed=BOOTSTRAP_SEED)
            for variant in by_variant
            if variant not in CONTROLS
        },
        "v1_minus_sc": paired_bootstrap(scored, "SC", PAIR[0], seed=BOOTSTRAP_SEED),
        "v2_minus_sc": paired_bootstrap(scored, "SC", PAIR[1], seed=BOOTSTRAP_SEED),
        "failure_classes": dict(
            sorted(Counter(r["failure_class"] for r in rows if r["failure_class"]).items())
        ),
    }


def main():
    output, oracle_dir, visible_root, scores = (Path(value) for value in sys.argv[1:5])
    try:
        verify_seals(output)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    protocol = json.loads((output / "protocol.json").read_text("utf-8"))
    backend = (output / "backend.txt").read_text("utf-8").strip()
    schedule = protocol_schedule(protocol)
    ledger_rows = Ledger(output / "ledger.jsonl").rows()
    rows = [
        score_trial(spec, ledger_rows, output, oracle_dir, visible_root, backend)
        for spec in schedule
        if spec.role != CANARY
    ]
    summary = summarize(rows, backend)
    baseline_path = protocol.get("canary_baseline")
    baseline = None if not baseline_path else json.loads(Path(baseline_path).read_text("utf-8"))
    summary["canaries"] = compare_canaries(schedule, ledger_rows, output, baseline)
    scores.mkdir(parents=True, exist_ok=True)
    (scores / "scores.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), "utf-8"
    )
    (scores / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", "utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
