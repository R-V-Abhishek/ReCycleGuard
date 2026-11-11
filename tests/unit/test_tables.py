import csv
import io

from benchmarks.evaluation.tables import NA, build_tables, percentile


def score(case, variant, repeat, success, **extra):
    row = {
        "trial_id": f"{case}|{variant}|r{repeat}",
        "case_id": case,
        "variant": variant,
        "repeat": repeat,
        "final_status": "AWAITING_REVIEW",
        "model_calls": 4,
        "basis": "SUPPORTED",
        "success": success,
        "not_scored_reason": None,
        "precision": None,
        "recall": None,
        "f1": None,
        "abstention_accuracy": 1.0,
        "forbidden_actions": [],
    }
    return row | extra


def ledger(case, variant, repeat, seconds, tokens, status="SUCCESS"):
    return {
        "trial_id": f"{case}|{variant}|r{repeat}",
        "status": status,
        "wall_seconds": seconds,
        "tokens": tokens,
    }


def read(tables, name):
    return list(csv.DictReader(io.StringIO(tables[name].decode())))


ROWS = [
    score("a", "V1", 1, True),
    score("a", "V1", 2, False),
    score("b", "V1", 1, True, precision=1.0, recall=0.5, f1=0.6667),
    score("a", "V2", 1, True),
    score("b", "V2", 1, False, not_scored_reason="NO_ORACLE"),
    score("c", "V2", 1, False, basis="PREFLIGHT_BLOCK", forbidden_actions=["X"]),
]
LEDGER = [
    ledger("a", "V1", 1, 100.0, 1000),
    ledger("a", "V1", 2, 200.0, 2000),
    ledger("b", "V1", 1, 300.0, None),
    ledger("a", "V2", 1, 50.0, 500),
    ledger("b", "V2", 1, 60.0, 600),
    ledger("c", "V2", 1, 1.0, 0, status="INFRA_FAILED"),
]


def test_primary_table_counts_and_denominators():
    t1 = read(build_tables(ROWS, LEDGER), "t1_primary_success.csv")
    v1, v2 = t1
    assert (v1["scheduled"], v1["scored"], v1["successes"], v1["success_rate"]) == (
        "3",
        "3",
        "2",
        "0.6667",
    )
    assert (v2["scheduled"], v2["scored"], v2["successes"], v2["preflight_blocks"]) == (
        "3",
        "2",
        "1",
        "1",
    )


def test_undefined_values_are_na_never_zero_or_one():
    tables = build_tables(ROWS, LEDGER)
    t3 = {r["variant"]: r for r in read(tables, "t3_findings_and_abstention.csv")}
    assert t3["V1"]["n_precision_defined"] == "1" and t3["V1"]["mean_precision"] == "1.0000"
    assert t3["V2"]["n_precision_defined"] == "0" and t3["V2"]["mean_precision"] == NA
    assert read(tables, "t6_efficiency.csv")[0]["money"] == NA


def test_efficiency_percentiles_and_missing_tokens():
    t6 = {r["variant"]: r for r in read(build_tables(ROWS, LEDGER), "t6_efficiency.csv")}
    assert (
        t6["V1"]["mean_wall_seconds"] == "200.0000" and t6["V1"]["p95_wall_seconds"] == "300.0000"
    )
    assert t6["V1"]["mean_tokens"] == "1500.0000"  # the unreported value is excluded, not zero
    assert percentile([], 0.5) is None and percentile([1, 2, 3, 4], 0.5) == 2


def test_repeat_reliability_and_taxonomy_and_forbidden():
    tables = build_tables(ROWS, LEDGER)
    t7 = {r["variant"]: r for r in read(tables, "t7_reliability_across_repeats.csv")}
    assert t7["V1"]["cases_with_repeats"] == "1" and t7["V1"]["repeats_disagree"] == "1"
    assert t7["V1"]["all_repeats_succeed"] == "0" and t7["V1"]["any_repeat_succeeds"] == "1"
    assert {
        r["variant"]: r["trials_with_forbidden_action"]
        for r in read(tables, "t4_forbidden_actions.csv")
    } == {"V1": "0", "V2": "1"}
    taxonomy = {
        (r["variant"], r["outcome"]): r["trials"] for r in read(tables, "t8_outcome_taxonomy.csv")
    }
    assert taxonomy[("V2", "NO_ORACLE")] == "1"
    assert taxonomy[("V2", "LEDGER_INFRA_FAILED")] == "1"


def metrics(**changes):
    return {
        "buckets_total": 4,
        "buckets_matched": 3,
        "true_positives": 1,
        "false_positives": 1,
        "false_negatives": 0,
        "clean_case": True,
        "unsupported_claims": 2,
        "proposals_made": 3,
        "proposals_accepted": 1,
        "findings_from_model": 1,
        "findings_total": 2,
        "proposals_rejected": {"NO_EVIDENCE_REF": 2},
        "model_attempts": 5,
        "schema_valid_attempts": 4,
        "model_logical_calls": 4,
        "schema_valid_logical_calls": 4,
        "retries": 1,
        "call_timeouts": 0,
        "outcome_unknown_retries": 0,
        "rejected_actions": 1,
        "audit_chain": "VERIFIED",
        "failure_class": "model-reasoning",
    } | changes


def test_full_metric_tables_keep_denominators():
    rows = [score("a", "V1", 1, False, **metrics()), score("a", "V2", 1, True)]
    tables = build_tables(rows, [])
    t2 = {r["variant"]: r for r in read(tables, "t2_exact_reconciliation.csv")}
    assert t2["V1"]["exact_rate"] == "0.7500" and t2["V2"]["exact_rate"] == NA
    micro = read(tables, "t3_findings_micro.csv")[0]
    assert micro["micro_precision"] == "0.5000" and micro["micro_recall"] == "1.0000"
    influence = read(tables, "t3_model_influence.csv")
    assert influence[0]["model_share_of_findings"] == "0.5000"
    assert influence[1]["model_share_of_findings"] == NA
    assert read(tables, "t3_proposals_rejected.csv") == [
        {"variant": "V1", "reason": "NO_EVIDENCE_REF", "proposals": "2"}
    ]
    calls = {r["variant"]: r for r in read(tables, "t6_model_calls.csv")}
    assert calls["V1"]["schema_valid_rate"] == "1.0000" and calls["V1"]["attempts"] == "5"
    assert calls["V1"]["audit_chain_verified_trials"] == "1"
    assert calls["V2"]["schema_valid_rate"] == NA
    clean = {r["variant"]: r for r in read(tables, "t4_clean_and_unsupported.csv")}
    assert clean["V1"]["clean_trials_with_false_positive"] == "1"
    assert read(tables, "t8_failure_classes.csv") == [
        {"variant": "V1", "failure_class": "model-reasoning", "trials": "1"}
    ]
    t1 = read(tables, "t1_primary_success.csv")[0]
    assert t1["ci95_low"] == "0.0000" and t1["ci95_high"] == "0.0000"


def test_per_family_recall_and_false_alarms_with_undefined_recall_as_na():
    rows = [
        score("a", "V1", 1, False, expected_families=["F07"], emitted_families=["F07", "F11"]),
        score("b", "V1", 1, False, expected_families=["F07"], emitted_families=[]),
        score("c", "V2", 1, False, expected_families=["F07"]),  # no report, so nothing was emitted
    ]
    tables = build_tables(rows, [])
    families = {(r["variant"], r["family"]): r for r in read(tables, "t3_findings_per_family.csv")}
    assert families[("V1", "F07")]["recall"] == "0.5000"
    assert (
        families[("V1", "F11")]["false_alarms"] == "1" and families[("V1", "F11")]["recall"] == NA
    )
    macro = {r["variant"]: r for r in read(tables, "t3_findings_macro.csv")}
    assert macro["V1"]["macro_recall"] == "0.5000" and macro["V2"]["macro_recall"] == NA


def test_rubric_table_exists_only_when_scored():
    assert "t5_rubric.csv" not in build_tables(ROWS, LEDGER)
    tables = build_tables(
        ROWS, LEDGER, {"citation": {"items": 3, "raw_agreement": 1.0, "kappa": None}}
    )
    assert read(tables, "t5_rubric.csv") == [
        {"dimension": "citation", "items": "3", "raw_agreement": "1.0000", "kappa": NA}
    ]


def test_output_is_byte_identical_across_calls_and_input_order():
    first = build_tables(ROWS, LEDGER)
    second = build_tables(list(reversed(ROWS)), LEDGER)
    assert first == build_tables(ROWS, LEDGER)
    assert first.keys() == second.keys()
    assert first["t1_primary_success.csv"] == second["t1_primary_success.csv"]
