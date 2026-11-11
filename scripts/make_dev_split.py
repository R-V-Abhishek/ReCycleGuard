"""Write the committed 16 tuning and 8 checking development protocols. Development cases only.

Stratified: single-family dossiers and combinations are each split two to one, ordered by a fixed
digest so no case is chosen by its results. Checking cases must not be used to tune a prompt.

    uv run scripts/make_dev_split.py docs/checkpoints/mg1/protocols
"""

import hashlib
import json
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))  # evaluator code is not part of the installed wheel

from benchmarks.generator.pilot_cases import DEV, build_pilot_cases  # noqa: E402

SEED = "mg1-dev-split-1"
CHECKING_SHARE = 3  # about one case in three from each stratum
SINGLE, COMBINATION = 16, 8


def _order(case_id):
    return hashlib.sha256(f"{SEED}|{case_id}".encode()).hexdigest()


def split_cases(strata):
    """``strata`` lists case ids per stratum; returns (tuning, checking), each sorted."""
    tuning, checking = [], []
    for cases in strata:
        ordered = sorted(cases, key=_order)
        count = round(len(ordered) / CHECKING_SHARE)
        checking += ordered[:count]
        tuning += ordered[count:]
    return sorted(tuning), sorted(checking)


def protocol(name, cases):
    return {
        "protocol_version": f"mg1-{name}",
        "case_ids": cases,
        "repeats": 1,
        "variants": ["FIXED_RETRIEVAL", "ADAPTIVE"],
        "wall_seconds": 25200,
        "tokens": 2000000,
    }


def main(argv):
    if len(argv) != 1:
        raise SystemExit(__doc__)
    out = Path(argv[0])
    development = [case for case in build_pilot_cases() if case.split == DEV]
    # The generator lists every single-family dossier first, then the combinations.
    if len(development) != SINGLE + COMBINATION:
        raise SystemExit("expected 16 single-family and 8 combined development cases")
    ids = [f"case_{case.world.case_tag}" for case in development]
    tuning, checking = split_cases([ids[:SINGLE], ids[SINGLE:]])
    for name, cases in (("tuning-16", tuning), ("checking-8", checking)):
        (out / f"{name}.json").write_text(json.dumps(protocol(name, cases)) + "\n", "utf-8")
    print(json.dumps({"tuning": len(tuning), "checking": len(checking)}))


if __name__ == "__main__":
    main(sys.argv[1:])
