import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from recycleguard.contracts import (
    BlobRef,
    CommandContext,
    Locator,
    Quantity,
    ServiceResult,
    TemporalValue,
)


@pytest.mark.parametrize(
    "value",
    [55, 55.0, "1e2", "NaN", "+1", "01", "1,000", ".5", "1000000000000000000", "0.000000001"],
)
def test_decimal_rejects_noncontract_numbers(quantity_payload, value):
    with pytest.raises(ValidationError):
        Quantity.model_validate({**quantity_payload, "decimal": value})


def test_exact_decimal_roundtrip(quantity_payload):
    value = Quantity.model_validate(quantity_payload)
    assert json.loads(value.model_dump_json())["decimal"] == "100.0000"
    assert Decimal(value.decimal) - Decimal("55") == Decimal("45.0000")


@pytest.mark.parametrize(
    "patch",
    [
        {"dimension": "MONEY"},
        {"metal": None},
        {"unit": "UNIT_COUNT"},
        {"extra": True},
    ],
)
def test_quantity_rejects_incompatible_dimensions(quantity_payload, patch):
    with pytest.raises(ValidationError):
        Quantity.model_validate({**quantity_payload, **patch})


def test_count_integrality():
    with pytest.raises(ValidationError):
        Quantity(decimal="1.5", unit="UNIT_COUNT", dimension="COUNT", metal=None)


@pytest.mark.parametrize(
    "patch",
    [
        {"contract_version": "1.0"},
        {"case_version_id": None},
        {"unknown": "field"},
        {"command_id": "untyped"},
        {"run_id": None, "turn_id": "turn:1"},
    ],
)
def test_context_strictness(context_payload, patch):
    with pytest.raises(ValidationError):
        CommandContext.model_validate({**context_payload, **patch})


def test_nullable_is_required(context_payload):
    del context_payload["parent_operation_id"]
    with pytest.raises(ValidationError):
        CommandContext.model_validate(context_payload)


@pytest.mark.parametrize("digest", ["A" * 64, "g" * 64, "a" * 63])
def test_blob_digest(digest):
    with pytest.raises(ValidationError):
        BlobRef(sha256=digest, byte_length=0, media_type="text/plain")


def test_zero_differs_from_missing(quantity_payload):
    assert Quantity.model_validate({**quantity_payload, "decimal": "0"}).decimal == "0"
    with pytest.raises(ValidationError):
        Quantity.model_validate({**quantity_payload, "decimal": None})


@pytest.mark.parametrize(
    "precision,value",
    [
        ("DATE", "2024-02-30"),
        ("MONTH", "2024-13"),
        ("YEAR", "0000"),
        ("INSTANT", "2024-01-01T00:00:00"),
        ("UNKNOWN", "2024"),
    ],
)
def test_temporal_rejects_bad_precision(precision, value):
    with pytest.raises(ValidationError):
        TemporalValue(
            raw=value,
            value=value,
            precision=precision,
            timezone=None,
            interpretation_status="PARSED",
        )


def test_source_time_retains_precision_and_unknown():
    t = TemporalValue(
        raw="Oct 2024",
        value="2024-10",
        precision="MONTH",
        timezone="Asia/Kolkata",
        interpretation_status="PARSED",
    )
    assert t.value == "2024-10"
    unknown = TemporalValue(
        raw="illegible",
        value=None,
        precision="UNKNOWN",
        timezone=None,
        interpretation_status="UNKNOWN",
    )
    assert unknown.value is None


@pytest.mark.parametrize(
    "kind,patch",
    [
        ("CSV_ROW", {}),
        ("PDF_PAGE", {}),
        ("PDF_CELL", {"page_index_1based": 1}),
        ("TEXT_SPAN", {"text_start": 10, "text_end": 5}),
        ("JSON_POINTER", {"json_pointer": "/bad~2escape"}),
    ],
)
def test_locator_requires_real_coordinates(kind, patch):
    fields = dict.fromkeys(set(Locator.model_fields) - {"kind"})
    with pytest.raises(ValidationError):
        Locator.model_validate({**fields, "kind": kind, **patch})


def test_fixture_results_preserve_partial_and_rejected():
    root = Path(__file__).parents[1] / "fixtures/visible/a01"
    results = [
        ServiceResult[Quantity].model_validate_json((root / f"{n}.json").read_bytes())
        for n in ("result_success", "result_partial", "result_rejected")
    ]
    assert [r.status for r in results] == ["SUCCESS", "PARTIAL", "REJECTED"]
    assert results[1].output.decimal == "55"
    assert results[1].issues[0].code == "INCOMPLETE_COVERAGE"
    assert results[2].output is None


def test_non_success_cannot_hide_failure():
    with pytest.raises(ValidationError):
        ServiceResult[Quantity](
            contract_version="1.1",
            operation_id="operation:1",
            attempt_id="attempt:1",
            status="FAILED",
            output=None,
            output_blob=None,
            issues=[],
            dependencies=[],
            audit_event_ids=[],
        )
