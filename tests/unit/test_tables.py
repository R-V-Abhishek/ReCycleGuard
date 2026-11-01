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


def test_output_is_byte_identical_across_calls_and_input_order():
    first = build_tables(ROWS, LEDGER)
    second = build_tables(list(reversed(ROWS)), LEDGER)
    assert first == build_tables(ROWS, LEDGER)
    assert first.keys() == second.keys()
    assert first["t1_primary_success.csv"] == second["t1_primary_success.csv"]
