# MG2 runbook (PC, real model)

Status: written and not yet run on the PC. The queue, its health check and the status page have
only been exercised with stubs. Nothing here is a result. The laptop has no model, so every quality
number comes from these steps. The container, the model server and the hidden-data import are in
`docs/checkpoints/mg1/DOCKER_RUNBOOK.md`; only what differs is listed here.

Read [PREREGISTRATION.md](PREREGISTRATION.md) first. It fixes the arms, the two arenas, the
selection rule and the held-out policy before any data exists.

## The idea: start it, leave it, come back

One command starts a queue. The queue keeps every model slot busy, restarts what fails, pauses
while the model server is down, and writes a status page. You do not have to be there.

| File | Runs | Needs the agent code? |
| --- | --- | --- |
| `queue/queue-baseline.json` | v7 (FIXED and ADAPTIVE) and the controls, in both arenas | No |
| `queue/queue-agents.json` | the three arms by the registered prompt versions, in both arenas | Yes |

The baseline queue (4 sessions) can start as soon as the branch is built, so the machine works
while everything else is finished. Arenas: `ablated` is the primary one (every deterministic family
off), `rules-on` is the no-regression gate.

## Before the first run

1. Open PowerShell at the repository root and set the three variables from the MG1 runbook
   (`COMPOSE_FILE`, `MSYS_NO_PATHCONV`, `$sh`).
2. `git pull` the branch, note `git rev-parse HEAD`, then
   `docker compose --profile tools build trials`. The image holds the code, so this is the code
   revision every run in that queue records. **Do not rebuild or pull while a queue runs.**
   Run the baseline queue from one build and the agent queue from a later one; say so in the
   report. The S1 and control code paths are the same in both; the unit tests are what say so.
3. Calibrate the slots once. The queue files say 6.
   ```powershell
   $env:SLOTS = "6"
   docker compose up -d --force-recreate model
   docker compose logs -f model     # wait for it to listen
   nvidia-smi                        # note the memory in use with the model loaded
   ```
   Keep at least 3 GB of the 24 GB free. If less is free, set `"slots": 4` in the queue file and
   `$env:SLOTS = "4"`, recreate the model, and write the number in the experiment log. Stay inside
   the dedicated 24 GB: spilling into shared GPU memory is far slower. Every arm of a comparison
   must use the same slot count; it is part of each run's configuration name (`-s6`).

## Start

```powershell
docker compose --profile tools run -d --name mg2-queue trials python scripts/run_queue.py docs/checkpoints/mg2/queue/queue-baseline.json
```

`-d` returns at once. If the PC reboots or the container stops, run the same command again: every
session continues from its own ledger and nothing finished is repeated. (Remove the old container
first with `docker rm mg2-queue`.)

## Look in

```powershell
docker exec mg2-queue cat /work/_status/status.md       # trials done, ETA, what is running
docker exec mg2-queue sh -c 'tail -n 20 /work/mg2-baseline/*.log'
docker compose --profile monitor up -d status           # optional page, http://<this PC>:8099
```

The page is read-only, serves only `/work/_status`, reloads every 30 seconds and sends nothing
anywhere. Start it after the queue has begun (the folder must exist). `status.json` holds the same
numbers for a script.

## Control it while it runs

Files in `/work/<queue name>/` (use `docker exec mg2-queue touch ...`):

| File | Effect |
| --- | --- |
| `PAUSE` | start nothing new; running sessions finish |
| `KILL` | stop every session before its next trial; rerun the same command to resume |
| `ALLOW_FINAL` | let jobs marked `"final": true` start; nothing else ever starts them |

Edit the queue file to add jobs or remove ones that have not started; it is read again between
sessions. `name`, `model_root` and `slots` cannot change. A prompt already in the queue must stay
byte-identical, or the queue refuses to continue.

## What the queue does by itself

- A session that exits non-zero, or whose ledger has not moved for 30 minutes, is started again,
  at most 3 times, then marked `FAILED`.
- While the model container is `unhealthy` or down, running sessions are stopped between trials and
  nothing starts. After 2 minutes it restarts the container (`docker restart`, same flags), at
  most twice, then waits for you. Trials that were in flight during an outage are recorded as
  infrastructure failures; list them in the report, do not hide them.
- A development session is scored the moment it is whole, and when the queue ends `compare.csv` in
  the queue folder puts the sessions side by side. A final session is never scored automatically.

## Afterwards

```powershell
& $sh scripts/docker/export-results.sh mg2-baseline docs/checkpoints/mg2/runs/pc
```

Commit what it copies, as MG1 did. Do not commit weights, tokens or `.env` values. Then append
the result, the decision and what it motivates to `EXPERIMENT_LOG.md`.

## What to read, and how to report it

- `supported_case_success` per arm and arena, with the paired bootstrap against SC. Report each
  number twice: full, and deterministic-only from `t3_model_influence`. The agents' contribution
  is the gap.
- False positives per case and proposals rejected, by reason: `NO_VERIFIED_CLAIM` (no verified
  claim backed it) and `CONTRADICTED_BY_CALCULATION`.
- Per agent, the schema-valid, semantically-valid and wrong-but-valid rates, calls, tokens, wall.
- From `graph.agent.result` in the traces: the Retriever's grades, refusals, searches and
  reformulations, claims proposed, verified and dropped (and why), passages read of passages
  available, and why it stopped.
- Signal families against judgement families, as in MG1 Improvement 2.

## Choosing, freezing, and the held-out run

1. Apply the selection rule in `PREREGISTRATION.md` to the development sessions. v4 is added only
   if a result motivates one change; log the reason before it runs.
2. A person creates and commits the freeze manifest (`benchmarks/evaluation/freeze.py`) for the
   chosen prompt digests, code revision and slot count. Nothing is tuned after this.
3. Add one job per arm to a new queue file, each with `"final": true` and
   `"held_out": "<committed freeze file>"`, for D0, SC, v7 (S1) and the single best new arm.
4. `docker exec mg2-queue touch /work/<queue name>/ALLOW_FINAL`. The sealed 24 held-out dossiers
   run once. `run_trials.py` refuses without a freeze that verifies against this exact code and
   protocol. Report the result whatever it is.

checking-8 is a development set that has been looked at; report it as a secondary check only.

## Known limits

- The status page and the container restart are untested on the PC. MG1 ran at most 4 sessions
  at once; 6 is new. If sessions collide on a container name or the GPU runs out of memory, drop
  the queue's `slots` to 4 and note it in the log.
- Greedy decoding under several slots can differ in the last digits of the logits, so compare
  arms only inside one slot count, and use the repeats.
- A 9B model chooses passages from their first 100 characters. Coverage shows what was not read.
- n=16 with one or two cases per family: intervals are wide.
