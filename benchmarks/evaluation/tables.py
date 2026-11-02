"""Results tables rebuilt from scores and the trial ledger. Pure functions; byte-stable output.

Every table keeps its denominators. A value that is undefined is written as ``NA``, never as 0 or 1.
Money is always ``NA``: local inference is not metered.
"""

import csv
import io
import math
from collections import defaultdict

from benchmarks.evaluation.analysis import rate_interval

NA = "NA"
INTERVAL_SEED = 20261101


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


def _ratio(part, whole):
    return part / whole if whole else None


def _total(rows, key):
    """Sum over the rows that report ``key``; None when none does, never 0."""
    defined = [r[key] for r in rows if r.get(key) is not None]
    return sum(defined) if defined else None


def build_tables(
    scores: list[dict], ledger_rows: list[dict], rubric: dict | None = None
) -> dict[str, bytes]:
    """Return ``{filename: csv bytes}``. ``scores`` are score_trials rows.

    ``rubric`` is ``rubric.agreement`` output; T5 needs human scoring, so without it there is no
    T5 file rather than an empty one that could be read as measured.
    """
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
        interval = rate_interval(scored, v, seed=INTERVAL_SEED) or (None, None)
        rows.append(
            [
                v,
                len(mine),
                len(scored),
                wins,
                wins / len(scored) if scored else None,
                interval[0],
                interval[1],
                blocks,
            ]
        )
    tables["t1_primary_success.csv"] = to_csv(
        [
            "variant",
            "scheduled",
            "scored",
            "successes",
            "success_rate",
            "ci95_low",
            "ci95_high",
            "preflight_blocks",
        ],
        rows,
    )

    rows = []
    for v in variants:
        with_buckets = [r for r in by_variant[v] if r.get("buckets_total") is not None]
        rows.append(
            [
                v,
                len(with_buckets),
                sum(r["buckets_total"] for r in with_buckets),
                sum(r["buckets_matched"] for r in with_buckets),
                _ratio(
                    sum(r["buckets_matched"] for r in with_buckets),
                    sum(r["buckets_total"] for r in with_buckets),
                ),
            ]
        )
    tables["t2_exact_reconciliation.csv"] = to_csv(
        ["variant", "trials_with_buckets", "buckets", "exact_buckets", "exact_rate"], rows
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
        tp = _total(by_variant[v], "true_positives")
        fp = _total(by_variant[v], "false_positives")
        fn = _total(by_variant[v], "false_negatives")
        precision = None if tp is None or fp is None else _ratio(tp, tp + fp)
        recall = None if tp is None or fn is None else _ratio(tp, tp + fn)
        f1 = (
            None
            if precision is None or recall is None
            else _ratio(2 * precision * recall, precision + recall)
        )
        rows.append([v, tp, fp, fn, precision, recall, f1])
    tables["t3_findings_micro.csv"] = to_csv(
        [
            "variant",
            "true_positives",
            "false_positives",
            "false_negatives",
            "micro_precision",
            "micro_recall",
            "micro_f1",
        ],
        rows,
    )

    family_counts = defaultdict(lambda: {"expected": 0, "found": 0, "false_alarms": 0})
    for r in scores:
        if r.get("expected_families") is None or r.get("emitted_families") is None:
            continue
        expected, emitted = set(r["expected_families"]), set(r["emitted_families"])
        for family in expected | emitted:
            counts_for = family_counts[(r["variant"], family)]
            counts_for["expected"] += family in expected
            counts_for["found"] += family in expected and family in emitted
            counts_for["false_alarms"] += family in emitted and family not in expected
    rows = []
    recalls = defaultdict(list)
    for (v, family), counted in sorted(family_counts.items()):
        recall = _ratio(counted["found"], counted["expected"])
        if recall is not None:
            recalls[v].append(recall)
        rows.append(
            [v, family, counted["expected"], counted["found"], counted["false_alarms"], recall]
        )
    tables["t3_findings_per_family.csv"] = to_csv(
        ["variant", "family", "trials_expected", "trials_found", "false_alarms", "recall"], rows
    )
    tables["t3_findings_macro.csv"] = to_csv(
        ["variant", "families_expected", "macro_recall"],
        [[v, len(recalls[v]), _mean(recalls[v])] for v in variants],
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
        clean = [r for r in by_variant[v] if r.get("clean_case") and r.get("buckets_total")]
        rows.append(
            [
                v,
                len(clean),
                sum(bool(r.get("false_positives")) for r in clean),
                _mean([r["abstention_accuracy"] for r in by_variant[v]]),
                _total(by_variant[v], "unsupported_claims"),
            ]
        )
    tables["t4_clean_and_unsupported.csv"] = to_csv(
        [
            "variant",
            "clean_trials",
            "clean_trials_with_false_positive",
            "mean_abstention_accuracy",
            "unsupported_claims",
        ],
        rows,
    )

    if rubric:
        tables["t5_rubric.csv"] = to_csv(
            ["dimension", "items", "raw_agreement", "kappa"],
            [
                [dimension, value["items"], value["raw_agreement"], value["kappa"]]
                for dimension, value in sorted(rubric.items())
            ],
        )

    rows = []
    for v in variants:
        mine = by_variant[v]
        rows.append(
            [
                v,
                _total(mine, "proposals_made"),
                _total(mine, "proposals_accepted"),
                _total(mine, "findings_from_model"),
                _total(mine, "findings_total"),
                _ratio(_total(mine, "findings_from_model"), _total(mine, "findings_total") or 0)
                if _total(mine, "findings_from_model") is not None
                else None,
            ]
        )
    tables["t3_model_influence.csv"] = to_csv(
        [
            "variant",
            "proposals_made",
            "proposals_accepted",
            "findings_from_model",
            "findings_total",
            "model_share_of_findings",
        ],
        rows,
    )

    reasons = defaultdict(int)
    for r in scores:
        for reason, count in (r.get("proposals_rejected") or {}).items():
            reasons[(r["variant"], reason)] += count
    tables["t3_proposals_rejected.csv"] = to_csv(
        ["variant", "reason", "proposals"], [[v, o, n] for (v, o), n in sorted(reasons.items())]
    )

    rows = []
    for v in variants:
        mine = by_variant[v]
        attempts = _total(mine, "model_attempts")
        logical = _total(mine, "model_logical_calls")
        valid = _total(mine, "schema_valid_logical_calls")
        timeouts = _total(mine, "call_timeouts")
        rows.append(
            [
                v,
                attempts,
                _total(mine, "schema_valid_attempts"),
                logical,
                valid,
                None if valid is None else _ratio(valid, logical or 0),
                _total(mine, "retries"),
                timeouts,
                None if timeouts is None else _ratio(timeouts, attempts or 0),
                _total(mine, "outcome_unknown_retries"),
                _total(mine, "rejected_actions"),
                sum(r.get("audit_chain") == "VERIFIED" for r in mine),
            ]
        )
    tables["t6_model_calls.csv"] = to_csv(
        [
            "variant",
            "attempts",
            "schema_valid_attempts",
            "logical_calls",
            "schema_valid_logical_calls",
            "schema_valid_rate",
            "retries",
            "call_timeouts",
            "call_timeout_rate",
            "outcome_unknown_retries",
            "rejected_actions",
            "audit_chain_verified_trials",
        ],
        rows,
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

    classes = defaultdict(int)
    for r in scores:
        if r.get("failure_class"):
            classes[(r["variant"], r["failure_class"])] += 1
    tables["t8_failure_classes.csv"] = to_csv(
        ["variant", "failure_class", "trials"],
        [[v, o, n] for (v, o), n in sorted(classes.items())],
    )
    return tables
