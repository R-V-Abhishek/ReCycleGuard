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
