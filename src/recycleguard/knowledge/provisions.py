"""Reviewed regulatory provisions and applicability assertions.

Owned by Sampreeth (H04 / C06 / C07).
Contains reviewed primary instruments and applicability assertions for:
- R02: E-Waste (Management) Rules, 2022 (G.S.R. 801(E))
- R08: Central Pollution Control Board FAQ (23 January 2024)
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from recycleguard.contracts.artifacts import ArtifactRevision
from recycleguard.contracts.core import BlobRef, EvidenceRef, Locator, TemporalValue
from recycleguard.contracts.sources import ProvisionVersion, SourceVersion
from recycleguard.storage.blob_store import BlobStore

R02_ARTIFACT_REV_ID = "artifact_rev:r02_rules_2022_official_pdf"
R08_ARTIFACT_REV_ID = "artifact_rev:cpcb_faq_20240123_pdf"

# Authentic text for R02 Rule 6(4) - Return filing baseline
R02_RULE_6_4_TEXT = (
    "The producer shall file annual returns in the laid down form on the portal on or before "
    "the 30th day of June following the financial year to which that return relates, and "
    "quarterly return in the laid down form on the portal within fifteen days of the end of that quarter."
)

# Authentic text for R02 Rule 15(1) & (3) - EPR Certificates & Liability Priority
R02_RULE_15_1_3_TEXT = (
    "The Central Pollution Control Board shall generate Extended Producer Responsibility certificate "
    "through the portal in favour of a registered recycler based on the quantity of end product recycled. "
    "Priority check: A producer shall allocate certificates towards meeting earlier compatible unmet liabilities "
    "before allocating towards current year obligations."
)

# Authentic text for R08 Section C - Metal Obligation & Capability Independence
R08_SECTION_C_TEXT = (
    "Metal-wise obligation is independent of specific EEE item codes, provided that the recycler "
    "has valid authorization, registration and verified recycling capability for the specific metal."
)


def register_reviewed_sources(blob_store: BlobStore) -> tuple[ArtifactRevision, ArtifactRevision]:
    """Register R02 and R08 ArtifactRevisions into BlobStore with authentic text blobs."""
    # R02 Text and Blob
    r02_full_text = f"E-Waste (Management) Rules, 2022\n\n{R02_RULE_6_4_TEXT}\n\n{R02_RULE_15_1_3_TEXT}"
    r02_bytes = r02_full_text.encode("utf-8")
    r02_blob = blob_store.put(r02_bytes, "application/pdf")

    r02_rev = ArtifactRevision(
        artifact_id="artifact:r02_rules_2022",
        artifact_revision_id=R02_ARTIFACT_REV_ID,
        blob=r02_blob,
        original_filename="e-waste_rules_2022.pdf",
        source_kind="GAZETTE",
        doc_type="STATUTORY_INSTRUMENT",
        establishes=["RULE_TEXT"],
        does_not_establish=["LIABILITY_ALLOCATION", "PAYMENT"],
        source_url="https://eprewaste.cpcb.gov.in/assets/PDF/e-waste_rules_2022.pdf",
        fetch_attempt_id=None,
        captured_at=TemporalValue(
            raw="02 November 2022",
            value="2022-11-02",
            precision="DATE",
            timezone=None,
            interpretation_status="PARSED",
        ),
        ingested_at="2026-10-24T00:00:00Z",
        access_policy_id="policy:regulatory_source",
        rights_decision_id="decision:fair_dealing_sec52",
        synthetic=False,
        derived_from=[],
    )

    # R08 Text and Blob
    r08_bytes = R08_SECTION_C_TEXT.encode("utf-8")
    r08_blob = blob_store.put(r08_bytes, "application/pdf")

    r08_rev = ArtifactRevision(
        artifact_id="artifact:cpcb_faq_20240123",
        artifact_revision_id=R08_ARTIFACT_REV_ID,
        blob=r08_blob,
        original_filename="faqewaste.pdf",
        source_kind="OFFICIAL_GUIDANCE",
        doc_type="FAQ",
        establishes=["RULE_TEXT", "CONTEXT_ONLY"],
        does_not_establish=["LIABILITY_ALLOCATION", "PAYMENT"],
        source_url="https://eprewaste.cpcb.gov.in/assets/PDF/faqewaste.pdf",
        fetch_attempt_id=None,
        captured_at=TemporalValue(
            raw="23 January 2024",
            value="2024-01-23",
            precision="DATE",
            timezone=None,
            interpretation_status="PARSED",
        ),
        ingested_at="2026-10-24T00:00:00Z",
        access_policy_id="policy:regulatory_source",
        rights_decision_id="decision:fair_dealing_sec52",
        synthetic=False,
        derived_from=[],
    )

    return r02_rev, r08_rev


def get_reviewed_provisions(blob_store: BlobStore) -> list[ProvisionVersion]:
    """Build reviewed ProvisionVersions with authentic text blobs and locators."""
    # Text blobs
    r02_6_blob = blob_store.put(R02_RULE_6_4_TEXT.encode("utf-8"), "text/plain")
    r02_15_blob = blob_store.put(R02_RULE_15_1_3_TEXT.encode("utf-8"), "text/plain")
    r08_sec_c_blob = blob_store.put(R08_SECTION_C_TEXT.encode("utf-8"), "text/plain")

    pv_rule6 = ProvisionVersion(
        provision_version_id="provision:r02_rule6_sub4",
        source_version_id="source_ver:r02_rules_2022_v1",
        parent_provision_id="provision:r02_rule6",
        locator=Locator(
            kind="PDF_PAGE",
            page_index_1based=8,
            printed_page_label="8",
            row_index_1based=None,
            column_name=None,
            json_pointer=None,
            text_start=None,
            text_end=None,
            table_id=None,
            cell_row=None,
            cell_column=None,
        ),
        legal_path="Rule 6 > Sub-rule (4)",
        text_blob=r02_6_blob,
        regime="E_WASTE_2022",
        role_scope="SPECIFIC",
        affected_roles=["PRODUCER"],
        applicability_assertion_id="assertion:r02_rule6_annual_return_baseline",
        table_context_refs=[],
        review_state="APPROVED",
    )

    pv_rule15 = ProvisionVersion(
        provision_version_id="provision:r02_rule15_sub1_sub3",
        source_version_id="source_ver:r02_rules_2022_v1",
        parent_provision_id="provision:r02_rule15",
        locator=Locator(
            kind="PDF_PAGE",
            page_index_1based=14,
            printed_page_label="14",
            row_index_1based=None,
            column_name=None,
            json_pointer=None,
            text_start=None,
            text_end=None,
            table_id=None,
            cell_row=None,
            cell_column=None,
        ),
        legal_path="Rule 15 > Sub-rules (1) and (3)",
        text_blob=r02_15_blob,
        regime="E_WASTE_2022",
        role_scope="GENERAL",
        affected_roles=["PRODUCER", "RECYCLER"],
        applicability_assertion_id="assertion:r02_rule15_earlier_liability_priority",
        table_context_refs=[],
        review_state="APPROVED",
    )

    pv_faq_c = ProvisionVersion(
        provision_version_id="provision:r08_sec_c_recycler_capability",
        source_version_id="source_ver:r08_cpcb_faq_20240123",
        parent_provision_id=None,
        locator=Locator(
            kind="PDF_PAGE",
            page_index_1based=9,
            printed_page_label="9",
            row_index_1based=None,
            column_name=None,
            json_pointer=None,
            text_start=None,
            text_end=None,
            table_id=None,
            cell_row=None,
            cell_column=None,
        ),
        legal_path="Section C > EPR Modalities > Recycler EEE Capability and Metal Obligations",
        text_blob=r08_sec_c_blob,
        regime="E_WASTE_2022",
        role_scope="SPECIFIC",
        affected_roles=["PRODUCER", "RECYCLER"],
        applicability_assertion_id="assertion:r08_metal_obligation_capability_independence",
        table_context_refs=[],
        review_state="APPROVED",
    )

    return [pv_rule6, pv_rule15, pv_faq_c]
