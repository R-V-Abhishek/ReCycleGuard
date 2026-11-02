"""Read-only check of a CP5 freeze manifest: recompute every digest and list any difference.

uv run scripts/verify_freeze.py docs/checkpoints/checkpoint-5/freeze.json [--strict-commit]
"""

import json
import sys
from pathlib import Path

from benchmarks.evaluation.freeze import freeze_digest, verify_freeze

REPOSITORY = Path(__file__).resolve().parents[1]


def main(argv):
    strict = "--strict-commit" in argv
    paths = [a for a in argv if not a.startswith("--")]
    if len(paths) != 1:
        raise SystemExit(__doc__)
    freeze = json.loads(Path(paths[0]).read_text("utf-8"))
    problems = verify_freeze(REPOSITORY, freeze, strict_commit=strict)
    print(
        json.dumps(
            {"freeze_digest": freeze_digest(freeze), "problems": problems, "ok": not problems},
            indent=2,
        )
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
