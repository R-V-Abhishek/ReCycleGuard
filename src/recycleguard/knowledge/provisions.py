"""Original source capture and draft page-context provisions; no invented approvals."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from recycleguard.contracts.artifacts import ArtifactRevision
from recycleguard.contracts.core import Locator, TemporalValue
from recycleguard.contracts.sources import ProvisionVersion
from recycleguard.extraction.pdf_extractor import extract_pdf_pages
from recycleguard.storage.blob_store import BlobStore

R02_ARTIFACT_REV_ID = "artifact_rev:r02_rules_2022_official_pdf"
R08_ARTIFACT_REV_ID = "artifact_rev:cpcb_faq_20240123_pdf"
SOURCE_DIGESTS = {
    R02_ARTIFACT_REV_ID: "d03f8744bc79d67a94b06e1020537e93d15572b0cf1d575cb32b76c89f30a5fb",
    R08_ARTIFACT_REV_ID: "30f56238fb7db53dd82f69d198be9a92e31d98ea5b21d2724eb7397641a80d16",
}


def register_reviewed_sources(
    blob_store: BlobStore,
    *,
    r02_path: Path,
    r08_path: Path,
) -> tuple[ArtifactRevision, ArtifactRevision]:
    """Capture supplied PDF originals. The historical name does not confer review."""
    result = []
    for path, artifact_id, revision_id, source_kind, doc_type, url in [
        (
            r02_path,
            "artifact:r02_rules_2022",
            R02_ARTIFACT_REV_ID,
            "GAZETTE",
            "STATUTORY_INSTRUMENT",
            "https://eprewaste.cpcb.gov.in/assets/PDF/e-waste_rules_2022.pdf",
        ),
        (
            r08_path,
            "artifact:cpcb_faq_20240123",
            R08_ARTIFACT_REV_ID,
            "OFFICIAL_GUIDANCE",
            "FAQ",
            "https://eprewaste.cpcb.gov.in/assets/PDF/faqewaste.pdf",
        ),
    ]:
        data = path.read_bytes()
        if not data.startswith(b"%PDF-"):
            raise ValueError(f"source must be an original PDF: {path.name}")
        if hashlib.sha256(data).hexdigest() != SOURCE_DIGESTS[revision_id]:
            raise ValueError(
                "source digest differs from the captured original; create a new reviewed revision"
            )
        result.append(
            ArtifactRevision(
                artifact_id=artifact_id,
                artifact_revision_id=revision_id,
                blob=blob_store.put(data, "application/pdf"),
                original_filename=path.name,
                source_kind=source_kind,
                doc_type=doc_type,
                establishes=["RULE_TEXT"],
                does_not_establish=["LIABILITY_ALLOCATION", "PAYMENT"],
                source_url=url,
                fetch_attempt_id=None,
                captured_at=TemporalValue(
                    raw=None,
                    value=None,
                    precision="UNKNOWN",
                    timezone=None,
                    interpretation_status="UNKNOWN",
                ),
                ingested_at=datetime.now(UTC).isoformat(),
                access_policy_id="policy:local_source_review",
                rights_decision_id="decision:review_required",
                synthetic=False,
                derived_from=[],
            )
        )
    return tuple(result)


def get_reviewed_provisions(
    blob_store: BlobStore,
    *,
    r02_revision: ArtifactRevision,
    r08_revision: ArtifactRevision,
) -> list[ProvisionVersion]:
    """Extract actual page context; all proposals remain DRAFT until trusted review."""
    revisions = {"r02": r02_revision, "r08": r08_revision}
    pages = {}
    for name, revision in revisions.items():
        observations, coverage, _, issues = extract_pdf_pages(
            blob_store.get(revision.blob), revision.artifact_revision_id, f"ext:{name}_provisions"
        )
        if issues or len(coverage) != (38 if name == "r02" else 13):
            raise ValueError(f"source page coverage is incomplete: {name}")
        pages[name] = {
            obs.locator.page_index_1based: obs.parsed_fields["text"] for obs in observations
        }
    definitions = [
        (
            "r02",
            24,
            "provision:r02_rule6_sub4",
            "Rule 6(4), full physical-page context",
            "SPECIFIC",
            ["PRODUCER"],
            "assertion:r02_rule6_filing_baseline",
        ),
        (
            "r02",
            27,
            "provision:r02_rule15_sub1_sub3",
            "Rule 15(1)-(3), full physical-page context",
            "GENERAL",
            ["PRODUCER", "RECYCLER"],
            "assertion:r02_rule15_priority",
        ),
        (
            "r08",
            9,
            "provision:r08_sec_c_recycler_capability",
            "Section C, EEE capability, full page context",
            "SPECIFIC",
            ["PRODUCER", "RECYCLER"],
            "assertion:r08_capability",
        ),
    ]
    return [
        ProvisionVersion(
            provision_version_id=pid,
            source_version_id=f"source_ver:{name}_original",
            parent_provision_id=None,
            locator=Locator(
                kind="PDF_PAGE",
                page_index_1based=page,
                printed_page_label=None,
                row_index_1based=None,
                column_name=None,
                json_pointer=None,
                text_start=None,
                text_end=None,
                table_id=None,
                cell_row=None,
                cell_column=None,
            ),
            legal_path=legal_path,
            text_blob=blob_store.put(pages[name][page].encode(), "text/plain"),
            regime="E_WASTE_2022",
            role_scope=role_scope,
            affected_roles=roles,
            applicability_assertion_id=assertion,
            table_context_refs=[],
            review_state="DRAFT",
        )
        for name, page, pid, legal_path, role_scope, roles, assertion in definitions
    ]
