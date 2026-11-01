"""Paired bootstrap against tables whose answers are known by hand."""

from benchmarks.evaluation.analysis import paired_bootstrap


def row(case, variant, success):
    return {"case_id": case, "variant": variant, "success": success}


def test_identical_variants_have_a_zero_interval():
    rows = [row(c, v, c == "a") for c in "abcd" for v in ("V1", "V2")]
    result = paired_bootstrap(rows, "V1", "V2", resamples=200, seed=1)
    assert result["difference"] == 0 and result["interval_95"] == [0, 0]
    assert result["cases"] == 4


def test_hand_checked_difference_and_interval_limits():
    # V2 wins 3 of 4 and V1 wins 1 of 4, so the difference is 0.75 - 0.25.
    rows = [
        row("a", "V1", True),
        row("a", "V2", True),
        row("b", "V1", False),
        row("b", "V2", True),
        row("c", "V1", False),
        row("c", "V2", True),
        row("d", "V1", False),
        row("d", "V2", False),
    ]
    result = paired_bootstrap(rows, "V1", "V2", resamples=2000, seed=7)
    assert result["difference"] == 0.5
    low, high = result["interval_95"]
    assert 0 <= low < 0.5 < high <= 1


def test_same_seed_repeats_and_another_seed_may_differ():
    rows = [row(c, "V1", c in "ab") for c in "abcdef"] + [
        row(c, "V2", c in "cde") for c in "abcdef"
    ]
    first = paired_bootstrap(rows, "V1", "V2", resamples=500, seed=3)
    assert first == paired_bootstrap(rows, "V1", "V2", resamples=500, seed=3)


def test_resampling_keeps_all_repeats_of_a_case():
    # Case a always ties; case b has V2 ahead in exactly one of two repeats.
    rows = [
        row("a", "V1", True),
        row("a", "V1", True),
        row("a", "V2", True),
        row("a", "V2", True),
        row("b", "V1", False),
        row("b", "V1", False),
        row("b", "V2", True),
        row("b", "V2", False),
    ]
    result = paired_bootstrap(rows, "V1", "V2", resamples=1000, seed=5)
    assert result["difference"] == 0.25
    # Whole-case resampling can only give 0, 1/4 or 1/2.
    assert set(result["interval_95"]) <= {0.0, 0.25, 0.5}


def test_unpaired_case_is_excluded_and_counted():
    rows = [row("a", "V1", True), row("a", "V2", True), row("b", "V1", True)]
    result = paired_bootstrap(rows, "V1", "V2", resamples=50, seed=1)
    assert result["cases"] == 1 and result["excluded_unpaired_cases"] == 1


def test_no_pairs_are_undefined_rather_than_zero():
    result = paired_bootstrap([row("a", "V1", True)], "V1", "V2", seed=1)
    assert result["difference"] is None and result["interval_95"] is None
