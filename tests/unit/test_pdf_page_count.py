"""A PDF whose "Page X of N" footers promise more pages than it holds is flagged by intake."""

from pathlib import Path

import pytest

from benchmarks.generator.s05_cases import build_worlds
from benchmarks.generator.s06_cases import build_s06_cases
from recycleguard.extraction import extract_pdf_pages
from recycleguard.extraction.pdf_extractor import _missing_printed_pages

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/visible"
CASES = {c.world.template_key: c for c in build_s06_cases()}


def _memo(tag: str) -> bytes:
    return next((FIXTURES / f"case_{tag}" / "documents").glob("memo_*.pdf")).read_bytes()


def _coverage_issues(pdf: bytes):
    _, coverage, _, issues = extract_pdf_pages(pdf, "art:check", "ext:check")
    return coverage, [i for i in issues if i.code == "INCOMPLETE_COVERAGE"]


def test_truncated_memo_is_flagged_on_the_absent_printed_page():
    coverage, issues = _coverage_issues(_memo(CASES["truncated"].world.case_tag))
    stated = len(coverage) + 1  # the recipe drops the last page
    assert all(c.disposition == "PARSED" for c in coverage)
    (issue,) = issues
    assert issue.field_path == f"page:{stated}"
    assert issue.severity == "WARNING"
    assert f"state {stated} pages" in issue.message


@pytest.mark.parametrize("key", ["textless", "textless_injection"])
def test_textless_page_is_reported_once_not_again_as_absent(key):
    coverage, issues = _coverage_issues(_memo(CASES[key].world.case_tag))
    (quarantined,) = [c for c in coverage if c.disposition == "QUARANTINED"]
    (issue,) = issues
    assert issue.field_path == f"page:{quarantined.locator.page_index_1based}"


def test_complete_documents_raise_nothing():
    for world in build_worlds():
        assert _coverage_issues(_memo(world.case_tag))[1] == []
    for key in ("baseline", "injection"):
        assert _coverage_issues(_memo(CASES[key].world.case_tag))[1] == []
    faq = FIXTURES / "h01/acquired_originals/cpcb_faq_20240123.pdf"
    assert _coverage_issues(faq.read_bytes())[1] == []


def _pages(*texts: str) -> list[tuple[int, str]]:
    return list(enumerate(texts, 1))


def test_footer_rules():
    # Consistent total above the physical count: every unprinted number is absent.
    assert _missing_printed_pages(_pages("a Page 1 of 4", "b Page 3 of 4")) == (4, [2, 4])
    # Footers that fit the file, no footers, or mixed totals (merged documents) prove nothing.
    assert _missing_printed_pages(_pages("Page 1 of 2", "Page 2 of 2")) == (2, [])
    assert _missing_printed_pages(_pages("text", "more text")) == (0, [])
    assert _missing_printed_pages(_pages("Page 1 of 2", "Page 1 of 3")) == (0, [])
    # A number outside its own total is not a usable footer.
    assert _missing_printed_pages(_pages("Page 5 of 3")) == (3, [])
    # A textless page between footers takes the next printed number.
    assert _missing_printed_pages(_pages("Page 1 of 4", "", "Page 3 of 4")) == (4, [4])
