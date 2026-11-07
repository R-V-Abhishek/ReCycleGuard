import pytest

from benchmarks.evaluation.rubric import (
    BRIEF_SCORES,
    agreement,
    brief_comparison,
    brief_item_key,
    build_brief_sheet,
    build_sheet,
    cohens_kappa,
    disputes,
    preference_agreement,
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


def brief_items(count):
    return {
        brief_item_key(f"c{n}|V1|r1", f"finding_revision:{n}"): {
            "finding_text": f"finding {n}",
            "model": f"model brief {n}",
            "template": f"template brief {n}",
        }
        for n in range(count)
    }


def test_brief_sheet_hides_which_brief_is_which_and_the_key_maps_both():
    items = brief_items(8)
    rows, key = build_brief_sheet(items, sorted(items), "s")
    assert (rows, key) == build_brief_sheet(items, sorted(items), "s")
    for row in rows:
        sides = key[row["item_id"]]
        item = items[brief_item_key(sides["trial_id"], sides["finding_revision_id"])]
        shown = {sides["brief_1"]: row["brief_1_text"], sides["brief_2"]: row["brief_2_text"]}
        assert shown == {"MODEL": item["model"], "TEMPLATE": item["template"]}
        assert row["finding_text"] == item["finding_text"]
        assert "trial_id" not in row and "|V1|" not in repr(row)
        assert all(row[score] is None for score in BRIEF_SCORES) and row["preferred"] is None
    # The order is seeded per item, so the model brief is not always shown first.
    assert {sides["brief_1"] for sides in key.values()} == {"MODEL", "TEMPLATE"}
    with pytest.raises(ValueError):
        build_brief_sheet({"a\0f": {"variant": "V1", "model": "m", "template": "t"}}, ["a\0f"], "s")


def test_brief_comparison_unblinds_scores_and_preferences_by_source():
    items = brief_items(2)
    rows, key = build_brief_sheet(items, sorted(items), "s")
    scores = {}
    for row in rows:
        model_slot = "1" if key[row["item_id"]]["brief_1"] == "MODEL" else "2"
        other = "2" if model_slot == "1" else "1"
        scores[row["item_id"]] = {
            f"brief_{model_slot}_usefulness": "PASS",
            f"brief_{other}_usefulness": "FAIL",
            "preferred": model_slot,
        }
    result = brief_comparison(scores, key)
    assert result["pass_rate"]["MODEL"]["usefulness"] == 1.0
    assert result["pass_rate"]["TEMPLATE"]["usefulness"] == 0.0
    assert result["pass_rate"]["MODEL"]["citation_support"] is None
    assert result["preferred"] == {"MODEL": 2}
    same = {i: {"preferred": "SAME"} for i in scores}
    assert brief_comparison(same, key)["preferred"] == {"SAME": 2}
    agreed = preference_agreement(scores, scores)["preferred"]
    assert agreed["items"] == 2 and agreed["raw_agreement"] == 1.0
    assert agreement(scores, scores, BRIEF_SCORES)["brief_1_usefulness"]["items"] == 2
