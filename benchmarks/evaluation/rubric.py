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
# Reviewer briefs: each item shows one finding and two briefs, a model brief and the template
# brief, in seeded order. The scorer rates each brief, then says which helps more.
BRIEF_DIMENSIONS = ("citation_support", "next_action_quality", "usefulness")
BRIEF_SLOTS = ("brief_1", "brief_2")
BRIEF_SCORES = tuple(f"{slot}_{d}" for slot in BRIEF_SLOTS for d in BRIEF_DIMENSIONS)
PREFERENCES = ("1", "2", "SAME")


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


def brief_item_key(trial_id: str, finding_revision_id: str) -> str:
    return f"{trial_id}\0{finding_revision_id}"


def build_brief_sheet(items: dict[str, dict], scored: list[str], seed: str):
    """``items`` maps a brief item key to its shown finding and its ``model``/``template`` text.

    Returns ``(rows, key)``. Which brief is shown first is seeded per item; only the key says
    which is which. The caller shows brief text without its source label.
    """
    rows, key = [], {}
    for item in scored:
        content = dict(items[item])
        leaked = HIDDEN & content.keys()
        if leaked:
            raise ValueError(f"sheet content must not carry {sorted(leaked)}")
        model, template = content.pop("model"), content.pop("template")
        identifier = item_id(seed, item)
        model_first = hashlib.sha256(f"{seed}\0order\0{identifier}".encode()).digest()[0] % 2 == 0
        first, second = (model, template) if model_first else (template, model)
        trial_id, finding_revision_id = item.split("\0", 1)
        key[identifier] = {
            "trial_id": trial_id,
            "finding_revision_id": finding_revision_id,
            "brief_1": "MODEL" if model_first else "TEMPLATE",
            "brief_2": "TEMPLATE" if model_first else "MODEL",
        }
        rows.append(
            {
                "item_id": identifier,
                **content,
                "brief_1_text": first,
                "brief_2_text": second,
                **dict.fromkeys(BRIEF_SCORES),
                "preferred": None,
            }
        )
    rows.sort(key=lambda row: row["item_id"])
    return rows, dict(sorted(key.items()))


def brief_comparison(scores: dict[str, dict], key: dict[str, dict]) -> dict:
    """One scorer's sheet unblinded: PASS rate per source and dimension, and preferences."""
    passed = {source: Counter() for source in ("MODEL", "TEMPLATE")}
    rated = {source: Counter() for source in ("MODEL", "TEMPLATE")}
    preferred = Counter()
    for identifier, row in scores.items():
        sides = key[identifier]
        for slot in BRIEF_SLOTS:
            for dimension in BRIEF_DIMENSIONS:
                label = row.get(f"{slot}_{dimension}")
                if label in LABELS:
                    rated[sides[slot]][dimension] += 1
                    passed[sides[slot]][dimension] += label == "PASS"
        choice = row.get("preferred")
        if choice in PREFERENCES:
            preferred["SAME" if choice == "SAME" else sides[f"brief_{choice}"]] += 1
    return {
        "pass_rate": {
            source: {
                d: (passed[source][d] / rated[source][d]) if rated[source][d] else None
                for d in BRIEF_DIMENSIONS
            }
            for source in passed
        },
        "rated": {source: dict(rated[source]) for source in rated},
        "preferred": dict(preferred),
    }


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


def agreement(first: dict[str, dict], second: dict[str, dict], dimensions=DIMENSIONS) -> dict:
    """Per-dimension raw agreement and kappa over the items both scorers labelled.

    For brief sheets pass ``dimensions=BRIEF_SCORES``; preferences use ``preference_agreement``.
    """
    return _agreement(first, second, dimensions, LABELS)


def preference_agreement(first: dict[str, dict], second: dict[str, dict]) -> dict:
    """Agreement on which brief helps more (``1``, ``2`` or ``SAME``)."""
    return _agreement(first, second, ("preferred",), PREFERENCES)


def _agreement(first, second, dimensions, labels) -> dict:
    shared = sorted(first.keys() & second.keys())
    result = {}
    for dimension in dimensions:
        pairs = [
            (first[i][dimension], second[i][dimension])
            for i in shared
            if first[i].get(dimension) in labels and second[i].get(dimension) in labels
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


def disputes(first: dict[str, dict], second: dict[str, dict], dimensions=DIMENSIONS) -> list[str]:
    """Item ids where the two scorers differ on any dimension, for third-scorer adjudication."""
    return [
        i
        for i in sorted(first.keys() & second.keys())
        if any(first[i].get(d) != second[i].get(d) for d in dimensions)
    ]
