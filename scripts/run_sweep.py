"""Run several prompt versions at once on one tuning protocol, then score and compare them.

Evaluator-only, in `trials`, against a llama-server started with ``SLOTS`` equal to the sweep's
``slots``. Each prompt is its own run_trials.py session in ``/work/<name>-<prompt>``, so the usual
score, table and export commands work on it. Rerunning the same sweep resumes every session.
Creating ``/work/<name>/KILL`` stops every session before its next trial.

    python scripts/run_sweep.py docs/checkpoints/mg1/sweeps/<sweep>.json

Sweep: {"sweep_version": "mg1-prompt-sweep", "name": "sweep-v8", "protocol": "<protocol.json>",
"model_root": "/models/provenance/<slug>", "slots": 4, "prompts": ["u01_non_thinking_v7", ...]}

The comparison only gathers the existing tables side by side. It ranks nothing: people choose.
"""

import csv
import hashlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
WORK = Path("/work")
PROMPT_DIRS = (
    REPOSITORY / "docs/checkpoints/mg1/prompts",
    REPOSITORY / "docs/checkpoints/mg2/prompts",
)
CHECKING = REPOSITORY / "docs/checkpoints/mg1/protocols/checking-8.json"
ORACLE = REPOSITORY / "benchmarks/hidden/pilot-0.1/oracle"
VISIBLE = REPOSITORY / "tests/fixtures/visible"
SCRIPTS = Path(__file__).resolve().parent
NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
POLL_SECONDS = 5
COMPARE_COLUMNS = [
    "prompt",
    "variant",
    "scheduled",
    "scored",
    "successes",
    "success_rate",
    "ci95_low",
    "ci95_high",
    "true_positives",
    "false_positives",
    "false_negatives",
    "micro_f1",
    "proposals_made",
    "proposals_accepted",
    "findings_from_model",
    "proposals_rejected",
    "logical_calls",
    "schema_valid_rate",
    "rejected_actions",
    "mean_model_calls",
    "mean_wall_seconds",
    "p95_wall_seconds",
    "failure_classes",
]


def configure_module():
    spec = importlib.util.spec_from_file_location("configure", SCRIPTS / "configure_local_model.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_sweep(path):
    sweep = json.loads(path.read_text("utf-8"))
    expected = {"sweep_version", "name", "protocol", "model_root", "slots", "prompts"}
    if set(sweep) != expected:
        raise SystemExit(f"sweep needs exactly the keys {sorted(expected)}")
    prompts = sweep["prompts"]
    if not NAME.match(sweep["name"]) or not all(NAME.match(p) for p in prompts):
        raise SystemExit("sweep and prompt names must be lowercase letters, digits, . _ or -")
    if not prompts or len(set(prompts)) != len(prompts):
        raise SystemExit("a sweep needs distinct prompt versions")
    if not isinstance(sweep["slots"], int) or not 1 <= sweep["slots"] <= 8:
        raise SystemExit("slots must be an integer from 1 to 8")
    for prompt in prompts:
        if not any((folder / f"{prompt}.json").is_file() for folder in PROMPT_DIRS):
            raise SystemExit(
                f"no prompt file named {prompt}.json in {[str(d) for d in PROMPT_DIRS]}"
            )
    protocol = json.loads((REPOSITORY / sweep["protocol"]).read_text("utf-8"))
    checking = set(json.loads(CHECKING.read_text("utf-8"))["case_ids"])
    if checking & set(protocol["case_ids"]) or checking & set(protocol.get("canaries", ())):
        raise SystemExit("a sweep chooses a prompt, so it may never run a checking case")
    return sweep


def sessions(sweep):
    return {prompt: WORK / f"{sweep['name']}-{prompt}" for prompt in sweep["prompts"]}


def write_configs(sweep, folder, configure):
    """Writes each prompt's configuration; a resumed sweep must find exactly the same ones."""
    model = Path(sweep["model_root"])
    configs = {
        prompt: configure.write_llama_cpp(model, prompt=prompt, slots=sweep["slots"])
        for prompt in sweep["prompts"]
    }
    digests = {
        prompt: hashlib.sha256(path.read_bytes()).hexdigest() for prompt, path in configs.items()
    }
    record = folder / "configs.json"
    if record.is_file() and json.loads(record.read_text("utf-8")) != digests:
        raise SystemExit(
            "a configuration changed since this sweep started (prompt file, model or code); "
            "start a new sweep name rather than mixing them"
        )
    record.write_text(json.dumps(digests, indent=2, sort_keys=True) + "\n", "utf-8")
    return configs


def require_server(sweep, configs):
    from recycleguard.local_model import LocalModelConfig

    session = Path(sweep["model_root"]) / "server-session.json"
    running = json.loads(session.read_text("utf-8"))["server_flags"] if session.is_file() else None
    for path in configs.values():
        wanted = LocalModelConfig.model_validate_json(path.read_bytes()).server_flags
        if running != wanted:
            raise SystemExit(
                f"the model server runs with {running}, the sweep needs {wanted}: run "
                f'$env:SLOTS = "{sweep["slots"]}"; docker compose up -d --force-recreate model'
            )


def run_sessions(sweep, folder, configs, *, launch=subprocess.Popen, poll=POLL_SECONDS):
    """At most ``slots`` sessions at once. Returns each started session's exit code."""
    outputs = sessions(sweep)
    kill = folder / "KILL"
    propagated = folder / "kill-propagated.json"
    if not kill.exists() and propagated.is_file():
        for path in json.loads(propagated.read_text("utf-8")):
            Path(path).unlink(missing_ok=True)  # only KILL files this sweep itself created
        propagated.unlink()
    pending, running, codes = list(sweep["prompts"]), {}, {}
    while pending or running:
        if kill.exists():
            created = []
            for prompt in running:
                target = outputs[prompt] / "KILL"
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.touch()
                    created.append(str(target))
            if created:
                old = json.loads(propagated.read_text("utf-8")) if propagated.is_file() else []
                propagated.write_text(json.dumps(sorted({*old, *created})), "utf-8")
            pending = []
        while pending and len(running) < sweep["slots"]:
            prompt = pending.pop(0)
            log = (folder / f"{prompt}.log").open("ab")
            command = [
                sys.executable,
                str(SCRIPTS / "run_trials.py"),
                str(REPOSITORY / sweep["protocol"]),
                str(outputs[prompt]),
                "--config",
                str(configs[prompt]),
                "--docker",
            ]
            running[prompt] = (launch(command, stdout=log, stderr=subprocess.STDOUT), log)
            print(f"started {prompt} -> {outputs[prompt]}", flush=True)
        for prompt, (process, log) in list(running.items()):
            code = process.poll()
            if code is not None:
                log.close()
                codes[prompt] = code
                del running[prompt]
                print(f"finished {prompt}: exit {code}", flush=True)
        if pending or running:
            time.sleep(poll)
    return codes


def score(output):
    scores, tables = Path(f"{output}-scores"), Path(f"{output}-tables")
    for command in (
        [sys.executable, str(SCRIPTS / "score_trials.py"), output, ORACLE, VISIBLE, scores],
        [sys.executable, str(SCRIPTS / "make_tables.py"), output, scores, tables],
        [sys.executable, str(SCRIPTS / "funnel.py"), output, scores, tables / "funnel.csv"],
    ):
        done = subprocess.run([str(part) for part in command], check=False)
        if done.returncode != 0:
            return None
    return tables


def _rows(tables, name):
    path = tables / name
    if not path.is_file():
        return []
    return list(csv.DictReader(io.StringIO(path.read_text("utf-8"))))


def _by_variant(tables, name):
    return {row["variant"]: row for row in _rows(tables, name)}


def _counts(tables, name, key, value):
    grouped = {}
    for row in _rows(tables, name):
        grouped.setdefault(row["variant"], []).append(f"{row[key]}:{row[value]}")
    return {variant: ";".join(items) for variant, items in grouped.items()}


def compare(tables_by_prompt):
    """One row per prompt and variant, copied from the existing tables. Nothing is recomputed."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COMPARE_COLUMNS)
    for prompt, tables in tables_by_prompt.items():
        primary = _by_variant(tables, "t1_primary_success.csv")
        micro = _by_variant(tables, "t3_findings_micro.csv")
        influence = _by_variant(tables, "t3_model_influence.csv")
        calls = _by_variant(tables, "t6_model_calls.csv")
        efficiency = _by_variant(tables, "t6_efficiency.csv")
        rejected = _counts(tables, "t3_proposals_rejected.csv", "reason", "proposals")
        failures = _counts(tables, "t8_failure_classes.csv", "failure_class", "trials")
        for variant in sorted(primary):
            merged = {
                **primary[variant],
                **micro.get(variant, {}),
                **influence.get(variant, {}),
                **calls.get(variant, {}),
                **efficiency.get(variant, {}),
                "prompt": prompt,
                "proposals_rejected": rejected.get(variant, ""),
                "failure_classes": failures.get(variant, ""),
            }
            writer.writerow([merged.get(column, "") for column in COMPARE_COLUMNS])
    return out.getvalue()


def main(argv):
    if len(argv) != 1:
        raise SystemExit(__doc__)
    sweep = load_sweep(Path(argv[0]))
    folder = WORK / sweep["name"]
    folder.mkdir(parents=True, exist_ok=True)
    record = folder / "sweep.json"
    if record.is_file() and json.loads(record.read_text("utf-8")) != sweep:
        raise SystemExit("this sweep name was used for a different sweep; choose a new name")
    record.write_text(json.dumps(sweep, indent=2, sort_keys=True) + "\n", "utf-8")
    (folder / "sessions").write_text(
        "".join(f"{path.name}\n" for path in sessions(sweep).values()), "utf-8"
    )
    configs = write_configs(sweep, folder, configure_module())
    require_server(sweep, configs)
    codes = run_sessions(sweep, folder, configs)
    if (folder / "KILL").exists():
        print("stopped by KILL. Remove it and rerun the same command to resume.")
        raise SystemExit(3)
    tables = {}
    for prompt, output in sessions(sweep).items():
        if codes.get(prompt) == 0:
            tables[prompt] = score(output)
    status = {
        prompt: {
            "coordinator_exit": codes.get(prompt),
            "scored": tables.get(prompt) is not None,
            "output": str(sessions(sweep)[prompt]),
        }
        for prompt in sweep["prompts"]
    }
    table = compare({p: t for p, t in tables.items() if t is not None})
    (folder / "compare.csv").write_text(table, "utf-8")
    (folder / "compare.json").write_text(json.dumps(status, indent=2) + "\n", "utf-8")
    print(table, end="")
    print(json.dumps(status))
    if any(not item["scored"] for item in status.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
