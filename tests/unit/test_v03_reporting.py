"""V03 deterministic report and numeric/citation verification tests."""

from pathlib import Path

from recycleguard.contracts.results import CalculationValueRef
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

    verification = ReportVerifier().verify(report)
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

    verification = ReportVerifier().verify(invalid)
    assert verification.verdict == "BLOCKED"
    assert any("calculation reference" in issue.message for issue in verification.issues)


def test_uncited_claim_qualifies_report(tmp_path):
    report = BaselineReportBuilder().build(calculation(tmp_path))
    claim = report.claims[0].model_copy(update={"evidence_refs": []})
    claims = [claim, *report.claims[1:]]
    invalid = report.model_copy(update={"claims": claims})

    verification = ReportVerifier().verify(invalid)
    assert verification.verdict == "QUALIFIED"
    assert any(issue.code == "MISSING_ARTIFACT" for issue in verification.issues)


def test_prohibited_verdict_blocks_publication(tmp_path):
    report = BaselineReportBuilder().build(calculation(tmp_path))
    claim = report.claims[0].model_copy(
        update={"template_or_text": "This proves legal compliance."}
    )
    claims = [claim, *report.claims[1:]]
    invalid = report.model_copy(update={"claims": claims})

    verification = ReportVerifier().verify(invalid)
    assert verification.verdict == "BLOCKED"
    assert any(issue.code == "PROHIBITED_VERDICT" for issue in verification.issues)
