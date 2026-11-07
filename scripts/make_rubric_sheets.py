"""Build blind human-scoring sheets from a finished trial output. Evaluator-side only.

PYTHONPATH=. uv run scripts/make_rubric_sheets.py <trial-output> <out-dir> --seed S \
    [--fraction 1.0] [--double-fraction 0.2] [--briefs 1]

Scorers get ``scorer_a.csv`` (and ``scorer_b.csv`` for the double-scored subset). Neither shows the
variant, repeat, run or trial id; cases appear as opaque labels. ``key.json`` (item -> trial) and
``case_map.json`` (label -> case id, for handing each scorer the visible dossier) stay with the
evaluator. Trials without a report (failed or blocked before one) are listed, not scored.

``--briefs 1`` builds reviewer-brief sheets instead: one item per finding that has an accepted
model brief, showing the finding and two unlabelled briefs (model and template, in seeded order).
``key.json`` says which is which. Model briefs that were rejected or dropped are counted in
``brief_outcomes.json``, not scored: the reviewer sees the template brief for those findings.
"""

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))  # evaluator code is not part of the installed wheel

from benchmarks.evaluation.rubric import (  # noqa: E402
    BRIEF_SCORES,
    DIMENSIONS,
    brief_item_key,
    build_brief_sheet,
    build_sheet,
    select_trials,
)

COLUMNS = ["item_id", "case_label", "report_text", "findings_text", *DIMENSIONS]
BRIEF_COLUMNS = [
    "item_id",
    "case_label",
    "finding_text",
    "brief_1_text",
    "brief_2_text",
    *BRIEF_SCORES,
    "preferred",
]


def case_label(seed: str, case_id: str) -> str:
    return "case-" + hashlib.sha256(f"{seed}\0case\0{case_id}".encode()).hexdigest()[:8]


def shown_text(report: dict) -> tuple[str, str]:
    findings = []
    for finding in report.get("findings", []):
        refs = ", ".join(ref["ref_id"] for ref in finding["fact_refs"])
        findings.append(
            f"[{finding['issue_type']}] {finding['advisory_status']}; "
            f"next action: {finding['next_action']['description']}; facts: {refs or 'none'}"
        )
    return report["report"]["rendered_markdown"], "\n".join(findings) or "No findings recorded."


def final_results(output: Path):
    """``(trial id, result)`` for every finished trial, in trial id order."""
    ledger = [
        json.loads(line) for line in (output / "ledger.jsonl").read_text("utf-8").splitlines()
    ]
    final = {row["trial_id"]: row for row in ledger if row["status"] != "STARTED"}
    for trial_id, row in sorted(final.items()):
        path = output / "results" / f"{row['result_digest']}.json"
        yield trial_id, json.loads(path.read_text("utf-8")) if row.get("result_digest") else {}


def finding_text(finding: dict) -> str:
    refs = ", ".join(ref["ref_id"] for ref in finding["fact_refs"])
    return (
        f"[{finding['issue_type']}] {finding['advisory_status']}; "
        f"basis: {finding['priority_basis']}; "
        f"next action: {finding['next_action']['description']}; facts: {refs or 'none'}"
    )


def brief_text(brief: dict) -> str:
    """A brief as the scorer sees it: its content, never its source label."""
    lines = [
        f"What to check: {brief['what_to_check']}",
        f"Why it was raised: {brief['explanation']}",
        f"Evidence request: {brief['evidence_request']}",
    ]
    if brief["figures"]:
        lines.append(
            "Figures: " + "; ".join(f"{f['label']}: {f['value']}" for f in brief["figures"])
        )
    cited = ", ".join(ref["ref_id"] for ref in brief["evidence_refs"])
    lines.append(f"Cited: {cited or 'none'}")
    return "\n".join(lines)


def load_brief_items(output: Path):
    """``(items by brief item key, case id by trial id, model brief outcomes)``."""
    items, cases, outcomes = {}, {}, Counter()
    for trial_id, data in final_results(output):
        briefs, report = data.get("briefs") or {}, data.get("report") or {}
        if not briefs.get("model_briefs") or not report:
            continue
        findings = {f["finding_revision_id"]: f for f in report.get("findings", [])}
        templates = {b["finding_revision_id"]: b for b in briefs["template_briefs"]}
        for brief in briefs["model_briefs"]:
            outcomes[f"{brief['status']}:{brief['reason'] or ''}".rstrip(":")] += 1
            revision = brief["finding_revision_id"]
            if brief["status"] != "ACCEPTED" or revision not in templates:
                continue
            cases[trial_id] = data["case_id"]
            items[brief_item_key(trial_id, revision)] = {
                "finding_text": finding_text(findings[revision]),
                "model": brief_text(brief),
                "template": brief_text(templates[revision]),
            }
    return items, cases, outcomes


def load_trials(output: Path) -> tuple[dict[str, dict], dict[str, str], list[str]]:
    """``(shown content by trial id, case id by trial id, trial ids without a report)``."""
    shown, cases, skipped = {}, {}, []
    for trial_id, data in final_results(output):
        if not data.get("report"):
            skipped.append(trial_id)
            continue
        report_text, findings_text = shown_text(data["report"])
        shown[trial_id] = {"report_text": report_text, "findings_text": findings_text}
        cases[trial_id] = data["case_id"]
    return shown, cases, skipped


def write_csv(path: Path, rows: list[dict], columns=COLUMNS):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def brief_sheets(output: Path, out: Path, seed: str, options: dict):
    items, cases, outcomes = load_brief_items(output)
    scored, double = select_trials(
        list(items),
        seed,
        fraction=float(options.get("--fraction", 1.0)),
        double_fraction=float(options.get("--double-fraction", 0.2)),
    )
    content = {
        item: {"case_label": case_label(seed, cases[item.split("\0", 1)[0]]), **items[item]}
        for item in scored
    }
    rows, key = build_brief_sheet(content, scored, seed)
    in_double = {
        i
        for i, sides in key.items()
        if brief_item_key(sides["trial_id"], sides["finding_revision_id"]) in set(double)
    }
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "scorer_a.csv", rows, BRIEF_COLUMNS)
    write_csv(out / "scorer_b.csv", [r for r in rows if r["item_id"] in in_double], BRIEF_COLUMNS)
    (out / "key.json").write_text(json.dumps(key, indent=2, sort_keys=True) + "\n", "utf-8")
    (out / "case_map.json").write_text(
        json.dumps({case_label(seed, c): c for c in sorted(set(cases.values()))}, indent=2) + "\n",
        "utf-8",
    )
    (out / "brief_outcomes.json").write_text(
        json.dumps(dict(sorted(outcomes.items())), indent=2) + "\n", "utf-8"
    )
    print(
        json.dumps({"items": len(rows), "double_scored": len(in_double), "model_briefs": outcomes})
    )


def main(argv):
    options = {a: argv[i + 1] for i, a in enumerate(argv) if a.startswith("--")}
    paths = [
        a for i, a in enumerate(argv) if not a.startswith("--") and not argv[i - 1].startswith("--")
    ]
    if len(paths) != 2 or "--seed" not in options:
        raise SystemExit(__doc__)
    output, out = Path(paths[0]), Path(paths[1])
    seed = options["--seed"]
    if options.get("--briefs") == "1":
        return brief_sheets(output, out, seed, options)
    shown, cases, skipped = load_trials(output)
    scored, double = select_trials(
        list(shown),
        seed,
        fraction=float(options.get("--fraction", 1.0)),
        double_fraction=float(options.get("--double-fraction", 0.2)),
    )
    content = {t: {"case_label": case_label(seed, cases[t]), **shown[t]} for t in scored}
    rows, key = build_sheet(content, scored, seed)
    in_double = {i for i, t in key.items() if t in set(double)}
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "scorer_a.csv", rows)
    write_csv(out / "scorer_b.csv", [r for r in rows if r["item_id"] in in_double])
    (out / "key.json").write_text(json.dumps(key, indent=2, sort_keys=True) + "\n", "utf-8")
    (out / "case_map.json").write_text(
        json.dumps({case_label(seed, c): c for c in sorted(set(cases.values()))}, indent=2) + "\n",
        "utf-8",
    )
    print(
        json.dumps(
            {"items": len(rows), "double_scored": len(in_double), "without_report": len(skipped)}
        )
    )


if __name__ == "__main__":
    main(sys.argv[1:])
