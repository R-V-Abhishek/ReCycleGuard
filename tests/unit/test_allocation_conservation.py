"""Gate G05 Allocation Conservation (S03).

Cross-year shared lot, prior-liability timing, incomplete history and selective caller inputs.
"""

import inspect

from recycleguard.domain import compute_reconciliation, reconcile_universe
from tests.support.c08 import (
    allocation,
    balance,
    bucket,
    bucket_result,
    certificate,
    event,
    run,
)

A, B = "bucket:a", "bucket:b"


def shared_lot(*, first="30.0000", second="30.0000", cap="55.0000"):
    """Two events on ONE lot; each event fits its own cap, so only the lot cap can bind."""
    return [
        bucket(A, "2023-2024", "60.0000"),
        bucket(B, "2024-2025", "100.0000"),
        certificate(face=cap),
        event("evt:1", quantity="40.0000"),
        event("evt:2", quantity="40.0000", when="2024-10-01T10:00:00Z"),
        allocation("alloc:1", A, evt="evt:1", quantity=first),
        allocation("alloc:2", B, evt="evt:2", quantity=second),
    ]


def dispositions(result, blobs):
    import json

    return {
        d["record_revision_id"]: d
        for d in json.loads(blobs.get(result.output.quantity_dispositions_blob))
    }


# --- cross-year shared lot -------------------------------------------------------------------


def test_cross_year_shared_lot_within_capacity_counts_both_years(tmp_path):
    result = run(tmp_path, shared_lot(first="30.0000", second="25.0000"), (A, B))
    assert bucket_result(result, A).supported.decimal == "30.0000"
    assert bucket_result(result, B).supported.decimal == "25.0000"
    lot = result.output.coverage  # lot fits, so nothing is BLOCKED
    assert lot != "BLOCKED"


def test_lot_overflow_excludes_every_supported_allocation_on_the_lot(tmp_path):
    result = run(tmp_path, shared_lot(first="30.0000", second="30.0000"), (A, B))
    assert result.status == "PARTIAL" and result.output.coverage == "BLOCKED"
    assert bucket_result(result, A).supported.decimal == "0.0000"
    assert bucket_result(result, B).supported.decimal == "0.0000"
    assert any(i.code == "INTEGRITY_FAILED" and i.severity == "BLOCKING" for i in result.issues)
    states = dispositions(result, tmp_path_blobs(tmp_path))
    assert states["rev:alloc_1"]["state"] == states["rev:alloc_2"]["state"] == "EXCLUDED"


def tmp_path_blobs(tmp_path):
    from recycleguard.storage import BlobStore

    return BlobStore(tmp_path / "blobs")


def test_per_event_cap_alone_is_insufficient(tmp_path):
    # Each allocation is within its event's 40 kg cap; together they break the 55 kg lot.
    records = shared_lot(first="40.0000", second="40.0000")
    result = run(tmp_path, records, (A, B))
    assert result.output.coverage == "BLOCKED"
    assert bucket_result(result, A).supported.decimal == "0.0000"


def test_event_over_allocation_is_a_conservation_fault(tmp_path):
    records = [
        bucket(),
        certificate(face="100.0000"),
        event(quantity="55.0000"),
        allocation("alloc:1", quantity="40.0000"),
        allocation("alloc:2", quantity="30.0000"),
    ]
    result = run(tmp_path, records)
    assert result.output.coverage == "BLOCKED"
    assert bucket_result(result).supported.decimal == "0.0000"


def test_pending_allocations_that_would_overflow_only_qualify(tmp_path):
    records = [
        bucket(),
        certificate(face="55.0000"),
        event(),
        allocation("alloc:1", quantity="55.0000"),
        allocation("alloc:2", quantity="10.0000", state="PENDING"),
    ]
    result = run(tmp_path, records)
    result_bucket = bucket_result(result)
    assert result_bucket.supported.decimal == "55.0000"
    assert result_bucket.pending.decimal == "10.0000"
    assert result.output.coverage == "QUALIFIED"


# --- superseded history ----------------------------------------------------------------------


def test_superseded_allocation_is_counted_once(tmp_path):
    records = [
        bucket(),
        certificate(),
        event(),
        allocation("alloc:1", quantity="55.0000", revision="rev:alloc_v1"),
        allocation(
            "alloc:1",
            quantity="55.0000",
            revision="rev:alloc_v2",
            supersedes_revision="rev:alloc_v1",
        ),
    ]
    result = run(tmp_path, records)
    assert bucket_result(result).supported.decimal == "55.0000"
    states = dispositions(result, tmp_path_blobs(tmp_path))
    assert states["rev:alloc_v1"]["state"] == "EXCLUDED"
    assert states["rev:alloc_v2"]["state"] == "INCLUDED"


def test_supersession_by_allocation_id_keeps_old_revision_as_history(tmp_path):
    records = [
        bucket(),
        certificate(),
        event(),
        allocation("alloc:1", quantity="30.0000"),
        allocation("alloc:2", quantity="55.0000", supersedes_allocation="alloc:1"),
    ]
    result = run(tmp_path, records)
    assert bucket_result(result).supported.decimal == "55.0000"
    assert bucket_result(result).allocation_ids == ["alloc:2"]
    assert dispositions(result, tmp_path_blobs(tmp_path))["rev:alloc_1"]["state"] == "EXCLUDED"


# --- validity: demote only, never promote ----------------------------------------------------


def test_pending_allocation_is_never_promoted(tmp_path):
    records = [bucket(), certificate(), event(), allocation(state="PENDING")]
    result = run(tmp_path, records)
    out = bucket_result(result)
    assert out.supported.decimal == "0.0000" and out.pending.decimal == "55.0000"
    assert result.output.coverage == "QUALIFIED"


def test_supported_allocation_on_a_pending_event_is_demoted_to_pending(tmp_path):
    records = [bucket(), certificate(), event(state="PENDING"), allocation()]
    out = bucket_result(run(tmp_path, records))
    assert out.supported.decimal == "0.0000" and out.pending.decimal == "55.0000"


def test_rejected_allocation_is_excluded_but_preserved(tmp_path):
    records = [bucket(), certificate(), event(), allocation(state="REJECTED")]
    result = run(tmp_path, records)
    assert bucket_result(result).supported.decimal == "0.0000"
    assert bucket_result(result).pending.decimal == "0.0000"
    assert dispositions(result, tmp_path_blobs(tmp_path))["rev:alloc_1"]["state"] == "EXCLUDED"


def test_metal_mismatch_and_wrong_recipient_are_excluded(tmp_path):
    wrong_metal = [
        bucket(),
        certificate(),
        event(),
        allocation(metal="AL"),
    ]
    assert bucket_result(run(tmp_path, wrong_metal)).supported.decimal == "0.0000"
    wrong_entity = [bucket(), certificate(), event(to="entity:other"), allocation()]
    assert bucket_result(run(tmp_path / "x", wrong_entity)).supported.decimal == "0.0000"


def test_unresolved_lot_keeps_supported_allocation_pending(tmp_path):
    # No certificate, so no lot can be derived: uncertain eligibility is PENDING, not zero proof.
    records = [bucket(), event(), allocation()]
    out = bucket_result(run(tmp_path, records))
    assert out.supported.decimal == "0.0000" and out.pending.decimal == "55.0000"


# --- prior-liability timing and incomplete history -------------------------------------------


def two_year(order_free=True):
    return [
        bucket(A, "2023-2024", "60.0000"),
        bucket(B, "2024-2025", "100.0000"),
        certificate(face="100.0000"),
        event("evt:1", quantity="100.0000"),
        allocation("alloc:a", A, quantity="60.0000"),
        allocation("alloc:b", B, quantity="30.0000"),
    ]


def derivation(result, blobs):
    import json

    return json.loads(blobs.get(result.output.derivation_blob))


def states(result, tmp_path):
    return {
        p["allocation_id"]: p["state"]
        for p in derivation(result, tmp_path_blobs(tmp_path))["priority_checks"]
    }


def test_later_year_allocation_with_open_earlier_liability_is_unresolved_without_order(tmp_path):
    result = run(tmp_path, two_year(), (A, B))
    assert states(result, tmp_path)["alloc:b"] == "UNKNOWN"
    assert any(i.code == "LIABILITY_PRIORITY_UNRESOLVED" for i in result.issues)
    assert bucket_result(result, B).supported.decimal == "30.0000"  # not proven wrong, so kept
    assert result.output.coverage == "QUALIFIED"


def test_allocation_made_before_earlier_liability_was_met_fails_priority(tmp_path):
    result = run(tmp_path, two_year(), (A, B), order={"alloc:b": 1, "alloc:a": 2})
    assert states(result, tmp_path)["alloc:b"] == "FAIL"
    assert any(i.code == "EARLIER_LIABILITY_UNMET" for i in result.issues)
    assert bucket_result(result, B).supported.decimal == "0.0000"
    assert bucket_result(result, A).supported.decimal == "60.0000"
    # Observed, so preserved in history rather than deleted.
    blobs = tmp_path_blobs(tmp_path)
    assert dispositions(result, blobs)["rev:alloc_b"]["state"] == "EXCLUDED"


def test_allocation_made_after_earlier_liability_was_met_passes_priority(tmp_path):
    result = run(tmp_path, two_year(), (A, B), order={"alloc:a": 1, "alloc:b": 2})
    assert states(result, tmp_path)["alloc:b"] == "PASS"
    assert bucket_result(result, B).supported.decimal == "30.0000"
    assert not any(i.code == "EARLIER_LIABILITY_UNMET" for i in result.issues)


def test_incomplete_or_tied_order_is_unknown_not_pass(tmp_path):
    incomplete = run(tmp_path, two_year(), (A, B), order={"alloc:b": 2})
    assert states(incomplete, tmp_path)["alloc:b"] == "UNKNOWN"
    tied = run(tmp_path / "t", two_year(), (A, B), order={"alloc:a": 1, "alloc:b": 1})
    assert states(tied, tmp_path / "t")["alloc:b"] == "UNKNOWN"


def test_no_earlier_bucket_is_not_evaluated_never_pass(tmp_path):
    result = run(tmp_path, [bucket(), certificate(), event(), allocation()])
    assert states(result, tmp_path)["alloc:1"] == "NOT_EVALUATED"
    assert not any(i.code == "LIABILITY_PRIORITY_UNRESOLVED" for i in result.issues)


def test_zero_earlier_liability_passes_without_order(tmp_path):
    records = two_year()
    records[0] = bucket(A, "2023-2024", "0.0000")
    records[4] = allocation("alloc:a", A, quantity="0.0000", state="REJECTED")
    result = run(tmp_path, records, (A, B))
    assert states(result, tmp_path)["alloc:b"] == "PASS"


# --- selective caller inputs -----------------------------------------------------------------


def test_requesting_one_bucket_still_considers_adverse_inputs_in_other_buckets(tmp_path):
    result = run(tmp_path, shared_lot(first="30.0000", second="30.0000"), (A,))
    assert result.output.analyzed_bucket_ids == [A]
    assert (
        bucket_result(result, A).supported.decimal == "0.0000"
    )  # B's allocation overflowed the lot
    assert result.output.coverage == "BLOCKED"
    assert any(i.code == "INCOMPLETE_COVERAGE" and i.severity == "INFO" for i in result.issues)


def test_empty_bucket_request_means_every_in_scope_bucket(tmp_path):
    result = run(tmp_path, two_year(), ())
    assert sorted(result.output.analyzed_bucket_ids) == [A, B]


def test_stale_membership_digest_is_rejected_before_any_computation(tmp_path):
    result = run(tmp_path, two_year(), (A,), digest="0" * 64)
    assert result.status == "REJECTED" and result.output is None
    assert result.issues[0].code == "STALE_SNAPSHOT"


def test_matching_membership_digest_is_accepted(tmp_path):
    from recycleguard.domain import universe_from_records
    from tests.support.c08 import SNAPSHOT

    digest = universe_from_records(SNAPSHOT, two_year()).digest
    assert run(tmp_path, two_year(), (A,), digest=digest).output is not None


def test_api_accepts_no_caller_supplied_records():
    for function in (compute_reconciliation, reconcile_universe):
        names = set(inspect.signature(function).parameters)
        assert not names & {"records", "allocations", "events", "buckets", "balances"}


def test_unknown_requested_bucket_blocks_rather_than_vanishes(tmp_path):
    result = run(tmp_path, two_year(), (A, "bucket:ghost"))
    assert result.output.coverage == "BLOCKED"
    assert any(i.code == "MISSING_ARTIFACT" for i in result.issues)
    assert result.output.analyzed_bucket_ids == [A]


def test_portal_balance_never_creates_supported_quantity(tmp_path):
    result = run(tmp_path, [bucket(), balance(reported="55.0000")])
    out = bucket_result(result)
    assert out.supported.decimal == "0.0000" and out.portal_reported.decimal == "55.0000"
    assert out.delta.decimal == "55.0000"
    assert result.output.coverage == "QUALIFIED"
