"""Build the CP5 freeze manifest for this repository from a spec; records, never approves.

    PYTHONPATH=. uv run scripts/make_freeze.py <spec.json> <freeze.json>

The spec names the scope, repository-relative ``files`` and ``trees``, and literal ``values`` such
as the prompt pin, model identifiers, budgets and provider/date. Freeze only from a clean tree.
"""

import json
import sys
from pathlib import Path

from benchmarks.evaluation.freeze import build_freeze, freeze_bytes, freeze_digest

REPOSITORY = Path(__file__).resolve().parents[1]


def main(argv):
    if len(argv) != 2:
        raise SystemExit(__doc__)
    spec = json.loads(Path(argv[0]).read_text("utf-8"))
    freeze = build_freeze(REPOSITORY, spec)
    if freeze["git"]["dirty"]:
        raise SystemExit("refusing to freeze a dirty working tree")
    Path(argv[1]).write_bytes(freeze_bytes(freeze))
    print(json.dumps({"freeze_digest": freeze_digest(freeze), "path": argv[1]}))


if __name__ == "__main__":
    main(sys.argv[1:])
