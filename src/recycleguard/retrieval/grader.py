"""Evidence grading never upgrades lexical relevance into legal support."""

from recycleguard.contracts.retrieval import EvidenceGrade


class EvidenceGrader:
    def __init__(self, assessment_version="cp3-conservative-1"):
        self.assessment_version = assessment_version

    def grade_candidate(
        self,
        candidate,
        question,
        *,
        target_period=None,
        source_class=None,
        source_reviewed=False,
        complete=False,
        temporal_fit="UNRESOLVED",
        evidence_refs=None,
    ):
        authority = "UNRESOLVED"
        if source_reviewed and source_class in {"STATUTE", "GAZETTE_RULE", "ORDER"}:
            authority = "PASS"
        if source_class == "NOTICE_LEAD":
            authority = "FAIL"
        return EvidenceGrade(
            candidate_ref=candidate.chunk_id,
            authority=authority,
            temporal_fit=temporal_fit,
            direct_support="UNRESOLVED",
            completeness="PASS" if complete else "UNRESOLVED",
            contradiction="UNRESOLVED",
            reasons=[
                "Lexical matching identifies context, not direct support.",
                "Temporal applicability requires reviewed interval evidence.",
                "Absence of a detected contradiction does not prove consistency.",
            ],
            assessed_by="recycleguard.retrieval.grader",
            assessment_version=self.assessment_version,
            evidence_refs=evidence_refs or [],
        )

    def grade_bundle(self, bundle, question, *, basis="REPORTING_PERIOD"):
        return [
            EvidenceGrade(
                candidate_ref=bundle.provision_version_id,
                authority=bundle.provenance.get("authority", "UNRESOLVED"),
                temporal_fit="UNRESOLVED",
                direct_support="UNRESOLVED",
                completeness="PASS" if bundle.provenance.get("complete_source") else "UNRESOLVED",
                contradiction="UNRESOLVED",
                reasons=["Passage is context pending claim-specific assessment."],
                assessed_by="recycleguard.retrieval.grader",
                assessment_version=self.assessment_version,
            )
        ]
