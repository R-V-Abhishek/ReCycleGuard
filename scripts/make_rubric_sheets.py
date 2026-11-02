"""Build blind human-scoring sheets from a finished trial output. Evaluator-side only.

PYTHONPATH=. uv run scripts/make_rubric_sheets.py <trial-output> <out-dir> --seed S \
    [--fraction 1.0] [--double-fraction 0.2]

Scorers get ``scorer_a.csv`` (and ``scorer_b.csv`` for the double-scored subset). Neither shows the
variant, repeat, run or trial id; cases appear as opaque labels. ``key.json`` (item -> trial) and
``case_map.json`` (label -> case id, for handing each scorer the visible dossier) stay with the
evaluator. Trials without a report (failed or blocked before one) are listed, not scored.
"""

import csv
import hashlib
import json
import sys
from pathlib import Path

from benchmarks.evaluation.rubric import DIMENSIONS, build_sheet, select_trials

COLUMNS = ["item_id", "case_label", "report_text", "findings_text", *DIMENSIONS]


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


def load_trials(output: Path) -> tuple[dict[str, dict], dict[str, str], list[str]]:
    """``(shown content by trial id, case id by trial id, trial ids without a report)``."""
    ledger = [
        json.loads(line) for line in (output / "ledger.jsonl").read_text("utf-8").splitlines()
    ]
    final = {row["trial_id"]: row for row in ledger if row["status"] != "STARTED"}
    shown, cases, skipped = {}, {}, []
    for trial_id, row in sorted(final.items()):
        path = output / "results" / f"{row['result_digest']}.json"
        data = json.loads(path.read_text("utf-8")) if row.get("result_digest") else {}
        if not data.get("report"):
            skipped.append(trial_id)
            continue
        report_text, findings_text = shown_text(data["report"])
        shown[trial_id] = {"report_text": report_text, "findings_text": findings_text}
        cases[trial_id] = data["case_id"]
    return shown, cases, skipped


def write_csv(path: Path, rows: list[dict]):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv):
    options = {a: argv[i + 1] for i, a in enumerate(argv) if a.startswith("--")}
    paths = [
        a for i, a in enumerate(argv) if not a.startswith("--") and not argv[i - 1].startswith("--")
    ]
    if len(paths) != 2 or "--seed" not in options:
        raise SystemExit(__doc__)
    output, out = Path(paths[0]), Path(paths[1])
    seed = options["--seed"]
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
