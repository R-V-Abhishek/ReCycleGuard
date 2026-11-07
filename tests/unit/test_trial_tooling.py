"""Evaluation tooling with stubs: no model, and no held-out case is opened or generated here."""

import ast
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import get_args

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
from recycleguard.contracts.results import FaultFamily

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
    for name in ("run_trials", "score_trials", "make_tables", "make_rubric_sheets"):
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


def _inspection(network="container:recycleguard-model", **host):
    mounts = [
        {"Type": "volume", "Source": "trial", "Target": "/visible", "ReadOnly": True},
        {"Type": "volume", "Source": "trial", "Target": "/program", "ReadOnly": True},
        {"Type": "volume", "Source": "trial", "Target": "/runtime"},
        {
            "Type": "volume",
            "Source": "provenance",
            "Target": "/models/provenance",
            "ReadOnly": True,
        },
    ]
    return {
        "Config": {"User": "10001:10001", "Env": ["PATH=/opt/venv/bin"]},
        "HostConfig": {
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "NetworkMode": network,
            "Mounts": mounts,
            **host,
        },
    }


def test_a_correct_trial_container_passes_inspection():
    from recycleguard.isolated_runtime import verify_trial_inspection

    assert (
        verify_trial_inspection(
            _inspection(), "container:recycleguard-model", {"trial", "provenance"}
        )
        == []
    )


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"Privileged": True}, "privileged"),
        ({"ReadonlyRootfs": False}, "writable"),
        ({"CapDrop": []}, "capabilities"),
        ({"Binds": ["/var/run/docker.sock:/var/run/docker.sock"]}, "bind"),
        ({"Devices": [{"PathOnHost": "/dev/nvidia0"}]}, "devices"),
        ({"NetworkMode": "bridge"}, "network mode"),
    ],
)
def test_a_weakened_trial_container_is_refused(change, expected):
    from recycleguard.isolated_runtime import verify_trial_inspection

    problems = verify_trial_inspection(
        _inspection(**change), "container:recycleguard-model", {"trial", "provenance"}
    )
    assert any(expected in problem for problem in problems)


def test_an_extra_mount_or_writable_evidence_or_foreign_volume_is_refused():
    from recycleguard.isolated_runtime import verify_trial_inspection

    network, volumes = "container:recycleguard-model", {"trial", "provenance"}
    inspection = _inspection()
    inspection["HostConfig"]["Mounts"].append(
        {"Type": "volume", "Source": "trial", "Target": "/evaluator", "ReadOnly": True}
    )
    assert any("mounts are" in p for p in verify_trial_inspection(inspection, network, volumes))

    inspection = _inspection()
    inspection["HostConfig"]["Mounts"][0] = {
        "Type": "volume",
        "Source": "trial",
        "Target": "/visible",
    }
    assert any("read-only" in p for p in verify_trial_inspection(inspection, network, volumes))

    inspection = _inspection()
    inspection["HostConfig"]["Mounts"][3]["Source"] = "evaluator"
    assert any(
        "not an allowed volume" in p for p in verify_trial_inspection(inspection, network, volumes)
    )

    inspection = _inspection()
    inspection["Config"]["User"] = "0"
    assert any("root" in p for p in verify_trial_inspection(inspection, network, volumes))


def test_a_control_container_has_no_model_mount_or_network():
    from recycleguard.isolated_runtime import verify_trial_inspection

    inspection = _inspection("none")
    assert verify_trial_inspection(inspection, "none", {"trial", "provenance"}) != []
    inspection["HostConfig"]["Mounts"].pop()
    assert verify_trial_inspection(inspection, "none", {"trial", "provenance"}) == []


def test_trial_container_arguments_mount_only_this_attempt_and_refuse_bad_paths():
    from recycleguard.isolated_runtime import trial_container_arguments

    command = trial_container_arguments(
        "trial-a", "image", "none", "data", "s/trials/t0000/attempt-1", None, ["-I", "/program/c"]
    )
    text = " ".join(command)
    assert "volume-subpath=s/trials/t0000/attempt-1/visible,readonly" in text
    assert "volume-subpath=s/trials/t0000/attempt-1/program,readonly" in text
    assert "target=/runtime,volume-subpath=s/trials/t0000/attempt-1/runtime " in text
    assert "/models/provenance" not in text and "docker.sock" not in text
    assert command[command.index("--network") + 1] == "none"
    assert {"--read-only", "--cap-drop", "ALL", "no-new-privileges"} <= set(command)
    assert command[-3:] == ["image", "-I", "/program/c"]
    for bad in ("a/../b", "a,target=/x", "a\nb"):
        with pytest.raises(ValueError):
            trial_container_arguments("t", "image", "none", "data", bad, None, [])


def test_container_command_gives_a_model_only_to_real_variants(run_trials, tmp_path, monkeypatch):
    spec = run_trials.protocol_schedule(
        {
            "case_ids": ["case_x"],
            "repeats": 1,
            "variants": ["FIXED_RETRIEVAL", "ADAPTIVE"],
            "controls": ["V0"],
        }
    )
    monkeypatch.setattr(
        run_trials,
        "prepare_attempt",
        lambda spec, attempt, fixtures: (
            attempt / "visible",
            attempt / "runtime",
            attempt / "program/trial_child.py",
        ),
    )
    monkeypatch.setattr(run_trials.os, "geteuid", lambda: 1, raising=False)
    config = Path("/models/provenance/m/local-model.json")
    launch = run_trials.Launch(run_trials.DOCKERED, config)
    by_variant = {}
    for index, item in enumerate(spec):
        attempt = tmp_path / f"attempt-{index}"
        by_variant[item.variant] = run_trials.container_command(
            launch, item, attempt, root=tmp_path.resolve()
        )
    real, _, real_network, _ = by_variant["ADAPTIVE"]
    assert real_network == "container:recycleguard-model"
    assert "--container" in real and config.as_posix() in real
    assert "--sandboxed" not in real
    control, _, control_network, _ = by_variant["V0"]
    assert control_network == "none"
    assert "--config" not in control
    assert "/models/provenance" not in " ".join(control)
    assert "--ablate" not in real and "--ablate" not in control
    # An ablated session switches off the same families in every trial, controls included.
    families = ["F09_EXPIRED_CANCELLED", "F02_OVERLAPPING_EXPORT"]
    for index, item in enumerate(spec):
        command, *_ = run_trials.container_command(
            launch, item, tmp_path / f"ablated-{index}", root=tmp_path.resolve(), ablated=families
        )
        at = command.index("--ablate")
        assert json.loads(command[at + 1]) == sorted(families)


def test_docker_session_refuses_output_outside_the_volume_and_a_running_api(
    run_trials, monkeypatch
):
    with pytest.raises(SystemExit, match="must be under"):
        run_trials.prepare_docker_session(Path("/elsewhere/out"))

    calls = []

    def fake_run(command, **_):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="abc123\n", stderr="")

    monkeypatch.setattr(run_trials.subprocess, "run", fake_run)
    with pytest.raises(SystemExit, match="demo API"):
        run_trials.prepare_docker_session(run_trials.TRIAL_ROOT / "session")


def test_a_timed_out_trial_container_is_removed(run_trials, tmp_path, monkeypatch):
    calls = []

    def fake_run(command, **_):
        calls.append(command)
        if command[:2] == ["docker", "start"]:
            raise subprocess.TimeoutExpired(command, 1)
        inspection = {**_inspection("container:model-id"), "Id": "model-id"}
        stdout = json.dumps([inspection]).encode() if command[1] == "inspect" else b""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=b"")

    monkeypatch.setattr(run_trials.subprocess, "run", fake_run)
    monkeypatch.setattr(run_trials, "TRIAL_VOLUME", "trial")
    monkeypatch.setattr(run_trials, "PROVENANCE_VOLUME", "provenance")
    with (tmp_path / "log").open("wb") as log, pytest.raises(subprocess.TimeoutExpired):
        run_trials.run_container(
            ["docker", "create"], "t", "container:recycleguard-model", tmp_path, log
        )
    assert calls[-1] == ["docker", "rm", "--force", "t"]
    assert (tmp_path / "isolation-inspect.json").is_file()


def test_a_container_failing_inspection_never_starts(run_trials, tmp_path, monkeypatch):
    calls = []

    def fake_run(command, **_):
        calls.append(command)
        inspection = {**_inspection("container:model-id", Privileged=True), "Id": "model-id"}
        stdout = json.dumps([inspection]).encode() if command[1] == "inspect" else b""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=b"")

    monkeypatch.setattr(run_trials.subprocess, "run", fake_run)
    monkeypatch.setattr(run_trials, "TRIAL_VOLUME", "trial")
    monkeypatch.setattr(run_trials, "PROVENANCE_VOLUME", "provenance")
    with (tmp_path / "log").open("wb") as log, pytest.raises(SystemExit, match="privileged"):
        run_trials.run_container(
            ["docker", "create"], "t", "container:recycleguard-model", tmp_path, log
        )
    assert not any(command[:2] == ["docker", "start"] for command in calls)
    assert calls[-1] == ["docker", "rm", "--force", "t"]


def test_parallel_sessions_label_and_clean_up_only_their_own_containers(
    run_trials, tmp_path, monkeypatch
):
    from recycleguard.isolated_runtime import trial_container_arguments, verify_trial_inspection

    first = run_trials.session_id(run_trials.TRIAL_ROOT / "sweep-a")
    assert first != run_trials.session_id(run_trials.TRIAL_ROOT / "sweep-b")
    command = trial_container_arguments(
        "t", "image", "none", "data", "s/trials/t0000/attempt-1", None, [], session=first
    )
    assert f"recycleguard.session={first}" in command
    with pytest.raises(ValueError, match="session label"):
        trial_container_arguments("t", "image", "none", "data", "s", None, [], session="x")

    inspection = _inspection()
    network, volumes = "container:recycleguard-model", {"trial", "provenance"}
    problems = verify_trial_inspection(inspection, network, volumes, first)
    assert any("session label" in problem for problem in problems)
    inspection["Config"]["Labels"] = {"recycleguard.session": first}
    assert verify_trial_inspection(inspection, network, volumes, first) == []

    calls = []

    def fake_run(command, **_):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(run_trials.subprocess, "run", fake_run)
    run_trials.prepare_docker_session(run_trials.TRIAL_ROOT / "sweep-a")
    listing = next(command for command in calls if "--all" in command)
    assert f"label=recycleguard.session={first}" in listing
    assert "label=recycleguard.trial=1" in listing


@pytest.fixture
def sweep(monkeypatch, tmp_path):
    module = script("run_sweep")
    monkeypatch.setattr(module, "WORK", tmp_path)
    return module


SWEEP = {
    "sweep_version": "mg1-prompt-sweep",
    "name": "sweep-t",
    "protocol": "docs/checkpoints/mg1/protocols/tuning-16.json",
    "model_root": "/models/provenance/m",
    "slots": 2,
    "prompts": ["u01_non_thinking_v7", "u01_non_thinking_v8a", "u01_non_thinking_v8b"],
}


def test_committed_sweeps_are_valid_and_never_touch_checking_cases(sweep):
    for path in sorted((ROOT / "docs/checkpoints/mg1/sweeps").glob("*.json")):
        loaded = sweep.load_sweep(path)
        assert path.stem == loaded["name"]


def test_a_sweep_refuses_checking_cases_unknown_prompts_and_bad_names(sweep, tmp_path):
    def attempt(**change):
        path = tmp_path / "s.json"
        path.write_text(json.dumps({**SWEEP, **change}))
        return sweep.load_sweep(path)

    assert attempt()["slots"] == 2
    with pytest.raises(SystemExit, match="checking case"):
        attempt(protocol="docs/checkpoints/mg1/protocols/checking-8.json")
    with pytest.raises(SystemExit, match="no prompt file"):
        attempt(prompts=["u01_missing"])
    with pytest.raises(SystemExit, match="distinct"):
        attempt(prompts=["u01_non_thinking_v7", "u01_non_thinking_v7"])
    with pytest.raises(SystemExit, match="lowercase"):
        attempt(name="../escape")
    with pytest.raises(SystemExit, match="slots"):
        attempt(slots=9)


class _Process:
    def __init__(self, polls):
        self.polls, self.done = polls, False

    def poll(self):
        code = self.polls.pop(0) if self.polls else 0
        self.done = code is not None
        return code


def test_a_sweep_runs_at_most_slots_sessions_at_once(sweep, tmp_path):
    folder = tmp_path / "sweep-t"
    folder.mkdir()
    started, processes = [], []

    def launch(command, **_):
        assert sum(not process.done for process in processes) < SWEEP["slots"]
        assert "--docker" in command and "--config" in command
        started.append(command)
        processes.append(_Process([None, 0]))
        return processes[-1]

    configs = {prompt: Path(f"/c/{prompt}.json") for prompt in SWEEP["prompts"]}
    codes = sweep.run_sessions(SWEEP, folder, configs, launch=launch, poll=0)
    assert codes == dict.fromkeys(SWEEP["prompts"], 0)
    assert [Path(command[3]).name for command in started] == [
        f"sweep-t-{prompt}" for prompt in SWEEP["prompts"]
    ]
    assert (folder / "u01_non_thinking_v7.log").is_file()


def test_a_sweep_kill_reaches_every_running_session_and_starts_no_more(sweep, tmp_path):
    folder = tmp_path / "sweep-t"
    folder.mkdir()
    (folder / "KILL").touch()
    configs = {prompt: Path(f"/c/{prompt}.json") for prompt in SWEEP["prompts"]}
    assert sweep.run_sessions(SWEEP, folder, configs, launch=None, poll=0) == {}

    (folder / "KILL").unlink()
    started = []

    def launch(command, **_):
        started.append(command)
        (folder / "KILL").touch()  # someone stops the sweep while the first sessions run
        return _Process([None, None, 0])

    sweep.run_sessions(SWEEP, folder, configs, launch=launch, poll=0)
    assert len(started) == 2  # the third prompt never starts
    for prompt in SWEEP["prompts"][:2]:
        assert (tmp_path / f"sweep-t-{prompt}" / "KILL").is_file()
    # Resuming after KILL is removed deletes only the KILL files the sweep itself created.
    (folder / "KILL").unlink()
    sweep.run_sessions(SWEEP, folder, configs, launch=lambda c, **_: _Process([0]), poll=0)
    assert not (tmp_path / f"sweep-t-{SWEEP['prompts'][0]}" / "KILL").exists()


def test_a_sweep_refuses_a_server_with_other_slots(sweep, tmp_path, monkeypatch):
    import recycleguard.local_model as local_model
    from recycleguard.local_model import llama_server_flags

    model = tmp_path / "model"
    model.mkdir()
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"server_flags": llama_server_flags(2)}))
    session = model / "server-session.json"
    session.write_text(json.dumps({"server_flags": llama_server_flags(1)}))

    class Config:
        @staticmethod
        def model_validate_json(raw):
            return type("C", (), json.loads(raw))

    monkeypatch.setattr(local_model, "LocalModelConfig", Config)
    with pytest.raises(SystemExit, match="SLOTS"):
        sweep.require_server({**SWEEP, "model_root": str(model)}, {"p": config})
    session.write_text(json.dumps({"server_flags": llama_server_flags(2)}))
    sweep.require_server({**SWEEP, "model_root": str(model)}, {"p": config})


def test_the_comparison_copies_existing_tables_side_by_side(sweep, tmp_path):
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "t1_primary_success.csv").write_text(
        "variant,scheduled,scored,successes,success_rate,ci95_low,ci95_high,preflight_blocks\n"
        "ADAPTIVE,16,16,3,0.1875,0.05,0.4,0\nFIXED_RETRIEVAL,16,16,2,0.125,0.0,0.3,0\n"
    )
    (tables / "t3_proposals_rejected.csv").write_text(
        "variant,reason,proposals\nADAPTIVE,AUTHORITY_TEXT,2\nADAPTIVE,UNCITED,1\n"
    )
    (tables / "t6_efficiency.csv").write_text(
        "variant,trials_with_result,mean_model_calls,mean_tokens,mean_wall_seconds,"
        "p50_wall_seconds,p95_wall_seconds,money\nADAPTIVE,16,4.5,9000,61.0,58.0,80.0,NA\n"
    )
    rows = list(csv_rows(sweep.compare({"u01_non_thinking_v8a": tables})))
    assert [row["variant"] for row in rows] == ["ADAPTIVE", "FIXED_RETRIEVAL"]
    adaptive = rows[0]
    assert adaptive["prompt"] == "u01_non_thinking_v8a" and adaptive["successes"] == "3"
    assert adaptive["proposals_rejected"] == "AUTHORITY_TEXT:2;UNCITED:1"
    assert adaptive["mean_model_calls"] == "4.5" and adaptive["micro_f1"] == ""
    assert list(rows[0]) == sweep.COMPARE_COLUMNS


def csv_rows(text):
    import csv
    import io

    return csv.DictReader(io.StringIO(text))


def test_configuration_names_never_collide(tmp_path):
    configure = script("configure_local_model")
    names = {
        configure.config_name(),
        configure.config_name(constrained=True),
        configure.config_name(cap=2),
        configure.config_name(prompt="u01_non_thinking_v8a"),
        configure.config_name(prompt="u01_non_thinking_v8a", slots=4),
        configure.config_name(slots=4),
        configure.config_name(prompt="u01_thinking_v1"),
        configure.config_name(prompt="u01_thinking_v1", thinking=True),
        configure.config_name(brief=True),
        configure.config_name(brief=True, slots=3),
    }
    assert len(names) == 10
    assert configure.config_name(brief=True) == "local-model-brief.json"
    assert configure.config_name(brief=True, slots=3) == "local-model-brief-s3.json"
    assert (
        configure.config_name(prompt="u01_thinking_v1", thinking=True, slots=3)
        == "local-model-u01_thinking_v1-thinking-s3.json"
    )
    assert configure.config_name(prompt="u01_non_thinking_v7") == "local-model.json"


def test_child_gives_test_adapters_only_to_controls_and_a_model_only_to_real_variants(tmp_path):
    child = script("trial_child")
    (tmp_path / "config.json").write_text("{}")
    config = tmp_path / "config.json"
    real = child.application_options("ADAPTIVE", tmp_path, tmp_path, config, "t")
    assert real.settings.mode == "runtime" and not real.settings.enable_test_adapters
    assert real.model_config_path == config and not real.test_exchanges
    # An ablated model run is an evaluation, held to the frozen budget.
    ablated = child.application_options("ADAPTIVE", tmp_path, tmp_path, config, "t", ablated=True)
    assert ablated.settings.mode == "evaluation"
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
    # The controls protocol is the same check plus the model-free baselines, nothing else.
    checking_protocol = json.loads((protocols / "checking-8.json").read_text("utf-8"))
    controls = json.loads((protocols / "checking-8-controls.json").read_text("utf-8"))
    assert controls.pop("controls") == ["V0", "SC"]
    assert controls.pop("protocol_version") != checking_protocol.pop("protocol_version")
    assert controls == checking_protocol
    # The ablated protocol is tuning-16 with every family's deterministic finding switched off.
    tuning_protocol = json.loads((protocols / "tuning-16.json").read_text("utf-8"))
    ablated = json.loads((protocols / "tuning-16-ablated.json").read_text("utf-8"))
    assert ablated.pop("controls") == ["SC"]
    assert ablated.pop("ablated_families") == list(get_args(FaultFamily))
    assert ablated.pop("protocol_version") != tuning_protocol.pop("protocol_version")
    assert ablated == tuning_protocol


def test_new_tooling_files_stay_outside_the_investigator_import_path():
    source = (ROOT / "scripts/trial_child.py").read_text("utf-8")
    imported = {
        node.module if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }
    assert not any(name.split(".")[0] in {"benchmarks", "tests"} for name in imported)


SECRET_EVIDENCE = "dossier text that must never be sealed"


def trace_events():
    decision = {
        "decision": "Supported allocations calculated",
        "evidence_data_json": '{"buckets":[],"issues":[{"code":"STALE_SNAPSHOT","severity":'
        + f'"WARNING","message":"{SECRET_EVIDENCE}"',
        "evidence_truncated": True,
    }
    assess = {
        "phase": "ASSESS",
        "action": {"allowed_operation": "compute_reconciliation"},
        "observation": {
            "stage_output": {
                "disposition": "QUALIFIED",
                "evidence_ref_ids": [],
                "calculation_ids": ["calc:1"],
                "concise_decision": decision,
            }
        },
    }
    reply = {
        "verdict": "WEAK",
        "disposition": "ABSTAIN",
        "next_check_or_stop": "stop",
        "weak_result_or_mistake": "x" * 900,
        "finding_proposal": {
            "issue_type": "F06_STALE_SNAPSHOT",
            "advisory_status": "PENDING_VERIFICATION",
            "evidence_ref_ids": ["calc:1"],
            "abstention_reason": "TEMPORAL_UNCERTAINTY",
            "withheld_claim_scopes": ["stale_portal_statement"],
            "basis": "Portal statement predates ledger events.",
        },
    }
    transport = {
        "request_body_utf8": json.dumps({"prompt": SECRET_EVIDENCE}),
        "response_body_utf8": json.dumps(
            {
                "choices": [{"finish_reason": "length", "text": "{}"}],
                "usage": {"prompt_tokens": 900, "completion_tokens": 1024},
            }
        ),
        "elapsed_seconds": 12.5,
    }
    return [
        {"kind": "PROMPT_PREPARED", "phase": "PLAN", "request": {"phase": "PLAN"}},
        {"kind": "PROMPT_PREPARED", "phase": "ASSESS", "request": assess},
        {
            "kind": "MODEL_RESULT",
            "operation_id": "operation:assess",
            "attempt_id": "attempt:0",
            "status": "SUCCESS",
            "issues": [],
            "response": {"validated_output_or_null": reply},
            "provider_trace": transport,
        },
    ]


def test_the_decision_trace_records_what_was_shown_and_why_without_evidence_text():
    child = script("trial_child")
    rows = child.decision_trace(trace_events())
    assert len(rows) == 1
    shown, reply = rows[0]["shown"], rows[0]["reply"]
    assert shown["tool"] == "compute_reconciliation" and shown["evidence_truncated"]
    assert shown["visible_issue_codes"] == ["STALE_SNAPSHOT"]
    assert shown["citable_calculation_ids"] == 1 and shown["citable_evidence_ids"] == 0
    assert reply["proposal"]["issue_type"] == "F06_STALE_SNAPSHOT"
    assert len(reply["weak_result_or_mistake"]) == 300
    assert rows[0]["transport"]["finish_reason"] == "length"
    assert SECRET_EVIDENCE not in json.dumps(rows)
    exact = child.model_calls(trace_events())
    assert SECRET_EVIDENCE in exact[0]["request_body_utf8"]  # kept in the runtime folder only
    assert "thinking_finish" not in rows[0]["transport"]
    assert "thinking_response_body_utf8" not in exact[0]


def test_a_thinking_call_reports_its_cut_but_its_reasoning_stays_in_the_runtime_folder():
    child = script("trial_child")
    reasoning = "private reasoning about the dossier"
    reply = {"choices": [{"finish_reason": "length", "text": reasoning}], "usage": {}}
    trace = {
        "response_body_utf8": json.dumps({"choices": [{"finish_reason": "stop"}], "usage": {}}),
        "thinking": {
            "request_body_utf8": "{}",
            "response_body_utf8": json.dumps(reply),
            "finish_reason": "length",
            "completion_tokens": 1024,
        },
    }
    event = {"kind": "MODEL_RESULT", "operation_id": "op", "provider_trace": trace}
    (row,) = child.decision_trace([event])
    assert row["transport"]["thinking_finish"] == "length"
    assert row["transport"]["thinking_tokens"] == 1024
    assert reasoning not in json.dumps(row)
    (exact,) = child.model_calls([event])
    assert reasoning in exact["thinking_response_body_utf8"]


def test_a_brief_call_is_traced_by_counts_and_lengths_without_its_text():
    child = script("trial_child")
    request = {
        "phase": "BRIEF",
        "finding": {"issue_type": "F07_PAID_NO_TRANSFER"},
        "citable_evidence_ref_ids": ["record:one", "record:two"],
        "evidence": [{"ref_id": "record:one", "text": SECRET_EVIDENCE}],
        "figures_shown_by_code": [{"label": "Required", "value": "100.0000 KG"}],
    }
    reply = {
        "what_to_check": "Check the private transfer wording.",
        "explanation": "A payment alone earns no credit.",
        "evidence_request": "Please send the transfer record.",
        "evidence_ref_ids": ["record:one"],
    }
    events = [
        {"kind": "PROMPT_PREPARED", "phase": "BRIEF", "request": request},
        {
            "kind": "MODEL_RESULT",
            "operation_id": "operation:brief_0",
            "status": "SUCCESS",
            "response": {"validated_output_or_null": reply},
        },
    ]
    (row,) = child.decision_trace(events)
    assert row["shown"] == {
        "phase": "BRIEF",
        "issue_type": "F07_PAID_NO_TRANSFER",
        "citable_evidence_ids": 2,
        "evidence_items": 1,
        "figures": 1,
    }
    assert row["reply"] == {
        "brief_chars": {
            "what_to_check": len(reply["what_to_check"]),
            "explanation": len(reply["explanation"]),
            "evidence_request": len(reply["evidence_request"]),
        },
        "cited_ids": 1,
    }
    text = json.dumps(row)
    assert SECRET_EVIDENCE not in text and "private transfer wording" not in text


def test_the_funnel_assigns_each_miss_to_the_stage_where_it_was_lost():
    funnel = script("funnel")
    shown = [{"shown": {"visible_issue_codes": ["STALE_SNAPSHOT"]}, "reply": {"proposal": None}}]
    proposed = [{"shown": {}, "reply": {"proposal": {"issue_type": "F06_STALE_SNAPSHOT"}}}]
    family = "F06_STALE_SNAPSHOT"
    assert funnel.stage(family, set(), proposed, {family: {"DIGITS_IN_TEXT"}})[0] == "S5_REJECTED"
    assert funnel.stage(family, set(), proposed, {})[0] == "S6_PROPOSED_LOST"
    assert funnel.stage(family, set(), shown, {})[0] == "S4_SHOWN_NOT_PROPOSED"
    assert funnel.stage(family, {"STALE_SNAPSHOT"}, [], {})[0] == "S3_COMPUTED_NOT_SHOWN"
    assert funnel.stage(family, {"STALE_SNAPSHOT"}, None, {})[0] == "S3_COMPUTED_NO_TRACE"
    assert funnel.stage(family, set(), [], {})[0] == "S1_NOT_COMPUTED"
    assert funnel.stage("F16_PROMPT_INJECTION", set(), [], {})[0] == "S0_JUDGEMENT_ONLY"


def test_the_replay_opens_thinking_only_on_recorded_prompts_and_labels_it(tmp_path):
    replay = script("replay_reasoning")
    session = tmp_path / "s"
    ledger = []
    for position, repeat in ((1, "r1"), (2, "r2")):
        runtime = session / "trials" / f"t{position:04d}" / "attempt-1" / "runtime"
        runtime.mkdir(parents=True)
        raw = json.dumps({"case_id": "case_x", "requested_variant": "ADAPTIVE", "r": repeat})
        (runtime / "result.json").write_bytes(raw.encode())
        # An attempt counts only once it has a model-call record, as a real trial does.
        (runtime / "model-calls.jsonl").write_text("")
        digest = hashlib.sha256(raw.encode()).hexdigest()
        ledger.append({"trial_id": f"case_x|ADAPTIVE|{repeat}", "result_digest": digest})
    (session / "ledger.jsonl").write_text("".join(json.dumps(row) + "\n" for row in ledger))
    # Repeats of one case are told apart by the sealed result digest, never merged.
    assert set(replay.attempts(session)) == {"case_x|ADAPTIVE|r1", "case_x|ADAPTIVE|r2"}
    runtime = session / "trials" / "t0001" / "attempt-1" / "runtime"
    prompt = "<|im_start|>system\nASSESS rules: ...<|im_start|>assistant\n" + replay.CLOSED_THINK
    calls = [
        {
            "operation_id": "operation:assess",
            "request_body_utf8": json.dumps({"prompt": prompt, "json_schema": {}, "stop": []}),
            "response_body_utf8": None,
        },
        {
            "operation_id": "operation:plan",
            "request_body_utf8": json.dumps({"prompt": "PLAN rules: x" + replay.CLOSED_THINK}),
            "response_body_utf8": None,
        },
    ]
    (runtime / "model-calls.jsonl").write_text("".join(json.dumps(c) + "\n" for c in calls))
    work = replay.jobs(tmp_path / "s", ["case_x|ADAPTIVE|r1"], "ASSESS", 10)
    assert [item["key"]["operation_id"] for item in work] == ["operation:assess"]
    job = work[0]["job"]
    assert job["prompt"].endswith("assistant\n<think>\n") and "json_schema" not in job["body"]
    assert replay.LABEL == "DIAGNOSTIC_NOT_EVIDENCE"


def test_the_census_counts_records_and_check_states_without_their_contents(tmp_path):
    from recycleguard.storage import BlobStore

    child = script("trial_child")
    blobs = BlobStore(tmp_path)

    def put(value):
        return blobs.put(json.dumps(value).encode(), "application/json").model_dump(mode="json")

    calculation = {
        "analyzed_input_membership_blob": put(
            {"members": [{"record_type": "Allocation"}, {"record_type": "Certificate"}]}
        ),
        "quantity_dispositions_blob": put([{"record_type": "Allocation", "state": "EXCLUDED"}]),
        "derivation_blob": put(
            {
                "allocation_checks": [{"rule": "LIFECYCLE", "state": "UNKNOWN", "code": None}],
                "priority_checks": [{"state": "PASS"}],
                "eligibility": [
                    {"condition": "LIFECYCLE", "testability": "TESTABLE", "state": "UNKNOWN"}
                ],
            }
        ),
    }
    found = child.census(tmp_path, {"report": {"calculations": [calculation]}})
    assert found == {
        "records": {"Allocation": 1, "Certificate": 1},
        "dispositions": {"Allocation:EXCLUDED": 1},
        "allocation_checks": {"LIFECYCLE:UNKNOWN:None": 1},
        "priority_checks": {"PASS": 1},
        "eligibility": {"LIFECYCLE:TESTABLE:UNKNOWN": 1},
    }
    broken = child.census(tmp_path, {"report": {"calculations": [{}]}})
    assert list(broken) == ["error"]


def test_the_funnel_reads_each_repeat_through_the_ledger(tmp_path):
    funnel = script("funnel")
    (tmp_path / "results").mkdir()
    ledger = [{"trial_id": "case_x|ADAPTIVE|r1", "status": "STARTED"}]
    for repeat in ("r1", "r2"):
        raw = json.dumps({"case_id": "case_x", "requested_variant": "ADAPTIVE", "r": repeat})
        digest = hashlib.sha256(raw.encode()).hexdigest()
        (tmp_path / "results" / f"{digest}.json").write_text(raw)
        ledger.append(
            {"trial_id": f"case_x|ADAPTIVE|{repeat}", "status": "OK", "result_digest": digest}
        )
    (tmp_path / "ledger.jsonl").write_text("".join(json.dumps(row) + "\n" for row in ledger))
    found = funnel.results_by_trial(tmp_path)
    assert {trial: result["r"] for trial, result in found.items()} == {
        "case_x|ADAPTIVE|r1": "r1",
        "case_x|ADAPTIVE|r2": "r2",
    }
