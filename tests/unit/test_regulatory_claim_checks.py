"""Visible original claims, independent of fault IDs or hidden benchmark truth."""

from pathlib import Path

from recycleguard.contracts.core import Locator, TemporalValue
from recycleguard.contracts.extraction import Observation
from recycleguard.extraction.pdf_extractor import extract_pdf_pages
from recycleguard.retrieval.claim_checks import inspect_regulatory_claims

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/visible"


def observation(text):
    unknown = TemporalValue(
        raw=None, value=None, precision="UNKNOWN", timezone=None, interpretation_status="UNKNOWN"
    )
    return Observation(
        observation_id="obs:literal",
        extraction_id="extraction:literal",
        artifact_revision_id="artifactrev:literal",
        locator=Locator(
            kind="PDF_PAGE",
            page_index_1based=1,
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
        observation_type="PAGE_TEXT",
        raw_fields={"text": text},
        parsed_fields={},
        validation_state="VALID",
        extraction_method="PDF_TEXT",
        field_quality={},
        event_time=unknown,
        source_capture_time=unknown,
        ingestion_time="2026-10-29T00:00:00Z",
    )


def test_dates_and_ordinary_gold_arithmetic_are_not_regulatory_faults():
    assert (
        inspect_regulatory_claims(
            [observation("Gold AU target100kg; supported55; captured2024-04-01; event2025-01-30")],
            "2024-2025",
        )
        == []
    )
    assert (
        inspect_regulatory_claims(
            [observation("FY2024-25 ordinary supplied gold target")], "2024-2025"
        )
        == []
    )


def test_literal_scope_and_exact_original_references():
    findings = inspect_regulatory_claims(
        [
            observation(
                "E-Waste Rules 2016 FY2022-23. Unsigned notice extends filing extension. "
                "Gold refurbishment offset requested."
            )
        ],
        "2024-2025",
    )
    assert {f.kind for f in findings} == {
        "OLD_RULE_PERIOD",
        "UNVERIFIED_EXTENSION",
        "UNSUPPORTED_REFURBISHMENT_OFFSET",
    }
    assert all(f.evidence_refs[0].locator.page_index_1based == 1 for f in findings)
    assert (
        next(f for f in findings if f.kind == "UNSUPPORTED_REFURBISHMENT_OFFSET").scope
        == "refurbishment offset only"
    )


def test_actual_visible_s06_pdf_claims():
    findings = []
    # These are the submitted visible originals, parsed by the actual PDF adapter.
    # Neither case names nor benchmark labels enter the detection decisions.
    for path in sorted(FIXTURES.glob("case_*/documents/*.pdf")):
        if path.name.startswith(("memo_", "notice_")):
            observations, _, _, _ = extract_pdf_pages(
                path.read_bytes(), f"artifactrev:{path.stem}", f"extraction:{path.stem}"
            )
            findings.extend(inspect_regulatory_claims(observations, "2024-2025"))
    kinds = {f.kind for f in findings}
    assert "OLD_RULE_PERIOD" in kinds
    assert "UNVERIFIED_EXTENSION" in kinds
    assert "UNSUPPORTED_REFURBISHMENT_OFFSET" in kinds
    assert all(f.evidence_refs and f.evidence_refs[0].ref_kind == "OBSERVATION" for f in findings)
