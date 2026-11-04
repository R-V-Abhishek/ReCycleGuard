"""Where each missed fault family was lost, one stage per miss. Evaluator-only.

    python scripts/funnel.py <trial-output> <scores-dir> <out.csv>

Stages, checked in this order for a family the oracle expects and the report does not hold:
  S5_REJECTED          the model proposed it and the gate refused it (reason given)
  S6_PROPOSED_LOST     the model proposed it, the gate did not refuse it, and it is still missing
  S4_SHOWN_NOT_PROPOSED a signal for it was in evidence the model saw, and it did not propose it
  S3_COMPUTED_NOT_SHOWN the report holds a signal for it, but no evidence shown to the model did
  S1_NOT_COMPUTED      the family has a deterministic signal, and nothing computed it in this run
  S0_JUDGEMENT_ONLY    no deterministic signal exists for the family; only the model can find it
Results without a decision trace (runs before it existed) stop at S3/S1/S0.

Extra families the report holds but the oracle does not are listed as FALSE_POSITIVE with
their source. Signals follow the public family definitions; they guide diagnosis only and are
never shown to the model.
"""

import csv
import io
import json
import sys
from collections import Counter
from pathlib import Path

SIGNALS = {
    "F02_OVERLAPPING_EXPORT": {"AMBIGUOUS_EVENT"},
    "F03_MULTISTAGE_ID_REUSE": {"AMBIGUOUS_EVENT"},
    "F04_UNIT_DIMENSION_MIX": {"DIMENSION_MISMATCH"},
    "F05_WRONG_ENTITY_ALIAS": {"AMBIGUOUS_IDENTITY"},
    "F06_STALE_SNAPSHOT": {"STALE_SNAPSHOT"},
    "F08_PRIOR_ARREARS_DRAIN": {"LIABILITY_PRIORITY_UNRESOLVED", "EARLIER_LIABILITY_UNMET"},
    "F09_EXPIRED_CANCELLED": {"CREDIT_EXPIRED", "CREDIT_CANCELLED"},
    "F10_CAPABILITY_MISMATCH": {"CAPABILITY_MISMATCH"},
    "F13_WEIGHT_BASIS_CONFLICT": {"WEIGHT_BASIS_CONFLICT"},
}
COLUMNS = [
    "trial_id",
    "case_id",
    "variant",
    "family",
    "stage",
    "detail",
    "tools_run",
    "model_calls",
    "truncated_evidence_calls",
    "length_stops",
    "stop_reason",
    "records",
    "checks",
]


def _codes(value, found):
    if isinstance(value, dict):
        if "code" in value and "severity" in value:
            found.add(value["code"])
        for item in value.values():
            _codes(item, found)
    elif isinstance(value, list):
        for item in value:
            _codes(item, found)
    return found


def _compact(counts):
    return "" if not counts else ";".join(f"{key}={value}" for key, value in counts.items())


def _source(finding):
    sources = {a.get("source") for a in finding.get("evidence_assessments") or []}
    if "MODEL_PROPOSAL" in sources:
        return "model"
    if "DETERMINISTIC_CALCULATION" in sources:
        return "calculation"
    return "claim_check"


def stage(family, report_codes, decisions, rejected):
    if family in rejected:
        return "S5_REJECTED", ";".join(sorted(rejected[family]))
    signals = SIGNALS.get(family, set())
    if decisions is not None:
        proposed = {
            d["reply"]["proposal"]["issue_type"]
            for d in decisions
            if (d.get("reply") or {}).get("proposal")
        }
        if family in proposed:
            return "S6_PROPOSED_LOST", ""
        shown = {
            code
            for d in decisions
            for code in ((d.get("shown") or {}).get("visible_issue_codes") or [])
        }
        if signals & shown:
            return "S4_SHOWN_NOT_PROPOSED", ",".join(sorted(signals & shown))
    if signals & report_codes:
        return (
            "S3_COMPUTED_NOT_SHOWN" if decisions is not None else "S3_COMPUTED_NO_TRACE",
            ",".join(sorted(signals & report_codes)),
        )
    if signals:
        return "S1_NOT_COMPUTED", ""
    return "S0_JUDGEMENT_ONLY", ""


def rows_for(result, score):
    report = result.get("report") or {}
    decisions = result.get("decisions")
    report_codes = _codes(report, set())
    rejected = {}
    for item in report.get("rejected_finding_proposals") or []:
        rejected.setdefault(item["proposal"]["issue_type"], set()).add(item["reason"])
    tools = [
        (d.get("shown") or {}).get("tool")
        for d in decisions or []
        if (d.get("shown") or {}).get("tool")
    ]
    common = {
        "trial_id": score["trial_id"],
        "case_id": score["case_id"],
        "variant": score["variant"],
        "tools_run": "" if decisions is None else ";".join(tools),
        "model_calls": score.get("model_calls"),
        "truncated_evidence_calls": ""
        if decisions is None
        else sum(bool((d.get("shown") or {}).get("evidence_truncated")) for d in decisions),
        "length_stops": ""
        if decisions is None
        else sum((d.get("transport") or {}).get("finish_reason") == "length" for d in decisions),
        "stop_reason": result.get("stop_reason"),
        # What the deterministic checks had to work with, when the trial recorded it.
        "records": _compact((result.get("census") or {}).get("records")),
        "checks": _compact(
            {
                **((result.get("census") or {}).get("allocation_checks") or {}),
                **((result.get("census") or {}).get("eligibility") or {}),
            }
        ),
    }
    expected = set(score.get("expected_families") or [])
    emitted = set(score.get("emitted_families") or [])
    out = []
    for family in sorted(expected - emitted):
        found, detail = stage(family, report_codes, decisions, rejected)
        out.append({**common, "family": family, "stage": found, "detail": detail})
    sources = {f["issue_type"]: _source(f) for f in report.get("findings") or []}
    for family in sorted(emitted - expected):
        out.append(
            {**common, "family": family, "stage": "FALSE_POSITIVE", "detail": sources.get(family)}
        )
    return out


def main(argv):
    if len(argv) != 3:
        raise SystemExit(__doc__)
    output, scores_dir, target = (Path(value) for value in argv)
    results = {}
    for path in sorted((output / "results").glob("*.json")):
        result = json.loads(path.read_text("utf-8"))
        results[(result["case_id"], result["requested_variant"])] = result
    rows = []
    for line in (scores_dir / "scores.jsonl").read_text("utf-8").splitlines():
        score = json.loads(line) if line else None
        if not score or score.get("basis") != "REVIEWED" or "expected_families" not in score:
            continue
        result = results.get((score["case_id"], score["variant"]))
        if result is not None:
            rows.extend(rows_for(result, score))
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(buffer.getvalue(), "utf-8")
    summary = Counter((row["variant"], row["stage"]) for row in rows)
    for (variant, name), count in sorted(summary.items()):
        print(f"{variant:16} {name:24} {count}")


if __name__ == "__main__":
    main(sys.argv[1:])
