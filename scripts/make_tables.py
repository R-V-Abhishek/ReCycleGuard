"""Rebuild the results tables from a trial output and its scores. Byte-identical on every run.

PYTHONPATH=. uv run scripts/make_tables.py <trial-output> <scores-dir> <tables-out>
"""

import json
import sys
from pathlib import Path

from benchmarks.evaluation.tables import build_tables
from benchmarks.evaluation.trials import Ledger


def main(argv):
    if len(argv) != 3:
        raise SystemExit(__doc__)
    output, scores_dir, out = (Path(value) for value in argv)
    scores = [
        json.loads(line)
        for line in (scores_dir / "scores.jsonl").read_text("utf-8").splitlines()
        if line
    ]
    tables = build_tables(scores, Ledger(output / "ledger.jsonl").rows())
    out.mkdir(parents=True, exist_ok=True)
    for name, content in tables.items():
        (out / name).write_bytes(content)
    print(json.dumps({"tables": sorted(tables), "out": str(out)}))


if __name__ == "__main__":
    main(sys.argv[1:])
