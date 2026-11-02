"""S06 fault recipes: coverage of F01-F16, declared invariant breaks, visible effects, records."""

from dataclasses import replace
from decimal import Decimal
from typing import get_args

import pytest

from benchmarks.generator.faults import recipes as r
from benchmarks.generator.faults.records import CorruptionRecord, ExpectedEffects
from benchmarks.generator.faults.validate import validate
from benchmarks.generator.hidden import fault_records, reference_balances
from benchmarks.generator.invariants import RULES, WorldInvariantError, check_world
from benchmarks.generator.render import render_case
from benchmarks.generator.s06_cases import TEMPLATES, build_s06_cases
from recycleguard.contracts.results import FaultFamily

CASES = {c.world.template_key: c for c in build_s06_cases()}


def test_every_fault_family_has_a_recipe_and_a_dossier():
    families = set(get_args(FaultFamily))
    assert set(r.RECIPES) == families
    covered = {f for c in CASES.values() for f in c.families}
    assert covered == families
    singles = [c for c in CASES.values() if len(c.changes) <= 1]
    combos = [c for c in CASES.values() if len(c.changes) > 1]
    assert len(singles) == 17 and len(combos) == 4  # F15 is rendered in both forms


@pytest.mark.parametrize("key", sorted(CASES))
def test_clean_counterpart_passes_every_invariant(key):
    case = CASES[key]
    assert case.clean.relaxed == ()
    check_world(case.clean)


@pytest.mark.parametrize("key", sorted(CASES))
def test_corruption_breaks_only_the_rules_it_declares(key):
    case = CASES[key]
    check_world(case.world)  # passes with its declared relaxations
    declared = {b for c in case.changes for b in c.breaks}
    assert set(case.world.relaxed) == declared
    for rule in declared:  # each declared break is real, not a blanket exemption
        with pytest.raises(WorldInvariantError, match=rule):
            check_world(replace(case.world, relaxed=tuple(sorted(declared - {rule}))))


def test_unknown_relaxations_are_rejected():
    world = CASES["baseline"].world
    with pytest.raises(WorldInvariantError, match="unknown invariant"):
        check_world(replace(world, relaxed=("NOT_A_RULE",)))
    assert "BALANCE_MATCHES_PORTAL" in RULES


def test_recipes_are_deterministic():
    for template in TEMPLATES[:6]:
        first_clean, steps = template()
        again_clean, again_steps = template()
        first = r.corrupt(first_clean, steps, first_clean.seed)
        again = r.corrupt(again_clean, again_steps, again_clean.seed)
        assert first.world == again.world and first.changes == again.changes


@pytest.mark.parametrize("key", sorted(k for k, c in CASES.items() if c.changes))
def test_validation_finds_the_effect_and_fails_without_it(tmp_path, key):
    case = CASES[key]
    out = render_case(case.world, tmp_path / "visible")
    assert validate(case, out) == []
    # The same claims made about the clean counterpart must not validate.
    clean = render_case(case.clean, tmp_path / "clean")
    fake = r.Corrupted(clean=case.clean, world=case.clean, changes=case.changes)
    assert validate(fake, clean) != []


@pytest.mark.parametrize("key", sorted(CASES))
def test_corruption_records_and_expected_effects_are_well_formed(tmp_path, key):
    case = CASES[key]
    out = render_case(case.world, tmp_path)
    records, expected = fault_records(case, out)
    assert len(records) == len(case.changes)
    for record in records:
        CorruptionRecord.model_validate(record)
        assert record["affected_visible_asset_refs"]
        for path in record["affected_visible_asset_refs"]:
            assert (out.case_dir / path).is_file(), path
    effects = ExpectedEffects.model_validate(expected)
    assert effects.fault_families == case.families
    if not case.changes:
        assert effects.clean_reference_buckets == effects.visible_reference_buckets


def test_text_and_representation_faults_change_no_quantity():
    text_only = {
        "F11_WRONG_PERIOD_RULE",
        "F12_UNSEEN_NOTICE_LEAD",
        "F14_OUT_OF_SCOPE_REGIME",
        "F15_EXTRACTION_PAGE_LOSS",
        "F16_PROMPT_INJECTION",
        "F13_WEIGHT_BASIS_CONFLICT",
        "F03_MULTISTAGE_ID_REUSE",
        "F04_UNIT_DIMENSION_MIX",
    }
    for case in CASES.values():
        if case.changes and set(case.families) <= text_only:
            assert (
                reference_balances(case.world)["buckets"]
                == reference_balances(case.clean)["buckets"]
            )


def test_quantity_faults_change_what_the_evidence_justifies():
    def visible(key):
        return reference_balances(CASES[key].world)["buckets"]

    def clean(key):
        return reference_balances(CASES[key].clean)["buckets"]

    for key in ("overlap", "alias", "arrears", "capability"):
        assert visible(key) != clean(key), key
    # A credit of another metal is excluded outright, so the totals stay the clean ones.
    assert visible("units_metal") == clean("units_metal")
    checks = reference_balances(CASES["units_metal"].world)["allocation_checks"].values()
    assert [c["code"] for c in checks if c["excluded"]] == ["DIMENSION_MISMATCH"]
    (row,) = visible("stale")
    assert Decimal(row["delta_portal_minus_supported"]) < 0  # an older statement reports less
    (paid,) = visible("paid")
    assert paid["supported"] == clean("paid")[0]["supported"]  # payment adds no supported credit
