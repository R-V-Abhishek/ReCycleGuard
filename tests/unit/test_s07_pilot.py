"""S07 pilot: grouped 24/24 split, independence, leakage, committed bytes and the held-out seal."""

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import get_args

import pytest

from benchmarks.evaluation.oracle import write_oracle_records
from benchmarks.generator import generate, pilot
from benchmarks.generator.hidden import write_hidden
from benchmarks.generator.pilot_cases import DEV, HELD_OUT, SPLIT_POLICY, build_pilot_cases
from benchmarks.generator.render import render_case
from benchmarks.generator.s04_cases import build_s04_worlds
from benchmarks.generator.s05_cases import build_worlds
from benchmarks.generator.s06_cases import build_s06_cases
from recycleguard.contracts.results import FaultFamily

REPO = Path(__file__).resolve().parents[2]
VISIBLE = REPO / "tests" / "fixtures" / "visible"
CASES = build_pilot_cases()
EARLIER = [*build_worlds(), *build_s04_worlds(), *(c.world for c in build_s06_cases())]


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    root = tmp_path_factory.mktemp("pilot")
    return [render_case(c.world, root / c.split) for c in CASES]


def _split(name):
    return [c for c in CASES if c.split == name]


@pytest.mark.parametrize("split", [DEV, HELD_OUT])
def test_each_split_has_sixteen_families_and_eight_combinations(split):
    cases = _split(split)
    singles = [c for c in cases if len(c.corrupted.changes) <= 1]
    combos = [c for c in cases if len(c.corrupted.changes) > 1]
    assert (len(cases), len(singles), len(combos)) == (24, 16, 8)
    assert {f for c in singles for f in c.corrupted.families} == set(get_args(FaultFamily))
    assert Counter(f for c in singles for f in c.corrupted.families).most_common(1)[0][1] == 1


def test_splits_share_no_template_combination_entity_group_or_world_id():
    assert pilot.split_problems(list(CASES)) == []


def test_held_out_parties_and_templates_appear_in_no_development_dossier():
    held = _split(HELD_OUT)
    dev_worlds = [c.world for c in _split(DEV)] + EARLIER
    seen = {w.producer.legal_name for w in dev_worlds} | {
        x.legal_name for w in dev_worlds for x in w.recyclers
    }
    for case in held:
        names = {case.world.producer.legal_name, *(x.legal_name for x in case.world.recyclers)}
        assert not names & seen, case.world.case_tag
    assert not {c.spec.template_key for c in held} & {w.template_key for w in EARLIER}
    tags = [w.case_tag for w in EARLIER] + [c.world.case_tag for c in CASES]
    assert len(tags) == len(set(tags)) == 33 + 48


def test_variant_families_take_different_forms_in_each_split():
    def forms(split, family):
        return {
            str(change.transformation)
            for c in _split(split)
            for change in c.corrupted.changes
            if change.family == family and len(c.corrupted.changes) == 1
        }

    for family in (
        "F08_PRIOR_ARREARS_DRAIN",
        "F10_CAPABILITY_MISMATCH",
        "F15_EXTRACTION_PAGE_LOSS",
    ):
        assert forms(DEV, family) and forms(HELD_OUT, family)
        assert not forms(DEV, family) & forms(HELD_OUT, family), family


def test_visible_bytes_carry_no_labels_duplicates_or_near_duplicates(rendered):
    assert pilot.leakage_problems(list(CASES), rendered) == []


def test_development_split_is_committed_byte_for_byte(rendered):
    for case, out in zip(CASES, rendered, strict=True):
        committed = VISIBLE / out.case_dir.name
        if case.split == DEV:
            assert generate._differences(out.case_dir, committed) == [], case.spec.name
        else:
            assert not committed.exists()  # held-out dossiers never land in the fixtures


def test_held_out_split_matches_the_committed_seal(rendered):
    committed = json.loads(pilot.SEAL_PATH.read_text("utf-8"))
    assert pilot.seal_problems(committed, pilot.seal(list(CASES), rendered)) == []
    assert set(committed) == {"dataset_version", "note", "cases", "aggregate_sha256"}
    assert len(committed["cases"]) == 24
    text = pilot.SEAL_PATH.read_text("utf-8").lower()
    for word in ("held", "dev", "seed", "template", "fault", "recipe", "split", "pilot_"):
        assert word not in text  # hex digests may contain "f0"; words cannot
    assert "benchmarks/heldout/" in (REPO / ".gitignore").read_text()


def test_hidden_record_carries_split_membership_and_oracle(tmp_path, rendered):
    worlds = [c.world for c in CASES]
    splits = {c.world.case_id: {"split": c.split, "template": c.spec.template_key} for c in CASES}
    root = write_hidden(
        tmp_path,
        worlds,
        rendered,
        cases=[c.corrupted for c in CASES],
        split_policy=SPLIT_POLICY,
        splits=splits,
    )
    blobs = write_oracle_records(tmp_path, worlds, rendered)
    manifest = json.loads((root / "generation_manifest.json").read_text())
    assert manifest["split_policy"] == SPLIT_POLICY
    assert Counter(manifest["split_assignments"].values()) == {DEV: 24, HELD_OUT: 24}
    assert manifest["split_groups"][worlds[0].case_id] == {"template": CASES[0].spec.template_key}
    assert manifest["oracle_blob"] == blobs
    for case in CASES:
        body = (root / "oracle" / f"{case.world.case_tag}.json").read_bytes()
        assert blobs[case.world.case_id] == hashlib.sha256(body).hexdigest()
        oracle = json.loads(body)
        assert (
            sorted(f["issue_type"] for f in oracle["expected_findings"]) == case.corrupted.families
        )


def test_a_regenerated_split_is_deterministic():
    again = [c.corrupted for c in build_pilot_cases.__wrapped__()]  # bypass the cache
    assert [c.world for c in again] == [c.world for c in CASES]
