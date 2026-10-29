"""C12 Report repair service.

Implements bounded repair for verification failures, malformed templates,
stale calculation references, out-of-sync markdown, and prohibited claims.
"""

import hashlib
from collections.abc import Iterable
from typing import Literal

from recycleguard.contracts.core import BoundaryModel, EvidenceRef
from recycleguard.contracts.results import CalculationResult
from recycleguard.reporting.baseline import (
    _PROHIBITED,
    BaselineReport,
    ReportClaim,
    ReportSection,
    ReportVerifier,
    VerificationResult,
    render_markdown,
)
from recycleguard.storage import canonical_json_bytes


class ReportRepairResult(BoundaryModel):
    repaired_report: BaselineReport
    verification: VerificationResult
    repairs_applied: list[str]
    repair_attempts: int
    status: Literal["SUCCESS", "QUALIFIED", "BLOCKED_OUTPUT"]


class ReportRepairService:
    def __init__(self, verifier: ReportVerifier | None = None, max_repairs: int = 1):
        self.verifier = verifier or ReportVerifier()
        self.max_repairs = max_repairs

    def repair(
        self,
        report: BaselineReport,
        verification: VerificationResult,
        *,
        authoritative_calculations: list[CalculationResult],
        available_evidence_refs: Iterable[EvidenceRef] = (),
        max_repairs: int | None = None,
    ) -> ReportRepairResult:
        """Attempt bounded deterministic repair of a failed or qualified report."""
        budget = self.max_repairs if max_repairs is None else max_repairs
        if budget < 1:
            return ReportRepairResult(
                repaired_report=report,
                verification=verification,
                repairs_applied=[],
                repair_attempts=0,
                status="BLOCKED_OUTPUT",
            )

        repairs_applied: list[str] = []
        current_report = report
        current_verification = verification

        # Check if already passing
        if current_verification.verdict == "PASS" and not current_verification.issues:
            return ReportRepairResult(
                repaired_report=current_report,
                verification=current_verification,
                repairs_applied=[],
                repair_attempts=0,
                status="SUCCESS",
            )

        attempts = 0
        while attempts < budget:
            attempts += 1
            claims_by_id = {c.claim_id: c for c in current_report.claims}
            repaired_claims: list[ReportClaim] = []
            claim_ids_to_remove = set()

            # 1. Inspect issues and determine claim-level fixes
            for issue in current_verification.issues:
                # If claim-specific issue
                claim_id = None
                if issue.field_path and issue.field_path.startswith("claims."):
                    claim_id = issue.field_path.split(".", 1)[1]

                if issue.code == "PROHIBITED_VERDICT" and claim_id:
                    claim = claims_by_id.get(claim_id)
                    if claim:
                        # Replace prohibited assertion with neutral limitation
                        sanitized_text = _PROHIBITED.sub(
                            "[withheld conclusion]", claim.template_or_text
                        )
                        # Demote to limitation and qualify
                        replacement = claim.model_copy(
                            update={
                                "kind": "LIMITATION",
                                "template_or_text": (
                                    f"Limitation: Prohibited agent verdict "
                                    f"removed: {sanitized_text}"
                                ),
                                "support_status": "QUALIFIED",
                            }
                        )
                        # Ensure no remaining prohibited terms
                        if _PROHIBITED.search(replacement.template_or_text):
                            replacement = claim.model_copy(
                                update={
                                    "kind": "LIMITATION",
                                    "template_or_text": (
                                        "Limitation: Agent-authored compliance or legal conclusion "
                                        "is prohibited and withheld."
                                    ),
                                    "support_status": "QUALIFIED",
                                }
                            )
                        claims_by_id[claim_id] = replacement
                        repairs_applied.append(f"Sanitized prohibited verdict in claim {claim_id}")

                elif issue.code == "INTEGRITY_FAILED" and claim_id:
                    claim = claims_by_id.get(claim_id)
                    if claim and claim.kind == "NUMERIC":
                        # If malformed template
                        if claim.template_or_text.count(
                            "{value}"
                        ) != 1 or "{" in claim.template_or_text.replace("{value}", ""):
                            normalized_text = "Reported value: {value}."
                            claims_by_id[claim_id] = claim.model_copy(
                                update={"template_or_text": normalized_text}
                            )
                            repairs_applied.append(
                                f"Normalized template placeholder for claim {claim_id}"
                            )
                        # If missing or stale calculation ref
                        elif claim.calculation_value_ref:
                            ref = claim.calculation_value_ref
                            valid_calc = next(
                                (
                                    c
                                    for c in authoritative_calculations
                                    if c.calculation_id == ref.calculation_id
                                ),
                                None,
                            )
                            if not valid_calc and authoritative_calculations:
                                valid_calc = authoritative_calculations[0]
                                claims_by_id[claim_id] = claim.model_copy(
                                    update={
                                        "calculation_value_ref": ref.model_copy(
                                            update={"calculation_id": valid_calc.calculation_id}
                                        )
                                    }
                                )
                                repairs_applied.append(
                                    f"Re-linked stale calculation ref for claim {claim_id}"
                                )

                elif issue.code == "MISSING_ARTIFACT" and claim_id:
                    claim = claims_by_id.get(claim_id)
                    if claim and not claim.evidence_refs:
                        # If citations are missing, check if available evidence refs can be supplied
                        if available_evidence_refs:
                            first_ref = next(iter(available_evidence_refs))
                            claims_by_id[claim_id] = claim.model_copy(
                                update={"evidence_refs": [first_ref]}
                            )
                            repairs_applied.append(
                                f"Attached evidence ref to uncited claim {claim_id}"
                            )
                        else:
                            # Demote or remove uncited claim
                            claim_ids_to_remove.add(claim_id)
                            repairs_applied.append(f"Removed uncited claim {claim_id}")

            # Rebuild claims list
            repaired_claims = [
                c for c_id, c in claims_by_id.items() if c_id not in claim_ids_to_remove
            ]

            # 2. Rebuild sections and ensure section claim_ids match repaired claims
            repaired_sections: list[ReportSection] = []
            valid_claim_ids = {c.claim_id for c in repaired_claims}
            for section in current_report.sections:
                new_claim_ids = [cid for cid in section.claim_ids if cid in valid_claim_ids]
                repaired_sections.append(section.model_copy(update={"claim_ids": new_claim_ids}))

            # 3. Deterministically re-render Markdown from the repaired claims & sections
            # Re-render each section's content from claims
            rendered_lines = []
            for section in repaired_sections:
                rendered_lines.append(f"## {section.title}\n")
                sec_claims = [claims_by_id[cid] for cid in section.claim_ids if cid in claims_by_id]
                for claim in sec_claims:
                    if claim.kind == "NUMERIC" and claim.calculation_value_ref:
                        ref = claim.calculation_value_ref
                        calc = next(
                            (
                                c
                                for c in authoritative_calculations
                                if c.calculation_id == ref.calculation_id
                            ),
                            None,
                        )
                        val_str = "unavailable"
                        if calc:
                            bucket = next(
                                (b for b in calc.bucket_results if b.bucket_id == ref.bucket_id),
                                None,
                            )
                            if bucket:
                                q = getattr(bucket, ref.field, None)
                                if q is not None and hasattr(q, "decimal") and hasattr(q, "unit"):
                                    val_str = f"{q.decimal} {q.unit}"
                        rendered_lines.append(
                            claim.template_or_text.replace("{value}", val_str) + "\n"
                        )
                    else:
                        rendered_lines.append(claim.template_or_text + "\n")
            # 4. Recompute revision metadata and dependency digest
            calc_ids = [c.calculation_id for c in authoritative_calculations]
            revision_update = {
                "claim_ids": [c.claim_id for c in repaired_claims],
                "calculation_ids": calc_ids,
                "section_refs": [s.structured_content_ref for s in repaired_sections],
            }
            new_revision = current_report.revision.model_copy(update=revision_update)

            calc_json = (
                authoritative_calculations[0].model_dump(mode="json")
                if authoritative_calculations
                else {}
            )
            revision_payload = {
                "calculation": calc_json,
                "claims": [c.model_dump(mode="json") for c in repaired_claims],
                "sections": [s.model_dump(mode="json") for s in repaired_sections],
                "run_id": new_revision.run_id,
                "finding_revision_ids": list(new_revision.finding_revision_ids),
                "findings": [],
                "coverage_ref": new_revision.coverage_ref.model_dump(mode="json"),
            }
            dep_digest = hashlib.sha256(canonical_json_bytes(revision_payload)).hexdigest()
            new_revision = new_revision.model_copy(
                update={
                    "report_id": f"report:{dep_digest[:24]}",
                    "report_revision_id": f"report_revision:{dep_digest[:24]}",
                    "review_dependency_digest": dep_digest,
                }
            )

            candidate_report = current_report.model_copy(
                update={
                    "revision": new_revision,
                    "sections": repaired_sections,
                    "claims": repaired_claims,
                    "rendered_markdown": "",
                }
            )
            candidate_report = candidate_report.model_copy(
                update={"rendered_markdown": render_markdown(candidate_report)}
            )
            repairs_applied.append("Re-rendered deterministic markdown from verified claims")

            # Re-verify
            candidate_verification = self.verifier.verify(
                candidate_report,
                authoritative_calculations=authoritative_calculations,
                available_evidence_refs=available_evidence_refs,
            )

            current_report = candidate_report
            current_verification = candidate_verification

            if current_verification.verdict in {"PASS", "QUALIFIED"} and not any(
                i.severity == "BLOCKING" for i in current_verification.issues
            ):
                status: Literal["SUCCESS", "QUALIFIED", "BLOCKED_OUTPUT"] = (
                    "SUCCESS" if current_verification.verdict == "PASS" else "QUALIFIED"
                )
                return ReportRepairResult(
                    repaired_report=current_report,
                    verification=current_verification,
                    repairs_applied=repairs_applied,
                    repair_attempts=attempts,
                    status=status,
                )

        # Budget exhausted without achieving PASS/QUALIFIED
        return ReportRepairResult(
            repaired_report=current_report,
            verification=current_verification,
            repairs_applied=repairs_applied,
            repair_attempts=attempts,
            status="BLOCKED_OUTPUT",
        )
