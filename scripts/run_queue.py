"""Run a queue of trial sessions unattended, keeping every model slot busy.

Evaluator-only, in `trials`, next to ``run_sweep.py`` and against the same kind of server. Where a
sweep runs one protocol and waits for its slowest prompt, a queue is one pool of sessions drawn from
many jobs: a slot that frees starts the next session of any job, so nothing idles at the tail.

    python scripts/run_queue.py docs/checkpoints/mg2/queue/queue-a.json     # in `trials`

Queue: {"queue_version": "mg2-queue", "name": "q1", "model_root": "/models/provenance/<slug>",
"slots": 6, "jobs": [{"id": "ablated", "protocol": "<protocol.json>", "prompts": ["<version>"]}]}
A job may add "final": true (needs ``<work>/<name>/ALLOW_FINAL``) and "held_out": "<freeze.json>".

The queue file is read again between sessions: append jobs or remove ones not yet started while it
runs. ``name``, ``model_root`` and ``slots`` cannot change. Beside the queue, in ``/work/<name>``:
``PAUSE`` starts nothing new, ``KILL`` stops every session before its next trial. Rerunning the same
command resumes: every session continues from its own ledger.

A session that exits non-zero, or whose ledger has not moved for ``stall_seconds``, is started again
(at most ``MAX_ATTEMPTS`` times). While the model container is not healthy nothing new starts and
running sessions are stopped between trials; it is restarted, at most twice, with the flags it has.
Trials that were in flight during an outage are recorded by the runner as infrastructure failures;
list them in the report. Status goes to ``/work/_status`` as status.json, status.md and index.html.
"""

import html
import importlib.util
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(REPOSITORY))
WORK = Path("/work")
MODEL_CONTAINER = "recycleguard-model"
MAX_ATTEMPTS = 3
MAX_RESTARTS = 2
POLL_SECONDS = 15
STALL_SECONDS = 1800
UNHEALTHY_GRACE_SECONDS = 120
RESTART_WAIT_SECONDS = 900
JOB_KEYS = {"id", "protocol", "prompts"}
OPTIONAL_JOB_KEYS = {"final", "held_out"}


def sibling(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_queue(path, sweep):
    """The queue file, checked. ``sweep`` is the run_sweep module, whose rules this reuses."""
    queue = json.loads(path.read_text("utf-8"))
    expected = {"queue_version", "name", "model_root", "slots", "jobs"}
    if set(queue) != expected or queue["queue_version"] != "mg2-queue":
        raise SystemExit(f"queue needs exactly the keys {sorted(expected)} and mg2-queue")
    if not sweep.NAME.match(queue["name"]) or not 1 <= queue["slots"] <= 8:
        raise SystemExit("queue name must be lowercase letters, digits, . _ or -; slots 1 to 8")
    seen = set()
    for job in queue["jobs"]:
        keys = set(job)
        if not JOB_KEYS <= keys <= JOB_KEYS | OPTIONAL_JOB_KEYS:
            raise SystemExit(
                f"job needs {sorted(JOB_KEYS)}, optionally {sorted(OPTIONAL_JOB_KEYS)}"
            )
        if not sweep.NAME.match(job["id"]) or job["id"] in seen:
            raise SystemExit(f"job id {job['id']!r} must be a unique lowercase name")
        seen.add(job["id"])
        prompts = job["prompts"]
        if not prompts or len(set(prompts)) != len(prompts):
            raise SystemExit(f"job {job['id']} needs distinct prompt versions")
        for prompt in prompts:
            if not sweep.NAME.match(prompt) or not any(
                (folder / f"{prompt}.json").is_file() for folder in sweep.PROMPT_DIRS
            ):
                raise SystemExit(f"job {job['id']}: no prompt file named {prompt}.json")
        if not (REPOSITORY / job["protocol"]).is_file():
            raise SystemExit(f"job {job['id']}: no protocol {job['protocol']}")
        if job.get("held_out") and not job.get("final"):
            raise SystemExit(f"job {job['id']}: a held-out job must also be final")
        if not job.get("final"):
            protocol = json.loads((REPOSITORY / job["protocol"]).read_text("utf-8"))
            checking = set(json.loads(sweep.CHECKING.read_text("utf-8"))["case_ids"])
            if checking & set(protocol["case_ids"]) | checking & set(protocol.get("canaries", ())):
                raise SystemExit(f"job {job['id']}: only a final job may run a checking case")
    return queue


@dataclass(frozen=True)
class Session:
    job: str
    prompt: str
    protocol: str
    final: bool
    held_out: str | None

    @property
    def key(self):
        return f"{self.job}:{self.prompt}"


def sessions_of(queue):
    return [
        Session(job["id"], prompt, job["protocol"], bool(job.get("final")), job.get("held_out"))
        for job in queue["jobs"]
        for prompt in job["prompts"]
    ]


def output_of(queue, session):
    return WORK / f"{queue['name']}-{session.job}-{session.prompt}"


def trial_counts(output, protocol_path):
    """(finished, scheduled) trials of one session, from its own ledger."""
    from benchmarks.evaluation.trials import Ledger, protocol_schedule

    protocol = json.loads((REPOSITORY / protocol_path).read_text("utf-8"))
    ledger = output / "ledger.jsonl"
    done = len(Ledger(ledger).terminal()) if ledger.is_file() else 0
    return done, len(protocol_schedule(protocol))


def model_health(run=subprocess.run):
    """healthy, starting, unhealthy or down, from the model container's own health check."""
    done = run(
        [
            "docker",
            "inspect",
            "--format",
            "{{.State.Status}} {{.State.Health.Status}}",
            MODEL_CONTAINER,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        return "down"
    state, _, health = done.stdout.strip().partition(" ")
    if state != "running":
        return "down"
    return {"healthy": "healthy", "starting": "starting"}.get(health, "unhealthy")


def restart_model(run=subprocess.run):
    return (
        run(["docker", "restart", MODEL_CONTAINER], capture_output=True, check=False).returncode
        == 0
    )


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, "utf-8")
    os.replace(temporary, path)


class State:
    """Per-session attempts and outcome. One file, rewritten whole, so a crash never half-writes."""

    def __init__(self, path):
        self.path = path
        self.data = (
            json.loads(path.read_text("utf-8"))
            if path.is_file()
            else {"sessions": {}, "restarts": 0, "started_at": datetime.now(UTC).isoformat()}
        )

    def entry(self, key):
        return self.data["sessions"].setdefault(
            key, {"status": "PENDING", "attempts": 0, "exit_codes": []}
        )

    def save(self):
        atomic_write(self.path, json.dumps(self.data, indent=2, sort_keys=True) + "\n")


def startable(session, entry, final_allowed):
    if entry["status"] != "PENDING":
        return False
    return not session.final or final_allowed


def stalled(output, started, now, stall_seconds):
    """True when nothing was written to the ledger (or session start) for ``stall_seconds``."""
    ledger = output / "ledger.jsonl"
    last = ledger.stat().st_mtime if ledger.is_file() else started
    return now - max(last, started) > stall_seconds


def eta_seconds(done, total, elapsed):
    if done <= 0 or elapsed <= 0:
        return None
    return round((total - done) * elapsed / done)


def render_status(snapshot):
    rows = [
        "| session | state | attempts | trials | idle (s) |",
        "| --- | --- | --- | --- | --- |",
        *(
            f"| {item['key']} | {item['status']} | {item['attempts']} | "
            f"{item['done']}/{item['total']} | {item['idle_seconds']} |"
            for item in snapshot["sessions"]
        ),
    ]
    head = [
        f"# Queue {snapshot['name']}",
        "",
        f"Updated {snapshot['updated_at']}. Model: {snapshot['model']}. "
        f"Slots in use: {snapshot['running']} of {snapshot['slots']}. "
        f"Held: {snapshot['held'] or 'no'}. Restarts used: {snapshot['restarts']}.",
        f"Trials: {snapshot['done']} of {snapshot['total']}. "
        f"ETA: {snapshot['eta_seconds'] if snapshot['eta_seconds'] is not None else 'unknown'} s.",
        "",
    ]
    return "\n".join([*head, *rows, ""])


def write_status(snapshot):
    folder = WORK / "_status"
    atomic_write(folder / "status.json", json.dumps(snapshot, indent=2) + "\n")
    markdown = render_status(snapshot)
    atomic_write(folder / "status.md", markdown)
    atomic_write(
        folder / "index.html",
        '<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="30">'
        f"<title>{html.escape(snapshot['name'])}</title>"
        f"<pre>{html.escape(markdown)}</pre>",
    )


def command_for(queue, session, config):
    command = [
        sys.executable,
        str(SCRIPTS / "run_trials.py"),
        str(REPOSITORY / session.protocol),
        str(output_of(queue, session)),
        "--config",
        str(config),
        "--docker",
    ]
    if session.held_out:
        command += ["--held-out", str(REPOSITORY / session.held_out)]
    return command


def write_configs(queue, folder, configure, prompts):
    """One configuration per prompt. A prompt already recorded must come out byte-identical."""
    import hashlib

    model = Path(queue["model_root"])
    configs = {
        prompt: configure.write_llama_cpp(model, prompt=prompt, slots=queue["slots"])
        for prompt in prompts
    }
    digests = {p: hashlib.sha256(path.read_bytes()).hexdigest() for p, path in configs.items()}
    record = folder / "configs.json"
    known = json.loads(record.read_text("utf-8")) if record.is_file() else {}
    changed = sorted(p for p in digests if p in known and known[p] != digests[p])
    if changed:
        raise SystemExit(
            f"a configuration changed since this queue started (prompt file, model or code): "
            f"{changed}; start a new queue name rather than mixing them"
        )
    atomic_write(record, json.dumps({**known, **digests}, indent=2, sort_keys=True) + "\n")
    return configs


def score_finished(queue, sessions, state, sweep, folder):
    """Tables for every finished development session, and one comparison across them."""
    tables = {}
    for session in sessions:
        if session.final or state.entry(session.key)["status"] != "DONE":
            continue
        output = output_of(queue, session)
        existing = Path(f"{output}-tables")
        tables[session.key] = existing if existing.is_dir() else sweep.score(output)
    scored = {key: path for key, path in tables.items() if path is not None}
    if scored:
        atomic_write(folder / "compare.csv", sweep.compare(scored))
    return sorted(set(tables) - set(scored))


def run(
    queue_path,
    *,
    launch=subprocess.Popen,
    health=model_health,
    restart=restart_model,
    sleep=time.sleep,
    clock=time.time,
    poll=POLL_SECONDS,
    stall_seconds=STALL_SECONDS,
):
    sweep = sibling("run_sweep")
    queue = load_queue(queue_path, sweep)
    folder = WORK / queue["name"]
    folder.mkdir(parents=True, exist_ok=True)
    identity = {key: queue[key] for key in ("name", "model_root", "slots")}
    record = folder / "queue-identity.json"
    if record.is_file() and json.loads(record.read_text("utf-8")) != identity:
        raise SystemExit("this queue name was used with another model or slot count; use a new one")
    atomic_write(record, json.dumps(identity, indent=2, sort_keys=True) + "\n")
    state = State(folder / "state.json")
    configure = sweep.configure_module()
    running, unhealthy_since, baseline = {}, None, None
    started_at = clock()

    def configs_for(current):
        prompts = sorted({prompt for job in current["jobs"] for prompt in job["prompts"]})
        configs = write_configs(queue, folder, configure, prompts)
        sweep.require_server(queue, configs)
        return configs

    configs = configs_for(queue)
    while True:
        try:
            current = load_queue(queue_path, sweep)
            if {key: current[key] for key in identity} != identity:
                raise SystemExit("name, model_root and slots cannot change while a queue runs")
            if current["jobs"] != queue["jobs"]:
                fresh = configs_for(current)
                queue, configs = current, fresh
        except (ValueError, SystemExit) as exc:
            print(f"queue file not applied: {exc}", flush=True)
        sessions = sessions_of(queue)
        for session in sessions:
            state.entry(session.key)
        # The same list a sweep writes, so scripts/docker/export-results.sh exports each session.
        names = "".join(f"{output_of(queue, session).name}\n" for session in sessions)
        atomic_write(folder / "sessions", names)
        killed = (folder / "KILL").exists()
        status = health()
        if status == "healthy":
            unhealthy_since = None
        elif unhealthy_since is None and status in {"unhealthy", "down"}:
            unhealthy_since = clock()
        # Trials must not be spent on a dead server: stop sessions between trials until it is back.
        halted = killed or status in {"unhealthy", "down"}
        for key, (process, log, begun, output, protocol) in list(running.items()):
            code = process.poll()
            if halted:
                (output / "KILL").parent.mkdir(parents=True, exist_ok=True)
                (output / "KILL").touch()
            elif code is None and stalled(output, begun, clock(), stall_seconds):
                process.kill()
                code = process.wait()
            if code is None:
                continue
            log.close()
            del running[key]
            entry = state.entry(key)
            entry["exit_codes"].append(code)
            (output / "KILL").unlink(missing_ok=True)
            done, total = trial_counts(output, protocol)
            if done >= total:
                entry["status"] = "DONE"
            elif halted:
                entry["attempts"] -= 1  # stopped on purpose; resumes without using an attempt
            elif entry["attempts"] >= MAX_ATTEMPTS:
                entry["status"] = "FAILED"
            print(f"finished {key}: exit {code}, {done} of {total} trials", flush=True)
        if (
            status in {"unhealthy", "down"}
            and not running
            and not killed
            and unhealthy_since is not None
            and clock() - unhealthy_since > UNHEALTHY_GRACE_SECONDS
            and state.data["restarts"] < MAX_RESTARTS
        ):
            state.data["restarts"] += 1
            print("model container not healthy: restarting it", flush=True)
            restart()
            deadline = clock() + RESTART_WAIT_SECONDS
            while health() != "healthy" and clock() < deadline:
                sleep(poll)
            unhealthy_since = None
        held = (
            "KILL"
            if killed
            else "PAUSE"
            if (folder / "PAUSE").exists()
            else f"model {status}"
            if status != "healthy"
            else ""
        )
        final_allowed = (folder / "ALLOW_FINAL").exists()
        if not held:
            for session in sessions:
                if len(running) >= queue["slots"]:
                    break
                entry = state.entry(session.key)
                if session.key in running or not startable(session, entry, final_allowed):
                    continue
                entry["attempts"] += 1
                output = output_of(queue, session)
                log = (folder / f"{session.job}-{session.prompt}.log").open("ab")
                process = launch(
                    command_for(queue, session, configs[session.prompt]),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                running[session.key] = (process, log, clock(), output, session.protocol)
                print(f"started {session.key} (attempt {entry['attempts']})", flush=True)
        state.save()
        rows, done_all, total_all = [], 0, 0
        for session in sessions:
            entry, output = state.entry(session.key), output_of(queue, session)
            done, total = trial_counts(output, session.protocol)
            done_all, total_all = done_all + done, total_all + total
            ledger = output / "ledger.jsonl"
            idle = round(clock() - ledger.stat().st_mtime) if ledger.is_file() else None
            rows.append(
                {
                    "key": session.key,
                    "status": "RUNNING" if session.key in running else entry["status"],
                    "attempts": entry["attempts"],
                    "done": done,
                    "total": total,
                    "idle_seconds": idle,
                    "output": str(output),
                }
            )
        baseline = done_all if baseline is None else baseline
        write_status(
            {
                "name": queue["name"],
                "updated_at": datetime.now(UTC).isoformat(),
                "model": status,
                "slots": queue["slots"],
                "running": len(running),
                "held": held,
                "restarts": state.data["restarts"],
                "done": done_all,
                "total": total_all,
                "eta_seconds": eta_seconds(
                    done_all - baseline, total_all - baseline, clock() - started_at
                ),
                "sessions": rows,
            }
        )
        waiting = [
            session
            for session in sessions
            if startable(session, state.entry(session.key), final_allowed)
        ]
        if killed and not running:
            print("stopped by KILL. Remove it and rerun the same command to resume.")
            raise SystemExit(3)
        if not running and not waiting:
            unscored = score_finished(queue, sessions, state, sweep, folder)
            if unscored:
                print(f"could not score: {unscored}", flush=True)
            return state
        sleep(poll)


def main(argv):
    if len(argv) != 1:
        raise SystemExit(__doc__)
    state = run(Path(argv[0]))
    failed = sorted(k for k, v in state.data["sessions"].items() if v["status"] == "FAILED")
    if failed:
        print(f"sessions that failed after {MAX_ATTEMPTS} attempts: {failed}")
        raise SystemExit(1)
    print("queue finished; development sessions are scored, see compare.csv in the queue folder.")


if __name__ == "__main__":
    main(sys.argv[1:])
