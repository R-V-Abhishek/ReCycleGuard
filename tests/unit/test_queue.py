"""The unattended trial queue, with stub processes, a stub model health check and a fake clock."""

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


class FakeConfigure:
    def __init__(self, folder):
        self.folder = folder

    def write_llama_cpp(self, model, prompt, slots):
        path = self.folder / f"{prompt}.config.json"
        path.write_text(json.dumps({"prompt": prompt, "slots": slots}), "utf-8")
        return path


class FakeSweep:
    NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

    def __init__(self, folder):
        self.folder = folder
        self.PROMPT_DIRS = [folder / "prompts"]
        self.CHECKING = folder / "checking.json"
        self.scored = []

    def configure_module(self):
        return FakeConfigure(self.folder)

    def require_server(self, queue, configs):
        return None

    def score(self, output):
        self.scored.append(output)
        return None

    def compare(self, tables):
        return "prompt\n"


class Process:
    """Finishes on its `life`-th poll, then reports `code` and, if 0, that all trials are done."""

    def __init__(self, world, output, life, code):
        self.world, self.output, self.life, self.code, self.polls = world, output, life, code, 0

    def poll(self):
        if (self.output / "KILL").exists() and self.code is not None:
            self.world.progress[self.output] = self.world.progress.get(self.output, 0)
            return 1
        self.polls += 1
        if self.polls < self.life:
            return None
        if self.code == 0:
            self.world.progress[self.output] = 2
        return self.code

    def kill(self):
        self.code = -9

    def wait(self):
        return self.code


class World:
    def __init__(self, tmp_path, monkeypatch):
        spec = importlib.util.spec_from_file_location("run_queue", ROOT / "scripts/run_queue.py")
        self.queue = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.queue)
        self.tmp = tmp_path
        self.work = tmp_path / "work"
        self.work.mkdir()
        (tmp_path / "prompts").mkdir()
        for name in ("p1", "p2", "p3"):
            (tmp_path / "prompts" / f"{name}.json").write_text("{}", "utf-8")
        (tmp_path / "checking.json").write_text(json.dumps({"case_ids": ["case_c"]}), "utf-8")
        self.protocol = tmp_path / "protocol.json"
        self.protocol.write_text(json.dumps({"case_ids": ["case_a"]}), "utf-8")
        self.sweep = FakeSweep(tmp_path)
        self.progress = {}
        self.launched, self.concurrent, self.health, self.restarts = [], [], ["healthy"], 0
        self.now, self.lives = 0.0, {}
        monkeypatch.setattr(self.queue, "WORK", self.work)
        monkeypatch.setattr(self.queue, "sibling", lambda name: self.sweep)
        monkeypatch.setattr(
            self.queue, "trial_counts", lambda output, protocol: (self.progress.get(output, 0), 2)
        )
        self.running = []

    def write_queue(self, jobs, slots=2):
        path = self.tmp / "queue.json"
        path.write_text(
            json.dumps(
                {
                    "queue_version": "mg2-queue",
                    "name": "q1",
                    "model_root": "/models/x",
                    "slots": slots,
                    "jobs": jobs,
                }
            ),
            "utf-8",
        )
        return path

    def job(self, name, prompts, **extra):
        return {"id": name, "protocol": str(self.protocol), "prompts": prompts, **extra}

    def launch(self, command, stdout, stderr):
        output = Path(command[command.index("--config") - 1])
        key = output.name
        life, code = self.lives.get(key, (2, 0))
        process = Process(self, output, life, code)
        self.launched.append(key)
        self.running.append(process)
        return process

    def sleep(self, seconds):
        self.now += 100
        self.concurrent.append(sum(1 for p in self.running if p.code is None and p.polls < p.life))
        if self.health and len(self.health) > 1:
            self.health.pop(0)

    def run(self, path, **options):
        return self.queue.run(
            path,
            launch=self.launch,
            health=lambda: self.health[0],
            restart=self._restart,
            sleep=self.sleep,
            clock=lambda: self.now,
            poll=0,
            **options,
        )

    def _restart(self):
        self.restarts += 1
        self.health[:] = ["healthy"]
        return True


@pytest.fixture
def world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)


def test_a_slot_that_frees_starts_the_next_session_from_any_job(world):
    path = world.write_queue([world.job("a", ["p1", "p2"]), world.job("b", ["p3"])], slots=2)
    state = world.run(path)
    assert world.launched == ["q1-a-p1", "q1-a-p2", "q1-b-p3"]
    assert {entry["status"] for entry in state.data["sessions"].values()} == {"DONE"}
    assert max(world.concurrent) <= 2
    assert sorted(path.name for path in world.sweep.scored[:3]) == [
        "q1-a-p1",
        "q1-a-p2",
        "q1-b-p3",
    ]
    status = json.loads((world.work / "_status" / "status.json").read_text("utf-8"))
    assert status["done"] == status["total"] == 6 and status["running"] == 0


def test_a_session_that_keeps_failing_is_retried_then_given_up(world):
    world.lives["q1-a-p1"] = (1, 7)
    path = world.write_queue([world.job("a", ["p1"])], slots=1)
    state = world.run(path)
    assert world.launched == ["q1-a-p1"] * world.queue.MAX_ATTEMPTS
    assert state.data["sessions"]["a:p1"]["status"] == "FAILED"
    assert state.data["sessions"]["a:p1"]["exit_codes"] == [7] * world.queue.MAX_ATTEMPTS


def test_a_final_job_waits_for_a_human_and_is_never_run_by_the_queue_alone(world):
    path = world.write_queue([world.job("a", ["p1"]), world.job("f", ["p2"], final=True)])
    state = world.run(path)
    assert world.launched == ["q1-a-p1"]
    assert state.data["sessions"]["f:p2"]["status"] == "PENDING"
    (world.work / "q1" / "ALLOW_FINAL").touch()
    world.run(path)
    assert world.launched == ["q1-a-p1", "q1-f-p2"]


def test_a_queue_file_is_checked(world):
    bad = world.write_queue([world.job("a", ["nope"])])
    with pytest.raises(SystemExit, match="no prompt file"):
        world.run(bad)
    held = world.write_queue([world.job("a", ["p1"], held_out="freeze.json")])
    with pytest.raises(SystemExit, match="must also be final"):
        world.run(held)
    world.protocol.write_text(json.dumps({"case_ids": ["case_c"]}), "utf-8")
    checking = world.write_queue([world.job("a", ["p1"])])
    with pytest.raises(SystemExit, match="only a final job"):
        world.run(checking)


def test_an_unhealthy_model_stops_new_work_and_restarts_it_at_most_twice(world):
    path = world.write_queue([world.job("a", ["p1"])], slots=1)
    world.health[:] = ["down"] * 50
    world.lives["q1-a-p1"] = (3, 0)
    state = world.run(path)
    assert world.restarts == 1 and state.data["restarts"] == 1
    assert state.data["sessions"]["a:p1"]["status"] == "DONE"
    assert world.launched == ["q1-a-p1"]


def test_pause_starts_nothing_and_a_kill_ends_the_run(world):
    path = world.write_queue([world.job("a", ["p1"])])
    folder = world.work / "q1"
    folder.mkdir()
    (folder / "KILL").touch()
    with pytest.raises(SystemExit) as stop:
        world.run(path)
    assert stop.value.code == 3 and world.launched == []


def test_a_stalled_session_is_stopped_and_started_again(world):
    world.lives["q1-a-p1"] = (10**6, None)  # never finishes
    path = world.write_queue([world.job("a", ["p1"])], slots=1)
    state = world.run(path, stall_seconds=250)
    assert world.launched.count("q1-a-p1") == world.queue.MAX_ATTEMPTS
    assert state.data["sessions"]["a:p1"]["status"] == "FAILED"


@pytest.mark.parametrize(
    ("output", "code", "expected"),
    [
        ("running healthy\n", 0, "healthy"),
        ("running none\n", 0, "healthy"),
        ("running starting\n", 0, "starting"),
        ("running unhealthy\n", 0, "unhealthy"),
        ("exited none\n", 0, "down"),
        ("", 1, "down"),
    ],
)
def test_the_model_container_state_is_read_from_docker(world, output, code, expected):
    class Done:
        returncode, stdout = code, output

    assert world.queue.model_health(lambda *args, **kwargs: Done()) == expected
