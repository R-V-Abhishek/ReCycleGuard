"""Deterministic C12 baseline report construction and claim verification."""

import hashlib
import re
from collections.abc import Iterable
from typing import Literal

from recycleguard.contracts.core import (
    ID,
    BoundaryModel,
    Digest,
    EvidenceRef,
    Issue,
)
from recycleguard.contracts.results import CalculationResult, CalculationValueRef, FindingRecord
from recycleguard.storage import canonical_json_bytes

SECTION_IDS = (
    "CASE_SCOPE",
    "EVIDENCE_COVERAGE",
    "BUCKET_RECONCILIATION",
    "FINDING_REGISTER",
    "INVESTIGATION_HISTORY",
    "NEXT_ACTIONS",
    "HUMAN_DECISIONS",
    "LIMITATIONS_AND_REPRODUCIBILITY",
)

ClaimKind = Literal["FACT", "NUMERIC", "INTERPRETATION", "LIMITATION", "RECOMMENDATION"]
SupportStatus = Literal["SUPPORTED", "QUALIFIED", "UNSUPPORTED"]
CoverageState = Literal["COMPLETE_WITHIN_SCOPE", "QUALIFIED", "BLOCKED"]
VerificationVerdict = Literal["PASS", "QUALIFIED", "BLOCKED"]


class ReportClaim(BoundaryModel):
    claim_id: ID
    kind: ClaimKind
    template_or_text: str
    evidence_refs: list[EvidenceRef]
    calculation_value_ref: CalculationValueRef | None
    support_status: SupportStatus


class ReportSection(BoundaryModel):
    section_id: Literal[
        "CASE_SCOPE",
        "EVIDENCE_COVERAGE",
        "BUCKET_RECONCILIATION",
        "FINDING_REGISTER",
        "INVESTIGATION_HISTORY",
        "NEXT_ACTIONS",
        "HUMAN_DECISIONS",
        "LIMITATIONS_AND_REPRODUCIBILITY",
    ]
    title: str
    claim_ids: list[ID]
    evidence_refs: list[EvidenceRef]
    structured_content_ref: ID
    coverage_state: CoverageState


class ReportRevision(BoundaryModel):
    report_id: ID
    report_revision_id: ID
    run_id: ID | None
    section_refs: list[ID]
    claim_ids: list[ID]
    finding_revision_ids: list[ID]
    calculation_ids: list[ID]
    coverage_ref: EvidenceRef
    review_dependency_digest: Digest
    supersedes_report_revision_id: ID | None


class BaselineReport(BoundaryModel):
    revision: ReportRevision
    sections: list[ReportSection]
    claims: list[ReportClaim]
    calculations: list[CalculationResult]
    rendered_markdown: str


class VerificationResult(BoundaryModel):
    verification_id: ID
    report_revision_id: ID
    verdict: VerificationVerdict
    checks: list[dict[str, str | bool]]
    issues: list[Issue]
    verifier_version: str
    verified_dependency_digest: Digest


_PROHIBITED = re.compile(
    r"\b(?:legal\s+compliance|fraud|intent(?:ional)?|conceal(?:ment)?|"
    r"compensation|penalt(?:y|ies))\b",
    re.IGNORECASE,
)


def _issue(code: str, message: str, *, claim_id: str | None = None) -> Issue:
    token = hashlib.sha256(canonical_json_bytes([code, message, claim_id])).hexdigest()[:16]
    return Issue(
        issue_id=f"issue:{code.lower()}_{token}",
        code=code,
        severity="BLOCKING"
        if code in {"PROHIBITED_VERDICT", "INVALID_SCHEMA", "INTEGRITY_FAILED"}
        else "WARNING",
        message=message,
        field_path=None if claim_id is None else f"claims.{claim_id}",
        evidence_refs=[],
        retryable=False,
    )


def _value(calculation: CalculationResult, reference: CalculationValueRef) -> str | None:
    bucket = next(
        (b for b in calculation.bucket_results if b.bucket_id == reference.bucket_id),
        None,
    )
    if bucket is None:
        return None
    quantity = getattr(bucket, reference.field)
    return None if quantity is None else quantity.decimal


def _quantity_label(calculation: CalculationResult, reference: CalculationValueRef) -> str:
    bucket = next(b for b in calculation.bucket_results if b.bucket_id == reference.bucket_id)
    quantity = getattr(bucket, reference.field)
    return "unavailable" if quantity is None else f"{quantity.decimal} {quantity.unit}"


def _calc_ref(calculation: CalculationResult, bucket_id: str, field: str) -> CalculationValueRef:
    return CalculationValueRef(
        calculation_id=calculation.calculation_id,
        bucket_id=bucket_id,
        field=field,
    )


class BaselineReportBuilder:
    """Build the eight-section report without copying unchecked numeric values."""

    def build(
        self,
        calculation: CalculationResult,
        *,
        findings: Iterable[FindingRecord] = (),
        coverage_ref: EvidenceRef | None = None,
        run_id: ID | None = None,
    ) -> BaselineReport:
        findings = tuple(findings)
        coverage_ref = coverage_ref or EvidenceRef(
            ref_kind="CALCULATION",
            ref_id=calculation.calculation_id,
            artifact_revision_id=None,
            locator=None,
        )
        calculation_ref = EvidenceRef(
            ref_kind="CALCULATION",
            ref_id=calculation.calculation_id,
            artifact_revision_id=None,
            locator=None,
        )
        support = "SUPPORTED" if calculation.coverage == "COMPLETE_WITHIN_SCOPE" else "QUALIFIED"
        claims: list[ReportClaim] = []
        sections: list[ReportSection] = []

        def add(
            section_id: str,
            title: str,
            text: str,
            kind: ClaimKind = "FACT",
            *,
            reference: CalculationValueRef | None = None,
            evidence_refs: list[EvidenceRef] | None = None,
            status: SupportStatus = support,
        ):
            claim_id = f"claim:{section_id.lower()}_{len(claims) + 1:03d}"
            claims.append(
                ReportClaim(
                    claim_id=claim_id,
                    kind=kind,
                    template_or_text=text,
                    evidence_refs=evidence_refs
                    or ([calculation_ref] if reference is not None else [coverage_ref]),
                    calculation_value_ref=reference,
                    support_status=status,
                )
            )
            return claim_id

        section_claims: dict[str, list[str]] = {section_id: [] for section_id in SECTION_IDS}
        section_claims["CASE_SCOPE"].append(
            add(
                "CASE_SCOPE",
                "Case scope",
                f"Case version {calculation.case_version_id}; profile {calculation.profile_id}.",
            )
        )
        section_claims["EVIDENCE_COVERAGE"].append(
            add(
                "EVIDENCE_COVERAGE",
                "Evidence coverage",
                f"Calculation coverage is {calculation.coverage}.",
            )
        )

        for bucket in calculation.bucket_results:
            for field, label in (
                ("required", "Required"),
                ("supported", "Supported"),
                ("signed_gap", "Signed gap"),
                ("pending", "Pending"),
                ("portal_reported", "Portal reported"),
                ("delta", "Portal delta"),
            ):
                reference = _calc_ref(calculation, bucket.bucket_id, field)
                section_claims["BUCKET_RECONCILIATION"].append(
                    add(
                        "BUCKET_RECONCILIATION",
                        "Bucket reconciliation",
                        f"{label} for {bucket.bucket_id}: {{value}}.",
                        "NUMERIC",
                        reference=reference,
                    )
                )

        for finding in findings:
            section_claims["FINDING_REGISTER"].append(
                add(
                    "FINDING_REGISTER",
                    "Finding register",
                    (
                        f"{finding.issue_type}: {finding.advisory_status}; "
                        f"priority {finding.priority}."
                    ),
                    "INTERPRETATION",
                    evidence_refs=finding.fact_refs or [coverage_ref],
                    status=(
                        "QUALIFIED"
                        if finding.advisory_status != "RECONCILED_WITHIN_SCOPE"
                        else support
                    ),
                )
            )
            section_claims["NEXT_ACTIONS"].append(
                add(
                    "NEXT_ACTIONS",
                    "Next action",
                    finding.next_action.description,
                    "RECOMMENDATION",
                    evidence_refs=finding.next_action.evidence_refs or [coverage_ref],
                    status="QUALIFIED",
                )
            )

        if not section_claims["FINDING_REGISTER"]:
            section_claims["FINDING_REGISTER"].append(
                add(
                    "FINDING_REGISTER",
                    "Finding register",
                    "No structured findings were supplied to this baseline report.",
                    "LIMITATION",
                    status="QUALIFIED",
                )
            )
        if not section_claims["NEXT_ACTIONS"]:
            section_claims["NEXT_ACTIONS"].append(
                add(
                    "NEXT_ACTIONS",
                    "Next action",
                    "No next action is proposed without a structured finding.",
                    "LIMITATION",
                    status="QUALIFIED",
                )
            )

        section_claims["INVESTIGATION_HISTORY"].append(
            add(
                "INVESTIGATION_HISTORY",
                "Investigation history",
                "No model-authored investigation steps are asserted in this baseline report.",
                "LIMITATION",
                status="QUALIFIED",
            )
        )
        section_claims["HUMAN_DECISIONS"].append(
            add(
                "HUMAN_DECISIONS",
                "Human decisions",
                "No human approval is implied by this report.",
                "LIMITATION",
                status="QUALIFIED",
            )
        )
        section_claims["LIMITATIONS_AND_REPRODUCIBILITY"].append(
            add(
                "LIMITATIONS_AND_REPRODUCIBILITY",
                "Limitations",
                "Numerical agreement does not establish legal correctness or filing readiness.",
                "LIMITATION",
                status="QUALIFIED",
            )
        )

        titles = {
            "CASE_SCOPE": "Case scope",
            "EVIDENCE_COVERAGE": "Evidence coverage",
            "BUCKET_RECONCILIATION": "Bucket reconciliation",
            "FINDING_REGISTER": "Finding register",
            "INVESTIGATION_HISTORY": "Investigation history",
            "NEXT_ACTIONS": "Next actions",
            "HUMAN_DECISIONS": "Human decisions",
            "LIMITATIONS_AND_REPRODUCIBILITY": "Limitations and reproducibility",
        }
        for section_id in SECTION_IDS:
            sections.append(
                ReportSection(
                    section_id=section_id,
                    title=titles[section_id],
                    claim_ids=section_claims[section_id],
                    evidence_refs=[coverage_ref],
                    structured_content_ref=f"section:{section_id.lower()}",
                    coverage_state=calculation.coverage,
                )
            )

        revision_payload = {
            "calculation": calculation.model_dump(mode="json"),
            "claims": [claim.model_dump(mode="json") for claim in claims],
            "sections": [section.model_dump(mode="json") for section in sections],
            "run_id": run_id,
        }
        digest = hashlib.sha256(canonical_json_bytes(revision_payload)).hexdigest()
        revision = ReportRevision(
            report_id=f"report:{digest[:24]}",
            report_revision_id=f"report_revision:{digest[:24]}",
            run_id=run_id,
            section_refs=[section.structured_content_ref for section in sections],
            claim_ids=[claim.claim_id for claim in claims],
            finding_revision_ids=[finding.finding_revision_id for finding in findings],
            calculation_ids=[calculation.calculation_id],
            coverage_ref=coverage_ref,
            review_dependency_digest=digest,
            supersedes_report_revision_id=None,
        )
        report = BaselineReport(
            revision=revision,
            sections=sections,
            claims=claims,
            calculations=[calculation],
            rendered_markdown="",
        )
        return report.model_copy(update={"rendered_markdown": render_markdown(report)})


def render_markdown(report: BaselineReport) -> str:
    calculations = {calculation.calculation_id: calculation for calculation in report.calculations}
    claims = {claim.claim_id: claim for claim in report.claims}
    lines = ["# Baseline reconciliation report", ""]
    for section in report.sections:
        lines.extend([f"## {section.title}", ""])
        for claim_id in section.claim_ids:
            claim = claims[claim_id]
            text = claim.template_or_text
            reference = claim.calculation_value_ref
            if reference is not None:
                calculation = calculations[reference.calculation_id]
                text = text.replace("{value}", _quantity_label(calculation, reference))
            lines.extend([f"- {text} [{', '.join(ref.ref_id for ref in claim.evidence_refs)}]", ""])
    return "\n".join(lines)


class ReportVerifier:
    """Verify report structure, exact numeric references, citations and scope safety."""

    version = "v03.1"

    def verify(
        self,
        report: BaselineReport,
        *,
        available_evidence_refs: Iterable[EvidenceRef] = (),
    ) -> VerificationResult:
        issues: list[Issue] = []
        checks: list[dict[str, str | bool]] = []
        calculations = {
            calculation.calculation_id: calculation for calculation in report.calculations
        }
        available = {(ref.ref_kind, ref.ref_id) for ref in available_evidence_refs}

        ordered = tuple(section.section_id for section in report.sections)
        checks.append({"check": "section_order", "passed": ordered == SECTION_IDS})
        if ordered != SECTION_IDS:
            issues.append(
                _issue(
                    "INVALID_SCHEMA",
                    "report must contain the eight sections in contract order",
                )
            )

        for claim in report.claims:
            if not claim.evidence_refs:
                issues.append(
                    _issue("MISSING_ARTIFACT", "claim has no citation", claim_id=claim.claim_id)
                )
            if available and any(
                (ref.ref_kind, ref.ref_id) not in available
                for ref in claim.evidence_refs
            ):
                issues.append(
                    _issue(
                        "MISSING_ARTIFACT",
                        "claim cites unavailable evidence",
                        claim_id=claim.claim_id,
                    )
                )
            if _PROHIBITED.search(claim.template_or_text):
                issues.append(
                    _issue(
                        "PROHIBITED_VERDICT",
                        "claim contains a prohibited compliance or wrongdoing conclusion",
                        claim_id=claim.claim_id,
                    )
                )
            reference = claim.calculation_value_ref
            if claim.kind == "NUMERIC":
                if reference is None or reference.calculation_id not in calculations:
                    issues.append(
                        _issue(
                            "INTEGRITY_FAILED",
                            "numeric claim has no resolvable calculation reference",
                            claim_id=claim.claim_id,
                        )
                    )
                    continue
                calculation = calculations[reference.calculation_id]
                value = _value(calculation, reference)
                if value is None and reference.field not in {"portal_reported", "delta"}:
                    issues.append(
                        _issue(
                            "INTEGRITY_FAILED",
                            "numeric claim references a missing bucket value",
                            claim_id=claim.claim_id,
                        )
                    )
                if "{value}" not in claim.template_or_text:
                    issues.append(
                        _issue(
                            "INTEGRITY_FAILED",
                            "numeric claim must use deterministic value insertion",
                            claim_id=claim.claim_id,
                        )
                    )
                checks.append(
                    {
                        "check": f"numeric:{claim.claim_id}",
                        "passed": value is not None
                        or reference.field in {"portal_reported", "delta"},
                    }
                )
            elif reference is not None:
                issues.append(
                    _issue(
                        "INTEGRITY_FAILED",
                        "only numeric claims may carry calculation value references",
                        claim_id=claim.claim_id,
                    )
                )

        rendered = report.rendered_markdown
        checks.append(
            {
                "check": "rendered_numeric_placeholders",
                "passed": "{value}" not in rendered,
            }
        )
        if "{value}" in rendered:
            issues.append(
                _issue(
                    "INTEGRITY_FAILED",
                    "rendered report contains an unresolved numeric placeholder",
                )
            )

        verdict: VerificationVerdict
        if any(issue.severity == "BLOCKING" for issue in issues):
            verdict = "BLOCKED"
        elif (
            issues
            or any(claim.support_status == "UNSUPPORTED" for claim in report.claims)
            or any(
                calculation.coverage != "COMPLETE_WITHIN_SCOPE"
                for calculation in report.calculations
            )
        ):
            verdict = "QUALIFIED"
        else:
            verdict = "PASS"
        dependency_digest = hashlib.sha256(
            canonical_json_bytes(
                [report.revision.review_dependency_digest, report.rendered_markdown]
            )
        ).hexdigest()
        verification_id = f"verification:{dependency_digest[:24]}"
        return VerificationResult(
            verification_id=verification_id,
            report_revision_id=report.revision.report_revision_id,
            verdict=verdict,
            checks=checks,
            issues=issues,
            verifier_version=self.version,
            verified_dependency_digest=dependency_digest,
        )