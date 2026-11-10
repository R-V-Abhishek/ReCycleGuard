"""Score a queue's sessions where the evaluator data is, after its /work came back from a notebook.

The notebooks never hold ``benchmarks/hidden``, so their queues print ``could not score``. Copy the
persisted ``work`` folder here, then:

    RECYCLEGUARD_WORK=<downloaded>/work uv run scripts/cloud/score.py <queue.json>

Every whole development session is scored exactly as ``run_queue.py`` would score it (tables next
to the session), and ``compare.csv`` goes in ``<work>/<queue name>/``. Unfinished sessions are
listed and left alone. Runbook: docs/checkpoints/mg2/CLOUD_RUNBOOK.md.
"""

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from run_queue import (  # noqa: E402
    WORK,
    atomic_write,
    load_queue,
    output_of,
    sessions_of,
    sibling,
    trial_counts,
)


def main(argv):
    if len(argv) != 1:
        raise SystemExit(__doc__)
    sweep = sibling("run_sweep")
    if not sweep.ORACLE.is_dir():
        raise SystemExit(f"no evaluator data at {sweep.ORACLE}; score where it is")
    queue = load_queue(Path(argv[0]), sweep)
    tables, unfinished = {}, []
    for session in sessions_of(queue):
        if session.final:
            continue
        output = output_of(queue, session)
        done, total = trial_counts(output, session.protocol)
        if done < total:
            unfinished.append(f"{session.key}: {done} of {total}")
            continue
        # Always rescore: the notebook's own tables were made without the oracle (all unscored).
        tables[session.key] = sweep.score(output)
    scored = {key: path for key, path in tables.items() if path is not None}
    if scored:
        atomic_write(WORK / queue["name"] / "compare.csv", sweep.compare(scored))
    for line in unfinished:
        print(f"not whole, not scored: {line}")
    failed = sorted(set(tables) - set(scored))
    if failed:
        raise SystemExit(f"could not score: {failed}")
    print(f"scored {len(scored)} sessions; compare.csv in {WORK / queue['name']}")


if __name__ == "__main__":
    main(sys.argv[1:])
