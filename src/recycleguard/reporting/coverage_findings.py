"""Page loss as a finding: a document page that was not read is reported, never read as empty.

PDF extraction records each page it could not read: a page with no text layer, which is
quarantined; a printed page that is absent from the file; or a page count that differs from what
the footers state. Each is an ``INCOMPLETE_COVERAGE`` issue on a page-level field path.

Such a dossier is still investigated. The lost page is reported once as F15, which withholds any
claim that depends on it. CSV row problems are not page loss and are not reported here.
"""

import hashlib
from collections.abc import Iterable

from recycleguard.contracts.core import EvidenceRef
from recycleguard.contracts.extraction import CoverageItem, ExtractionResult
from recycleguard.contracts.results import FindingRecord, Recommendation
from recycleguard.storage import canonical_json_bytes

COVERAGE_SOURCE = "COVERAGE_CHECK"
FAMILY = "F15_EXTRACTION_PAGE_LOSS"


def _page_signal(issue) -> bool:
    path = issue.field_path or ""
    return issue.code == "INCOMPLETE_COVERAGE" and (
        path.startswith("page:") or path == "document:page_count"
    )


def coverage_findings(
    case_version_id: str,
    extractions: Iterable[tuple[ExtractionResult, list[CoverageItem]]],
) -> list[FindingRecord]:
    """At most one F15 finding, citing each document that lost a page."""
    refs, signals = [], []
    for extraction, coverage in sorted(extractions, key=lambda pair: pair[0].artifact_revision_id):
        paths = sorted({i.field_path for i in extraction.issues if _page_signal(i)})
        if not paths:
            continue
        quarantined = [
            item
            for item in coverage
            if item.disposition == "QUARANTINED" and item.locator.kind == "PDF_PAGE"
        ]
        refs.append(
            EvidenceRef(
                ref_kind="ARTIFACT",
                ref_id=extraction.artifact_revision_id,
                artifact_revision_id=extraction.artifact_revision_id,
                # A missing page has no locator of its own; a quarantined one does.
                locator=quarantined[0].locator if quarantined else None,
            )
        )
        signals.append({"artifact": extraction.artifact_revision_id, "pages": paths})
    if not refs:
        return []
    token = hashlib.sha256(canonical_json_bytes([case_version_id, FAMILY, signals])).hexdigest()
    action = (
        "Request a legible, complete copy of the affected document; an unread page does not "
        "establish zero activity or a missing event."
    )
    return [
        FindingRecord(
            finding_id=f"finding:coverage_{token[:24]}",
            finding_revision_id=f"finding_revision:coverage_{token[:24]}",
            case_version_id=case_version_id,
            bucket_ids=[],
            issue_type=FAMILY,
            advisory_status="REQUIRES_EXPERT_REVIEW",
            priority="HIGH",
            priority_basis="A document page could not be read or is missing from the file.",
            portal_reported_value_ref=None,
            ledger_supported_value_ref=None,
            delta_value_ref=None,
            snapshot_comparison_ref=None,
            fact_refs=refs,
            calculation_refs=[],
            provision_refs=[],
            evidence_assessments=[{"source": COVERAGE_SOURCE, "signals": signals}],
            hypotheses=[],
            abstention_reason="MISSING_EVIDENCE",
            withheld_claim_scopes=["lost_document_page"],
            next_action=Recommendation(
                kind="REQUEST_EVIDENCE", description=action, evidence_refs=refs
            ),
            action_owner_ref=None,
            scope_limits=[
                "Pages that could not be read were not used; no conclusion is drawn from them."
            ],
            supersedes_finding_revision_id=None,
        )
    ]


__all__ = ["COVERAGE_SOURCE", "coverage_findings"]
