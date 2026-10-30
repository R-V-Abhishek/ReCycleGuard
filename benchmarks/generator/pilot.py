"""S07 pilot checks: split independence, leakage, duplicates, and the held-out seal.

The held-out visible dossiers are rendered to a gitignored root. Git keeps only
``benchmarks/pilot/heldout_seal.json``: the opaque held-out case ids and a digest of each case's
visible file tree, so anyone can confirm a regeneration is byte-identical without the files
being browsable in the repository. The seal carries no family, template, seed or split label.
"""

import hashlib
import json
import re
from pathlib import Path

from benchmarks.generator.faults.recipes import RECIPES
from benchmarks.generator.pilot_cases import DATASET_VERSION, DEV, HELD_OUT, PilotCase
from benchmarks.generator.render import Rendered
from recycleguard.extraction.pdf_extractor import extract_pdf_pages

SEAL_PATH = Path(__file__).resolve().parents[1] / "pilot" / "heldout_seal.json"
NEAR_DUPLICATE = 0.85  # word 5-shingle Jaccard between a development and a held-out dossier
# World fields whose values identify a hidden world object; none may recur across the splits.
ID_FIELDS = (
    "lot_id",
    "certificate_id",
    "external_ref",
    "event_id",
    "txn_ref",
    "allocation_id",
    "bucket_id",
    "commercial_id",
    "utr",
    "balance_id",
    "mapping_id",
    "case_id",
)
LABEL_WORDS = (
    r"held[ _-]?out",
    r"\bpilot\b",
    r"\bdev(elopment)? (split|set)\b",
    r"\btest set\b",
    r"\bsplit\b",
    r"\bseed\b",
    r"\boracle\b",
    r"\brecipe\b",
)


def tree_digest(case_dir: Path) -> str:
    """SHA-256 over the sorted relative paths and file digests of one visible case."""
    lines = [
        f"{p.relative_to(case_dir).as_posix()}\t{hashlib.sha256(p.read_bytes()).hexdigest()}"
        for p in sorted(case_dir.rglob("*"))
        if p.is_file()
    ]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def visible_text(case_dir: Path) -> str:
    """Every visible string a reader or the runtime can see: data files and PDF text layers."""
    parts = [
        p.read_text("utf-8")
        for p in sorted(case_dir.rglob("*"))
        if p.suffix in {".csv", ".json", ".jsonl"}
    ]
    for pdf in sorted(case_dir.rglob("*.pdf")):
        parts.append(extract_pdf_pages(pdf.read_bytes(), "art:check", "ext:check")[2])
    return "\n".join(parts)


def _shingles(text: str, k: int = 5) -> set[tuple[str, ...]]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {tuple(words[i : i + k]) for i in range(max(0, len(words) - k + 1))}


def _ids(world_json, found: set[str]) -> set[str]:
    if isinstance(world_json, dict):
        for key, value in world_json.items():
            if key in ID_FIELDS and isinstance(value, str):
                found.add(value)
            else:
                _ids(value, found)
    elif isinstance(world_json, list | tuple):
        for item in world_json:
            _ids(item, found)
    return found


def _entities(case: PilotCase) -> set[str]:
    w = case.world
    return {w.producer.legal_name, *(x.legal_name for x in w.recyclers)} | {
        x.legal_name for x in w.affiliates
    }


def _hidden_terms(case: PilotCase) -> set[str]:
    families = {k.lower() for k in RECIPES} | {k.split("_", 1)[0].lower() + "_" for k in RECIPES}
    return (
        families
        | {recipe.key for recipe in RECIPES.values()}
        | {case.spec.template_key.lower(), case.world.timeline_group.lower(), DATASET_VERSION}
    )


def split_problems(cases: list[PilotCase]) -> list[str]:
    """Independence of the two splits, decided before rendering."""
    problems = []
    dev = [c for c in cases if c.split == DEV]
    held = [c for c in cases if c.split == HELD_OUT]
    if (len(dev), len(held)) != (24, 24):
        problems.append(f"split sizes {len(dev)}/{len(held)}, expected 24/24")
    for label, key in (
        ("template", lambda c: {c.spec.template_key}),
        # Single fault definitions are shared on purpose; their combinations may not be.
        ("combination", lambda c: {c.spec.combination} if len(c.spec.combination) > 1 else set()),
        ("timeline group", lambda c: {c.world.timeline_group}),
        ("entity", _entities),
        ("hidden world id", lambda c: _ids(c.world.to_json(), set())),
    ):
        left = set().union(*(key(c) for c in dev))
        right = set().union(*(key(c) for c in held))
        for shared in sorted(map(str, left & right)):
            problems.append(f"{label} shared by the splits: {shared}")
    return problems


def leakage_problems(cases: list[PilotCase], rendered: list[Rendered]) -> list[str]:
    """Labels in visible bytes, exact duplicates, and near-duplicates across the splits."""
    problems = []
    texts, digests = {}, {}
    for case, out in zip(cases, rendered, strict=True):
        text = visible_text(out.case_dir)
        lowered = text.lower()
        names = " ".join(p.name.lower() for p in out.case_dir.rglob("*"))
        for term in _hidden_terms(case):
            if term in lowered or term in names:
                problems.append(f"{out.case_dir.name}: hidden term visible: {term}")
        for pattern in LABEL_WORDS:
            if re.search(pattern, lowered) or re.search(pattern, names):
                problems.append(f"{out.case_dir.name}: label word visible: {pattern}")
        texts[case.world.case_id] = (case.split, _shingles(text))
        digest = tree_digest(out.case_dir)
        if digest in digests:
            problems.append(f"{out.case_dir.name}: exact duplicate of {digests[digest]}")
        digests[digest] = out.case_dir.name
    worst = max_cross_similarity(texts)
    if worst[0] >= NEAR_DUPLICATE:
        problems.append(
            f"near-duplicate across the splits: {worst[1]} ~ {worst[2]} ({worst[0]:.3f})"
        )
    return problems


def max_cross_similarity(texts: dict[str, tuple[str, set]]) -> tuple[float, str, str]:
    best = (0.0, "", "")
    dev = [(k, s) for k, (split, s) in texts.items() if split == DEV]
    held = [(k, s) for k, (split, s) in texts.items() if split == HELD_OUT]
    for a, sa in dev:
        for b, sb in held:
            score = len(sa & sb) / len(sa | sb) if sa | sb else 1.0
            if score > best[0]:
                best = (score, a, b)
    return best


def seal(cases: list[PilotCase], rendered: list[Rendered]) -> dict:
    held = sorted(
        (case.world.case_id, tree_digest(out.case_dir))
        for case, out in zip(cases, rendered, strict=True)
        if case.split == HELD_OUT
    )
    return {
        "dataset_version": DATASET_VERSION,
        "note": (
            "Digests of the sealed visible dossiers kept outside version control. Regenerate them "
            "with benchmarks.generator.generate and compare; the files are not distributed here."
        ),
        "cases": {case_id: digest for case_id, digest in held},
        "aggregate_sha256": hashlib.sha256(
            "\n".join(f"{k}\t{v}" for k, v in held).encode()
        ).hexdigest(),
    }


def seal_bytes(payload: dict) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def seal_problems(expected: dict, actual: dict) -> list[str]:
    if expected == actual:
        return []
    problems = [
        f"sealed case {k}: digest differs"
        for k in sorted(set(expected.get("cases", {})) | set(actual["cases"]))
        if expected.get("cases", {}).get(k) != actual["cases"].get(k)
    ]
    return problems or ["seal differs"]


__all__ = [
    "NEAR_DUPLICATE",
    "SEAL_PATH",
    "leakage_problems",
    "max_cross_similarity",
    "seal",
    "seal_bytes",
    "seal_problems",
    "split_problems",
    "tree_digest",
    "visible_text",
]
