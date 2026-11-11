"""Replay recorded model calls with thinking on, to read how the model reaches its reply.

Diagnostic only, in `trials`, with the model server up. The replies are labelled
DIAGNOSTIC_NOT_EVIDENCE: they are never scored, never become findings and never change a run.
Thinking-mode reasoning explains a thinking-mode answer; it is a strong hint about how the model
reads the evidence, not a record of the original non-thinking decision.

    python scripts/replay_reasoning.py /work/<session> --from-funnel <funnel.csv> \
        --stage S4_SHOWN_NOT_PROPOSED [--phase ASSESS] [--limit 20]
    python scripts/replay_reasoning.py /work/<session> --trial "case_x|ADAPTIVE|r1" [...]

Each recorded call's exact prompt is resent with its empty think block opened. The server caps
each reply at its --n-predict, so thinking runs first, then the answer is asked for with the
thinking closed. Output: <session>-reasoning/replays.jsonl and a short summary on stdout.
"""

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

INVESTIGATOR_IMAGE = "recycleguard-investigator:local"
MODEL_CONTAINER = "recycleguard-model"
CLOSED_THINK = "<think>\n\n</think>\n\n"
LABEL = "DIAGNOSTIC_NOT_EVIDENCE"
# Runs in a throwaway container on the model's network: stdlib only, jobs on stdin, rows on stdout.
WORKER = r"""
import http.client, json, sys
def complete(body):
    connection = http.client.HTTPConnection("127.0.0.1", 8766, timeout=600)
    headers = {"Content-Type": "application/json"}
    connection.request("POST", "/v1/completions", json.dumps(body), headers)
    reply = json.loads(connection.getresponse().read())
    connection.close()
    choice = reply["choices"][0]
    return choice["text"], choice.get("finish_reason")
for line in sys.stdin:
    job = json.loads(line)
    body = job["body"]
    think = dict(body, prompt=job["prompt"], stop=["</think>", *body.get("stop", [])])
    reasoning, think_finish = complete(think)
    answer_body = dict(body, prompt=job["prompt"] + reasoning + "\n</think>\n\n")
    answer, answer_finish = complete(answer_body)
    print(json.dumps({"key": job["key"], "reasoning": reasoning, "thinking_finish": think_finish,
                      "answer": answer, "answer_finish": answer_finish}), flush=True)
"""


def phase_of(prompt):
    if "ASSESS rules:" in prompt:
        return "ASSESS"
    return "PLAN" if "PLAN rules:" in prompt else "OTHER"


def attempts(session):
    """Model calls of each trial's sealed attempt, keyed by trial id through the ledger.

    The ledger names each trial's sealed result by the SHA-256 of its result.json, so repeats of
    one case stay apart.
    """
    sealed = {}
    for line in (session / "ledger.jsonl").read_text("utf-8").splitlines():
        row = json.loads(line) if line.strip() else None
        if row and row.get("result_digest"):
            sealed[row["result_digest"]] = row["trial_id"]
    found = {}
    for runtime in sorted(session.glob("trials/t*/attempt-*/runtime")):
        result, calls = runtime / "result.json", runtime / "model-calls.jsonl"
        if result.is_file() and calls.is_file():
            trial = sealed.get(hashlib.sha256(result.read_bytes()).hexdigest())
            if trial is not None:
                found[trial] = calls
    return found


def selected_trials(arguments):
    trials = set(arguments.trial or [])
    if arguments.from_funnel:
        with arguments.from_funnel.open(encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                if arguments.stage is None or row["stage"] == arguments.stage:
                    trials.add(row["trial_id"])
    return sorted(trials)


def jobs(session, trials, phase, limit):
    by_trial = attempts(session)
    out = []
    for trial in trials:
        path = by_trial.get(trial)
        if path is None:
            print(f"no recorded calls for {trial} (run before the decision trace existed?)")
            continue
        for line in path.read_text("utf-8").splitlines():
            call = json.loads(line)
            body = json.loads(call["request_body_utf8"] or "{}")
            prompt = body.get("prompt", "")
            if not prompt.endswith(CLOSED_THINK) or phase not in {"ALL", phase_of(prompt)}:
                continue
            body.pop("json_schema", None)  # the thinking text is free; the answer is judged after
            out.append(
                {
                    "key": {"trial_id": trial, "operation_id": call["operation_id"]},
                    "phase": phase_of(prompt),
                    "original_reply": call["response_body_utf8"],
                    "job": {
                        "key": {"trial_id": trial, "operation_id": call["operation_id"]},
                        "body": body,
                        "prompt": prompt[: -len(CLOSED_THINK)] + "<think>\n",
                    },
                }
            )
    return out[:limit]


def original_text(raw):
    try:
        return json.loads(raw)["choices"][0]["text"]
    except (TypeError, ValueError, KeyError, IndexError):
        return None


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("--trial", action="append")
    parser.add_argument("--from-funnel", type=Path)
    parser.add_argument("--stage")
    parser.add_argument("--phase", default="ASSESS", choices=["ASSESS", "PLAN", "ALL"])
    parser.add_argument("--limit", type=int, default=20)
    arguments = parser.parse_args(argv)
    trials = selected_trials(arguments)
    if not trials:
        parser.error("name trials with --trial or --from-funnel")
    work = jobs(arguments.session, trials, arguments.phase, arguments.limit)
    if not work:
        raise SystemExit("nothing to replay")
    command = [
        "docker", "run", "--rm", "-i",
        "--network", f"container:{MODEL_CONTAINER}",
        "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", "10001:10001",
        "--entrypoint", "/opt/venv/bin/python",
        INVESTIGATOR_IMAGE, "-I", "-c", WORKER,
    ]  # fmt: skip
    stdin = "".join(json.dumps(item["job"]) + "\n" for item in work)
    done = subprocess.run(command, input=stdin, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise SystemExit(f"replay container failed: {done.stderr.strip()[-2000:]}")
    replies = {}
    for line in done.stdout.splitlines():
        row = json.loads(line)
        replies[json.dumps(row["key"], sort_keys=True)] = row
    target = Path(f"{arguments.session}-reasoning")
    target.mkdir(parents=True, exist_ok=True)
    with (target / "replays.jsonl").open("a", encoding="utf-8") as stream:
        for item in work:
            reply = replies.get(json.dumps(item["key"], sort_keys=True), {})
            row = {
                "label": LABEL,
                **item["key"],
                "phase": item["phase"],
                "original_reply": original_text(item["original_reply"]),
                "reasoning": reply.get("reasoning"),
                "thinking_complete": reply.get("thinking_finish") == "stop",
                "answer_with_thinking": reply.get("answer"),
                "answer_finish": reply.get("answer_finish"),
            }
            stream.write(json.dumps(row, sort_keys=True) + "\n")
            print(
                f"{row['trial_id']} {row['phase']}: thinking "
                f"{len(row['reasoning'] or '')} chars"
                f"{'' if row['thinking_complete'] else ' (cut at the server cap)'}"
            )
    print(f"wrote {target / 'replays.jsonl'} ({LABEL})")


if __name__ == "__main__":
    main(sys.argv[1:])
