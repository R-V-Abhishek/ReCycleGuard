import pytest

from benchmarks.evaluation.rubric import (
    agreement,
    build_sheet,
    cohens_kappa,
    disputes,
    select_trials,
)

TRIALS = [f"c{n}|V{v}|r{r}" for n in range(6) for v in (1, 2) for r in (1, 2)]


def test_selection_is_seeded_nested_and_covers_the_requested_share():
    scored, double = select_trials(TRIALS, "s", fraction=0.5, double_fraction=0.25)
    assert (scored, double) == select_trials(TRIALS, "s", fraction=0.5, double_fraction=0.25)
    assert len(scored) == 12 and len(double) == 3 and set(double) <= set(scored)
    assert select_trials(TRIALS, "t", fraction=0.5, double_fraction=0.25)[0] != scored
    assert select_trials(TRIALS, "s", fraction=1, double_fraction=0.01)[1]  # at least one
    with pytest.raises(ValueError):
        select_trials(TRIALS, "s", fraction=0, double_fraction=0.2)


def test_sheet_hides_trial_identity_and_is_reproducible():
    items = {t: {"claim": f"claim for {t}", "evidence": "e"} for t in TRIALS[:4]}
    rows, key = build_sheet(items, TRIALS[:4], "s")
    assert (rows, key) == build_sheet(items, TRIALS[:4], "s")
    shown = repr(rows)
    assert not any(t in shown.replace("claim for " + t, "") for t in TRIALS[:4])
    assert sorted(key.values()) == sorted(TRIALS[:4])
    assert all(row["citation_support"] is None for row in rows)
    with pytest.raises(ValueError):
        build_sheet({"a": {"variant": "V1"}}, ["a"], "s")


def test_kappa_and_agreement_handle_undefined_cases():
    assert cohens_kappa(["PASS", "FAIL"], ["PASS", "FAIL"]) == 1.0
    assert cohens_kappa(["PASS", "PASS"], ["PASS", "PASS"]) is None
    assert cohens_kappa(["PASS", "FAIL"], ["FAIL", "PASS"]) == -1.0
    first = {"i1": {"citation_support": "PASS"}, "i2": {"citation_support": "FAIL"}}
    second = {"i1": {"citation_support": "PASS"}, "i2": {"citation_support": "PARTIAL"}}
    result = agreement(first, second)
    assert result["citation_support"]["raw_agreement"] == 0.5
    assert result["temporal_correctness"] == {"items": 0, "raw_agreement": None, "kappa": None}
    assert disputes(first, second) == ["i2"]
