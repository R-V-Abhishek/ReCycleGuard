"""Turn a generated results CSV into a LaTeX tabular, so report tables are never typed by hand.

Pure functions; evaluator-side only. Undefined values (``NA``) stay visible as ``n/a`` and are never
turned into 0 or 1. Variant ids are shown with the names used in the report.
"""

import csv
import io

VARIANT_NAMES = {"FIXED_RETRIEVAL": "V1", "ADAPTIVE": "V2", "V0": "V0", "SC": "SC"}
_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_NUMERIC = frozenset("0123456789.-+")


def escape(text: str) -> str:
    return "".join(_ESCAPES.get(char, char) for char in text)


def cell(value: str) -> str:
    if value == "NA":
        return "n/a"
    return escape(VARIANT_NAMES.get(value, value))


def header(name: str) -> str:
    return escape(name.replace("_", " "))


def csv_to_tabular(content: str) -> str:
    rows = list(csv.reader(io.StringIO(content)))
    if not rows or not rows[0]:
        raise ValueError("a results table needs a header row")
    names, body = rows[0], rows[1:]
    if any(len(row) != len(names) for row in body):
        raise ValueError("every row must have as many cells as the header")
    numeric = [
        bool(body) and all(row[i] == "NA" or (row[i] and set(row[i]) <= _NUMERIC) for row in body)
        for i in range(len(names))
    ]
    spec = "".join("r" if flag else "l" for flag in numeric)
    lines = [
        rf"\begin{{tabular}}{{{spec}}}",
        r"\toprule",
        " & ".join(rf"\textbf{{{header(name)}}}" for name in names) + r" \\",
        r"\midrule",
        *(" & ".join(cell(value) for value in row) + r" \\" for row in body),
        r"\bottomrule",
        r"\end{tabular}",
    ]
    return "\n".join(lines) + "\n"
