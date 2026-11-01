"""Paired case-level bootstrap. Repeats are not independent, so whole cases are resampled."""

import random
from collections import defaultdict
from collections.abc import Iterable


def paired_bootstrap(
    rows: Iterable[dict], a: str, b: str, *, resamples: int = 10000, seed: int
) -> dict:
    """Difference in success rate, ``b`` minus ``a``, with a 95% percentile interval.

    Each row needs ``case_id``, ``variant`` and a boolean ``success``. A case missing either
    variant cannot be paired: it is excluded and counted.
    """
    outcomes = defaultdict(lambda: {a: [], b: []})
    for row in rows:
        if row["variant"] in (a, b):
            outcomes[row["case_id"]][row["variant"]].append(row["success"])
    paired = sorted(case for case, seen in outcomes.items() if seen[a] and seen[b])
    result = {"cases": len(paired), "excluded_unpaired_cases": len(outcomes) - len(paired)}
    if not paired:
        return result | {"difference": None, "interval_95": None}

    def difference(cases):
        wins = {a: 0, b: 0}
        trials = {a: 0, b: 0}
        for case in cases:
            for variant in (a, b):
                wins[variant] += sum(outcomes[case][variant])
                trials[variant] += len(outcomes[case][variant])
        return wins[b] / trials[b] - wins[a] / trials[a]

    generator = random.Random(seed)
    samples = sorted(difference(generator.choices(paired, k=len(paired))) for _ in range(resamples))
    return result | {
        "difference": difference(paired),
        "interval_95": [samples[int(0.025 * resamples)], samples[int(0.975 * resamples) - 1]],
    }
