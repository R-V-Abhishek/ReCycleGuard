"""Findings from structured reconciliation checks: one per family, never from a code alone."""

from recycleguard.contracts.core import EvidenceRef
from recycleguard.contracts.results import CalculationResult
from recycleguard.domain.models import (
    AllocationCheck,
    Derivation,
    EligibilityOutcome,
    PriorityCheck,
)
from recycleguard.domain.refs import make_issue
from recycleguard.reporting.calculation_findings import calculation_findings

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


def test_only_a_bucket_dimension_failure_is_a_unit_mix_not_a_wrong_metal():
    blocking = make_issue(
        "DIMENSION_MISMATCH", "BLOCKING", "adjustment is not metal mass", [RECORD]
    )
    wrong_metal = make_issue("DIMENSION_MISMATCH", "WARNING", "metal differs from bucket")
    assert set(families(calculation(wrong_metal), derivation())) == set()
    found = families(calculation(blocking, wrong_metal), derivation())["F04_UNIT_DIMENSION_MIX"]
    assert found.advisory_status == "DISCREPANCY_DETECTED" and found.abstention_reason is None
    assert {ref.ref_id for ref in found.fact_refs} == {"record:a1", "calc:test"}
    assert found.calculation_refs == ["calc:test"]


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


def test_only_a_definite_lifecycle_end_is_an_expired_or_cancelled_finding():
    assert families(calculation(), derivation(checks=[check("LIFECYCLE", "UNKNOWN")])) == {}
    found = families(
        calculation(), derivation(checks=[check("LIFECYCLE", "FAIL", "CREDIT_EXPIRED")])
    )
    assert set(found) == {"F09_EXPIRED_CANCELLED"}


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
