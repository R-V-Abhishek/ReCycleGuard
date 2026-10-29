"""Unit tests for H07 deadline register, temporal overlays, and amendment edges.

Owned by Sampreeth (H07).
Tests:
- Deadline register with verified extensions, notice leads, and missing baseline (abstention)
- Cross-kind deadline independence (RETURN_FILING cannot extend OBLIGATION_ACHIEVEMENT)
- Amendment overlay resolution (REPLACES, AMENDS, unaffected surviving clauses)
- Missing extension order tests (Rule 9A enabling vs signed extension order)
- Temporal applicability half-open intervals and general vs role-specific overrides
"""

from recycleguard.contracts.core import EvidenceRef, Locator, TemporalValue
from recycleguard.contracts.sources import (
    AmendmentEdge,
    ApplicabilityAssertion,
    DeadlineEntry,
)
from recycleguard.knowledge.deadline_register import (
    AmendmentOverlayService,
    DeadlineRegister,
    TemporalApplicabilityChecker,
)


def _make_temporal(val: str | None) -> TemporalValue:
    if val is None:
        return TemporalValue(
            raw=None,
            value=None,
            precision="UNKNOWN",
            timezone=None,
            interpretation_status="UNKNOWN",
        )
    return TemporalValue(
        raw=val,
        value=val,
        precision="DATE",
        timezone=None,
        interpretation_status="REVIEWED",
    )


def _make_ref(name: str) -> EvidenceRef:
    return EvidenceRef(
        ref_kind="PROVISION",
        ref_id=f"prov:{name}",
        artifact_revision_id=f"artrev:{name}",
        locator=Locator(
            kind="PDF_PAGE",
            page_index_1based=1,
            printed_page_label="1",
            row_index_1based=None,
            column_name=None,
            json_pointer=None,
            text_start=None,
            text_end=None,
            table_id=None,
            cell_row=None,
            cell_column=None,
        ),
    )


# ──────────────────────────────────────────────────────────────────────────────
# DeadlineRegister tests
# ──────────────────────────────────────────────────────────────────────────────


def test_deadline_register_verified_extension():
    """A verified extension order updates the effective deadline."""
    register = DeadlineRegister(verified_order_refs={"prov:cpcb_order_20250620", "prov:order_v2"})
    entry = DeadlineEntry(
        deadline_id="deadline:ret_filing_2024_25",
        producer_or_role_scope="PRODUCER",
        fiscal_year="2024-25",
        quarter=None,
        kind="RETURN_FILING",
        baseline_basis_refs=[_make_ref("baseline")],
        baseline_due=_make_temporal("2025-06-30"),
        extended_due=_make_temporal("2025-09-30"),
        extension_order_refs=[_make_ref("cpcb_order_20250620")],
        enabling_provision_refs=[_make_ref("e_waste_rule_9a")],
        unverified_notice=False,
        review_state="APPROVED",
    )
    register.add_entry(entry)

    result = register.resolve_deadline("PRODUCER", "2024-25", "RETURN_FILING")
    assert result.verdict == "PASS"
    assert result.is_verified_extension is True
    assert result.effective_date == "2025-09-30"
    assert any("Verified extension order found" in r for r in result.reasons)


def test_deadline_register_unverified_notice_lead():
    """A notice lead (unverified_notice=True) never creates a verified extension."""
    register = DeadlineRegister(verified_order_refs={"prov:cpcb_order_20250620", "prov:order_v2"})
    entry = DeadlineEntry(
        deadline_id="deadline:ret_filing_2024_25_notice",
        producer_or_role_scope="PRODUCER",
        fiscal_year="2024-25",
        quarter=None,
        kind="RETURN_FILING",
        baseline_basis_refs=[_make_ref("baseline")],
        baseline_due=_make_temporal("2025-06-30"),
        extended_due=_make_temporal("2025-10-31"),
        extension_order_refs=[_make_ref("news_report_extension")],
        enabling_provision_refs=[_make_ref("e_waste_rule_9a")],
        unverified_notice=True,  # Press report / unverified portal notice
        review_state="APPROVED",
    )
    register.add_entry(entry)

    result = register.resolve_deadline("PRODUCER", "2024-25", "RETURN_FILING")
    assert result.verdict == "ABSTAIN"
    assert result.is_verified_extension is False
    # Must fall back to baseline date because notice lead is not verified
    assert result.effective_date == "2025-06-30"
    assert any("unverified_notice=True" in r for r in result.reasons)


def test_deadline_register_enabling_provision_alone_fails_extension():
    """Rule 9A is an enabling provision, not the extension order itself.

    extended_due without extension_order_refs must not apply the extension.
    """
    register = DeadlineRegister(verified_order_refs={"prov:cpcb_order_20250620", "prov:order_v2"})
    entry = DeadlineEntry(
        deadline_id="deadline:ret_filing_2024_25_enabling_only",
        producer_or_role_scope="PRODUCER",
        fiscal_year="2024-25",
        quarter=None,
        kind="RETURN_FILING",
        baseline_basis_refs=[_make_ref("baseline")],
        baseline_due=_make_temporal("2025-06-30"),
        extended_due=_make_temporal("2025-12-31"),
        extension_order_refs=[],  # Missing order ref!
        enabling_provision_refs=[_make_ref("rule_9a")],
        unverified_notice=False,
        review_state="APPROVED",
    )
    register.add_entry(entry)

    result = register.resolve_deadline("PRODUCER", "2024-25", "RETURN_FILING")
    assert result.verdict == "ABSTAIN"
    assert result.is_verified_extension is False
    assert result.effective_date == "2025-06-30"
    assert any("enabling provision alone" in r for r in result.reasons)


def test_deadline_register_missing_baseline_abstains():
    """Missing baseline_due date stays unknown and returns ABSTAIN; never invent a default."""
    register = DeadlineRegister(verified_order_refs={"prov:cpcb_order_20250620", "prov:order_v2"})
    entry = DeadlineEntry(
        deadline_id="deadline:credit_event_unknown_baseline",
        producer_or_role_scope="PRODUCER",
        fiscal_year="2024-25",
        quarter=None,
        kind="CREDIT_EVENT",
        baseline_basis_refs=[_make_ref("baseline")],
        baseline_due=_make_temporal(None),  # Unknown baseline date
        extended_due=None,
        extension_order_refs=[],
        enabling_provision_refs=[],
        unverified_notice=False,
        review_state="APPROVED",
    )
    register.add_entry(entry)

    result = register.resolve_deadline("PRODUCER", "2024-25", "CREDIT_EVENT")
    assert result.verdict == "ABSTAIN"
    assert result.effective_date is None
    assert any("unknown value" in r for r in result.reasons)


def test_deadline_register_missing_entry_abstains():
    """Querying an unregistered FY/kind returns ABSTAIN."""
    register = DeadlineRegister(verified_order_refs={"prov:cpcb_order_20250620", "prov:order_v2"})
    result = register.resolve_deadline("RECYCLER", "2022-23", "OBLIGATION_ACHIEVEMENT")
    assert result.verdict == "ABSTAIN"
    assert result.effective_date is None


def test_deadline_register_cross_kind_independence():
    """A RETURN_FILING extension cannot extend OBLIGATION_ACHIEVEMENT or CREDIT_EVENT."""
    register = DeadlineRegister(verified_order_refs={"prov:cpcb_order_20250620", "prov:order_v2"})
    filing_entry = DeadlineEntry(
        deadline_id="deadline:ret_filing_2024_25",
        producer_or_role_scope="PRODUCER",
        fiscal_year="2024-25",
        quarter=None,
        kind="RETURN_FILING",
        baseline_basis_refs=[_make_ref("baseline")],
        baseline_due=_make_temporal("2025-06-30"),
        extended_due=_make_temporal("2025-09-30"),
        extension_order_refs=[_make_ref("cpcb_order")],
        enabling_provision_refs=[_make_ref("rule_9a")],
        unverified_notice=False,
        review_state="APPROVED",
    )
    register.add_entry(filing_entry)

    # Cross-kind check for OBLIGATION_ACHIEVEMENT
    check = register.check_cross_kind_independence(
        "deadline:ret_filing_2024_25", "OBLIGATION_ACHIEVEMENT"
    )
    assert check["verdict"] == "PASS"
    assert any("does not automatically extend" in r for r in check["reasons"])

    # Querying OBLIGATION_ACHIEVEMENT deadline should not return the filing date
    obl_result = register.resolve_deadline("PRODUCER", "2024-25", "OBLIGATION_ACHIEVEMENT")
    assert obl_result.verdict == "ABSTAIN"  # No obligation entry registered


def test_deadline_register_supersedes_chain():
    """A superseding entry takes precedence over the earlier one."""
    register = DeadlineRegister(verified_order_refs={"prov:cpcb_order_20250620", "prov:order_v2"})
    entry1 = DeadlineEntry(
        deadline_id="deadline:ret_filing_v1",
        producer_or_role_scope="PRODUCER",
        fiscal_year="2024-25",
        quarter=None,
        kind="RETURN_FILING",
        baseline_basis_refs=[_make_ref("baseline")],
        baseline_due=_make_temporal("2025-06-30"),
        extended_due=None,
        review_state="APPROVED",
    )
    entry2 = DeadlineEntry(
        deadline_id="deadline:ret_filing_v2",
        producer_or_role_scope="PRODUCER",
        fiscal_year="2024-25",
        quarter=None,
        kind="RETURN_FILING",
        baseline_basis_refs=[_make_ref("baseline")],
        baseline_due=_make_temporal("2025-06-30"),
        extended_due=_make_temporal("2025-08-31"),
        extension_order_refs=[_make_ref("order_v2")],
        review_state="APPROVED",
        supersedes_deadline_id="deadline:ret_filing_v1",
    )
    register.add_entry(entry1)
    register.add_entry(entry2)

    result = register.resolve_deadline("PRODUCER", "2024-25", "RETURN_FILING")
    assert result.deadline_id == "deadline:ret_filing_v2"
    assert result.effective_date == "2025-08-31"


# ──────────────────────────────────────────────────────────────────────────────
# AmendmentOverlayService tests
# ──────────────────────────────────────────────────────────────────────────────


def test_amendment_overlay_replaces():
    """REPLACES relation completely supersedes the prior provision."""
    service = AmendmentOverlayService()
    edge = AmendmentEdge(
        edge_id="edge:amendment_2024_replaces_rule4",
        from_provision_id="prov:amendment_2024_rule4",
        to_provision_id="prov:original_2022_rule4",
        relation="REPLACES",
        review_state="APPROVED",
    )
    service.add_edge(edge)

    status = service.check_amendment_status("prov:original_2022_rule4")
    assert status.is_replaced is True
    assert status.surviving_amendment == "prov:amendment_2024_rule4"
    assert any("replaced by" in r for r in status.reasons)


def test_amendment_overlay_partial_amends_preserves_unaffected():
    """AMENDS relation partially changes text; unaffected clauses survive."""
    service = AmendmentOverlayService()
    amend_edge = AmendmentEdge(
        edge_id="edge:amend_clause_b",
        from_provision_id="prov:amend_rule5_clause_b",
        to_provision_id="prov:rule5_base",
        relation="AMENDS",
        affected_scope="clause_b",
        review_state="APPROVED",
    )
    ref_edge = AmendmentEdge(
        edge_id="edge:ref_clause_a",
        from_provision_id="prov:rule5_base",
        to_provision_id="prov:rule5_clause_a",
        relation="REFERENCES",
        review_state="APPROVED",
    )
    service.add_edge(amend_edge)
    service.add_edge(ref_edge)

    status = service.check_amendment_status("prov:rule5_base")
    assert status.is_amended is True
    assert status.is_replaced is False
    assert "prov:rule5_clause_a" in status.unaffected_clauses
    assert any("unaffected clauses survive" in r for r in status.reasons)


def test_amendment_overlay_relaxes_deadline_missing_order_warning():
    """RELAXES_DEADLINE without extension_order_refs produces a warning reason."""
    service = AmendmentOverlayService()
    edge = AmendmentEdge(
        edge_id="edge:rule9a_relax",
        from_provision_id="prov:rule9a",
        to_provision_id="prov:deadline_target",
        relation="RELAXES_DEADLINE",
        extension_order_refs=[],  # Missing order refs
        review_state="APPROVED",
    )
    service.add_edge(edge)

    status = service.check_amendment_status("prov:rule9a")
    assert any("enabling provision alone does not constitute" in r for r in status.reasons)


def test_amendment_overlay_batch_applicable():
    """get_applicable_provisions returns overlay status for multiple provisions."""
    service = AmendmentOverlayService()
    edge = AmendmentEdge(
        edge_id="edge:rep",
        from_provision_id="prov:new",
        to_provision_id="prov:old",
        relation="REPLACES",
        review_state="APPROVED",
    )
    service.add_edge(edge)

    results = service.get_applicable_provisions(["prov:old", "prov:unaffected"])
    assert results["prov:old"].is_replaced is True
    assert results["prov:unaffected"].is_replaced is False
    assert results["prov:unaffected"].is_amended is False


# ──────────────────────────────────────────────────────────────────────────────
# TemporalApplicabilityChecker tests
# ──────────────────────────────────────────────────────────────────────────────


def test_temporal_applicability_intervals():
    """Check half-open interval [effective_from, effective_until)."""
    checker = TemporalApplicabilityChecker()
    assertion = ApplicabilityAssertion(
        assertion_id="assert:fy2024_25",
        provision_version_id="prov:rules_2022_schedule_iii",
        sources=[_make_ref("effective_interval")],
        event_basis="TRANSACTION_DATE",
        effective_from=_make_temporal("2024-04-01"),
        effective_until=_make_temporal("2025-04-01"),  # exclusive
        affected_roles=["PRODUCER"],
        review_state="APPROVED",
    )
    checker.add_assertion(assertion)

    # Within interval -> PASS
    assert (
        checker.check_temporal_fit("assert:fy2024_25", None, "2024-06-15", "TRANSACTION_DATE")
        == "PASS"
    )
    assert (
        checker.check_temporal_fit("assert:fy2024_25", None, "2024-04-01", "TRANSACTION_DATE")
        == "PASS"
    )

    # Prior to effective_from -> FAIL
    assert (
        checker.check_temporal_fit("assert:fy2024_25", None, "2024-03-31", "TRANSACTION_DATE")
        == "FAIL"
    )

    # At or after effective_until (exclusive) -> FAIL
    assert (
        checker.check_temporal_fit("assert:fy2024_25", None, "2025-04-01", "TRANSACTION_DATE")
        == "FAIL"
    )
    assert (
        checker.check_temporal_fit("assert:fy2024_25", None, "2025-05-01", "TRANSACTION_DATE")
        == "FAIL"
    )

    # Missing target period -> UNRESOLVED
    assert checker.check_temporal_fit("assert:fy2024_25", None) == "UNRESOLVED"

    # Unknown assertion id -> UNRESOLVED
    assert checker.check_temporal_fit("assert:non_existent", "2024-06-15") == "UNRESOLVED"


def test_temporal_applicability_rejected_assertion_fails():
    """A REJECTED assertion returns FAIL."""
    checker = TemporalApplicabilityChecker()
    assertion = ApplicabilityAssertion(
        assertion_id="assert:rejected_rule",
        provision_version_id="prov:bad",
        sources=[_make_ref("effective_interval")],
        event_basis="TRANSACTION_DATE",
        effective_from=_make_temporal("2024-04-01"),
        affected_roles=["PRODUCER"],
        review_state="REJECTED",
    )
    checker.add_assertion(assertion)
    assert checker.check_temporal_fit("assert:rejected_rule", "2024-06-15") == "FAIL"


def test_temporal_applicability_role_override():
    """General-role clause applies unless a role-specific clause overrides."""
    checker = TemporalApplicabilityChecker()
    general = ApplicabilityAssertion(
        assertion_id="assert:general_rule",
        provision_version_id="prov:general",
        affected_roles=["PRODUCER", "RECYCLER", "REFURBISHER"],
        review_state="APPROVED",
    )
    specific_producer = ApplicabilityAssertion(
        assertion_id="assert:producer_specific",
        provision_version_id="prov:producer_override",
        affected_roles=["PRODUCER"],
        review_state="APPROVED",
    )
    checker.add_assertion(general)
    checker.add_assertion(specific_producer)

    # For PRODUCER, specific override exists and is approved -> PASS
    verdict_producer = checker.check_role_override(
        general_assertion_id="assert:general_rule",
        role="PRODUCER",
        specific_assertion_ids=["assert:producer_specific"],
    )
    assert verdict_producer == "PASS"

    # For RECYCLER, no specific override exists -> general applies -> PASS
    verdict_recycler = checker.check_role_override(
        general_assertion_id="assert:general_rule",
        role="RECYCLER",
        specific_assertion_ids=["assert:producer_specific"],
    )
    assert verdict_recycler == "PASS"


def test_reporting_year_requires_reviewed_full_interval_and_explicit_open_end():
    assertion = ApplicabilityAssertion(
        assertion_id="assert:whole_year",
        provision_version_id="prov:whole_year",
        effective_from=_make_temporal("2024-04-01"),
        effective_until=_make_temporal("2025-04-01"),
        affected_roles=["PRODUCER"],
        sources=[_make_ref("interval")],
        review_state="APPROVED",
    )
    checker = TemporalApplicabilityChecker([assertion])
    assert checker.check_temporal_fit(assertion.assertion_id, "2024-2025") == "PASS"
    assert checker.check_temporal_fit(assertion.assertion_id, "FY2023-24") == "FAIL"
    checker.add_assertion(
        assertion.model_copy(update={"effective_from": _make_temporal("2024-06-01")})
    )
    assert checker.check_temporal_fit(assertion.assertion_id, "2024-2025") == "UNRESOLVED"
    checker.add_assertion(assertion.model_copy(update={"effective_until": None}))
    assert checker.check_temporal_fit(assertion.assertion_id, "2024-2025") == "UNRESOLVED"
    checker.add_assertion(
        assertion.model_copy(update={"effective_until": None, "end_open_ended": True})
    )
    assert checker.check_temporal_fit(assertion.assertion_id, "2024-2025") == "PASS"
    checker.add_assertion(assertion.model_copy(update={"applicability_scope": "UNKNOWN"}))
    assert checker.check_temporal_fit(assertion.assertion_id, "2024-2025") == "UNRESOLVED"
