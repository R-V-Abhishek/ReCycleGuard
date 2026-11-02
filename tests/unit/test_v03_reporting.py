"""V03 deterministic report and numeric/citation verification tests."""

from pathlib import Path

import pytest

from recycleguard.contracts.core import EvidenceRef
from recycleguard.contracts.results import CalculationValueRef, FindingRecord, Recommendation
from recycleguard.reporting import BaselineReportBuilder, ReportVerifier
from tests.support.c08 import clean_case, run

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def calculation(tmp_path):
    return run(tmp_path, clean_case()).output


def test_baseline_report_has_eight_sections_and_exact_numbers(tmp_path):
    report = BaselineReportBuilder().build(calculation(tmp_path))

    assert [section.section_id for section in report.sections] == [
        "CASE_SCOPE",
        "EVIDENCE_COVERAGE",
        "BUCKET_RECONCILIATION",
        "FINDING_REGISTER",
        "INVESTIGATION_HISTORY",
        "NEXT_ACTIONS",
        "HUMAN_DECISIONS",
        "LIMITATIONS_AND_REPRODUCIBILITY",
    ]
    assert "Required for bucket:a: 100.0000 KG." in report.rendered_markdown
    assert "Supported for bucket:a: 55.0000 KG." in report.rendered_markdown
    assert "Signed gap for bucket:a: 45.0000 KG." in report.rendered_markdown
    assert "{value}" not in report.rendered_markdown

    verification = ReportVerifier().verify(report, authoritative_calculations=report.calculations)
    assert verification.verdict == "PASS"
    assert not verification.issues


def test_numeric_claim_with_stale_calculation_reference_is_blocked(tmp_path):
    report = BaselineReportBuilder().build(calculation(tmp_path))
    claim = next(claim for claim in report.claims if claim.kind == "NUMERIC")
    stale = claim.model_copy(
        update={
            "calculation_value_ref": CalculationValueRef(
                calculation_id="calc:missing",
                bucket_id="bucket:a",
                field="required",
            )
        }
    )
    claims = [stale if item.claim_id == claim.claim_id else item for item in report.claims]
    invalid = report.model_copy(update={"claims": claims})

    verification = ReportVerifier().verify(invalid, authoritative_calculations=report.calculations)
    assert verification.verdict == "BLOCKED"
    assert any("calculation reference" in issue.message for issue in verification.issues)


def test_uncited_claim_blocks_report(tmp_path):
    report = BaselineReportBuilder().build(calculation(tmp_path))
    claim = report.claims[0].model_copy(update={"evidence_refs": []})
    claims = [claim, *report.claims[1:]]
    invalid = report.model_copy(update={"claims": claims})

    verification = ReportVerifier().verify(invalid, authoritative_calculations=report.calculations)
    assert verification.verdict == "BLOCKED"
    assert any(issue.code == "MISSING_ARTIFACT" for issue in verification.issues)


def test_prohibited_verdict_blocks_publication(tmp_path):
    report = BaselineReportBuilder().build(calculation(tmp_path))
    claim = report.claims[0].model_copy(
        update={"template_or_text": "This proves legal compliance."}
    )
    claims = [claim, *report.claims[1:]]
    invalid = report.model_copy(update={"claims": claims})

    verification = ReportVerifier().verify(invalid, authoritative_calculations=report.calculations)
    assert verification.verdict == "BLOCKED"
    assert any(issue.code == "PROHIBITED_VERDICT" for issue in verification.issues)


@pytest.mark.parametrize(
    "text",
    [
        "Required: {value} and {value}.",
        "Required: {value} {other}.",
        "Required: {value!r}.",
        "Required: 100 KG.",
    ],
)
def test_malformed_numeric_templates_are_blocked(tmp_path, text):
    report = BaselineReportBuilder().build(calculation(tmp_path))
    index = next(i for i, claim in enumerate(report.claims) if claim.kind == "NUMERIC")
    claims = list(report.claims)
    claims[index] = claims[index].model_copy(update={"template_or_text": text})
    result = ReportVerifier().verify(
        report.model_copy(update={"claims": claims}), authoritative_calculations=report.calculations
    )
    assert result.verdict == "BLOCKED"


@pytest.mark.parametrize(
    "addition", ["Supported: 999 KG.", "The producer is legally compliant.", ""]
)
def test_rendered_report_must_match_verified_claims(tmp_path, addition):
    report = BaselineReportBuilder().build(calculation(tmp_path))
    invalid = report.model_copy(update={"rendered_markdown": addition})
    result = ReportVerifier().verify(invalid, authoritative_calculations=report.calculations)
    assert result.verdict == "BLOCKED"
    assert any(
        check["check"] == "rendered_content" and not check["passed"] for check in result.checks
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("claim_ids", []),
        ("calculation_ids", []),
        ("section_refs", []),
        ("finding_revision_ids", ["finding_revision:invented"]),
        ("review_dependency_digest", "0" * 64),
        ("report_id", "report:invented"),
        ("supersedes_report_revision_id", "report_revision:invented"),
    ],
)
def test_inconsistent_revision_metadata_is_blocked(tmp_path, field, value):
    report = BaselineReportBuilder().build(calculation(tmp_path))
    invalid = report.model_copy(
        update={"revision": report.revision.model_copy(update={field: value})}
    )
    result = ReportVerifier().verify(invalid, authoritative_calculations=report.calculations)
    assert result.verdict == "BLOCKED"


def test_embedded_calculation_cannot_replace_authoritative_input(tmp_path):
    trusted = calculation(tmp_path)
    fake = trusted.model_copy(update={"case_version_id": "case_version:fake"})
    report = BaselineReportBuilder().build(fake)
    assert (
        ReportVerifier().verify(report, authoritative_calculations=[trusted]).verdict == "BLOCKED"
    )
    assert ReportVerifier().verify(report, authoritative_calculations=[]).verdict == "BLOCKED"


def test_duplicate_claim_and_missing_section_claim_are_blocked(tmp_path):
    report = BaselineReportBuilder().build(calculation(tmp_path))
    for invalid in (
        report.model_copy(update={"claims": [*report.claims, report.claims[0]]}),
        report.model_copy(
            update={
                "sections": [
                    report.sections[0].model_copy(update={"claim_ids": ["claim:missing"]}),
                    *report.sections[1:],
                ]
            }
        ),
    ):
        assert (
            ReportVerifier().verify(invalid, authoritative_calculations=report.calculations).verdict
            == "BLOCKED"
        )


def test_evidence_requires_exact_revision_and_locator(tmp_path):
    trusted = calculation(tmp_path)
    coverage = EvidenceRef(
        ref_kind="ARTIFACT",
        ref_id="artifact:coverage",
        artifact_revision_id="artifact_revision:one",
        locator=None,
    )
    report = BaselineReportBuilder().build(trusted, coverage_ref=coverage)
    wrong_revision = coverage.model_copy(update={"artifact_revision_id": "artifact_revision:two"})
    verifier = ReportVerifier()
    assert (
        verifier.verify(
            report, authoritative_calculations=[trusted], available_evidence_refs=[wrong_revision]
        ).verdict
        == "BLOCKED"
    )
    assert (
        verifier.verify(
            report, authoritative_calculations=[trusted], available_evidence_refs=[coverage]
        ).verdict
        == "PASS"
    )


def test_qualified_baseline_preserves_unknown_comparison(tmp_path):
    trusted = calculation(tmp_path)
    bucket = trusted.bucket_results[0].model_copy(
        update={"portal_reported": None, "delta": None, "snapshot_comparison_ref": None}
    )
    qualified = trusted.model_copy(update={"coverage": "QUALIFIED", "bucket_results": [bucket]})
    report = BaselineReportBuilder().build(qualified)
    assert "Portal reported for bucket:a: unavailable." in report.rendered_markdown
    result = ReportVerifier().verify(report, authoritative_calculations=[qualified])
    assert result.verdict == "QUALIFIED"
    assert not result.issues


def test_every_finding_has_its_own_action_and_pinned_revision(tmp_path):
    trusted = calculation(tmp_path)
    calc_ref = EvidenceRef(
        ref_kind="CALCULATION",
        ref_id=trusted.calculation_id,
        artifact_revision_id=None,
        locator=None,
    )
    findings = [
        FindingRecord(
            finding_id=f"finding:{i}",
            finding_revision_id=f"finding_revision:{i}",
            case_version_id=trusted.case_version_id,
            bucket_ids=["bucket:a"],
            issue_type="F01_CLEAN_BASELINE",
            advisory_status="PENDING_VERIFICATION",
            priority="LOW",
            priority_basis="Unreviewed baseline",
            portal_reported_value_ref=None,
            ledger_supported_value_ref=None,
            delta_value_ref=None,
            snapshot_comparison_ref=None,
            fact_refs=[calc_ref],
            calculation_refs=[trusted.calculation_id],
            provision_refs=[],
            evidence_assessments=[],
            hypotheses=[],
            abstention_reason="MISSING_EVIDENCE",
            withheld_claim_scopes=["allocation support"],
            next_action=Recommendation(
                kind="REQUEST_EVIDENCE",
                description=f"Inspect evidence item {i}.",
                evidence_refs=[calc_ref],
            ),
            action_owner_ref=None,
            scope_limits=[],
            supersedes_finding_revision_id=None,
        )
        for i in range(2)
    ]
    report = BaselineReportBuilder().build(trusted, findings=findings)
    next_actions = next(
        section for section in report.sections if section.section_id == "NEXT_ACTIONS"
    )
    assert len(next_actions.claim_ids) == 2
    assert all(f"Inspect evidence item {i}." in report.rendered_markdown for i in range(2))
    verifier = ReportVerifier()
    assert (
        verifier.verify(report, authoritative_calculations=[trusted], findings=findings).verdict
        == "PASS"
    )
    assert verifier.verify(report, authoritative_calculations=[trusted]).verdict == "BLOCKED"


def test_missing_numeric_bucket_is_blocked_without_crashing(tmp_path):
    report = BaselineReportBuilder().build(calculation(tmp_path))
    claims = list(report.claims)
    index = next(i for i, claim in enumerate(claims) if claim.kind == "NUMERIC")
    reference = claims[index].calculation_value_ref.model_copy(
        update={"bucket_id": "bucket:missing"}
    )
    claims[index] = claims[index].model_copy(update={"calculation_value_ref": reference})
    result = ReportVerifier().verify(
        report.model_copy(update={"claims": claims}), authoritative_calculations=report.calculations
    )
    assert result.verdict == "BLOCKED"


def test_blocked_calculation_cannot_be_published_as_qualified(tmp_path):
    trusted = calculation(tmp_path).model_copy(update={"coverage": "BLOCKED"})
    report = BaselineReportBuilder().build(trusted)
    assert (
        ReportVerifier().verify(report, authoritative_calculations=[trusted]).verdict == "BLOCKED"
    )
