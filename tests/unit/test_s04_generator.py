"""S04 development worlds: committed bytes, invariants, leakage and independent reference."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.generator import generate
from benchmarks.generator.hidden import allocation_outcomes, reference_balances
from benchmarks.generator.invariants import WorldInvariantError, check_world
from benchmarks.generator.render import render_case
from benchmarks.generator.s04_cases import DATASET_VERSION, build_s04_worlds
from benchmarks.generator.s05_cases import build_worlds
from recycleguard.contracts.dossier import CaseManifest

VISIBLE = Path(__file__).resolve().parents[1] / "fixtures" / "visible"
WORLDS = {w.template_key: w for w in build_s04_worlds()}
S05_WORLDS = build_worlds()


def _text(case: Path) -> str:
    return "\n".join(
        p.read_text("utf-8") for p in sorted(case.rglob("*")) if p.suffix in {".jsonl", ".csv"}
    )


def test_regeneration_is_byte_identical_to_the_committed_cases(tmp_path):
    for world in WORLDS.values():
        out = render_case(world, tmp_path)
        committed = VISIBLE / f"case_{world.case_tag}"
        assert generate._differences(out.case_dir, committed) == [], committed.name


def test_each_set_has_its_own_version_and_distinct_case_tags():
    assert {w.dataset_version for w in WORLDS.values()} == {DATASET_VERSION}
    assert DATASET_VERSION != S05_WORLDS[0].dataset_version
    tags = [w.case_tag for w in (*S05_WORLDS, *WORLDS.values())]
    assert len(tags) == len(set(tags)) == 12


def test_manifests_declare_the_optional_tables_that_are_present():
    for world in WORLDS.values():
        case = VISIBLE / f"case_{world.case_tag}"
        manifest = CaseManifest.model_validate_json((case / "case_manifest.json").read_bytes())
        states = {d.table: d.disposition for d in manifest.optional_table_dispositions}
        assert states["product_mappings"] == ("PRESENT" if world.products else "ABSENT")
        assert states["sales"] == ("PRESENT" if world.sales else "ABSENT")
        assert (case / "records/product_mappings.jsonl").exists() == bool(world.products)


def test_worlds_pass_invariants_and_deliberate_ambiguities_are_rejected():
    for world in WORLDS.values():
        check_world(world)
    expired = WORLDS["expired_credit"]
    lot = next(item for item in expired.lots if item.expires_on is not None)
    same_day = next(
        t.when[:10] for t in expired.transfers if t.lot == lot.key
    )  # an end date on the transfer day cannot be ordered at day resolution
    lots = tuple(replace(x, expires_on=same_day) if x is lot else x for x in expired.lots)
    with pytest.raises(WorldInvariantError):
        check_world(replace(expired, lots=lots))
    dated = WORLDS["earlier_liability_dated"]
    first = dated.allocations[0]
    early = replace(first, allocated_on="2024-04-01")  # before its own transfer
    with pytest.raises(WorldInvariantError):
        check_world(replace(dated, allocations=(early, *dated.allocations[1:])))
    cancelled = WORLDS["cancelled_credit"]
    stray = replace(cancelled.lifecycle[0], lot="lot_missing")
    with pytest.raises(WorldInvariantError):
        check_world(replace(cancelled, lifecycle=(stray,)))


def test_visible_files_leak_no_generation_truth():
    hidden = {"fault", "oracle", "hidden", "template", "seed", "s04-dev", "s05-dev"}
    for world in WORLDS.values():
        hidden |= {world.template_key, world.timeline_group}
        lowered = _text(VISIBLE / f"case_{world.case_tag}").lower()
        for term in hidden:
            assert term.lower() not in lowered, (world.template_key, term)
        assert not any(note.lower() in lowered for note in world.notes)


def test_reference_plants_exactly_the_stated_effect_in_each_world():
    def verdicts(key, rule):
        return [r[rule] for r in allocation_outcomes(WORLDS[key]).values()]

    assert verdicts("expired_credit", "lifecycle").count("FAIL") == 1
    assert verdicts("cancelled_credit", "lifecycle").count("FAIL") == 1
    assert verdicts("capability_mismatch", "capability").count("FAIL") == 1
    for key in ("linked_invoice_payment", "weight_basis_conflict", "earlier_liability_dated"):
        assert all(
            r["lifecycle"] == "PASS" and not r["excluded"]
            for r in allocation_outcomes(WORLDS[key]).values()
        )
    assert set(verdicts("earlier_liability_dated", "priority")) == {"NOT_EVALUATED", "PASS"}
    products = reference_balances(WORLDS["weight_basis_conflict"])["product_checks"]
    assert sorted(products["weight_basis"].values()) == ["FAIL", "PASS"]
    assert products["sales"] == "FAIL"


def test_reference_is_independent_of_the_portal_and_keeps_pending_separate():
    reference = reference_balances(WORLDS["expired_credit"])
    (row,) = reference["buckets"]
    assert Decimal(row["delta_portal_minus_supported"]) > 0  # the portal still reports the credit
    pending = reference_balances(WORLDS["linked_invoice_payment"])["buckets"][0]
    initiated = next(
        t for t in WORLDS["linked_invoice_payment"].transfers if t.stage == "INITIATED"
    )
    assert pending["pending"] == initiated.quantity_kg  # payments never add a second quantity
