"""S04 dispatcher and contract surface: full-universe inputs, determinism, strict rejection."""

import json

import pytest
from pydantic import ValidationError

from recycleguard.application import local_application
from recycleguard.config import Settings
from recycleguard.contracts.artifacts import SnapshotRef
from recycleguard.contracts.checks import CheckRequest, CheckTarget
from recycleguard.contracts.domain import RECORD_ADAPTER, Allocation
from recycleguard.domain import TOOL_VERSION, run_check, universe_from_records
from recycleguard.storage import BlobStore
from tests.integration.test_s03_cp1_snapshot import publish_case
from tests.support.c08 import (
    CONTEXT,
    PRODUCER,
    RECYCLER,
    SNAPSHOT,
    allocation,
    bucket_result,
    check,
    clean_case,
    commercial,
    day,
    mapping,
    registration,
    run,
    sale,
    verdicts,
)


def request(**kw):
    base = {
        "check_kind": "CHECK_CREDIT_EVENTS",
        "case_version_id": SNAPSHOT,
        "subjects": ["alloc:1"],
    }
    return CheckRequest(**(base | kw))


def test_unknown_check_kind_cannot_be_expressed():
    with pytest.raises(ValidationError):
        request(check_kind="RUN_SHELL")
    with pytest.raises(ValidationError):
        request(unexpected_field="x")


def test_tool_version_is_the_s04_version():
    assert TOOL_VERSION == "c08-s04-0.1"


def test_wrong_subject_count_is_rejected_not_guessed(tmp_path):
    result = check(tmp_path, clean_case(), "COMPARE_IDENTITY", [PRODUCER])
    assert result.status == "REJECTED" and result.issues[0].code == "INVALID_SCHEMA"
    assert result.output is None


def test_stale_case_version_and_digest_are_rejected(tmp_path):
    universe = universe_from_records(SNAPSHOT, clean_case())
    stale = check(tmp_path, clean_case(), "CHECK_CREDIT_EVENTS", ["alloc:1"], digest="0" * 64)
    assert stale.status == "REJECTED" and stale.issues[0].code == "STALE_SNAPSHOT"
    exact = check(
        tmp_path, clean_case(), "CHECK_CREDIT_EVENTS", ["alloc:1"], digest=universe.digest
    )
    assert exact.status == "SUCCESS"


def test_reference_event_must_exist(tmp_path):
    result = check(
        tmp_path, clean_case(), "CHECK_CAPABILITY", [RECYCLER, PRODUCER], event="evt:nope"
    )
    assert result.status == "REJECTED" and result.issues[0].code == "MISSING_ARTIFACT"


def test_result_is_deterministic_and_check_id_follows_the_inputs(tmp_path):
    first = check(tmp_path / "a", clean_case(), "CHECK_CREDIT_EVENTS", ["alloc:1"])
    second = check(tmp_path / "b", clean_case(), "CHECK_CREDIT_EVENTS", ["alloc:1"])
    assert first.output.model_dump_json() == second.output.model_dump_json()
    other = check(tmp_path / "c", clean_case(), "CHECK_CREDIT_EVENTS", ["cert:1"])
    assert other.output.check_id != first.output.check_id
    assert first.output.tool_version == TOOL_VERSION


def test_every_check_reads_the_whole_universe_regardless_of_subjects(tmp_path):
    one = check(tmp_path / "a", clean_case(), "CHECK_CREDIT_EVENTS", ["alloc:1"])
    extra = [*clean_case(), mapping(), registration(), sale(), commercial()]
    two = check(tmp_path / "b", extra, "CHECK_CREDIT_EVENTS", ["alloc:1"])
    store = BlobStore(tmp_path / "a" / "blobs")
    members_one = json.loads(store.get(one.output.input_membership_blob))["members"]
    members_two = json.loads(
        BlobStore(tmp_path / "b" / "blobs").get(two.output.input_membership_blob)
    )["members"]
    assert len(members_two) == len(extra) > len(members_one) == len(clean_case())


def test_unresolved_verdicts_make_the_result_partial_with_issues(tmp_path):
    result = check(tmp_path, clean_case(), "GET_CERTIFICATE_HISTORY", ["cert:nope"])
    assert result.status == "PARTIAL" and result.issues
    definite = check(tmp_path / "d", clean_case(), "GET_CERTIFICATE_HISTORY", ["cert:1"])
    assert definite.status == "SUCCESS" and definite.issues == []


def test_a_definite_fail_is_a_complete_answer_with_a_warning(tmp_path):
    records = [
        *clean_case()[:1],
        clean_case()[1].model_copy(update={"expiry_time": day("2024-01-01")}),
        *clean_case()[2:],
    ]
    result = check(tmp_path, records, "CHECK_CREDIT_EVENTS", ["alloc:1"])
    assert verdicts(result) == {"alloc:1": "FAIL"} and result.status == "SUCCESS"
    assert [i.severity for i in result.issues] == ["WARNING"]
    assert result.issues[0].code == "CREDIT_EXPIRED"


def test_non_pass_target_must_explain_itself():
    with pytest.raises(ValidationError):
        CheckTarget(target_refs=["a:1"], verdict="UNKNOWN", reasons=[], evidence=[], values={})
    with pytest.raises(ValidationError):
        CheckTarget(target_refs=[], verdict="PASS", reasons=[], evidence=[], values={})


def test_checks_never_change_the_calculation(tmp_path):
    before = run(tmp_path / "a", clean_case())
    check(tmp_path / "b", clean_case(), "CHECK_CREDIT_EVENTS", ["alloc:1"])
    after = run(tmp_path / "c", clean_case())
    assert before.output.calculation_id == after.output.calculation_id


# --- allocation_time contract and digest stability -------------------------------------------


def test_unset_allocation_time_serializes_exactly_as_before():
    dumped = allocation().model_dump(mode="json")
    assert "allocation_time" not in dumped
    assert "allocation_time" in allocation(time=day("2024-10-01")).model_dump(mode="json")


def test_record_union_round_trips_every_new_record_type():
    for record in (allocation(time=day("2024-10-01")), mapping(), sale(), registration()):
        again = RECORD_ADAPTER.validate_json(record.model_dump_json())
        assert again == record
    assert isinstance(
        RECORD_ADAPTER.validate_python(allocation().model_dump(mode="json")), Allocation
    )


def test_adding_an_allocation_time_changes_the_universe_digest():
    plain = universe_from_records(SNAPSHOT, clean_case())
    timed = [*clean_case()[:3], allocation(time=day("2024-10-01")), clean_case()[4]]
    assert universe_from_records(SNAPSHOT, timed).digest != plain.digest


def test_calculation_ids_differ_when_allocation_time_differs(tmp_path):
    a = run(
        tmp_path / "a", [*clean_case()[:3], allocation(time=day("2024-10-01")), clean_case()[4]]
    )
    b = run(tmp_path / "b", clean_case())
    assert a.output.calculation_id != b.output.calculation_id
    assert bucket_result(a).supported.decimal == bucket_result(b).supported.decimal


# --- real pinned snapshot ---------------------------------------------------------------------


def test_run_check_reads_only_the_pinned_case_snapshot(tmp_path):
    membership = {"normalization": {"records": [r.model_dump(mode="json") for r in clean_case()]}}
    with local_application(Settings(data_root=tmp_path)) as (cases, context, cap):
        snapshot = publish_case(cases, context, cap, membership, SNAPSHOT)
        pinned = SnapshotRef(
            snapshot_id=snapshot.snapshot_id, membership_digest=snapshot.membership_digest
        )
        result = run_check(CONTEXT, request(), snapshots=cases.snapshots, snapshot_ref=pinned)
        assert result.status == "SUCCESS" and verdicts(result) == {"alloc:1": "PASS"}
        stale = pinned.model_copy(update={"membership_digest": "0" * 64})
        rejected = run_check(CONTEXT, request(), snapshots=cases.snapshots, snapshot_ref=stale)
        assert rejected.status == "REJECTED"
