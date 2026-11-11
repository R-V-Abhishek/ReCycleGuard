# MG2 runbook: run the experiment on the PC with Docker

Follow the parts in order. Every command is for **PowerShell on the Windows PC**, run from the
repository root, and every step says what you should see and what to do if you do not. The
container, the model and the hidden data are all covered here; you do not need another document.

**Status.** Written from the code and from checks on a laptop without a GPU. Nothing here has run
against the real model yet, so Part 3 and later are where a surprise can still happen. If a step
does not behave as written, stop and write down the command and its output. Do not improvise.

## What you will run

| Queue file | Sessions | Trials | Needs |
| --- | --- | --- | --- |
| `queue-baseline.json` | 4 (v7 FIXED and ADAPTIVE, in both arenas) | 224 | the model |
| `queue-agents.json` | 14 (the three agent arms by prompt version, in both arenas) | 784 | the model |

The trial counts are what `run_queue.py --check` prints. Each session is one prompt version run
over 16 development dossiers with 2 repeats, plus model-free controls. The **ablated** arena (every
deterministic check off) is the primary result. **rules-on** is the no-regression check. Read
[PREREGISTRATION.md](PREREGISTRATION.md) once: it fixes the arms and the rules before any data.

Both queues run from **one build of the image**, one after the other (Part 5). The code is
committed, so there is no reason to use two builds; one revision makes the arms comparable.

## Part 0. What the PC needs

| Need | How to check | Pass |
| --- | --- | --- |
| Docker Desktop running, WSL 2 backend | `docker version --format '{{.Server.Version}}'` | prints a version |
| At least **8 CPUs** visible to Docker | `docker info --format 'cpus={{.NCPU}} memory={{.MemTotal}}'` | `cpus=8` or more |
| NVIDIA GPU visible to Docker | `docker run --rm --gpus all ubuntu nvidia-smi` | the GPU table prints |
| Git for Windows (`sh.exe`) | `Test-Path "$env:ProgramFiles\Git\bin\sh.exe"` | `True` |
| The private `benchmarks\hidden` folder | `Test-Path .\benchmarks\hidden\pilot-0.1\oracle` (only if you keep a copy in the clone; Part 1, step 3 imports it into Docker) | `True` |

Every trial starts its own container that asks Docker for 8 CPUs. With fewer, Docker refuses with
`range of CPUs is from 0.01 to 2.00, as there are only 2 CPUs available`, and every trial is
recorded as an infrastructure failure. Raise the CPUs for the WSL 2 backend in `%UserProfile%\.wslconfig`
(`[wsl2]` then `processors=16`), run `wsl --shutdown`, and start Docker Desktop again.

`benchmarks\hidden` holds the evaluator's answers. Copy it in privately; it is never in Git and
never in an image.

## Part 1. One-time setup

### 1. Open PowerShell and set three variables

Do this in **every** new PowerShell window.

```powershell
$env:COMPOSE_FILE = "deploy/compose.yaml"
$env:MSYS_NO_PATHCONV = "1"
$sh = "$env:ProgramFiles\Git\bin\sh.exe"
```

Nothing prints. `MSYS_NO_PATHCONV` stops Git for Windows rewriting container paths such as
`/export`; without it the scripts print success and copy nothing.

### 2. Get the code

First time:

```powershell
git clone --branch codex/multi-agent-mg2 https://github.com/R-V-Abhishek/ReCycleGuard.git
cd ReCycleGuard
```

Already cloned for the earlier runs:

```powershell
cd ReCycleGuard
git status --short
git fetch origin
git switch codex/multi-agent-mg2
git pull --ff-only
```

`git status --short` must print nothing before you pull (if it lists files, stash or commit them
first; the experiment needs a clean tree). Then record the revision, and write it in your notes:

```powershell
git rev-parse HEAD
```

### 3. Copy the evaluator data into its Docker volume (once)

Replace the path with where your copy of the folder is.

```powershell
& $sh scripts/docker/import-hidden.sh C:\path\to\hidden
```

Expect `Imported ... into the evaluator volume.` If it prints `missing s06-dev-0.1/clean` or
`missing pilot-0.1/oracle`, the folder is wrong or incomplete. The volume keeps the data across
rebuilds, so skip this step next time.

### 4. Build the images

```powershell
docker compose --profile setup --profile tools --profile build-only --profile monitor build
```

Expect it to end without `ERROR`. The first build downloads a lot and can take 10 minutes or more.
The `trials` image contains the code, so **this build fixes the code revision of every run**.
**Do not rebuild or `git pull` while a queue is running.**

### 5. Download and configure the model (once)

Skip this step if you did the earlier runs on this PC. Check first:

```powershell
docker compose --profile tools run --rm --no-deps trials ls /models/provenance/qwen3.5-9b-q8_0
```

If it lists `local-model.json`, `server-session.json` and a weights manifest, skip to step 6.
Otherwise:

```powershell
docker compose --profile setup run --rm model-download
docker compose --profile tools run --rm trials python scripts/configure_local_model.py --llama-cpp /models/provenance/qwen3.5-9b-q8_0
```

The download is about 10 GB. It is pinned by revision and checked against a manifest; a mismatch
stops it.

### 6. Start the model with 6 slots

```powershell
$env:SLOTS = "6"
docker compose up -d --force-recreate model
docker compose logs -f model
```

Wait until the log reports that the server is listening, then press **Ctrl+C**. That only stops the
log; the model keeps running. Then confirm all three of these:

```powershell
docker inspect --format '{{.State.Health.Status}}' recycleguard-model
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
docker compose --profile tools run --rm --no-deps trials cat /models/provenance/qwen3.5-9b-q8_0/server-session.json
```

| Check | Expect | If not |
| --- | --- | --- |
| Health | `healthy` (it can say `starting` for up to 3 minutes) | `docker compose logs model`, look for the first error |
| GPU memory | `memory.used` well under `memory.total`, at least 3 GB free | see below |
| `server_flags` in the JSON | contains `--parallel` and `6` | you skipped `$env:SLOTS`; repeat this step |

If less than 3 GB of the 24 GB is free, use 4 slots instead. Set `$env:SLOTS = "4"`, repeat step 6,
and change `"slots": 6` to `"slots": 4` in **both** files in `docs/checkpoints/mg2/queue/`. Write the
number in `EXPERIMENT_LOG.md`. Do not let the model spill into shared GPU memory: it is far slower.
Every arm must use the same slot count.

### 7. Probe the model

```powershell
docker run --rm --network container:recycleguard-model --volume recycleguard-model-provenance:/models/provenance:ro --entrypoint /opt/venv/bin/recycleguard recycleguard-investigator:local model probe --config /models/provenance/qwen3.5-9b-q8_0/local-model.json
```

It must pass and show the prompt `u01_non_thinking_v7`. If the probe fails, fix that before going
on; see Part 8.

## Part 2. Checks before you leave it running

All of these run inside the container and change nothing.

```powershell
docker compose --profile tools run --rm --no-deps trials python scripts/write_mg2_prompts.py --check
docker compose --profile tools run --rm --no-deps trials python scripts/run_queue.py --check docs/checkpoints/mg2/queue/queue-baseline.json
docker compose --profile tools run --rm --no-deps trials python scripts/run_queue.py --check docs/checkpoints/mg2/queue/queue-agents.json
```

| Command | Expect |
| --- | --- |
| prompt check | no output |
| baseline queue | 4 lines, then `queue mg2-baseline: 4 sessions, 224 trials, 6 slots` |
| agents queue | 14 lines, then `queue mg2-agents: 14 sessions, 784 trials, 6 slots` |

An error here (a missing prompt, a bad protocol) is a defect in the files. Do not start the queue.

Optional but recommended once: the whole test suite, about 20 minutes. It continues past failures
and reports them at the end.

```powershell
docker compose --profile tools run --rm test
```

## Part 3. Start the baseline queue

```powershell
docker rm mg2-queue 2>$null
docker compose --profile tools run -d --name mg2-queue trials python scripts/run_queue.py docs/checkpoints/mg2/queue/queue-baseline.json
```

`docker rm` prints an error the first time because nothing exists; ignore it. The second command
prints a container id and returns at once. The queue now runs by itself.

Confirm it started, within a minute:

```powershell
docker ps --filter name=mg2-queue
docker logs --tail 20 mg2-queue
```

Expect `Up ...` and lines such as `started ablated-baseline-fixed:u01_non_thinking_v7 (attempt 1)`.
If the container is gone, run `docker logs mg2-queue` and read the last lines; the usual cause is
the server check in Part 8.

## Part 4. Watch it, or leave it

You do not have to watch. Come back whenever you like.

```powershell
docker exec mg2-queue cat /work/_status/status.md
docker exec mg2-queue sh -c 'tail -n 5 /work/mg2-baseline/*.log'
docker logs --tail 20 mg2-queue
```

The status file shows trials done of the total, the time left, how many slots are busy and which
session is running. Sessions are named `<job>:<prompt>`. A session may show `idle_seconds`; if one
passes 1800 the queue restarts that session by itself.

A page for the same information (optional, start it after the queue has begun):

```powershell
docker compose --profile monitor up -d status
ipconfig
```

Open `http://localhost:8099`, or `http://<this PC's IPv4 address>:8099` from another machine on the
network. It is read-only, serves one folder, and reloads every 30 seconds. Stop it with
`docker compose --profile monitor rm -sf status`.

### Control it while it runs

```powershell
docker exec mg2-queue touch /work/mg2-baseline/PAUSE    # start nothing new; running sessions finish
docker exec mg2-queue rm /work/mg2-baseline/PAUSE       # carry on
docker exec mg2-queue touch /work/mg2-baseline/KILL     # stop every session before its next trial
```

`KILL` ends the queue with exit code 3 and the message `stopped by KILL. Remove it and rerun the same
command to resume.` The container is then gone, so remove the file this way and start Part 3 again:

```powershell
docker compose --profile tools run --rm --no-deps trials rm /work/mg2-baseline/KILL
```

Nothing finished is repeated: every session continues from its own ledger. The same applies if the
PC reboots; run the two Part 3 commands again.

### What the queue does by itself

- A session that exits non-zero, or whose ledger has not moved for 30 minutes, is started again, at
  most 3 times, then marked `FAILED`.
- While the model container is `unhealthy` or down, running sessions stop between trials and nothing
  new starts. After 2 minutes it restarts the model (same flags), at most twice, then waits for you.
  Trials in flight during an outage are recorded as infrastructure failures. List them in the
  report; do not hide them.
- Each finished development session is scored as soon as it is whole. When the queue ends,
  `compare.csv` in `/work/mg2-baseline/` puts the sessions side by side.

The queue ends by itself. Exit code 0 prints `queue finished; development sessions are scored`.
Exit code 1 lists the sessions that failed after 3 attempts.

```powershell
docker wait mg2-queue
docker logs --tail 5 mg2-queue
```

`docker wait` blocks until it ends and prints the exit code.

## Part 5. The agent queue, from the same build

When the baseline queue has finished, with **no rebuild and no pull**:

```powershell
docker rm mg2-queue
docker compose --profile tools run -d --name mg2-queue trials python scripts/run_queue.py docs/checkpoints/mg2/queue/queue-agents.json
```

Watch and control it as in Part 4, replacing `mg2-baseline` with `mg2-agents` in the paths. The
model container stays up between the two queues; if you stopped it, repeat Part 1 step 6 with the
same `$env:SLOTS`.

You can edit `queue-agents.json` while it runs: it is read again between sessions. Adding a job or
removing one that has not started is allowed. A prompt that is already in the queue must stay
byte-identical, and `name`, `model_root` and `slots` cannot change, or the queue refuses.

## Part 6. After each queue: export and commit

```powershell
& $sh scripts/docker/export-results.sh mg2-baseline docs/checkpoints/mg2/runs/pc
& $sh scripts/docker/export-results.sh mg2-agents docs/checkpoints/mg2/runs/pc
git status --short
```

Expect `Exported mg2-baseline to ...` and files under `docs\checkpoints\mg2\runs\pc`. It copies
ledgers, results, protocols, scores, tables, logs and isolation evidence for each session. Bundles
and data roots hold dossier data and stay in the volume. Then:

1. Read `compare.csv` and the tables, and report as in Part 7.
2. Add the result, the decision and what it motivates as the next numbered entry in
   `EXPERIMENT_LOG.md` (entry 12 onward). Never edit an earlier entry.
3. Commit only the exported files and the log. Do not commit weights, tokens, `.env` values or
   anything from `benchmarks\hidden`.

## Part 7. What to read, and how to report it

- `supported_case_success` per arm and arena, with the paired bootstrap against SC. Report each
  number twice: full, and deterministic-only from `t3_model_influence`. The agents' contribution is
  the gap.
- False positives per case, and proposals rejected by reason (`NO_VERIFIED_CLAIM`,
  `CONTRADICTED_BY_CALCULATION`).
- Per agent: schema-valid, semantically valid and wrong-but-valid rates, calls, tokens, wall time.
- From `graph.agent.result` in the traces: the Retriever's grades, refusals, searches and
  reformulations; claims proposed, verified and dropped, and why; passages read of passages
  available; why it stopped.
- Signal families against judgement families, as in MG1 improvement 2.
- Infrastructure failures from outages, listed separately.

A result of no lift is valid. Report it as such.

## Part 8. Something went wrong

| What you see | Cause | What to do |
| --- | --- | --- |
| `range of CPUs is from 0.01 to N.00` in a trial's `child.log`; every trial `INFRA_FAILED` | Docker has fewer than 8 CPUs | Part 0, `.wslconfig` |
| Queue exits: `the model server runs with None, the sweep needs [...]` | model not started, or started with other slots | Part 1 step 6 |
| Queue exits: `a configuration changed since this queue started` | a prompt, the model or the code changed under a running queue | start a new queue `name`; never mix |
| Queue exits: `this queue name was used with another model or slot count` | `slots` was edited after the queue began | restore it, or use a new `name` |
| `run_trials.py` refuses: `api` is up | the demo stack is running | `docker compose --profile demo down` |
| Docker error `container name "/mg2-queue" is already in use` | an old queue container exists | `docker rm mg2-queue` |
| A session shows `FAILED` | 3 attempts exhausted; rerunning the queue does **not** retry it | read `/work/<queue>/<job>-<prompt>.log`, fix the cause, then run that job again in a new queue file with a new `name`; report both |
| `compare.csv` is missing | a session is not whole | `docker exec mg2-queue cat /work/_status/status.md` |
| Probe fails or replies are refused | model server or reply format | `docker compose logs model`; `docs/checkpoints/mg1/DOCKER_RUNBOOK.md` section "If the first start fails" lists causes and where to fix them |
| The status page is blank | queue has not begun, so `/work/_status` does not exist yet | start the queue, then `docker compose --profile monitor up -d --force-recreate status` |

To look inside a session's data: `docker compose --profile tools run --rm --no-deps trials ls /work`.

Never delete the Docker volumes (`recycleguard-trial-data`, `recycleguard-model-weights`,
`recycleguard-model-provenance`, `recycleguard-evaluator-data`): they hold the ledgers, the 10 GB
download and the evaluator data. `docker compose down` without `-v` is safe.

## Part 9. Choose, freeze, and the held-out run (a person does this)

**Superseded for this project (2026-11-11).** The held-out run was done once on a Kaggle T4
instead: `CLOUD_RUNBOOK.md` Part 5, log entry 15, PREREGISTRATION deviations of 2026-11-11. It
settles both open points below: the freezes stay untracked in `benchmarks/heldout/freeze/`, and
`held_out_visible_root` is the checkout-relative `benchmarks/heldout/visible`. The text below is kept
as written.

This part cannot be run from here step by step yet, and it should not be rushed. The held-out
dossiers run once, for D0, SC, v7 and the single best new arm, and the result stands.

1. Apply the selection rule in `PREREGISTRATION.md` (false positives first, then recall, then calls)
   to the development sessions. A fourth prompt version is allowed only if a result motivates one
   change; log the reason before it runs.
2. Commit and push everything. The tree must be clean. Rebuild the image from that commit.
3. A person builds a freeze manifest with `scripts/make_freeze.py <spec.json> <freeze.json>` for the
   chosen prompt digests, code revision and slot count, and the protocol digest. Nothing is tuned
   after this.
4. A final queue file lists one job per arm with `"final": true` and `"held_out": "<freeze file>"`.
   Start it as in Part 3, then allow it: `docker exec mg2-queue touch /work/<queue name>/ALLOW_FINAL`.
   `run_trials.py` refuses unless the freeze verifies against this exact code and protocol.

Two things are **not verified and need a decision before step 3**, so do not start without them:

- `verify_freeze(strict_commit=True)` compares the current commit to the frozen one. A committed
  freeze file creates a newer commit, so it can never verify. Decide how the file is kept (for
  example, untracked and copied into the image) and test it on a development protocol first.
- The freeze must name `held_out_visible_root`, a directory that exists where the run happens.
  Confirm which folder holds the held-out visible dossiers in the evaluator volume.

checking-8 is a development set that has been looked at; report it as a secondary check only.

## Known limits

- The status page, the model restart and six concurrent sessions are untested on the PC. The earlier
  runs used at most four. If sessions collide or the GPU runs out of memory, use 4 slots and note it.
- Greedy decoding under several slots can differ in the last digits of the logits. Compare arms only
  inside one slot count, and use the repeats.
- A 9B model chooses passages from their first 100 characters. Coverage shows what was not read.
- n=16 with one or two cases per family: the intervals are wide.
