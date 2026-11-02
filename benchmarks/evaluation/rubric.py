"""Blind human-scoring sheets and agreement statistics. Pure functions; evaluator-side only.

A sheet shows scorers an opaque item id and the evidence to judge, never the variant, repeat or
trial id. The key that maps item ids back to trials is written separately and stays with the
evaluator. Selection and ordering are seeded, so the same inputs rebuild the same sheet.
"""

import hashlib
import random
from collections import Counter

DIMENSIONS = ("citation_support", "temporal_correctness", "next_action_quality")
LABELS = ("PASS", "PARTIAL", "FAIL")
HIDDEN = {"trial_id", "variant", "repeat", "case_id"}


def item_id(seed: str, trial_id: str) -> str:
    return "item-" + hashlib.sha256(f"{seed}\0{trial_id}".encode()).hexdigest()[:12]


def select_trials(trial_ids: list[str], seed: str, *, fraction: float, double_fraction: float):
    """Return ``(scored, double_scored)``; double-scored is a subset of scored."""
    if not (0 < fraction <= 1 and 0 <= double_fraction <= 1):
        raise ValueError("fractions must lie in (0, 1] and [0, 1]")
    ordered = sorted(set(trial_ids))
    rng = random.Random(seed)
    rng.shuffle(ordered)
    scored = ordered[: max(1, round(len(ordered) * fraction))] if ordered else []
    count = min(len(scored), round(len(scored) * double_fraction))
    if double_fraction > 0 and scored:
        count = max(1, count)
    return sorted(scored), sorted(scored[:count])


def build_sheet(items: dict[str, dict], scored: list[str], seed: str) -> tuple[list[dict], dict]:
    """``items`` maps trial id to the shown content. Returns ``(sheet rows, key)``."""
    rows, key = [], {}
    for trial_id in scored:
        content = items[trial_id]
        leaked = HIDDEN & content.keys()
        if leaked:
            raise ValueError(f"sheet content must not carry {sorted(leaked)}")
        identifier = item_id(seed, trial_id)
        key[identifier] = trial_id
        rows.append({"item_id": identifier, **content, **dict.fromkeys(DIMENSIONS)})
    rows.sort(key=lambda row: row["item_id"])
    return rows, dict(sorted(key.items()))


def cohens_kappa(first: list[str], second: list[str]):
    """Cohen's kappa for two raters; ``None`` when chance agreement is total (undefined)."""
    if len(first) != len(second) or not first:
        raise ValueError("ratings must be non-empty and the same length")
    total = len(first)
    observed = sum(a == b for a, b in zip(first, second, strict=True)) / total
    left, right = Counter(first), Counter(second)
    expected = sum(left[label] * right[label] for label in left.keys() | right.keys()) / total**2
    if expected == 1:
        return None
    return (observed - expected) / (1 - expected)


def agreement(first: dict[str, dict], second: dict[str, dict]) -> dict:
    """Per-dimension raw agreement and kappa over the items both scorers labelled."""
    shared = sorted(first.keys() & second.keys())
    result = {}
    for dimension in DIMENSIONS:
        pairs = [
            (first[i][dimension], second[i][dimension])
            for i in shared
            if first[i].get(dimension) in LABELS and second[i].get(dimension) in LABELS
        ]
        if not pairs:
            result[dimension] = {"items": 0, "raw_agreement": None, "kappa": None}
            continue
        a, b = (list(side) for side in zip(*pairs, strict=True))
        result[dimension] = {
            "items": len(pairs),
            "raw_agreement": sum(x == y for x, y in pairs) / len(pairs),
            "kappa": cohens_kappa(a, b),
        }
    return result


def disputes(first: dict[str, dict], second: dict[str, dict]) -> list[str]:
    """Item ids where the two scorers differ on any dimension, for third-scorer adjudication."""
    return [
        i
        for i in sorted(first.keys() & second.keys())
        if any(first[i].get(d) != second[i].get(d) for d in DIMENSIONS)
    ]
