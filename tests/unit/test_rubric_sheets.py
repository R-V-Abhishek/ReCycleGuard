import csv
import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "make_rubric_sheets", Path(__file__).parents[2] / "scripts" / "make_rubric_sheets.py"
)
sheets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sheets)


def finding():
    return {
        "issue_type": "F07_PAID_NO_TRANSFER",
        "advisory_status": "REQUIRES_EXPERT_REVIEW",
        "next_action": {"description": "Request the transfer record"},
        "fact_refs": [{"ref_id": "observation:one"}],
    }


def build(tmp_path, trials):
    output = tmp_path / "out"
    (output / "results").mkdir(parents=True)
    rows = []
    for index, (case, variant, with_report) in enumerate(trials):
        digest = f"{index:064x}"
        report = {
            "report": {"rendered_markdown": "# Baseline reconciliation report"},
            "findings": [finding()],
        }
        result = {"case_id": case, "requested_variant": variant, "run_id": f"run:{index}"}
        if with_report:
            result["report"] = report
        (output / "results" / f"{digest}.json").write_text(json.dumps(result))
        rows.append(
            {
                "trial_id": f"{case}|{variant}|r1",
                "status": "SUCCESS" if with_report else "FAILED",
                "result_digest": digest,
            }
        )
    (output / "ledger.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return output


def test_sheets_hide_variant_and_trial_and_are_reproducible(tmp_path, capsys):
    output = build(
        tmp_path,
        [
            ("case_a", "ADAPTIVE", True),
            ("case_a", "FIXED_RETRIEVAL", True),
            ("case_b", "ADAPTIVE", False),
        ],
    )
    for name in ("one", "two"):
        sheets.main([str(output), str(tmp_path / name), "--seed", "s", "--double-fraction", "0.5"])
    summary = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert summary == {"items": 2, "double_scored": 1, "without_report": 1}
    one, two = (
        (tmp_path / "one").joinpath("scorer_a.csv"),
        (tmp_path / "two").joinpath("scorer_a.csv"),
    )
    assert one.read_bytes() == two.read_bytes()
    text = one.read_text()
    assert not any(
        word in text for word in ("ADAPTIVE", "FIXED_RETRIEVAL", "|r1", "run:", "case_a")
    )
    rows = list(csv.DictReader(one.open()))
    assert {r["case_label"] for r in rows} == {sheets.case_label("s", "case_a")}
    assert all(r["citation_support"] == "" for r in rows)
    key = json.loads((tmp_path / "one" / "key.json").read_text())
    assert sorted(key.values()) == ["case_a|ADAPTIVE|r1", "case_a|FIXED_RETRIEVAL|r1"]
    assert json.loads((tmp_path / "one" / "case_map.json").read_text()) == {
        sheets.case_label("s", "case_a"): "case_a"
    }


def brief(source, status="ACCEPTED", reason=None, revision="finding_revision:one"):
    accepted = status == "ACCEPTED"
    return {
        "finding_revision_id": revision,
        "source": source,
        "status": status,
        "reason": reason,
        "what_to_check": f"{source.lower()} check" if accepted else None,
        "explanation": f"{source.lower()} explanation" if accepted else None,
        "evidence_request": f"{source.lower()} request" if accepted else None,
        "evidence_refs": [{"ref_id": "observation:one"}] if accepted else [],
        "figures": [{"label": "Required", "value": "100.0000 KG"}] if accepted else [],
        "label": "Advisory, model-drafted" if source == "MODEL" else "Template brief",
    }


def test_brief_sheets_show_two_unlabelled_briefs_and_count_the_rest(tmp_path, capsys):
    output = build(tmp_path, [("case_a", "ADAPTIVE", True), ("case_b", "ADAPTIVE", True)])
    results = sorted((output / "results").iterdir())
    briefed = [
        (brief("MODEL"), "finding_revision:one"),
        (brief("MODEL", "REJECTED", "DIGITS_IN_TEXT"), "finding_revision:one"),
    ]
    for path, (model, revision) in zip(results, briefed, strict=True):
        data = json.loads(path.read_text())
        data["report"]["findings"][0].update(
            finding_revision_id=revision, priority_basis="A payment has no transfer."
        )
        data["briefs"] = {"model_briefs": [model], "template_briefs": [brief("TEMPLATE")]}
        path.write_text(json.dumps(data))
    sheets.main([str(output), str(tmp_path / "b"), "--seed", "s", "--briefs", "1"])
    summary = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert summary["items"] == 1 and summary["model_briefs"] == {
        "ACCEPTED": 1,
        "REJECTED:DIGITS_IN_TEXT": 1,
    }
    (row,) = list(csv.DictReader((tmp_path / "b" / "scorer_a.csv").open()))
    text = (tmp_path / "b" / "scorer_a.csv").read_text()
    assert not any(w in text for w in ("Advisory", "Template brief", "|r1", "case_a", "MODEL"))
    assert "100.0000 KG" in text and "A payment has no transfer." in text
    key = json.loads((tmp_path / "b" / "key.json").read_text())
    (sides,) = key.values()
    assert sides["trial_id"] == "case_a|ADAPTIVE|r1"
    assert {sides["brief_1"], sides["brief_2"]} == {"MODEL", "TEMPLATE"}
    shown = {sides["brief_1"]: row["brief_1_text"], sides["brief_2"]: row["brief_2_text"]}
    assert shown["MODEL"].startswith("What to check: model check")
    assert shown["TEMPLATE"].startswith("What to check: template check")
    assert json.loads((tmp_path / "b" / "brief_outcomes.json").read_text()) == {
        "ACCEPTED": 1,
        "REJECTED:DIGITS_IN_TEXT": 1,
    }
