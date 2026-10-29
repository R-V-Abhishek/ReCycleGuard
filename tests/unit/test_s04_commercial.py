"""S04 commercial matching (F07, T09): a payment is not an allocation, and money is not credit."""

import json

from recycleguard.storage import BlobStore
from tests.support.c08 import (
    PRODUCER,
    RECYCLER,
    allocation,
    bucket,
    bucket_result,
    certificate,
    check,
    clean_case,
    commercial,
    event,
    run,
    verdicts,
)

UNALLOCATED = [bucket(), certificate(), event()]  # a completed 55 kg transfer nobody allocated


def dispositions(result, tmp_path):
    blob = BlobStore(tmp_path / "blobs").get(result.output.quantity_dispositions_blob)
    return {d["record_id"]: d for d in json.loads(blob)}


def match(tmp_path, records, subjects=()):
    return check(tmp_path, records, "MATCH_TRANSACTIONS", subjects)


def test_unlinked_payment_is_pending_never_supported(tmp_path):
    records = [*UNALLOCATED, commercial("comm:p", "55.0000", "PAYMENT")]
    out = bucket_result(run(tmp_path, records))
    assert out.supported.decimal == "0.0000" and out.pending.decimal == "55.0000"
    assert out.signed_gap.decimal == "100.0000"  # pending is not subtracted from the gap


def test_invoice_and_its_payment_are_one_quantity_counted_once(tmp_path):
    records = [
        *UNALLOCATED,
        commercial("comm:1", "25.0000", "INVOICE"),
        commercial("comm:2", "25.0000", "PAYMENT", linked=("comm:1",)),
    ]
    result = run(tmp_path, records)
    assert bucket_result(result).pending.decimal == "25.0000"  # not 50
    states = dispositions(result, tmp_path)
    assert {states["comm:1"]["state"], states["comm:2"]["state"]} == {"PENDING", "OUT_OF_SCOPE"}
    assert sorted(t.verdict for t in match(tmp_path, records).output.results) == ["PASS", "PASS"]


def test_invoice_and_payment_that_disagree_are_not_counted(tmp_path):
    records = [
        *UNALLOCATED,
        commercial("comm:1", "25.0000", "INVOICE"),
        commercial("comm:2", "30.0000", "PAYMENT", linked=("comm:1",)),
    ]
    result = run(tmp_path, records)
    assert bucket_result(result).pending.decimal == "0.0000"
    assert result.output.coverage == "QUALIFIED"
    assert any(i.code == "INTEGRITY_FAILED" for i in result.issues)
    assert set(verdicts(match(tmp_path, records)).values()) == {"FAIL"}


def test_record_backing_an_allocated_transfer_adds_no_second_quantity(tmp_path):
    records = [*clean_case(), commercial("comm:1", "55.0000", "INVOICE", linked=("evt:1",))]
    result = run(tmp_path, records)
    out = bucket_result(result)
    assert out.supported.decimal == "55.0000" and out.pending.decimal == "0.0000"
    assert result.output.coverage == "COMPLETE_WITHIN_SCOPE"
    assert dispositions(result, tmp_path)["comm:1"]["state"] == "OUT_OF_SCOPE"


def test_record_linked_through_an_allocation_or_a_lot_also_backs_it(tmp_path):
    for ref in ("alloc:1", "lot:1", "cert:1"):
        records = [*clean_case(), commercial("comm:1", "55.0000", linked=(ref,))]
        assert bucket_result(run(tmp_path / ref.replace(":", "_"), records)).pending.decimal == (
            "0.0000"
        ), ref


def test_paid_credit_on_an_unallocated_transfer_is_pending(tmp_path):
    records = [*UNALLOCATED, commercial("comm:1", "25.0000", linked=("evt:1",))]
    assert bucket_result(run(tmp_path, records)).pending.decimal == "25.0000"


def test_invoice_and_payment_backing_one_transfer_count_once_against_its_quantity(tmp_path):
    records = [
        *clean_case(),
        commercial("comm:1", "55.0000", "INVOICE", linked=("evt:1",)),
        commercial("comm:2", "55.0000", "PAYMENT", linked=("comm:1", "evt:1")),
    ]
    result = run(tmp_path, records)
    assert verdicts(match(tmp_path, records)) == {"comm:1": "PASS", "comm:2": "PASS"}
    assert bucket_result(result).pending.decimal == "0.0000"
    assert result.output.coverage == "COMPLETE_WITHIN_SCOPE"


def test_payment_paired_only_with_a_backed_invoice_adds_no_pending(tmp_path):
    records = [
        *clean_case(),
        commercial("comm:1", "55.0000", "INVOICE", linked=("evt:1",)),
        commercial("comm:2", "55.0000", "PAYMENT", linked=("comm:1",)),
    ]
    result = run(tmp_path, records)
    assert bucket_result(result).pending.decimal == "0.0000"
    assert {dispositions(result, tmp_path)[c]["state"] for c in ("comm:1", "comm:2")} == {
        "OUT_OF_SCOPE"
    }


def test_payment_may_run_from_producer_to_recycler(tmp_path):
    ok = commercial(
        "comm:p", "55.0000", "PAYMENT", linked=("evt:1",), issuer=PRODUCER, recipient=RECYCLER
    )
    assert verdicts(match(tmp_path, [*clean_case(), ok])) == {"comm:p": "PASS"}
    wrong = commercial(
        "comm:p", "55.0000", "PAYMENT", linked=("evt:1",), issuer="entity:x", recipient=RECYCLER
    )
    assert verdicts(match(tmp_path / "w", [*clean_case(), wrong])) == {"comm:p": "FAIL"}


def test_unlinked_payment_from_the_producer_is_still_placed_in_its_bucket(tmp_path):
    payment = commercial("comm:p", "25.0000", "PAYMENT", issuer=PRODUCER, recipient=RECYCLER)
    assert bucket_result(run(tmp_path, [*UNALLOCATED, payment])).pending.decimal == "25.0000"


def test_a_failed_invoice_fails_its_paired_payment(tmp_path):
    records = [
        *clean_case(),
        commercial("comm:1", "55.0000", "INVOICE", linked=("evt:1",), recipient="entity:x"),
        commercial("comm:2", "55.0000", "PAYMENT", linked=("comm:1",)),
    ]
    assert verdicts(match(tmp_path, records)) == {"comm:1": "FAIL", "comm:2": "FAIL"}


def test_wrong_recipient_is_a_mismatch_and_not_counted(tmp_path):
    records = [
        *clean_case(),
        commercial("comm:1", "55.0000", linked=("evt:1",), recipient="entity:x"),
    ]
    result = run(tmp_path, records)
    assert bucket_result(result).pending.decimal == "0.0000"
    assert dispositions(result, tmp_path)["comm:1"]["state"] == "EXCLUDED"
    assert any(i.code == "AMBIGUOUS_IDENTITY" for i in result.issues)
    assert result.output.coverage == "QUALIFIED"


def test_wrong_issuer_is_a_mismatch(tmp_path):
    records = [*clean_case(), commercial("comm:1", "55.0000", linked=("evt:1",), issuer="entity:x")]
    assert verdicts(match(tmp_path, records, ["comm:1"])) == {"comm:1": "FAIL"}


def test_quantity_beyond_the_transfer_is_a_mismatch(tmp_path):
    records = [*clean_case(), commercial("comm:1", "60.0000", linked=("evt:1",))]
    result = match(tmp_path, records, ["comm:1"])
    assert verdicts(result) == {"comm:1": "FAIL"}
    assert result.output.results[0].values["code"] == "INTEGRITY_FAILED"


def test_two_records_together_exceeding_the_transfer_are_flagged(tmp_path):
    records = [
        *clean_case(),
        commercial("comm:1", "30.0000", linked=("evt:1",)),
        commercial("comm:2", "30.0000", "PAYMENT", linked=("evt:1",)),
    ]
    assert verdicts(match(tmp_path, records)) == {"comm:1": "PASS", "comm:2": "FAIL"}


def test_unresolvable_link_is_reported_and_not_counted(tmp_path):
    records = [*UNALLOCATED, commercial("comm:1", "25.0000", linked=("evt:missing",))]
    result = run(tmp_path, records)
    assert bucket_result(result).pending.decimal == "0.0000"
    assert any(i.code == "MISSING_ARTIFACT" for i in match(tmp_path, records).issues)
    assert dispositions(result, tmp_path)["comm:1"]["state"] == "OUT_OF_SCOPE"


def test_several_unrelated_payables_for_one_bucket_are_not_counted(tmp_path):
    records = [
        *UNALLOCATED,
        commercial("comm:1", "10.0000"),
        commercial("comm:2", "15.0000", "PAYMENT"),
    ]
    assert bucket_result(run(tmp_path, records)).pending.decimal == "0.0000"


def test_purchase_orders_and_contracts_are_context_only(tmp_path):
    records = [
        *UNALLOCATED,
        commercial("comm:1", "25.0000", "PO"),
        commercial("comm:2", kind="CONTRACT"),
    ]
    assert bucket_result(run(tmp_path, records)).pending.decimal == "0.0000"
    assert verdicts(match(tmp_path, records)) == {"comm:1": "PASS", "comm:2": "PASS"}


def test_other_metal_or_other_producer_is_left_unplaced(tmp_path):
    records = [*UNALLOCATED, commercial("comm:1", "25.0000", recipient="entity:other")]
    result = run(tmp_path, records)
    assert bucket_result(result).pending.decimal == "0.0000"
    assert dispositions(result, tmp_path)["comm:1"]["allocated_bucket_id"] is None


def test_selecting_subjects_does_not_change_matching(tmp_path):
    records = [
        *UNALLOCATED,
        commercial("comm:1", "10.0000"),
        commercial("comm:2", "15.0000", "PAYMENT"),
    ]
    one = match(tmp_path, records, ["comm:1"])
    assert verdicts(one) == {"comm:1": "UNKNOWN"}  # still ambiguous with comm:2 in the universe


def test_unknown_commercial_subject_is_unknown(tmp_path):
    assert verdicts(match(tmp_path, UNALLOCATED, ["comm:zzz"])) == {"comm:zzz": "UNKNOWN"}


def test_existing_minimal_pending_case_is_unchanged(tmp_path):
    records = [*clean_case(), commercial("comm:1", "25.0000")]
    out = bucket_result(run(tmp_path, records))
    assert (out.required.decimal, out.supported.decimal) == ("100.0000", "55.0000")
    assert (out.signed_gap.decimal, out.pending.decimal) == ("45.0000", "25.0000")


def test_parties_default_to_the_shared_test_entities():
    record = commercial()
    assert (record.issuer_entity_id, record.recipient_entity_id) == (RECYCLER, PRODUCER)
    assert allocation().allocation_time is None


def test_failed_invoice_also_fails_paired_payment_linked_to_unallocated_transfer(tmp_path):
    records = [
        *UNALLOCATED,
        commercial("comm:1", "25.0000", "INVOICE", linked=("evt:1",), recipient="entity:x"),
        commercial("comm:2", "25.0000", "PAYMENT", linked=("comm:1", "evt:1")),
    ]
    result = run(tmp_path, records)
    assert verdicts(match(tmp_path, records)) == {"comm:1": "FAIL", "comm:2": "FAIL"}
    assert bucket_result(result).pending.decimal == "0.0000"
    assert bucket_result(result).supported.decimal == "0.0000"


def test_failed_group_does_not_consume_transfer_capacity_for_later_group(tmp_path):
    records = [
        *clean_case(),
        commercial("comm:1", "55.0000", "INVOICE", linked=("evt:1",)),
        commercial(
            "comm:2", "55.0000", "PAYMENT", linked=("comm:1", "evt:1"), recipient="entity:x"
        ),
        commercial("comm:3", "55.0000", "INVOICE", linked=("evt:1",)),
    ]
    assert verdicts(match(tmp_path, records)) == {
        "comm:1": "FAIL",
        "comm:2": "FAIL",
        "comm:3": "PASS",
    }
