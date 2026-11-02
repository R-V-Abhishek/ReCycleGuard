"""S03 baseline arithmetic: required - supported = signed gap, pending, portal comparison."""

import json
from pathlib import Path

from recycleguard.contracts.domain import RECORD_ADAPTER
from recycleguard.domain import reconcile_universe, universe_from_records
from recycleguard.storage import BlobStore
from tests.support.c08 import (
    CONTEXT,
    PROFILE,
    SNAPSHOT,
    allocation,
    balance,
    bucket,
    bucket_result,
    certificate,
    clean_case,
    commercial,
    event,
    profile,
    qty,
    request,
    run,
    signed_qty,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
RECORD_FILES = (
    "entities",
    "registrations",
    "obligations",
    "certificates",
    "certificate_events",
    "allocations",
    "commercial_records",
    "account_balances",
)


def test_clean_baseline_is_100_required_55_supported_45_gap(tmp_path):
    result = run(tmp_path, clean_case())
    out = bucket_result(result)
    assert result.status == "SUCCESS" and result.output.coverage == "COMPLETE_WITHIN_SCOPE"
    assert (out.required.decimal, out.supported.decimal) == ("100.0000", "55.0000")
    assert (out.signed_gap.decimal, out.shortfall.decimal) == ("45.0000", "45.0000")
    assert (out.surplus.decimal, out.pending.decimal) == ("0.0000", "0.0000")
    assert (out.portal_reported.decimal, out.delta.decimal) == ("55.0000", "0.0000")
    assert out.ledger_supported == out.supported
    assert out.allocation_ids == ["alloc:1"]


def test_case_001_reference_records_match_the_independent_expected_values(tmp_path):
    """Reviewed-state reference records (S01); the expected JSON is read by the test only."""
    records = []
    for name in RECORD_FILES:
        for line in (FIXTURES / f"visible/case_001/records/{name}.jsonl").read_text().splitlines():
            records.append(RECORD_ADAPTER.validate_json(line))
    expected = json.loads((FIXTURES / "expected/case_001_expected.json").read_text())
    want = expected["expected_balances"][0]
    universe = universe_from_records(SNAPSHOT, records)
    result = reconcile_universe(
        CONTEXT,
        request((want["bucket_id"],)),
        universe,
        profile(),
        BlobStore(tmp_path / "blobs"),
    )
    out = bucket_result(result, want["bucket_id"])
    assert out.required.decimal == want["required_target"]
    assert out.supported.decimal == out.ledger_supported.decimal == want["ledger_supported"]
    assert out.signed_gap.decimal == want["signed_gap"]
    assert out.pending.decimal == want["pending_quantity"]
    assert out.portal_reported.decimal == want["portal_reported"]
    assert out.delta.decimal == want["delta_portal_vs_ledger"]
    assert result.status == "PARTIAL" and result.output.coverage == "QUALIFIED"
    assert expected["audit_invariants"]["total_gap"] == out.signed_gap.decimal


def test_surplus_is_retained_not_clamped(tmp_path):
    records = [bucket(target="40.0000"), certificate(), event(), allocation(), balance()]
    out = bucket_result(run(tmp_path, records))
    assert out.signed_gap.decimal == "-15.0000"
    assert (out.shortfall.decimal, out.surplus.decimal) == ("0.0000", "15.0000")


def test_missing_portal_evidence_is_null_never_zero(tmp_path):
    out = bucket_result(run(tmp_path, [bucket(), certificate(), event(), allocation()]))
    assert out.portal_reported is None and out.delta is None
    assert out.snapshot_comparison_ref is None


def test_zero_supported_is_a_real_zero_string(tmp_path):
    out = bucket_result(run(tmp_path, [bucket()]))
    assert out.supported.decimal == "0.0000" and out.signed_gap.decimal == "100.0000"


def test_portal_difference_is_distinct_from_the_gap(tmp_path):
    records = clean_case()[:-1] + [balance(reported="70.0000")]
    out = bucket_result(run(tmp_path, records))
    assert out.delta.decimal == "15.0000" and out.signed_gap.decimal == "45.0000"
    assert out.snapshot_comparison_ref.startswith("comparison:")


def test_portal_value_is_never_added_to_supported(tmp_path):
    out = bucket_result(run(tmp_path, clean_case()))
    assert out.supported.decimal == "55.0000"  # not 110


def test_ambiguous_portal_observations_are_not_guessed(tmp_path):
    same = "2024-10-15T09:00:00Z"
    records = clean_case()[:-1] + [
        balance("bal:1", reported="55.0000", capture=same),
        balance("bal:2", reported="60.0000", capture=same),
    ]
    result = run(tmp_path, records)
    out = bucket_result(result)
    assert out.portal_reported is None and out.delta is None
    assert any(i.code == "INCOMPLETE_COVERAGE" for i in result.issues)


def test_latest_portal_observation_wins_when_strictly_ordered(tmp_path):
    records = clean_case()[:-1] + [
        balance("bal:1", reported="40.0000", capture="2024-10-01T09:00:00Z"),
        balance("bal:2", reported="55.0000", capture="2024-10-15T09:00:00Z"),
    ]
    assert bucket_result(run(tmp_path, records)).portal_reported.decimal == "55.0000"


def test_tonne_units_convert_exactly_to_kg(tmp_path):
    records = [bucket(target="0.1", unit="TONNE"), certificate(), event(), allocation()]
    assert bucket_result(run(tmp_path, records)).required.decimal == "100.0000"


def test_reviewed_adjustments_change_required(tmp_path):
    adjustments = [signed_qty("5.0000"), signed_qty("-10.0000")]
    out = bucket_result(run(tmp_path, [bucket(adjustments=adjustments)]))
    assert out.required.decimal == "95.0000"


def test_negative_required_blocks_instead_of_crashing(tmp_path):
    result = run(tmp_path, [bucket(adjustments=[signed_qty("-150.0000")])])
    assert result.output.coverage == "BLOCKED" and result.output.bucket_results == []
    assert any(i.code == "INTEGRITY_FAILED" for i in result.issues)


def test_metals_are_never_combined(tmp_path):
    records = [
        bucket("bucket:a", target="100.0000"),
        bucket("bucket:al", target="10.0000", metal="AL"),
        certificate(),
        event(),
        allocation(),
    ]
    result = run(tmp_path, records, ("bucket:a", "bucket:al"))
    assert bucket_result(result, "bucket:a").supported.decimal == "55.0000"
    assert bucket_result(result, "bucket:al").supported.decimal == "0.0000"
    assert bucket_result(result, "bucket:al").required.metal == "AL"


def test_precision_overflow_is_a_failure_not_a_silent_round(tmp_path):
    big = "999999999999999999"
    result = run(tmp_path, [bucket(target=big, adjustments=[signed_qty(big)])])
    assert result.status == "FAILED" and result.issues[0].code == "NUMERIC_PRECISION_EXCEEDED"


def test_unlinked_payment_is_pending_not_supported(tmp_path):
    result = run(tmp_path, clean_case() + [commercial()])
    out = bucket_result(result)
    assert out.pending.decimal == "25.0000" and out.supported.decimal == "55.0000"
    assert out.signed_gap.decimal == "45.0000"  # pending is not subtracted
    assert result.output.coverage == "QUALIFIED"


def test_ambiguous_or_linked_commercial_records_are_not_counted(tmp_path):
    two = clean_case() + [commercial("comm:1"), commercial("comm:2", kind="PAYMENT")]
    assert bucket_result(run(tmp_path, two)).pending.decimal == "0.0000"
    linked = clean_case() + [commercial(linked=["evt:1"])]
    assert bucket_result(run(tmp_path / "l", linked)).pending.decimal == "0.0000"


def test_every_universe_member_has_exactly_one_disposition(tmp_path):
    records = clean_case() + [commercial()]
    result = run(tmp_path, records)
    items = json.loads(BlobStore(tmp_path / "blobs").get(result.output.quantity_dispositions_blob))
    assert len(items) == len(records)
    assert len({d["record_revision_id"] for d in items}) == len(records)


def test_unapproved_profile_is_rejected(tmp_path):
    result = run(tmp_path, clean_case(), prof=profile(state="DRAFT"))
    assert result.status == "REJECTED" and result.issues[0].code == "UNAPPROVED_PROFILE"


def test_unavailable_deadlines_qualify_an_otherwise_clean_result(tmp_path):
    result = run(tmp_path, clean_case(), prof=profile(deadlines_testable=False))
    assert result.output.coverage == "QUALIFIED"
    assert any(i.code == "APPLICABILITY_UNRESOLVED" for i in result.issues)


def test_records_needing_review_qualify_the_result(tmp_path):
    records = [bucket(), certificate(), event(), allocation(validation="REVIEW_REQUIRED")]
    result = run(tmp_path, records)
    assert result.output.coverage == "QUALIFIED"
    assert bucket_result(result).qualification_refs


def test_mismatched_pins_are_rejected(tmp_path):
    universe = universe_from_records(SNAPSHOT, clean_case())
    store = BlobStore(tmp_path / "blobs")
    other = reconcile_universe(
        CONTEXT, request(snapshot="snapshot:other"), universe, profile(), store
    )
    assert other.status == "REJECTED" and other.issues[0].code == "STALE_SNAPSHOT"
    wrong = request().model_copy(update={"profile_id": "profile:other"})
    assert reconcile_universe(CONTEXT, wrong, universe, profile(), store).status == "REJECTED"


def test_result_is_deterministic_and_archives_three_blobs(tmp_path):
    first = run(tmp_path, clean_case())
    second = run(tmp_path, clean_case())
    assert first.output.calculation_id == second.output.calculation_id
    assert first.output.input_digest == second.output.input_digest
    store = BlobStore(tmp_path / "blobs")
    for ref in (
        first.output.analyzed_input_membership_blob,
        first.output.quantity_dispositions_blob,
        first.output.derivation_blob,
    ):
        assert store.get(ref)
    derivation = json.loads(store.get(first.output.derivation_blob))
    assert derivation["purchase_ceiling"] == "NOT_EVALUATED"
    assert len(derivation["unsupported_features"]) == 6


def test_helpers_use_the_expected_profile_id():
    assert profile().profile_id == PROFILE and qty("1.0000").metal == "CU"
