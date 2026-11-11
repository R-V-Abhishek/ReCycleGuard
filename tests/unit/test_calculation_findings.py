"""Findings from deterministic checks: one per family, never from a shared code alone.

Each new rule is tested with its positive shape and the near miss that must not fire.
"""

from recycleguard.contracts.core import EvidenceRef
from recycleguard.contracts.extraction import Observation
from recycleguard.contracts.results import CalculationResult
from recycleguard.domain.models import (
    AllocationCheck,
    Derivation,
    EligibilityOutcome,
    PriorityCheck,
)
from recycleguard.domain.refs import make_issue
from recycleguard.domain.universe import universe_from_records
from recycleguard.reporting.calculation_findings import (
    calculation_findings,
    contradicted_families,
    settled_without_finding,
)
from recycleguard.storage import BlobStore
from tests.support.c08 import (
    SNAPSHOT,
    allocation,
    balance,
    bucket,
    certificate,
    clean_case,
    commercial,
    day,
    event,
    instant,
    mapping,
    registration,
    run,
)

RECORD = EvidenceRef(ref_kind="RECORD", ref_id="record:a1", artifact_revision_id=None, locator=None)


def calculation(*issues):
    return CalculationResult.model_construct(
        calculation_id="calc:test", case_version_id="case_version:test", issues=list(issues)
    )


def derivation(*, eligibility=(), priority=(), checks=()):
    return Derivation.model_construct(
        eligibility=list(eligibility),
        priority_checks=list(priority),
        allocation_checks=list(checks),
    )


def check(rule, state, code=None):
    return AllocationCheck(
        rule=rule,
        allocation_id="allocation:a1",
        state=state,
        code=code,
        reason="test",
        evidence_refs=[RECORD],
    )


def outcome(condition, state):
    return EligibilityOutcome(condition=condition, testability="TESTABLE", state=state, reason="x")


def priority(state):
    return PriorityCheck(
        allocation_id="allocation:a1",
        bucket_id="bucket:b1",
        state=state,
        earlier_bucket_ids=[],
        reason="x",
    )


def families(calc, deriv):
    return {f.issue_type: f for f in calculation_findings(calc, deriv)}


def test_nothing_established_gives_no_finding():
    assert calculation_findings(calculation(), derivation()) == []


def test_every_dimension_failure_is_one_unit_dimension_mix():
    blocking = make_issue(
        "DIMENSION_MISMATCH", "BLOCKING", "adjustment is not metal mass", [RECORD]
    )
    wrong_metal = make_issue("DIMENSION_MISMATCH", "WARNING", "metal differs from bucket")
    assert set(families(calculation(wrong_metal), derivation())) == {"F04_UNIT_DIMENSION_MIX"}
    found = calculation_findings(calculation(blocking, wrong_metal), derivation())
    assert [f.issue_type for f in found] == ["F04_UNIT_DIMENSION_MIX"]
    assert found[0].advisory_status == "DISCREPANCY_DETECTED"
    assert found[0].abstention_reason is None
    assert {ref.ref_id for ref in found[0].fact_refs} == {"record:a1", "calc:test"}
    assert found[0].calculation_refs == ["calc:test"]


def test_entity_and_registration_failures_and_unknowns():
    assert families(calculation(), derivation(eligibility=[outcome("ENTITY", "UNKNOWN")])) == {}
    found = families(
        calculation(),
        derivation(eligibility=[outcome("ENTITY", "FAIL"), outcome("REGISTRATION", "FAIL")]),
    )
    assert set(found) == {"F05_WRONG_ENTITY_ALIAS", "F10_CAPABILITY_MISMATCH"}


def test_a_stale_portal_statement_is_withheld_not_asserted():
    stale = make_issue("STALE_SNAPSHOT", "WARNING", "cut-off precedes ledger events", [RECORD])
    found = families(calculation(stale), derivation())["F06_STALE_SNAPSHOT"]
    assert found.advisory_status == "PENDING_VERIFICATION"
    assert (found.abstention_reason, found.withheld_claim_scopes) == (
        "TEMPORAL_UNCERTAINTY",
        ["stale_portal_statement"],
    )


def test_earlier_liability_breach_and_an_unknown_order_both_withhold_the_priority_claim():
    # A refuted order still leaves the correct order unestablished.
    breach = families(calculation(), derivation(priority=[priority("FAIL")]))
    found = breach["F08_PRIOR_ARREARS_DRAIN"]
    assert found.advisory_status == "REQUIRES_EXPERT_REVIEW"
    assert (found.abstention_reason, found.withheld_claim_scopes) == (
        "RULE_CONFLICT",
        ["earlier_liability_priority"],
    )
    unknown = families(calculation(), derivation(priority=[priority("FAIL"), priority("UNKNOWN")]))
    assert unknown["F08_PRIOR_ARREARS_DRAIN"].withheld_claim_scopes == [
        "earlier_liability_priority"
    ]
    assert families(calculation(), derivation(priority=[priority("PASS")])) == {}


def test_an_order_unknown_for_a_missing_time_also_withholds_undated_history():
    undated = priority("UNKNOWN").model_copy(update={"reason": "allocation time not recorded"})
    found = families(calculation(), derivation(priority=[undated]))["F08_PRIOR_ARREARS_DRAIN"]
    assert found.withheld_claim_scopes == ["earlier_liability_priority", "undated_history"]
    assert found.abstention_reason == "INCOMPLETE_HISTORY"


def test_a_lifecycle_end_is_asserted_and_unresolved_lifecycle_evidence_withheld():
    ended = families(
        calculation(), derivation(checks=[check("LIFECYCLE", "FAIL", "CREDIT_EXPIRED")])
    )["F09_EXPIRED_CANCELLED"]
    assert ended.advisory_status == "DISCREPANCY_DETECTED"
    unresolved = families(calculation(), derivation(checks=[check("LIFECYCLE", "UNKNOWN")]))
    assert unresolved["F09_EXPIRED_CANCELLED"].withheld_claim_scopes == ["undated_history"]
    # An unknown capability is missing evidence, not a capability fault.
    assert families(calculation(), derivation(checks=[check("CAPABILITY", "UNKNOWN")])) == {}


def test_each_family_is_emitted_once_however_many_checks_fail():
    found = calculation_findings(
        calculation(),
        derivation(
            checks=[check("CAPABILITY", "FAIL", "CAPABILITY_MISMATCH")] * 3,
            eligibility=[outcome("REGISTRATION", "FAIL")],
        ),
    )
    assert [f.issue_type for f in found] == ["F10_CAPABILITY_MISMATCH"]
    assert found[0].evidence_assessments[0]["source"] == "DETERMINISTIC_CALCULATION"


# --- the domain-check sweep over a real reconciliation ----------------------------------------


def swept(tmp_path, records, observations=()):
    result = run(tmp_path, records)
    calc = result.output
    universe = universe_from_records(SNAPSHOT, records)
    found = calculation_findings(
        calc,
        Derivation.model_validate_json(BlobStore(tmp_path / "blobs").get(calc.derivation_blob)),
        universe,
        observations,
    )
    return calc, universe, found


def sweep(tmp_path, records, observations=()):
    return {f.issue_type: f for f in swept(tmp_path, records, observations)[2]}


def signal_checks(finding):
    return [s.get("check") for s in finding.evidence_assessments[0]["signals"]]


def test_a_clean_case_with_capability_evidence_gives_no_finding(tmp_path):
    assert sweep(tmp_path, [*clean_case(), registration(), mapping()]) == {}


def test_credits_sent_to_another_party_are_a_wrong_entity(tmp_path):
    records = [bucket(), certificate(), event(to="entity:other"), allocation(), balance()]
    found = sweep(tmp_path, records)["F05_WRONG_ENTITY_ALIAS"]
    assert found.evidence_assessments[0]["signals"][0]["check"] == "COMPARE_IDENTITY"


def test_capability_is_checked_on_an_allocation_excluded_for_another_reason(tmp_path):
    records = [
        bucket(),
        certificate(),
        event(),
        allocation(metal="AU"),
        balance(),
        registration(codes=("EEE-9",)),
        mapping(code="EEE-1"),
    ]
    # The wrong-metal allocation is a metal mismatch on its own records, not a unit mix.
    found = sweep(tmp_path, records)
    assert set(found) == {"F10_CAPABILITY_MISMATCH"}
    assert signal_checks(found["F10_CAPABILITY_MISMATCH"]) == [
        "METAL_COMPATIBILITY",
        "CHECK_CAPABILITY",
    ]


def test_an_expired_credit_is_asserted_and_an_undated_end_withheld(tmp_path):
    expired = [
        bucket(),
        certificate(expiry=instant("2024-01-01T00:00:00Z")),
        event(),
        allocation(),
        balance(),
    ]
    found = sweep(tmp_path, expired)["F09_EXPIRED_CANCELLED"]
    assert found.advisory_status == "DISCREPANCY_DETECTED"
    undated = [bucket(), certificate(status="EXPIRED"), event(), allocation(), balance()]
    found = sweep(tmp_path / "undated", undated)["F09_EXPIRED_CANCELLED"]
    assert (found.abstention_reason, found.withheld_claim_scopes) == (
        "TEMPORAL_UNCERTAINTY",
        ["undated_history"],
    )


def test_two_weight_bases_for_one_product_are_withheld_not_averaged(tmp_path):
    records = [
        *clean_case(),
        mapping(),
        mapping(key="map:2", basis="GROSS_PACKAGED", weight="1.5000"),
    ]
    found = sweep(tmp_path, records)["F13_WEIGHT_BASIS_CONFLICT"]
    assert found.advisory_status == "PENDING_VERIFICATION"
    assert found.withheld_claim_scopes == ["weight_basis_selection"]


def source(unit_fields):
    return Observation.model_construct(
        observation_id="obs:1", parsed_fields=unit_fields, raw_fields={}
    )


def test_a_bucket_supplied_in_two_mass_units_is_a_unit_mix(tmp_path):
    tonnes = [
        bucket(target="0.1000", unit="TONNE"),
        certificate(),
        event(),
        allocation(),
        balance(),
    ]
    found = sweep(tmp_path, tonnes)
    assert set(found) == {"F04_UNIT_DIMENSION_MIX"}
    assert signal_checks(found["F04_UNIT_DIMENSION_MIX"]) == ["UNIT_MIX"]
    assert "bucket:a" in {ref.ref_id for ref in found["F04_UNIT_DIMENSION_MIX"].fact_refs}
    # A source supplied in tonnes is a mix even after normalization converted it to kg.
    sourced = sweep(tmp_path / "source", clean_case(), [source({"quantity": {"unit": "TONNE"}})])
    assert set(sourced) == {"F04_UNIT_DIMENSION_MIX"}
    assert sweep(tmp_path / "kg", clean_case(), [source({"unit": "KG"})]) == {}


def test_an_unlinked_invoice_is_paid_without_transfer_and_withholds_pending_credit(tmp_path):
    found = sweep(tmp_path, [*clean_case(), commercial()])
    assert set(found) == {"F07_PAID_NO_TRANSFER"}
    paid = found["F07_PAID_NO_TRANSFER"]
    assert paid.advisory_status == "PENDING_VERIFICATION"
    assert (paid.abstention_reason, paid.withheld_claim_scopes) == (
        "MISSING_EVIDENCE",
        ["pending_untransferred_credits"],
    )
    assert "comm:1" in {ref.ref_id for ref in paid.fact_refs}
    # An invoice backing a recorded allocation is evidence about it, not unpaid credit.
    assert sweep(tmp_path / "linked", [*clean_case(), commercial(linked=("alloc:1",))]) == {}


def test_an_unsupported_copy_of_a_transfer_is_an_overlap_not_a_shared_instrument(tmp_path):
    records = [
        bucket(),
        certificate(),
        event(),
        event(key="evt:2", state="PENDING"),
        allocation(),
        allocation(key="alloc:2", evt="evt:2"),
        balance(),
    ]
    found = sweep(tmp_path, records)
    assert set(found) == {"F02_OVERLAPPING_EXPORT"}
    overlap = found["F02_OVERLAPPING_EXPORT"]
    assert overlap.advisory_status == "REQUIRES_EXPERT_REVIEW"
    assert overlap.withheld_claim_scopes == ["pending_untransferred_credits"]
    assert {"evt:1", "evt:2", "alloc:2"} <= {ref.ref_id for ref in overlap.fact_refs}


def test_supported_tranches_of_one_certificate_are_a_shared_instrument_not_an_overlap(tmp_path):
    tranches = [
        bucket(),
        certificate(face="110.0000"),
        event(),
        event(key="evt:2", when="2024-09-20T10:00:00Z"),
        allocation(),
        allocation(key="alloc:2", evt="evt:2"),
        balance(reported="110.0000"),
    ]
    found = sweep(tmp_path, tranches)
    assert set(found) == {"F03_MULTISTAGE_ID_REUSE"}
    shared = found["F03_MULTISTAGE_ID_REUSE"]
    assert (shared.advisory_status, shared.abstention_reason) == ("REQUIRES_EXPERT_REVIEW", None)
    # One unsupported tranche at a distinct time is neither shape.
    pending = [*tranches[:3], event(key="evt:2", when="2024-09-20T10:00:00Z", state="PENDING")]
    pending += [allocation(), allocation(key="alloc:2", evt="evt:2"), balance()]
    assert sweep(tmp_path / "pending", pending) == {}


def test_an_export_row_repeating_a_tranche_does_not_hide_the_shared_instrument(tmp_path):
    def ref(record, value):
        return record.model_copy(update={"external_event_ref": value})

    tranches = [
        bucket(),
        certificate(face="110.0000"),
        ref(event(), "TXN-1"),
        ref(event(key="evt:2", when="2024-09-20T10:00:00Z"), "TXN-2"),
        allocation(),
        allocation(key="alloc:2", evt="evt:2"),
        balance(reported="110.0000"),
    ]
    # The ledger export repeats the second tranche: same reference and quantity, a dated time.
    copy = ref(event(key="evt:3", state="PENDING"), "TXN-2").model_copy(
        update={"event_time": day("2024-09-20"), "to_entity_id": None}
    )
    assert set(sweep(tmp_path, [*tranches, copy])) == {"F03_MULTISTAGE_ID_REUSE"}
    # An unsupported transfer that repeats no tranche leaves the certificate unresolved.
    other = event(key="evt:4", state="PENDING", quantity="10.0000", when="2024-09-25T10:00:00Z")
    assert sweep(tmp_path / "other", [*tranches, other]) == {}


def test_a_dated_cutoff_wholly_before_an_allocated_transfer_is_stale(tmp_path):
    def records(cutoff):
        stale = balance().model_copy(update={"business_cutoff": day(cutoff)})
        return [bucket(), certificate(), event(), allocation(), stale]

    found = sweep(tmp_path, records("2024-09-01"))["F06_STALE_SNAPSHOT"]
    assert found.withheld_claim_scopes == ["stale_portal_statement"]
    assert signal_checks(found) == ["CUTOFF_BEFORE_TRANSFER"]
    # The transfer's own day may be after it, or not: no claim of staleness.
    assert sweep(tmp_path / "same_day", records("2024-09-15")) == {}


def test_complete_checks_that_found_nothing_contradict_their_family(tmp_path):
    _, universe, found = swept(tmp_path, [*clean_case(), commercial()])
    assert contradicted_families(found, universe) == {
        "F02_OVERLAPPING_EXPORT",
        "F04_UNIT_DIMENSION_MIX",
    }
    # Without the swept records nothing is known to be absent.
    assert contradicted_families(found, None) == set()


def test_only_a_settled_reconciliation_can_be_clean(tmp_path):
    clean, _, _ = swept(tmp_path, clean_case())
    assert settled_without_finding(clean)
    pending, _, _ = swept(tmp_path / "pending", [*clean_case(), commercial()])
    assert not settled_without_finding(pending)
    # No analyzed bucket is not a clean result.
    assert not settled_without_finding(CalculationResult.model_construct(bucket_results=[]))


def test_a_clean_finding_cites_its_reconciliation_and_certifies_nothing(tmp_path):
    from recycleguard.investigation import InvestigationService

    calc, _, found = swept(tmp_path, clean_case())
    assert found == [] and settled_without_finding(calc)
    clean = InvestigationService._clean_finding(calc)
    assert (clean.issue_type, clean.advisory_status) == (
        "F01_CLEAN_BASELINE",
        "RECONCILED_WITHIN_SCOPE",
    )
    assert [ref.ref_id for ref in clean.fact_refs] == [calc.calculation_id]
    assert clean.next_action.kind == "NO_FURTHER_ACTION"
    assert any("does not establish that the target was met" in s for s in clean.scope_limits)
