"""S04 entity, registration and capability checks (F05, F10): unknown is not false."""

import json

from recycleguard.domain.identity import code_covers
from recycleguard.storage import BlobStore
from tests.support.c08 import (
    PRODUCER,
    RECYCLER,
    bucket_result,
    check,
    clean_case,
    entity,
    event,
    interval,
    mapping,
    registration,
    run,
    verdicts,
)

BASE = clean_case()  # transfer evt:1 on 2024-09-15 from RECYCLER to PRODUCER


def capability(tmp_path, extra):
    result = check(
        tmp_path, [*BASE, *extra], "CHECK_CAPABILITY", [RECYCLER, PRODUCER], event="evt:1"
    )
    return result, result.output.results[0]


def eligibility(result, tmp_path):
    blob = BlobStore(tmp_path / "blobs").get(result.output.derivation_blob)
    return {e["condition"]: e for e in json.loads(blob)["eligibility"]}


# --- F10 capability -------------------------------------------------------------------------


def test_no_registration_evidence_is_unknown(tmp_path):
    _, target = capability(tmp_path, [mapping()])
    assert target.verdict == "UNKNOWN" and "No registration evidence" in target.reasons[0]


def test_unmapped_producer_categories_are_unknown(tmp_path):
    _, target = capability(tmp_path, [registration()])
    assert target.verdict == "UNKNOWN" and "not mapped" in target.reasons[0]


def test_covered_category_passes(tmp_path):
    _, target = capability(tmp_path, [registration(), mapping()])
    assert target.verdict == "PASS"


def test_uncovered_category_fails_with_capability_mismatch(tmp_path):
    result, target = capability(tmp_path, [registration(codes=("EEE-9",)), mapping(code="EEE-1")])
    assert target.verdict == "FAIL" and target.values["code"] == "CAPABILITY_MISMATCH"
    assert result.status == "SUCCESS"


def test_category_code_covers_numbered_items_but_nothing_looser():
    assert code_covers("ITEW", "ITEW15") and code_covers("EEE-1", "EEE-1")
    assert not code_covers("ITEW", "ITEWX") and not code_covers("ITEW", "CEEW1")
    assert not code_covers("ITEW", "itew1") and not code_covers("EEE-", "EEE-1")
    assert not code_covers("ITEW1", "ITEW15")  # numbered codes are exact only


def test_registered_category_covers_a_numbered_producer_item(tmp_path):
    _, target = capability(tmp_path, [registration(codes=("ITEW",)), mapping(code="ITEW15")])
    assert target.verdict == "PASS"


def test_partial_coverage_cannot_attribute_the_credit_and_is_unknown(tmp_path):
    extra = [
        registration(codes=("EEE-1",)),
        mapping("map:1", sku="A", code="EEE-1"),
        mapping("map:2", sku="B", code="EEE-2"),
    ]
    _, target = capability(tmp_path, extra)
    assert target.verdict == "UNKNOWN" and "EEE-2" in target.reasons[0]


def test_registration_that_ended_before_the_transfer_fails(tmp_path):
    ended = interval("2023-01-01", "2024-01-01", open_ended=False)
    _, target = capability(tmp_path, [registration(validity=ended), mapping()])
    assert target.verdict == "FAIL"


def test_registration_not_yet_valid_at_the_transfer_fails(tmp_path):
    _, target = capability(tmp_path, [registration(validity=interval("2025-01-01")), mapping()])
    assert target.verdict == "FAIL"


def test_unreviewed_or_unbounded_validity_is_unknown_not_unlimited(tmp_path):
    for validity in (
        interval("2024-01-01", review="DRAFT"),
        interval(None),
        interval("2024-01-01", open_ended=False),  # end neither set nor declared open
    ):
        _, target = capability(tmp_path, [registration(validity=validity), mapping()])
        assert target.verdict == "UNKNOWN", validity


def test_revoked_status_fails_regardless_of_dates(tmp_path):
    _, target = capability(tmp_path, [registration(status="Revoked"), mapping()])
    assert target.verdict == "FAIL"


def test_reference_event_is_required_to_date_validity(tmp_path):
    result = check(
        tmp_path, [*BASE, registration(), mapping()], "CHECK_CAPABILITY", [RECYCLER, PRODUCER]
    )
    assert result.output.results[0].verdict == "UNKNOWN"


def test_registration_lookup_reports_each_registration(tmp_path):
    extra = [registration("reg:1"), registration("reg:2", validity=interval("2025-01-01"))]
    result = check(
        tmp_path, [*BASE, *extra], "LOOKUP_REGISTRATION_EVIDENCE", [RECYCLER], event="evt:1"
    )
    assert verdicts(result) == {"reg:1": "PASS", "reg:2": "FAIL"}


def test_engine_excludes_a_credit_from_an_unregistered_category(tmp_path):
    result = run(tmp_path, [*BASE, registration(codes=("EEE-9",)), mapping(code="EEE-1")])
    assert bucket_result(result).supported.decimal == "0.0000"
    assert any(i.code == "CAPABILITY_MISMATCH" for i in result.issues)
    assert eligibility(result, tmp_path)["CAPABILITY"]["state"] == "FAIL"


def test_engine_keeps_a_covered_credit_and_reports_the_rule_passed(tmp_path):
    result = run(tmp_path, [*BASE, registration(), mapping()])
    assert bucket_result(result).supported.decimal == "55.0000"
    assert eligibility(result, tmp_path)["CAPABILITY"]["state"] == "PASS"
    assert eligibility(result, tmp_path)["REGISTRATION"]["state"] == "PASS"


def test_engine_without_capability_evidence_does_not_change_the_baseline(tmp_path):
    result = run(tmp_path, BASE)
    assert result.status == "SUCCESS" and result.output.coverage == "COMPLETE_WITHIN_SCOPE"
    states = eligibility(result, tmp_path)
    assert states["CAPABILITY"]["state"] == "NOT_EVALUATED"
    assert states["LIFECYCLE"]["state"] == "PASS"


def test_engine_with_only_one_kind_of_capability_evidence_reports_not_evaluated(tmp_path):
    for extra in ([mapping()], [registration()]):  # either alone cannot test the rule
        out = tmp_path / extra[0].record_type
        result = run(out, [*BASE, *extra])
        assert bucket_result(result).supported.decimal == "55.0000"
        assert result.output.coverage == "COMPLETE_WITHIN_SCOPE"
        assert eligibility(result, out)["CAPABILITY"]["state"] == "NOT_EVALUATED"


def test_engine_with_registration_but_a_different_recycler_is_qualified(tmp_path):
    # Evidence exists for another entity only, so this recycler's capability is genuinely open.
    other = registration(entity_id="entity:other")
    result = run(tmp_path, [*BASE, other, mapping()])
    assert bucket_result(result).supported.decimal == "55.0000"
    assert result.output.coverage == "QUALIFIED"
    assert eligibility(result, tmp_path)["CAPABILITY"]["state"] == "UNKNOWN"


# --- F05 identity ---------------------------------------------------------------------------


def two(*, left_ids=(), right_ids=(), left_aliases=(), right_name="Other Name"):
    return [
        entity("entity:a", ("PRODUCER",), "Brand Industries", left_ids, left_aliases),
        entity("entity:b", ("PRODUCER",), right_name, right_ids),
    ]


def compare(tmp_path, records, when=None):
    result = check(tmp_path, records, "COMPARE_IDENTITY", ["entity:a", "entity:b"], event=when)
    return result.output.results[0]


def test_same_entity_passes(tmp_path):
    result = check(tmp_path, two(), "COMPARE_IDENTITY", ["entity:a", "entity:a"])
    assert result.output.results[0].verdict == "PASS"


def test_shared_confirmed_identifier_passes(tmp_path):
    ids = [("PAN", "SYNTH-PAN-1", "VALID")]
    assert compare(tmp_path, two(left_ids=ids, right_ids=ids)).verdict == "PASS"


def test_brand_prefix_with_distinct_confirmed_identifiers_is_rejected(tmp_path):
    target = compare(
        tmp_path,
        two(
            left_ids=[("GSTIN", "SYNTH-GSTIN-A", "VALID")],
            right_ids=[("GSTIN", "SYNTH-GSTIN-B", "VALID")],
            right_name="Brand Industries Exports",
        ),
    )
    assert target.verdict == "FAIL" and target.values["code"] == "AMBIGUOUS_IDENTITY"


def test_unconfirmed_identifier_is_unknown(tmp_path):
    target = compare(
        tmp_path,
        two(
            left_ids=[("GSTIN", "SYNTH-GSTIN-A", "REVIEW_REQUIRED")],
            right_ids=[("GSTIN", "SYNTH-GSTIN-A", "VALID")],
        ),
    )
    assert target.verdict == "UNKNOWN" and target.values["code"] == "UNCONFIRMED_IDENTIFIER"


def test_name_similarity_alone_never_establishes_identity(tmp_path):
    target = compare(tmp_path, two(right_name="Brand Industries Pvt Ltd"))
    assert target.verdict == "UNKNOWN" and "names are not matched" in target.reasons[0]


def test_reviewed_alias_is_valid_only_inside_its_dated_interval(tmp_path):
    alias = [("Old Name", interval("2024-01-01", "2024-06-01", open_ended=False))]
    records = [
        *two(left_aliases=alias, right_name="Old Name"),
        event("evt:early", when="2024-03-10T00:00:00Z"),
        event("evt:late", when="2024-09-15T00:00:00Z"),
    ]
    assert compare(tmp_path, records, "evt:early").verdict == "PASS"
    assert compare(tmp_path, records, "evt:late").verdict == "FAIL"
    assert compare(tmp_path, records).verdict == "UNKNOWN"  # no reference time


def test_missing_entity_is_unknown(tmp_path):
    result = check(tmp_path, two(), "COMPARE_IDENTITY", ["entity:a", "entity:zzz"])
    assert result.output.results[0].verdict == "UNKNOWN"


def test_party_roles_pass_and_fail_in_the_engine(tmp_path):
    good = [entity(PRODUCER, ("PRODUCER",)), entity(RECYCLER, ("RECYCLER",))]
    ok = run(tmp_path, [*BASE, *good])
    assert eligibility(ok, tmp_path)["ENTITY"]["state"] == "PASS"
    bad = [entity(PRODUCER, ("PRODUCER",)), entity(RECYCLER, ("PRODUCER",))]
    failed = run(tmp_path / "b", [*BASE, *bad])
    assert eligibility(failed, tmp_path / "b")["ENTITY"]["state"] == "FAIL"
    assert failed.output.coverage == "QUALIFIED"
    assert any(i.code == "AMBIGUOUS_IDENTITY" for i in failed.issues)
    assert bucket_result(failed).supported.decimal == "55.0000"  # roles alone never demote
