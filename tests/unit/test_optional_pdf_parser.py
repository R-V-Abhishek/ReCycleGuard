"""Optional PDF parser input and failure boundaries use real valid blank PDFs."""

import pytest

from benchmarks.generator.pdf_style import write_pdf
from recycleguard.extraction import extract_pdf_pages
from recycleguard.extraction.vlm_parser import DeterministicVLMPdfParser, VLMPageExtraction


class RecordingParser:
    def __init__(self, *, failure=None, page_number=1):
        self.calls = []
        self.failure = failure
        self.page_number = page_number

    def parse_page(self, page_bytes_or_text, page_number, *, metadata=None):
        self.calls.append((page_bytes_or_text, page_number, metadata))
        if self.failure is not None:
            raise self.failure
        return VLMPageExtraction(self.page_number, "Extracted page evidence")


def _blank_pdf(tmp_path):
    path = tmp_path / "blank.pdf"
    write_pdf(path, "", fonts={})
    return path.read_bytes()


def test_optional_parser_receives_original_pdf_and_exact_page(tmp_path):
    original = _blank_pdf(tmp_path)
    parser = RecordingParser()
    observations, coverage, text, issues = extract_pdf_pages(
        original, "art:test", "ext:test", vlm_parser=parser
    )
    assert parser.calls == [
        (original, 1, {"input_format": "application/pdf", "page_index_1based": 1})
    ]
    assert observations[0].extraction_method == "OCR"
    assert observations[0].validation_state == "REVIEW_REQUIRED"
    assert observations[0].field_quality["quality"] == "VLM_ASSISTED_UNREVIEWED"
    assert coverage[0].disposition == "PARSED"
    assert "Extracted page evidence" in text
    assert not issues


@pytest.mark.parametrize("failure", [ValueError("unsupported PDF"), TimeoutError("timeout")])
def test_optional_parser_failure_is_visible_and_never_success(tmp_path, failure):
    parser = RecordingParser(failure=failure)
    observations, coverage, text, issues = extract_pdf_pages(
        _blank_pdf(tmp_path), "art:test", "ext:test", vlm_parser=parser
    )
    assert observations == [] and text == ""
    assert coverage[0].disposition == "QUARANTINED"
    assert {i.code for i in issues} == {"EXTRACTION_FAILED", "INCOMPLETE_COVERAGE"}


def test_optional_parser_wrong_page_is_quarantined(tmp_path):
    observations, coverage, _, issues = extract_pdf_pages(
        _blank_pdf(tmp_path), "art:test", "ext:test", vlm_parser=RecordingParser(page_number=2)
    )
    assert observations == []
    assert coverage[0].disposition == "QUARANTINED"
    assert {i.code for i in issues} == {"EXTRACTION_FAILED", "INCOMPLETE_COVERAGE"}


def test_text_only_test_parser_cannot_interpret_pdf_binary_as_evidence(tmp_path):
    observations, coverage, _, issues = extract_pdf_pages(
        _blank_pdf(tmp_path), "art:test", "ext:test", vlm_parser=DeterministicVLMPdfParser()
    )
    assert observations == []
    assert coverage[0].disposition == "QUARANTINED"
    assert {i.code for i in issues} == {"EXTRACTION_FAILED", "INCOMPLETE_COVERAGE"}
