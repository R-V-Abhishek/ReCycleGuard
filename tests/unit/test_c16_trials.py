import pytest

from benchmarks.evaluation.trials import (
    Caps,
    Coordinator,
    Ledger,
    TrialOutcome,
    build_schedule,
)


def ok(spec):
    return TrialOutcome(status="SUCCESS", tokens=100)


def test_schedule_is_repeat_major_and_counterbalanced():
    schedule = build_schedule(["a", "b", "c", "d"], ("V1", "V2"), 2)
    assert len(schedule) == 16
    assert {s.repeat for s in schedule[:8]} == {1}
    first = [schedule[i].variant for i in range(0, 8, 2)]
    assert first == ["V2", "V1", "V2", "V1"]
    assert [s.position for s in schedule] == list(range(16))
    assert len({s.trial_id for s in schedule}) == 16


def test_schedule_rejects_duplicate_cases_and_bad_variants():
    with pytest.raises(ValueError):
        build_schedule(["a", "a"], ("V1", "V2"), 1)
    with pytest.raises(ValueError):
        build_schedule(["a"], ("V1", "V1"), 1)


def test_complete_run_records_every_trial(tmp_path):
    schedule = build_schedule(["a", "b"], ("V1", "V2"), 1)
    ledger = Ledger(tmp_path / "ledger.jsonl")
    summary = Coordinator(schedule, ledger, ok, tmp_path / "STOP").run()
    assert summary.stopped_because is None and summary.completed == 4
    assert summary.tokens == 400
    assert ledger.terminal() == {s.trial_id for s in schedule}


def test_kill_switch_stops_at_run_boundary_and_resume_continues(tmp_path):
    schedule = build_schedule(["a", "b", "c"], ("V1", "V2"), 1)
    ledger = Ledger(tmp_path / "ledger.jsonl")
    stop = tmp_path / "STOP"
    calls = []

    def runner(spec):
        calls.append(spec.trial_id)
        if len(calls) == 2:
            stop.touch()
        return ok(spec)

    first = Coordinator(schedule, ledger, runner, stop).run()
    assert first.stopped_because == "KILL_SWITCH" and len(calls) == 2
    stop.unlink()
    second = Coordinator(schedule, ledger, runner, stop).run()
    assert second.stopped_because is None
    assert len(calls) == 6 and len(set(calls)) == 6
    assert ledger.terminal() == {s.trial_id for s in schedule}


def test_crash_leaves_started_row_and_resume_marks_interrupted_then_retries(tmp_path):
    schedule = build_schedule(["a"], ("V1", "V2"), 1)
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.append({"trial_id": schedule[0].trial_id, "status": "STARTED", "attempt": 1})
    Coordinator(schedule, ledger, ok, tmp_path / "STOP").run()
    statuses = [r["status"] for r in ledger.rows() if r["trial_id"] == schedule[0].trial_id]
    assert statuses == ["STARTED", "INTERRUPTED", "STARTED", "SUCCESS"]


def test_infrastructure_failures_stop_the_night_and_are_retained(tmp_path):
    schedule = build_schedule(["a", "b", "c", "d"], ("V1", "V2"), 1)
    ledger = Ledger(tmp_path / "ledger.jsonl")

    def runner(spec):
        raise RuntimeError("server down")

    summary = Coordinator(schedule, ledger, runner, tmp_path / "STOP").run()
    assert summary.stopped_because == "INFRASTRUCTURE_FAILURES"
    failed = [r for r in ledger.rows() if r["status"] == "INFRA_FAILED"]
    assert len(failed) == 3 and "server down" in failed[0]["detail"]


def test_attempts_exhausted_becomes_failed_not_dropped(tmp_path):
    schedule = build_schedule(["a"], ("V1", "V2"), 1)
    ledger = Ledger(tmp_path / "ledger.jsonl")
    caps = Caps(consecutive_infra_failures=99)
    bad = lambda spec: TrialOutcome(status="INFRA_FAILED", detail="x")  # noqa: E731
    for _ in range(3):
        Coordinator(schedule, ledger, bad, tmp_path / "STOP", caps).run()
    rows = [r for r in ledger.rows() if r["trial_id"] == schedule[0].trial_id]
    assert ledger.attempts(schedule[0].trial_id) == 2
    assert rows[-1]["status"] == "FAILED" and "exhausted" in rows[-1]["detail"]
    assert ledger.terminal() == {s.trial_id for s in schedule}


def test_token_and_wall_caps_and_not_run_accounting(tmp_path):
    schedule = build_schedule(["a", "b", "c"], ("V1", "V2"), 1)
    ledger = Ledger(tmp_path / "ledger.jsonl")
    summary = Coordinator(schedule, ledger, ok, tmp_path / "STOP", Caps(tokens=250)).run()
    assert summary.stopped_because == "TOKEN_CAP" and summary.completed == 3
    count = Coordinator(schedule, ledger, ok, tmp_path / "STOP").close_unfinished("deadline")
    assert count == 3
    assert ledger.terminal() == {s.trial_id for s in schedule}
    ticks = iter(range(0, 10_000, 100))
    wall = Coordinator(
        schedule,
        Ledger(tmp_path / "other.jsonl"),
        ok,
        tmp_path / "STOP",
        Caps(wall_seconds=150),
        clock=lambda: next(ticks),
    ).run()
    assert wall.stopped_because == "WALL_CAP"
