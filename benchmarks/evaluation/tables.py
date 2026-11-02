"""Results tables rebuilt from scores and the trial ledger. Pure functions; byte-stable output.

Every table keeps its denominators. A value that is undefined is written as ``NA``, never as 0 or 1.
Money is always ``NA``: local inference is not metered.
"""

import csv
import io
import math
from collections import defaultdict

NA = "NA"


def percentile(values: list[float], fraction: float):
    """Nearest-rank percentile; None for no data."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def _cell(value):
    if value is None:
        return NA
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def to_csv(header: list[str], rows: list[list]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([_cell(value) for value in row])
    return stream.getvalue().encode("utf-8")


def _last_ledger_rows(ledger_rows: list[dict]) -> dict:
    last = {}
    for row in ledger_rows:
        if row["status"] != "STARTED":
            last[row["trial_id"]] = row
    return last


def _mean(values):
    defined = [v for v in values if v is not None]
    return (sum(defined) / len(defined)) if defined else None


def build_tables(scores: list[dict], ledger_rows: list[dict]) -> dict[str, bytes]:
    """Return ``{filename: csv bytes}``. ``scores`` are score_trials rows."""
    ledger = _last_ledger_rows(ledger_rows)
    variants = sorted({row["variant"] for row in scores})
    by_variant = {v: [r for r in scores if r["variant"] == v] for v in variants}
    tables = {}

    rows = []
    for v in variants:
        mine = by_variant[v]
        scored = [r for r in mine if r["not_scored_reason"] is None]
        wins = sum(bool(r["success"]) for r in scored)
        blocks = sum(r["basis"] == "PREFLIGHT_BLOCK" for r in scored)
        rows.append(
            [v, len(mine), len(scored), wins, wins / len(scored) if scored else None, blocks]
        )
    tables["t1_primary_success.csv"] = to_csv(
        ["variant", "scheduled", "scored", "successes", "success_rate", "preflight_blocks"], rows
    )

    rows = [
        [
            v,
            sum(r["precision"] is not None for r in by_variant[v]),
            _mean([r["precision"] for r in by_variant[v]]),
            sum(r["recall"] is not None for r in by_variant[v]),
            _mean([r["recall"] for r in by_variant[v]]),
            sum(r["f1"] is not None for r in by_variant[v]),
            _mean([r["f1"] for r in by_variant[v]]),
            _mean([r["abstention_accuracy"] for r in by_variant[v]]),
        ]
        for v in variants
    ]
    tables["t3_findings_and_abstention.csv"] = to_csv(
        [
            "variant",
            "n_precision_defined",
            "mean_precision",
            "n_recall_defined",
            "mean_recall",
            "n_f1_defined",
            "mean_f1",
            "mean_abstention_accuracy",
        ],
        rows,
    )

    rows = []
    for v in variants:
        mine = by_variant[v]
        violating = sum(bool(r["forbidden_actions"]) for r in mine)
        rows.append([v, len(mine), violating])
    tables["t4_forbidden_actions.csv"] = to_csv(
        ["variant", "trials", "trials_with_forbidden_action"], rows
    )

    rows = []
    for v in variants:
        seen = [ledger[r["trial_id"]] for r in by_variant[v] if r["trial_id"] in ledger]
        seconds = [x["wall_seconds"] for x in seen if x.get("wall_seconds") is not None]
        tokens = [x["tokens"] for x in seen if x.get("tokens") is not None]
        calls = [r["model_calls"] for r in by_variant[v] if r["model_calls"] is not None]
        rows.append(
            [
                v,
                len(seen),
                _mean(calls),
                _mean(tokens),
                _mean(seconds),
                percentile(seconds, 0.5),
                percentile(seconds, 0.95),
                NA,
            ]
        )
    tables["t6_efficiency.csv"] = to_csv(
        [
            "variant",
            "trials_with_result",
            "mean_model_calls",
            "mean_tokens",
            "mean_wall_seconds",
            "p50_wall_seconds",
            "p95_wall_seconds",
            "money",
        ],
        rows,
    )

    per_case = defaultdict(lambda: defaultdict(list))
    for r in scores:
        if r["not_scored_reason"] is None:
            per_case[r["variant"]][r["case_id"]].append(bool(r["success"]))
    rows = []
    for v in variants:
        cases = per_case[v]
        repeated = {c: s for c, s in cases.items() if len(s) > 1}
        rows.append(
            [
                v,
                len(cases),
                len(repeated),
                sum(all(s) for s in repeated.values()),
                sum(any(s) for s in repeated.values()),
                sum(len(set(s)) > 1 for s in repeated.values()),
            ]
        )
    tables["t7_reliability_across_repeats.csv"] = to_csv(
        [
            "variant",
            "cases_scored",
            "cases_with_repeats",
            "all_repeats_succeed",
            "any_repeat_succeeds",
            "repeats_disagree",
        ],
        rows,
    )

    counts = defaultdict(int)
    for r in scores:
        reason = r["not_scored_reason"] or r["basis"] or "UNKNOWN"
        counts[(r["variant"], reason.split(":")[0])] += 1
        entry = ledger.get(r["trial_id"])
        if entry and entry["status"] in {"INFRA_FAILED", "FAILED"}:
            counts[(r["variant"], f"LEDGER_{entry['status']}")] += 1
    tables["t8_outcome_taxonomy.csv"] = to_csv(
        ["variant", "outcome", "trials"], [[v, o, n] for (v, o), n in sorted(counts.items())]
    )
    return tables
