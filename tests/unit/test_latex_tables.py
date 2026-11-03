import pytest

from benchmarks.evaluation.latex_tables import csv_to_tabular, escape

CSV = (
    "variant,scheduled,success_rate,note\n"
    "FIXED_RETRIEVAL,24,0.0833,a_b & 50%\n"
    "ADAPTIVE,24,NA,plain\n"
)


def test_variants_numbers_and_undefined_values():
    text = csv_to_tabular(CSV)
    assert r"\begin{tabular}{lrrl}" in text
    assert r"V1 & 24 & 0.0833 & a\_b \& 50\% \\" in text
    assert r"V2 & 24 & n/a & plain \\" in text
    assert "NA" not in text  # an undefined value is never turned into a number
    assert r"\textbf{success rate}" in text


def test_escapes_special_characters():
    assert escape(r"a_b#c$d{e}~^\ ") == (
        r"a\_b\#c\$d\{e\}\textasciitilde{}\textasciicircum{}\textbackslash{} "
    )


def test_rejects_ragged_and_empty_tables():
    with pytest.raises(ValueError):
        csv_to_tabular("a,b\n1\n")
    with pytest.raises(ValueError):
        csv_to_tabular("")


def test_header_only_table_is_not_numeric():
    assert r"\begin{tabular}{l}" in csv_to_tabular("variant\n")
