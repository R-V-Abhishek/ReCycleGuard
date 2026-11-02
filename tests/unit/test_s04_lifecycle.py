"""S04 lifecycle (F09) and allocation chronology (F08): only evidence demotes, ties are UNKNOWN."""

import json

import pytest

from recycleguard.storage import BlobStore
from tests.support.c08 import (
    allocation,
    bucket,
    bucket_result,
    certificate,
    check,
    day,
    event,
    run,
    unknown_time,
    verdicts,
)

A, B = "bucket:a", "bucket:b"


def allocation_checks(result, tmp_path, rule="LIFECYCLE"):
    blob = BlobStore(tmp_path / "blobs").get(result.output.derivation_blob)
    return {
        c["allocation_id"]: c for c in json.loads(blob)["allocation_checks"] if c["rule"] == rule
    }


def case(*, expiry=None, status=None, time=None, extra=()):
    return [
        bucket(),
        certificate(expiry=expiry, status=status),
        event(),
        *extra,
        allocation(time=time),
    ]


# --- F09: expired / cancelled credit ---------------------------------------------------------


def test_credit_expired_before_the_transfer_is_excluded(tmp_path):
    result = run(tmp_path, case(expiry=day("2024-08-01")))
    out = bucket_result(result)
    assert out.supported.decimal == "0.0000" and out.signed_gap.decimal == "100.0000"
    assert any(i.code == "CREDIT_EXPIRED" for i in result.issues)
    check_ = allocation_checks(result, tmp_path)["alloc:1"]
    assert check_["state"] == "FAIL" and check_["code"] == "CREDIT_EXPIRED"
    assert result.output.coverage == "QUALIFIED"


def test_allocation_before_expiry_stays_supported(tmp_path):
    result = run(tmp_path, case(expiry=day("2025-01-10"), time=day("2024-10-01")))
    assert bucket_result(result).supported.decimal == "55.0000"
    assert allocation_checks(result, tmp_path)["alloc:1"]["state"] == "PASS"
    assert not any(i.code == "CREDIT_EXPIRED" for i in result.issues)


def test_allocation_after_expiry_is_excluded_even_when_the_transfer_preceded_it(tmp_path):
    result = run(tmp_path, case(expiry=day("2024-10-01"), time=day("2024-11-01")))
    assert bucket_result(result).supported.decimal == "0.0000"
    assert any(i.code == "CREDIT_EXPIRED" for i in result.issues)


def test_later_expiry_without_allocation_time_is_unknown_not_assumed_live(tmp_path):
    result = run(tmp_path, case(expiry=day("2025-01-10")))
    out = bucket_result(result)
    assert out.supported.decimal == "55.0000"  # not proven wrong, so kept
    assert allocation_checks(result, tmp_path)["alloc:1"]["state"] == "UNKNOWN"
    assert result.output.coverage == "QUALIFIED"
    assert [r.ref_id for r in out.qualification_refs] == ["alloc:1"]


def test_same_day_expiry_is_a_tie_and_unknown(tmp_path):
    result = run(tmp_path, case(expiry=day("2024-10-01"), time=day("2024-10-01")))
    assert allocation_checks(result, tmp_path)["alloc:1"]["state"] == "UNKNOWN"
    assert bucket_result(result).supported.decimal == "55.0000"


def test_cancellation_event_before_the_allocation_excludes_it(tmp_path):
    cancelled = event("evt:2", kind="CANCELLED", when="2024-10-20T00:00:00Z", quantity="55.0000")
    result = run(tmp_path, case(extra=[cancelled], time=day("2024-11-01")))
    assert bucket_result(result).supported.decimal == "0.0000"
    assert any(i.code == "CREDIT_CANCELLED" for i in result.issues)
    assert allocation_checks(result, tmp_path)["alloc:1"]["code"] == "CREDIT_CANCELLED"


def test_unsupported_cancellation_assertion_is_unknown_and_never_excludes(tmp_path):
    claimed = event(
        "evt:2", kind="CANCELLED", when="2024-10-20T00:00:00Z", quantity="55.0000", state="PENDING"
    )
    result = run(tmp_path, case(extra=[claimed], time=day("2024-11-01")))
    assert bucket_result(result).supported.decimal == "55.0000"
    assert allocation_checks(result, tmp_path)["alloc:1"]["state"] == "UNKNOWN"
    assert result.output.coverage == "QUALIFIED"


def test_undated_terminal_status_is_unknown_not_a_guess(tmp_path):
    result = run(tmp_path, case(status="cancelled", time=day("2024-10-01")))
    assert allocation_checks(result, tmp_path)["alloc:1"]["state"] == "UNKNOWN"
    assert bucket_result(result).supported.decimal == "55.0000"


def test_unusable_expiry_date_is_unknown(tmp_path):
    result = run(tmp_path, case(expiry=unknown_time(), time=day("2024-10-01")))
    assert allocation_checks(result, tmp_path)["alloc:1"]["state"] == "UNKNOWN"


def test_dated_event_supersedes_an_undated_status_of_the_same_kind(tmp_path):
    expired = event("evt:2", kind="EXPIRED", when="2025-02-01T00:00:00Z", quantity="55.0000")
    result = run(tmp_path, case(status="EXPIRED", extra=[expired], time=day("2024-10-01")))
    assert allocation_checks(result, tmp_path)["alloc:1"]["state"] == "PASS"


def test_no_lifecycle_evidence_passes_but_the_trace_states_the_limit(tmp_path):
    result = run(tmp_path, case())
    assert allocation_checks(result, tmp_path)["alloc:1"]["state"] == "PASS"
    traced = check(tmp_path, case(), "GET_CERTIFICATE_HISTORY", ["cert:1"])
    assert "absence is not proof" in traced.output.results[0].reasons[0]


def test_ended_credit_does_not_consume_event_capacity(tmp_path):
    # 30 + 30 would exceed the 55 kg event, but the second use came after expiry and is dropped
    # first, so the event cap is not breached and no conservation fault is raised.
    records = [
        bucket(A, "2024-2025", "100.0000"),
        bucket(B, "2024-2025", "100.0000"),
        certificate(expiry=day("2024-10-01")),
        event(),
        allocation("alloc:x", A, quantity="30.0000", time=day("2024-09-20")),
        allocation("alloc:y", B, quantity="30.0000", time=day("2024-11-01")),
    ]
    result = run(tmp_path, records, (A, B))
    assert result.output.coverage != "BLOCKED"
    assert not any(i.code == "OVER_ALLOCATION" for i in result.issues)
    assert bucket_result(result, A).supported.decimal == "30.0000"
    assert bucket_result(result, B).supported.decimal == "0.0000"


# --- F08: chronology from reviewed allocation_time -------------------------------------------


def two_year(a_time=None, b_time=None):
    return [
        bucket(A, "2023-2024", "60.0000"),
        bucket(B, "2024-2025", "100.0000"),
        certificate(face="100.0000"),
        event("evt:1", quantity="100.0000"),
        allocation("alloc:a", A, quantity="60.0000", time=a_time),
        allocation("alloc:b", B, quantity="30.0000", time=b_time),
    ]


def priority(result, tmp_path):
    blob = BlobStore(tmp_path / "blobs").get(result.output.derivation_blob)
    return {p["allocation_id"]: p["state"] for p in json.loads(blob)["priority_checks"]}


def test_later_year_allocation_after_the_earlier_one_passes_by_time(tmp_path):
    result = run(tmp_path, two_year(day("2024-05-01"), day("2024-06-01")), (A, B))
    assert priority(result, tmp_path)["alloc:b"] == "PASS"
    assert bucket_result(result, B).supported.decimal == "30.0000"


def test_later_year_allocation_before_the_earlier_one_fails_by_time(tmp_path):
    result = run(tmp_path, two_year(day("2024-06-01"), day("2024-05-01")), (A, B))
    assert priority(result, tmp_path)["alloc:b"] == "FAIL"
    assert any(i.code == "EARLIER_LIABILITY_UNMET" for i in result.issues)
    assert bucket_result(result, B).supported.decimal == "0.0000"
    assert bucket_result(result, A).supported.decimal == "60.0000"


def test_same_day_allocations_are_tied_and_unknown(tmp_path):
    result = run(tmp_path, two_year(day("2024-05-01"), day("2024-05-01")), (A, B))
    assert priority(result, tmp_path)["alloc:b"] == "UNKNOWN"
    assert bucket_result(result, B).supported.decimal == "30.0000"


@pytest.mark.parametrize("which", ["a", "b"])
def test_one_missing_allocation_time_is_unknown(tmp_path, which):
    times = {"a_time": day("2024-05-01")} if which == "a" else {"b_time": day("2024-06-01")}
    result = run(tmp_path, two_year(**times), (A, B))
    assert priority(result, tmp_path)["alloc:b"] == "UNKNOWN"


def test_transfer_time_is_never_used_as_allocation_chronology(tmp_path):
    result = run(tmp_path, two_year(), (A, B))  # same transfer event, no allocation_time
    assert priority(result, tmp_path)["alloc:b"] == "UNKNOWN"


def test_explicit_order_overrides_allocation_time(tmp_path):
    records = two_year(day("2024-06-01"), day("2024-05-01"))  # times say b came first
    result = run(tmp_path, records, (A, B), order={"alloc:a": 1, "alloc:b": 2})
    assert priority(result, tmp_path)["alloc:b"] == "PASS"


def test_requesting_one_bucket_does_not_change_the_chronology_result(tmp_path):
    records = two_year(day("2024-06-01"), day("2024-05-01"))
    narrow = run(tmp_path, records, (B,))
    assert priority(narrow, tmp_path)["alloc:b"] == "FAIL"
    assert bucket_result(narrow, B).supported.decimal == "0.0000"


# --- the trace tools --------------------------------------------------------------------------


def test_credit_event_check_returns_the_fail_verdict_and_code(tmp_path):
    result = check(tmp_path, case(expiry=day("2024-08-01")), "CHECK_CREDIT_EVENTS", ["alloc:1"])
    assert verdicts(result) == {"alloc:1": "FAIL"}
    assert result.output.results[0].values["code"] == "CREDIT_EXPIRED"
    assert result.status == "SUCCESS"  # a definite FAIL is a complete answer


def test_credit_event_check_on_a_certificate_covers_its_allocations(tmp_path):
    result = check(tmp_path, case(), "CHECK_CREDIT_EVENTS", ["cert:1"])
    assert verdicts(result) == {"alloc:1": "PASS"}


def test_history_lists_events_lots_and_allocations(tmp_path):
    result = check(tmp_path, case(), "GET_CERTIFICATE_HISTORY", ["evt:1"])
    values = result.output.results[0].values
    assert "evt:1|TRANSFERRED|SUPPORTED|COMPLETED" in values["events"]
    assert values["lots"] == "lot:1" and "alloc:1|SUPPORTED|bucket:a" in values["allocations"]


def test_history_with_unresolved_event_is_unknown(tmp_path):
    records = case(extra=[event("evt:2", state="CONFLICTING", quantity="5.0000")])
    result = check(tmp_path, records, "GET_CERTIFICATE_HISTORY", ["cert:1"])
    assert verdicts(result) == {"cert:1": "UNKNOWN"} and result.status == "PARTIAL"


def test_unknown_subject_is_unknown_not_a_pass(tmp_path):
    result = check(tmp_path, case(), "GET_CERTIFICATE_HISTORY", ["cert:nope"])
    assert verdicts(result) == {"cert:nope": "UNKNOWN"}
