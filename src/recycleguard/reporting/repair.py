"""One deterministic canonical rebuild; the workflow owns persistent repair reservations."""

from collections.abc import Iterable
from typing import Literal

from recycleguard.contracts.core import BoundaryModel, EvidenceRef
from recycleguard.contracts.results import CalculationResult, FindingRecord
from recycleguard.reporting.baseline import (
    BaselineReport,
    BaselineReportBuilder,
    ReportVerifier,
    VerificationResult,
)


class ReportRepairResult(BoundaryModel):
    repaired_report: BaselineReport
    verification: VerificationResult
    repairs_applied: list[str]
    repair_attempts: int
    status: Literal["SUCCESS", "QUALIFIED", "BLOCKED_OUTPUT"]


class ReportRepairService:
    """Trusted composition fixes a zero/one bound; request JSON cannot increase it.

    This performs no model calls or evidence mutations. A persistent workflow must
    reserve its report_repair action before invoking this deterministic function.
    """

    def __init__(self, verifier: ReportVerifier | None = None, max_repairs: int = 1):
        if max_repairs not in {0, 1}:
            raise ValueError("report repair limit must be zero or one")
        self.verifier = verifier or ReportVerifier()
        self.max_repairs = max_repairs

    def repair(
        self,
        report: BaselineReport,
        verification: VerificationResult,
        *,
        authoritative_calculations: list[CalculationResult],
        available_evidence_refs: Iterable[EvidenceRef] = (),
        findings: Iterable[FindingRecord] = (),
    ) -> ReportRepairResult:
        references, findings = tuple(available_evidence_refs), tuple(findings)
        # Supplied verification is diagnostic data, never authority to skip checks.
        checked = self.verifier.verify(
            report,
            authoritative_calculations=authoritative_calculations,
            available_evidence_refs=references,
            findings=findings,
        )
        if checked.verdict != "BLOCKED":
            return ReportRepairResult(
                repaired_report=report,
                verification=checked,
                repairs_applied=[],
                repair_attempts=0,
                status="SUCCESS" if checked.verdict == "PASS" else "QUALIFIED",
            )
        if not self.max_repairs or len(authoritative_calculations) != 1:
            return ReportRepairResult(
                repaired_report=report,
                verification=checked,
                repairs_applied=[],
                repair_attempts=0,
                status="BLOCKED_OUTPUT",
            )
        calculation = authoritative_calculations[0]
        coverage = (
            report.revision.coverage_ref if report.revision.coverage_ref in references else None
        )
        repaired = BaselineReportBuilder().build(
            calculation,
            findings=findings,
            coverage_ref=coverage,
            run_id=report.revision.run_id,
        )
        final = self.verifier.verify(
            repaired,
            authoritative_calculations=authoritative_calculations,
            available_evidence_refs=references,
            findings=findings,
        )
        return ReportRepairResult(
            repaired_report=repaired,
            verification=final,
            repairs_applied=[
                "Rebuilt canonical report from authoritative calculations and findings"
            ],
            repair_attempts=1,
            status="BLOCKED_OUTPUT"
            if final.verdict == "BLOCKED"
            else ("SUCCESS" if final.verdict == "PASS" else "QUALIFIED"),
        )
