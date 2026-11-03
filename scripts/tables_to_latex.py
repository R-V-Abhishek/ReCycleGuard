"""Write one LaTeX tabular per generated results CSV, for ``\\input`` in the report.

uv run scripts/tables_to_latex.py <tables-dir> <out-dir>

The report supplies its own caption and label around ``\\input{<name>.tex}``. Rebuild the tables
first with scripts/make_tables.py; never edit the generated files by hand.
"""

import json
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))  # evaluator code is not part of the installed wheel

from benchmarks.evaluation.latex_tables import csv_to_tabular  # noqa: E402


def main(argv):
    if len(argv) != 2:
        raise SystemExit(__doc__)
    tables, out = Path(argv[0]), Path(argv[1])
    sources = sorted(tables.glob("*.csv"))
    if not sources:
        raise SystemExit(f"no CSV tables in {tables}")
    out.mkdir(parents=True, exist_ok=True)
    for source in sources:
        text = csv_to_tabular(source.read_text("utf-8"))
        (out / f"{source.stem}.tex").write_bytes(text.encode("utf-8"))
    print(json.dumps({"tables": [s.stem for s in sources], "out": str(out)}))


if __name__ == "__main__":
    main(sys.argv[1:])
