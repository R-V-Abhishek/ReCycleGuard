"""Score sealed trials against oracle records. Evaluator-only; run as its own process.

Every scheduled trial gets a row. A case whose independent visible reference cannot be computed is
written as NOT_SCORED and never becomes a score.

    uv run scripts/score_trials.py <trial-output> <oracle-dir> <visible-root> <scores-output>
"""

import json
import sys
from pathlib import Path

from benchmarks.evaluation.analysis import paired_bootstrap
from benchmarks.evaluation.oracle import OracleCase
from benchmarks.evaluation.scoring import (
    ScoringProtocol,
    case_success,
    project_investigation_report,
)
from benchmarks.evaluation.trials import Ledger, build_schedule, verify_seals
from benchmarks.evaluation.visible_reference import bind_oracle_reference, inspect_visible

BOOTSTRAP_SEED = 20261101
PAIR = ("FIXED_RETRIEVAL", "ADAPTIVE")


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
    }
    finished = [
        r for r in ledger_rows if r["trial_id"] == spec.trial_id and r["status"] != "STARTED"
    ]
    last = finished[-1] if finished else None
    if last is None or last.get("result_digest") is None:
        row["basis"] = "NOT_RUN" if last is None else last["status"]
        return row
    result = json.loads((output / "results" / f"{last['result_digest']}.json").read_text("utf-8"))
    row["final_status"] = result["status"]
    row["model_calls"] = result["budget"]["model_calls"]
    oracle_path = oracle_dir / f"{spec.case_id.removeprefix('case_')}.json"
    if not oracle_path.is_file():
        row["not_scored_reason"] = "NO_ORACLE"
        return row
    oracle = OracleCase.model_validate_json(oracle_path.read_bytes())
    if oracle.visible_reference_status == "UNVERIFIED_WORLD_PROJECTION":
        # Stored candidates are unreviewed; the reference is recomputed from visible evidence.
        try:
            reference = inspect_visible(visible_root / spec.case_id)
            oracle, _, _ = bind_oracle_reference(oracle, reference)
        except (ValueError, OSError) as exc:
            row["not_scored_reason"] = f"REFERENCE_FAILED: {exc}"[:200]
            return row
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
        )
    row["success"], row["basis"] = case_success(
        trial, oracle, result["status"], result["budget"]["model_calls"]
    )
    return row


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
            "preflight_blocks": sum(row["basis"] == "PREFLIGHT_BLOCK" for row in mine),
        }
    return {
        "backend": backend,
        "not_scored": sum(row["not_scored_reason"] is not None for row in rows),
        "by_variant": by_variant,
        "v2_minus_v1": paired_bootstrap(scored, *PAIR, seed=BOOTSTRAP_SEED),
        "v2_minus_v1_without_preflight_blocks": paired_bootstrap(
            without_blocks, *PAIR, seed=BOOTSTRAP_SEED
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
    schedule = build_schedule(
        protocol["case_ids"], tuple(protocol["variants"]), protocol["repeats"]
    )
    ledger_rows = Ledger(output / "ledger.jsonl").rows()
    rows = [
        score_trial(spec, ledger_rows, output, oracle_dir, visible_root, backend)
        for spec in schedule
    ]
    summary = summarize(rows, backend)
    scores.mkdir(parents=True, exist_ok=True)
    (scores / "scores.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), "utf-8"
    )
    (scores / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", "utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
