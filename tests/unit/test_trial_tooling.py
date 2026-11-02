"""Evaluation tooling with stubs: no model, and no held-out case is opened or generated here."""

import ast
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks.evaluation.bundles import open_bundle, write_bundle
from benchmarks.evaluation.taxonomy import (
    BUDGET_STOP,
    INFRASTRUCTURE,
    MODEL_REASONING,
    MODEL_SCHEMA,
    NOT_RUN,
    ORACLE,
    PARSER,
    TIMEOUT,
    classify_failure,
)
from benchmarks.evaluation.trials import (
    Coordinator,
    Ledger,
    TrialOutcome,
    build_schedule,
    protocol_schedule,
    verify_seals,
)

ROOT = Path(__file__).resolve().parents[2]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def run_trials(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return script("run_trials")


def test_controls_run_once_after_trials_and_canaries_bracket_the_session():
    schedule = build_schedule(["a", "b"], ("V1", "V2"), 2, controls=("V0", "SC"), canaries=["c"])
    ids = [spec.trial_id for spec in schedule]
    assert ids[:2] == ["c|V1|canary-start", "c|V2|canary-start"]
    assert ids[-2:] == ["c|V1|canary-end", "c|V2|canary-end"]
    assert [i for i in ids if "|V0|" in i or "|SC|" in i] == [
        "a|V0|r1",
        "a|SC|r1",
        "b|V0|r1",
        "b|SC|r1",
    ]
    assert {spec.role for spec in schedule if "canary" in spec.trial_id} == {"CANARY"}
    assert [spec.position for spec in schedule] == list(range(len(schedule)))


def test_adding_no_controls_keeps_the_existing_schedule():
    plain = build_schedule(["a", "b"], ("V1", "V2"), 1)
    assert [s.trial_id for s in plain] == ["a|V2|r1", "a|V1|r1", "b|V1|r1", "b|V2|r1"]
    assert plain == protocol_schedule(
        {"case_ids": ["a", "b"], "variants": ["V1", "V2"], "repeats": 1}
    )


@pytest.mark.parametrize(
    "arguments",
    [
        {"controls": ("V1",)},
        {"controls": ("V0", "V0")},
        {"canaries": ["a"]},
    ],
)
def test_invalid_controls_and_canaries_are_refused(arguments):
    with pytest.raises(ValueError):
        build_schedule(["a"], ("V1", "V2"), 1, **arguments)


def test_blocked_output_is_terminal_and_never_called_success(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    schedule = build_schedule(["a"], ("V1", "V2"), 1)
    Coordinator(schedule, ledger, lambda _: TrialOutcome(status="BLOCKED"), tmp_path / "K").run()
    assert ledger.terminal() == {spec.trial_id for spec in schedule}
    assert "SUCCESS" not in {row["status"] for row in ledger.rows()}


def test_scripts_run_without_pythonpath():
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    for name in ("run_trials", "score_trials", "make_tables"):
        done = subprocess.run(
            [sys.executable, str(ROOT / f"scripts/{name}.py"), "--help"],
            capture_output=True,
            text=True,
            env=env,
            cwd=ROOT.parent,
            check=False,
        )
        assert "ModuleNotFoundError" not in done.stderr, done.stderr


def test_bundle_round_trip_and_tamper_detection(tmp_path):
    root = tmp_path / "root"
    (root / "blobs").mkdir(parents=True)
    (root / "application.sqlite").write_bytes(b"sqlite")
    (root / "blobs/one").write_bytes(b"blob")
    output = tmp_path / "output"
    digest = write_bundle(root, output / "bundles")
    opened = open_bundle(output, digest, tmp_path / "opened")
    assert (opened / "blobs/one").read_bytes() == b"blob"
    with pytest.raises(ValueError, match="fresh"):
        open_bundle(output, digest, tmp_path / "opened")
    Ledger(output / "ledger.jsonl").append(
        {"trial_id": "a|V1|r1", "status": "SUCCESS", "bundle_digest": digest}
    )
    assert verify_seals(output) == 1
    (output / f"bundles/{digest}.zip").write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        verify_seals(output)
    with pytest.raises(ValueError, match="changed"):
        open_bundle(output, digest, tmp_path / "again")


def row(**changes):
    return {"success": False, "not_scored_reason": None, "missing_abstentions": []} | changes


def result(status="AWAITING_REVIEW", stop=None, calls=(), rejected=()):
    return {
        "status": status,
        "stop_reason": stop,
        "calls": list(calls),
        "rejected_actions": list(rejected),
        "report": None,
    }


def call(kind, *codes):
    return {
        "kind": kind,
        "event_type": f"graph.{kind.lower()}.x.result",
        "issue_codes": list(codes),
    }


@pytest.mark.parametrize(
    ("score", "ledger", "sealed", "expected"),
    [
        (row(success=True), "SUCCESS", result(), None),
        (row(not_scored_reason="NO_ORACLE"), "SUCCESS", result(), ORACLE),
        (row(), None, None, NOT_RUN),
        (row(), "NOT_RUN", None, NOT_RUN),
        (row(), "INFRA_FAILED", None, INFRASTRUCTURE),
        (row(), "FAILED", result("FAILED", calls=[call("MODEL", "PROVIDER_TIMEOUT")]), TIMEOUT),
        (row(), "SUCCESS", result(stop="BUDGET_EXHAUSTED"), BUDGET_STOP),
        (row(), "SUCCESS", result("BLOCKED_INPUT"), PARSER),
        (
            row(),
            "FAILED",
            result("FAILED", calls=[call("MODEL", "PROVIDER_INVALID_OUTPUT")]),
            MODEL_SCHEMA,
        ),
        (row(), "FAILED", result("FAILED", rejected=["op"]), MODEL_SCHEMA),
        (row(), "BLOCKED", result("BLOCKED_OUTPUT"), MODEL_SCHEMA),
        (row(), "SUCCESS", result(), MODEL_REASONING),
    ],
)
def test_each_failure_gets_exactly_one_class(score, ledger, sealed, expected):
    assert classify_failure(score, ledger, sealed) == expected


def test_failure_classes_cover_the_protocol_taxonomy():
    from benchmarks.evaluation import taxonomy

    text = (ROOT / "docs/evaluation/PROTOCOL.md").read_text("utf-8")
    section = text[text.index("## 7. Failure taxonomy") : text.index("## 8.")]
    for name in taxonomy.CLASSES:
        if name != taxonomy.NOT_RUN:
            assert name in section


def test_canaries_report_drift_between_session_ends(tmp_path):
    scoring = script("score_trials")
    results = tmp_path / "results"
    results.mkdir()

    def sealed(status):
        raw = json.dumps(
            {
                "status": status,
                "stop_reason": None,
                "budget": {"model_calls": 3},
                "report": None,
            }
        ).encode()
        digest = hashlib.sha256(raw).hexdigest()
        (results / f"{digest}.json").write_bytes(raw)
        return digest

    schedule = build_schedule(["a"], ("V1", "V2"), 1, canaries=["c"])
    rows = [
        {"trial_id": "c|V1|canary-start", "status": "SUCCESS", "result_digest": sealed("OK")},
        {"trial_id": "c|V1|canary-end", "status": "SUCCESS", "result_digest": sealed("OK")},
        {"trial_id": "c|V2|canary-start", "status": "SUCCESS", "result_digest": sealed("OK")},
        {"trial_id": "c|V2|canary-end", "status": "SUCCESS", "result_digest": sealed("OTHER")},
    ]
    report = scoring.compare_canaries(schedule, rows, tmp_path)
    assert report["checked"] == 4 and report["drifted"] == ["c|V2|canary-end"]
    baseline = dict(report["signatures"])
    assert scoring.compare_canaries(schedule, rows, tmp_path, baseline)["drifted"] == [
        "c|V2|canary-end"
    ]
    baseline["c|V1|canary-start"] = {"status": "DIFFERENT"}
    assert (
        "c|V1|canary-start"
        in scoring.compare_canaries(schedule, rows, tmp_path, baseline)["drifted"]
    )


def test_a_missing_canary_is_drift_not_a_pass(tmp_path):
    scoring = script("score_trials")
    schedule = build_schedule(["a"], ("V1", "V2"), 1, canaries=["c"])
    assert "c|V1|canary-end" in scoring.compare_canaries(schedule, [], tmp_path)["drifted"]


def freeze_file(tmp_path, **values):
    path = tmp_path / "freeze.json"
    path.write_text(
        json.dumps(
            {
                "format": "recycleguard-freeze-v1",
                "scope": values.pop("scope", "INCLUDES_REAL_MODEL"),
                "git": {"commit": "x", "dirty": False},
                "files": {},
                "trees": {},
                "values": values,
            }
        )
    )
    return path


@pytest.fixture
def passing_verification(run_trials, monkeypatch):
    monkeypatch.setattr(run_trials, "verify_freeze", lambda *a, **k: [])
    return run_trials


def test_held_out_refuses_a_changed_or_wrong_freeze(run_trials, tmp_path):
    protocol = tmp_path / "protocol.json"
    protocol.write_text("{}")
    root = tmp_path / "heldout"
    root.mkdir()
    # This repository's HEAD is not commit "x", so real verification must refuse it.
    with pytest.raises(SystemExit, match="held-out run refused"):
        run_trials.require_verified_freeze(
            freeze_file(
                tmp_path,
                protocol_sha256=hashlib.sha256(b"{}").hexdigest(),
                held_out_visible_root=str(root),
            ),
            protocol,
        )


@pytest.mark.parametrize(
    ("values", "problem"),
    [
        ({"protocol_sha256": "wrong"}, "exact protocol"),
        ({"scope": "NON_MODEL_ONLY"}, "does not include the real model"),
        ({"held_out_visible_root": None}, "held-out visible root"),
    ],
)
def test_held_out_needs_real_model_scope_exact_protocol_and_root(
    passing_verification, tmp_path, values, problem
):
    protocol = tmp_path / "protocol.json"
    protocol.write_text("{}")
    root = tmp_path / "heldout"
    root.mkdir()
    base = {
        "protocol_sha256": hashlib.sha256(b"{}").hexdigest(),
        "held_out_visible_root": str(root),
    }
    with pytest.raises(SystemExit, match=problem):
        passing_verification.require_verified_freeze(
            freeze_file(tmp_path, **(base | values)), protocol
        )


def test_held_out_returns_the_frozen_root_when_everything_matches(passing_verification, tmp_path):
    protocol = tmp_path / "protocol.json"
    protocol.write_text("{}")
    root = tmp_path / "heldout"
    root.mkdir()
    returned = passing_verification.require_verified_freeze(
        freeze_file(
            tmp_path,
            protocol_sha256=hashlib.sha256(b"{}").hexdigest(),
            held_out_visible_root=str(root),
        ),
        protocol,
    )
    assert returned == root.resolve()


def test_held_out_cases_are_checked_against_the_stubbed_list(run_trials, monkeypatch):
    monkeypatch.setattr(run_trials, "held_out_case_ids", lambda: {"case_h"})
    run_trials.require_held_out_cases(["case_h"])
    with pytest.raises(SystemExit, match="not held-out"):
        run_trials.require_held_out_cases(["case_d"])


def test_fixture_dry_run_refuses_the_held_out_flag(tmp_path):
    done = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_trials.py"),
            str(tmp_path / "p.json"),
            str(tmp_path / "o"),
            "--fixture-model",
            "--held-out",
            str(tmp_path / "f.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode != 0 and "never use held-out" in done.stderr


def test_sandbox_grant_overlapping_an_evaluator_path_is_refused(run_trials, tmp_path):
    evaluator = tmp_path / "benchmarks" / "evaluation"
    evaluator.mkdir(parents=True)
    other = tmp_path / "wheel"
    other.mkdir()
    run_trials.require_separate_grants((other.resolve(),), [evaluator])
    for grant in (tmp_path, evaluator, evaluator / "inner"):
        with pytest.raises(SystemExit, match="overlaps evaluator"):
            run_trials.require_separate_grants((grant.resolve(),), [evaluator])


def test_read_grants_name_single_files_not_the_directories_around_them(run_trials, tmp_path):
    from tests.unit.test_local_model import configuration

    model = tmp_path / "model"
    model.mkdir()
    settings = configuration((None, "http://127.0.0.1:8080/v1/completions", model), tmp_path)
    config_dir = tmp_path / "data"
    config_dir.mkdir()
    config_path = config_dir / "local-model.json"
    config_path.write_text(settings.model_dump_json(), "utf-8")
    reads, port = run_trials.sandbox_reads(config_path, Path(sys.executable))
    assert port == 8080
    assert config_path.resolve() in reads and config_dir.resolve() not in reads
    assert settings.runtime_lock_path.resolve() in reads
    assert settings.runtime_lock_path.resolve().parent not in reads


def test_each_evaluator_tree_and_session_result_gets_its_own_probe(run_trials, tmp_path):
    (tmp_path / "results").mkdir()
    (tmp_path / "ledger.jsonl").touch()
    probed = {path.resolve() for path in run_trials.forbidden_paths(tmp_path)}
    for name in ("benchmarks/evaluation", "scripts", "tests", ".git", "docs/evaluation"):
        assert (ROOT / name).resolve() in probed
    assert {(tmp_path / "results").resolve(), (tmp_path / "ledger.jsonl").resolve()} <= probed


def test_child_gives_test_adapters_only_to_controls_and_a_model_only_to_real_variants(tmp_path):
    child = script("trial_child")
    (tmp_path / "config.json").write_text("{}")
    config = tmp_path / "config.json"
    real = child.application_options("ADAPTIVE", tmp_path, tmp_path, config, "t")
    assert real.settings.mode == "runtime" and not real.settings.enable_test_adapters
    assert real.model_config_path == config and not real.test_exchanges
    for control in child.CONTROL_EXCHANGES:
        options = child.application_options(control, tmp_path, tmp_path, config, "t")
        assert options.settings.enable_test_adapters and options.model_config_path is None
        assert child.trial_body(control)["mode"] == "SCRIPTED_TEST"
    with pytest.raises(ValueError, match="needs its model"):
        child.application_options("FIXED_RETRIEVAL", tmp_path, tmp_path, None, "t")
    with pytest.raises(ValueError, match="unknown variant"):
        child.application_options("V9", tmp_path, tmp_path, config, "t")


def test_call_summary_keeps_codes_and_no_model_text():
    child = script("trial_child")
    events = [
        {
            "kind": "MODEL_RESULT",
            "event_type": "graph.model.plan.result",
            "operation_id": "op",
            "status": "FAILED",
            "issues": [{"code": "PROVIDER_INVALID_OUTPUT", "message": "model said secret"}],
            "exact_response": "model said secret",
        },
        {
            "kind": "TOOL_OR_STAGE_RESULT",
            "event_type": "graph.tool.tool.result",
            "operation_id": "t",
            "status": "SUCCESS",
            "issues": [],
        },
        {"kind": "AUDIT", "event_type": "graph.action_rejected.result", "operation_id": "r"},
    ]
    calls, rejected = child.call_summary(events)
    assert [c["kind"] for c in calls] == ["MODEL", "TOOL"] and rejected == ["r"]
    assert "secret" not in json.dumps(calls)


def test_split_is_stratified_two_to_one_and_stable():
    split = script("make_dev_split")
    singles = [f"s{i}" for i in range(16)]
    combined = [f"c{i}" for i in range(8)]
    tuning, checking = split.split_cases([singles, combined])
    assert len(tuning) == 16 and len(checking) == 8
    assert sum(case.startswith("c") for case in checking) == 3
    assert not set(tuning) & set(checking)
    assert (tuning, checking) == split.split_cases([singles, combined])


def test_committed_split_uses_every_dev_case_once():
    protocols = ROOT / "docs/checkpoints/mg1/protocols"
    tuning = json.loads((protocols / "tuning-16.json").read_text("utf-8"))["case_ids"]
    checking = json.loads((protocols / "checking-8.json").read_text("utf-8"))["case_ids"]
    every = json.loads((protocols / "reliability.json").read_text("utf-8"))["case_ids"]
    assert len(tuning) == 16 and len(checking) == 8
    assert sorted(tuning + checking) == sorted(every)


def test_new_tooling_files_stay_outside_the_investigator_import_path():
    source = (ROOT / "scripts/trial_child.py").read_text("utf-8")
    imported = {
        node.module if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }
    assert not any(name.split(".")[0] in {"benchmarks", "tests"} for name in imported)
