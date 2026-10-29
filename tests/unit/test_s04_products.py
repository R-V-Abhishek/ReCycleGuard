"""S04 product mapping and sales (F13): weight bases are labelled, conflicts escalated."""

import pytest
from pydantic import ValidationError

from recycleguard.contracts.core import Quantity
from tests.support.c08 import PRODUCER, check, interval, mapping, sale, verdicts

FY = "2024-2025"


def lookup(tmp_path, records, sku="SKU-1", period=FY):
    result = check(tmp_path, records, "LOOKUP_PRODUCT_MAPPING", [PRODUCER, sku], period=period)
    return result.output.results[0]


def test_mapping_valid_for_the_whole_year_passes(tmp_path):
    target = lookup(tmp_path, [mapping()])
    assert target.verdict == "PASS"
    assert target.values["weight_basis"] == "NET_EEE" and target.values["eee_code"] == "EEE-1"


def test_unmapped_sku_is_unknown(tmp_path):
    assert lookup(tmp_path, [mapping()], sku="SKU-9").verdict == "UNKNOWN"


def test_mapping_that_starts_mid_year_is_unresolved_not_assumed(tmp_path):
    assert lookup(tmp_path, [mapping(validity=interval("2024-09-01"))]).verdict == "UNKNOWN"


def test_mapping_that_ended_before_the_year_fails(tmp_path):
    ended = interval("2022-01-01", "2024-03-01", open_ended=False)
    assert lookup(tmp_path, [mapping(validity=ended)]).verdict == "FAIL"


def test_unreviewed_mapping_validity_is_unknown(tmp_path):
    assert lookup(tmp_path, [mapping(validity=interval(review="DRAFT"))]).verdict == "UNKNOWN"


# --- F13 weight basis ------------------------------------------------------------------------


def weight(tmp_path, records):
    result = check(tmp_path, records, "COMPARE_WEIGHT_BASIS", [PRODUCER, "SKU-1"])
    return result.output.results[0]


def test_net_and_packaged_weights_in_force_together_are_a_conflict_never_averaged(tmp_path):
    records = [
        mapping("map:1", weight="1.2000", basis="NET_EEE"),
        mapping("map:2", weight="1.6500", basis="GROSS_PACKAGED"),
    ]
    target = weight(tmp_path, records)
    assert target.verdict == "FAIL" and target.values["code"] == "WEIGHT_BASIS_CONFLICT"
    assert target.values["NET_EEE"] == "1.2000" and target.values["GROSS_PACKAGED"] == "1.6500"
    assert not any("1.4" in v for v in target.values.values())  # no averaged figure


def test_different_bases_in_separate_periods_are_not_a_conflict(tmp_path):
    first = interval("2023-01-01", "2024-04-01", open_ended=False)
    records = [
        mapping("map:1", weight="1.2000", basis="NET_EEE", validity=first),
        mapping("map:2", weight="1.6500", basis="GROSS_PACKAGED", validity=interval("2024-04-01")),
    ]
    assert weight(tmp_path, records).verdict == "PASS"


def test_unreviewed_overlap_is_treated_as_overlap(tmp_path):
    records = [
        mapping("map:1", weight="1.2000"),
        mapping("map:2", weight="1.3000", validity=interval("2025-01-01", review="DRAFT")),
    ]
    assert weight(tmp_path, records).verdict == "FAIL"


def test_identical_duplicate_mappings_are_consistent(tmp_path):
    assert weight(tmp_path, [mapping("map:1"), mapping("map:2")]).verdict == "PASS"


def test_tonne_and_kg_expressions_of_the_same_weight_are_equal(tmp_path):
    tonne = mapping("map:2")
    tonne = tonne.model_copy(
        update={
            "unit_weight": Quantity(
                decimal="0.0012", unit="TONNE", dimension="EQUIPMENT_MASS", metal=None
            )
        }
    )
    assert weight(tmp_path, [mapping("map:1"), tonne]).verdict == "PASS"


# --- sales aggregation ------------------------------------------------------------------------


def sales(tmp_path, records, period=FY):
    result = check(tmp_path, records, "AGGREGATE_SALES", [PRODUCER], period=period)
    return result, result.output.results[0]


def test_sales_mass_is_units_times_mapped_weight_per_basis(tmp_path):
    _, target = sales(tmp_path, [mapping(), sale(units="100")])
    assert target.verdict == "PASS" and target.values["total_kg_NET_EEE"] == "120.0000"


def test_bases_are_totalled_separately_never_mixed(tmp_path):
    records = [
        mapping("map:1", sku="A", weight="1.0000", basis="NET_EEE"),
        mapping("map:2", sku="B", weight="2.0000", basis="GROSS_PACKAGED"),
        sale("sale:1", sku="A", units="10"),
        sale("sale:2", sku="B", units="10"),
    ]
    _, target = sales(tmp_path, records)
    assert target.values["total_kg_NET_EEE"] == "10.0000"
    assert target.values["total_kg_GROSS_PACKAGED"] == "20.0000"
    assert "total_kg" not in target.values


def test_unmapped_sku_leaves_the_total_unknown_but_reports_what_is_known(tmp_path):
    records = [mapping(), sale("sale:1", units="10"), sale("sale:2", sku="SKU-9", units="5")]
    result, target = sales(tmp_path, records)
    assert target.verdict == "UNKNOWN" and result.status == "PARTIAL"
    assert target.values["total_kg_NET_EEE"] == "12.0000"
    assert "SKU-9" in target.reasons[0]


def test_supplied_mass_that_disagrees_with_the_mapped_weight_fails(tmp_path):
    _, target = sales(tmp_path, [mapping(), sale(units="100", mass_kg="165.0000")])
    assert target.verdict == "FAIL" and target.values["code"] == "WEIGHT_BASIS_CONFLICT"


def test_agreeing_supplied_mass_passes(tmp_path):
    _, target = sales(tmp_path, [mapping(), sale(units="100", mass_kg="120.0000")])
    assert target.verdict == "PASS"


def test_conflicting_mappings_make_the_sales_total_fail(tmp_path):
    records = [
        mapping("map:1", weight="1.2000"),
        mapping("map:2", weight="1.6500", basis="GROSS_PACKAGED"),
        sale(),
    ]
    assert sales(tmp_path, records)[1].verdict == "FAIL"


def test_no_sales_is_unknown_not_zero(tmp_path):
    _, target = sales(tmp_path, [mapping()])
    assert target.verdict == "UNKNOWN" and "total_kg_NET_EEE" not in target.values


def test_sales_check_needs_a_period(tmp_path):
    result = check(tmp_path, [mapping(), sale()], "AGGREGATE_SALES", [PRODUCER])
    assert result.status == "REJECTED" and result.issues[0].code == "INVALID_SCHEMA"


def test_sales_of_another_entity_or_year_are_not_included(tmp_path):
    records = [mapping(), sale("sale:1", units="10"), sale("sale:2", year="2023-2024", units="99")]
    _, target = sales(tmp_path, records)
    assert target.values["total_kg_NET_EEE"] == "12.0000"


# --- contract validation ----------------------------------------------------------------------


def test_zero_or_non_equipment_unit_weight_is_rejected():
    with pytest.raises(ValidationError):
        mapping(weight="0")
    good = mapping()
    with pytest.raises(ValidationError):
        type(good).model_validate(
            good.model_dump(mode="json")
            | {"unit_weight": {"decimal": "1", "unit": "KG", "dimension": "COUNT", "metal": None}}
        )


def test_fractional_or_negative_sales_units_are_rejected():
    for units in ("1.5", "-1"):
        with pytest.raises(ValidationError):
            sale(units=units)


def test_verdict_helper_keys_are_stable(tmp_path):
    result = check(tmp_path, [mapping()], "COMPARE_WEIGHT_BASIS", [PRODUCER, "SKU-1"])
    assert list(verdicts(result)) == [PRODUCER]
