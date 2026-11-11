"""Rebuild the results tables from a trial output and its scores. Byte-identical on every run.

uv run scripts/make_tables.py <trial-output> <scores-dir> <tables-out> [<rubric-agreement.json>]
"""

import json
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))  # evaluator code is not part of the installed wheel

from benchmarks.evaluation.tables import build_tables  # noqa: E402
from benchmarks.evaluation.trials import Ledger  # noqa: E402


def main(argv):
    if len(argv) not in {3, 4}:
        raise SystemExit(__doc__)
    output, scores_dir, out, *rubric_path = (Path(value) for value in argv)
    scores = [
        json.loads(line)
        for line in (scores_dir / "scores.jsonl").read_text("utf-8").splitlines()
        if line
    ]
    rubric = json.loads(rubric_path[0].read_text("utf-8")) if rubric_path else None
    tables = build_tables(scores, Ledger(output / "ledger.jsonl").rows(), rubric)
    out.mkdir(parents=True, exist_ok=True)
    for name, content in tables.items():
        (out / name).write_bytes(content)
    print(json.dumps({"tables": sorted(tables), "out": str(out)}))


if __name__ == "__main__":
    main(sys.argv[1:])
