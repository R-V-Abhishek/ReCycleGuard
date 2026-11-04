"""Findings from deterministic checks: one per family, never from a shared code alone."""

from recycleguard.contracts.core import EvidenceRef
from recycleguard.contracts.results import CalculationResult
from recycleguard.domain.models import (
    AllocationCheck,
    Derivation,
    EligibilityOutcome,
    PriorityCheck,
)
from recycleguard.domain.refs import make_issue
from recycleguard.domain.universe import universe_from_records
from recycleguard.reporting.calculation_findings import calculation_findings
from recycleguard.storage import BlobStore
from tests.support.c08 import (
    SNAPSHOT,
    allocation,
    balance,
    bucket,
    certificate,
    clean_case,
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


def test_earlier_liability_breach_is_asserted_and_an_unknown_order_withheld():
    breach = families(calculation(), derivation(priority=[priority("FAIL")]))
    assert breach["F08_PRIOR_ARREARS_DRAIN"].advisory_status == "DISCREPANCY_DETECTED"
    unknown = families(calculation(), derivation(priority=[priority("FAIL"), priority("UNKNOWN")]))
    assert unknown["F08_PRIOR_ARREARS_DRAIN"].withheld_claim_scopes == [
        "earlier_liability_priority"
    ]
    assert families(calculation(), derivation(priority=[priority("PASS")])) == {}


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


def sweep(tmp_path, records):
    result = run(tmp_path, records)
    calc = result.output
    found = calculation_findings(
        calc,
        Derivation.model_validate_json(BlobStore(tmp_path / "blobs").get(calc.derivation_blob)),
        universe_from_records(SNAPSHOT, records),
    )
    return {f.issue_type: f for f in found}


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
    assert set(sweep(tmp_path, records)) == {"F04_UNIT_DIMENSION_MIX", "F10_CAPABILITY_MISMATCH"}


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
