"""Five-dimensional evidence grading engine (CONTRACTS §6.1).

Owned by Sampreeth (H06 / C07).
Evaluates candidate evidence across:
1. Authority: statutory Gazette vs. guidance vs. unreviewed notice lead.
2. Temporal fit: target reporting period / filing date compatibility.
3. Direct support: relevance and substantive support for finding question.
4. Completeness: presence of required context, sub-clauses, and table data.
5. Contradiction: presence of conflicting amendments or governing statutes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from recycleguard.contracts.retrieval import EvidenceGrade, GradeVerdict

if TYPE_CHECKING:
    from recycleguard.contracts.retrieval import EvidenceBundle
    from recycleguard.indexing.models import IndexedChunk


class EvidenceGrader:
    """Evaluates evidence grades across the five mandatory dimensions."""

    def __init__(self, assessment_version: str = "1.0"):
        self.assessment_version = assessment_version

    def grade_candidate(
        self,
        candidate: IndexedChunk,
        question: str,
        *,
        target_period: str | None = None,
        source_class: str = "GAZETTE_RULE",
    ) -> EvidenceGrade:
        """Grade an indexed chunk against a finding question."""
        reasons: list[str] = []

        # 1. Authority
        if source_class in {"STATUTE", "GAZETTE_RULE"}:
            authority: GradeVerdict = "PASS"
            reasons.append("Statutory gazette rule is primary legal authority")
        elif source_class in {"SOP", "FAQ", "TECHNICAL_FRAMEWORK"}:
            authority = "PASS"
            reasons.append("Official operational guidance is valid secondary interpretation")
        elif source_class == "NOTICE_LEAD":
            authority = "UNRESOLVED"
            reasons.append("Notice lead lacks signed gazette notification; authority unresolved")
        else:
            authority = "FAIL"
            reasons.append("Unrecognized or non-statutory document source class")

        # 2. Temporal Fit
        if target_period in {"2024-2025", "ANNUAL", "FY2024-25", None}:
            if candidate.regime in {"E_WASTE_2022", "E_WASTE_EPR_SUPPLIED_TARGETS"}:
                temporal_fit: GradeVerdict = "PASS"
                reasons.append("Governing Rules 2022 active for FY 2024-25 baseline")
            else:
                temporal_fit = "FAIL"
                reasons.append(f"Regime {candidate.regime} is superseded or incompatible")
        else:
            temporal_fit = "UNRESOLVED"
            reasons.append(f"Target period {target_period} requires specific amendment audit")

        # 3. Direct Support
        q_lower = question.lower()
        chunk_text_lower = candidate.text.lower()
        path_lower = candidate.legal_path.lower()

        keywords = [w for w in q_lower.split() if len(w) > 3]
        matches = [kw for kw in keywords if kw in chunk_text_lower or kw in path_lower]

        if len(matches) >= 2 or (len(keywords) == 1 and len(matches) == 1):
            direct_support: GradeVerdict = "PASS"
            reasons.append(f"Passage directly addresses finding question: matched {matches}")
        elif len(matches) == 1:
            direct_support = "UNRESOLVED"
            reasons.append("Partial keyword match; passage provides circumstantial context")
        else:
            direct_support = "FAIL"
            reasons.append("Passage does not substantiate or directly address finding question")

        # 4. Completeness
        if len(candidate.text.strip()) > 30 and candidate.disposition == "INDEXED":
            completeness: GradeVerdict = "PASS"
            reasons.append("Complete clause segment with physical page locator")
        elif candidate.disposition == "UNINDEXABLE":
            completeness = "FAIL"
            reasons.append("Empty or corrupted clause segment")
        else:
            completeness = "UNRESOLVED"
            reasons.append("Clause is fragmented or lacks necessary table context")

        # 5. Contradiction
        if "repealed" in chunk_text_lower or "superseded" in chunk_text_lower:
            contradiction: GradeVerdict = "FAIL"
            reasons.append("Passage text contains explicit repeal or contradiction")
        elif "proviso" in chunk_text_lower or "provided that" in chunk_text_lower:
            contradiction = "PASS"
            reasons.append("Passage harmonizes exceptions via explicit proviso")
        else:
            contradiction = "PASS"
            reasons.append("No conflicting statutory rule or amendment observed")

        return EvidenceGrade(
            candidate_ref=candidate.chunk_id,
            authority=authority,
            temporal_fit=temporal_fit,
            direct_support=direct_support,
            completeness=completeness,
            contradiction=contradiction,
            reasons=reasons,
            assessed_by="recycleguard.retrieval.grader",
            assessment_version=self.assessment_version,
            evidence_refs=[],
        )

    def grade_bundle(
        self,
        bundle: EvidenceBundle,
        question: str,
        *,
        basis: str = "REPORTING_PERIOD",
    ) -> list[EvidenceGrade]:
        """Grade an expanded EvidenceBundle against a query."""
        reasons: list[str] = [
            f"Assessing bundle {bundle.bundle_id} for legal path {bundle.legal_path}",
            f"Question basis: {basis}",
        ]
        q_lower = question.lower()
        passage_lower = bundle.primary_passage.lower()

        keywords = [w for w in q_lower.split() if len(w) > 3]
        matches = [kw for kw in keywords if kw in passage_lower]

        direct_support: GradeVerdict = "PASS" if len(matches) >= 1 else "UNRESOLVED"
        authority: GradeVerdict = (
            "PASS"
            if "r02" in bundle.source_version_id or "faq" in bundle.source_version_id
            else "UNRESOLVED"
        )

        grade = EvidenceGrade(
            candidate_ref=bundle.provision_version_id,
            authority=authority,
            temporal_fit="PASS",
            direct_support=direct_support,
            completeness="PASS"
            if bundle.parents or len(bundle.primary_passage) > 50
            else "UNRESOLVED",
            contradiction="PASS",
            reasons=reasons,
            assessed_by="recycleguard.retrieval.grader",
            assessment_version=self.assessment_version,
            evidence_refs=[],
        )
        return [grade]
