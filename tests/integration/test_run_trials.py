"""Trial runner failure paths with stub runners: no model or dossier, so seconds per test."""

import hashlib
import importlib.util
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from benchmarks.evaluation.trials import (
    Coordinator,
    Ledger,
    TrialOutcome,
    build_schedule,
    verify_seals,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def run_trials(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("run_trials", ROOT / "scripts/run_trials.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seeded(output, text="result"):
    (output / "results").mkdir(parents=True)
    digest = hashlib.sha256(text.encode()).hexdigest()
    path = output / "results" / f"{digest}.json"
    path.write_text(text, newline="")
    Ledger(output / "ledger.jsonl").append(
        {"trial_id": "a|V1|r1", "status": "SUCCESS", "result_digest": digest}
    )
    return path


def test_hard_exit_mid_trial_resumes_with_no_lost_rows(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    # os._exit skips all cleanup, as kill -9 does, and leaves a STARTED row with no result.
    program = textwrap.dedent(
        f"""
        import os
        from pathlib import Path
        from benchmarks.evaluation.trials import Coordinator, Ledger, TrialOutcome, build_schedule
        calls = []
        def runner(spec):
            calls.append(spec)
            if len(calls) == 2:
                os._exit(137)
            return TrialOutcome(status="SUCCESS", tokens=1)
        schedule = build_schedule(["a", "b"], ("V1", "V2"), 1)
        ledger = Ledger(Path({str(ledger_path)!r}))
        Coordinator(schedule, ledger, runner, Path({str(tmp_path / "KILL")!r})).run()
        """
    )
    died = subprocess.run([sys.executable, "-c", program], cwd=ROOT, check=False)
    assert died.returncode == 137

    schedule = build_schedule(["a", "b"], ("V1", "V2"), 1)
    ledger = Ledger(ledger_path)
    interrupted = [r["trial_id"] for r in ledger.rows() if r["status"] == "STARTED"][-1]
    ran = []

    def resume(spec):
        ran.append(spec.trial_id)
        return TrialOutcome(status="SUCCESS", tokens=1)

    Coordinator(schedule, ledger, resume, tmp_path / "KILL").run()
    rows = ledger.rows()
    assert {"trial_id": interrupted, "status": "INTERRUPTED"}.items() <= next(
        r for r in rows if r["status"] == "INTERRUPTED"
    ).items()
    assert interrupted in ran and len(ran) == 3
    assert ledger.terminal() == {s.trial_id for s in schedule}
    assert ledger.attempts(interrupted) == 2


def test_kill_file_stops_before_the_next_trial_and_stays_resumable(tmp_path):
    schedule = build_schedule(["a", "b"], ("V1", "V2"), 1)
    ledger = Ledger(tmp_path / "ledger.jsonl")
    kill = tmp_path / "KILL"

    def stop_after_first(spec):
        kill.touch()
        return TrialOutcome(status="SUCCESS")

    summary = Coordinator(schedule, ledger, stop_after_first, kill).run()
    assert summary.stopped_because == "KILL_SWITCH" and summary.completed == 1
    kill.unlink()
    summary = Coordinator(schedule, ledger, lambda _: TrialOutcome(status="SUCCESS"), kill).run()
    assert summary.stopped_because is None and summary.completed == 3


def test_intact_seal_passes(tmp_path):
    seeded(tmp_path)
    assert verify_seals(tmp_path) == 1


def test_changed_sealed_result_is_detected(tmp_path):
    seeded(tmp_path).write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        verify_seals(tmp_path)


def test_missing_sealed_result_is_detected(tmp_path):
    seeded(tmp_path).unlink()
    with pytest.raises(ValueError, match="missing"):
        verify_seals(tmp_path)


def test_output_directory_refuses_a_different_protocol(tmp_path, run_trials):
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    first.write_text(json.dumps({"protocol_version": "1"}))
    second.write_text(json.dumps({"protocol_version": "2"}))
    output = tmp_path / "output"
    run_trials.freeze(first, output)
    run_trials.freeze(first, output)
    with pytest.raises(SystemExit, match="different protocol"):
        run_trials.freeze(second, output)


def test_held_out_case_is_refused(run_trials):
    from benchmarks.generator.pilot_cases import DEV, build_pilot_cases

    held_out = next(c for c in build_pilot_cases() if c.split != DEV)
    with pytest.raises(SystemExit, match="not development cases"):
        run_trials.require_development_cases([f"case_{held_out.world.case_tag}"])


def test_child_cannot_reach_evaluator_code():
    source = (ROOT / "scripts/trial_child.py").read_text("utf-8")
    assert "benchmarks" not in source.replace("No evaluator code", "")
    assert "import tests" not in source and "from tests" not in source
