# Docker runbook: the RTX PC

The active way to run ReCycleGuard's tests and real-model trials. It replaces the Mac steps in
[MODEL_TEST_HANDOFF.md](MODEL_TEST_HANDOFF.md), which stay as the backup route and as the reference for how to
read each check. **Nothing here is an approval.** Dev cases only: never run `--held-out` or create a freeze
from this runbook.

## What is proven and what is not

Run on Windows Docker Desktop with a fake model and no GPU (backend `FIXTURE_NOT_EVIDENCE_DOCKER`):
image builds, per-trial containers, isolation evidence, all four variants, scoring, tables, export, the server-down
stop and resume. That shows the pipeline works, not that the model does.

**Never run yet:** `llama-server` itself, the GPU, the real download and the real model. The reply format
comes from reading llama.cpp's source, so expect the first start to need small fixes.

## Setup

| Item | Value |
| --- | --- |
| Model | `unsloth/Qwen3.5-9B-GGUF`, `Qwen3.5-9B-Q8_0.gguf`, 9.5 GB, Apache-2.0 |
| Tokenizer | `Qwen/Qwen3.5-9B` |
| Runtime | llama.cpp build `b12033`, CUDA image pinned by digest |
| Everything pinned in | [deploy/model.env](../../../deploy/model.env) |

Clone on Windows and run everything from the repository root in **PowerShell**, with Docker Desktop running. The
repository's `.gitattributes` keeps the files containers read on LF line endings, so no Git setting is needed. Trial data and
weights live in Docker volumes, so the Windows folder does not slow the runs.

The two shell scripts need Git for Windows' `sh.exe`. `MSYS_NO_PATHCONV` stops it rewriting container paths such as
`/export`; without it they print success and copy nothing.

Set these in every new PowerShell window:

```powershell
$env:COMPOSE_FILE = "deploy/compose.yaml"
$env:MSYS_NO_PATHCONV = "1"
$sh = "$env:ProgramFiles\Git\bin\sh.exe"
```

First time only:

```powershell
git clone --branch cp-5_windows_model https://github.com/R-V-Abhishek/ReCycleGuard.git
cd ReCycleGuard
```

`benchmarks/hidden/` is git-ignored and holds evaluator answers. Copy it into the clone privately, never through Git. It
stays out of every image. Then:

```powershell
& $sh scripts/docker/import-hidden.sh benchmarks/hidden
docker compose --profile setup --profile tools --profile build-only build
docker compose --profile setup run --rm model-download     # about 10 GB
docker compose --profile tools run --rm trials python scripts/configure_local_model.py --llama-cpp /models/provenance/qwen3.5-9b-q8_0
docker compose up -d model
docker compose logs -f model                               # wait for the server to report it is listening
```

Confirm the GPU is really used: the log reports layers offloaded and `nvidia-smi` shows about 10 GB or more in use.
Then probe from inside the model's network. It must pass and show prompt `u01_non_thinking_v7`:

```powershell
docker run --rm --network container:recycleguard-model --volume recycleguard-model-provenance:/models/provenance:ro --entrypoint /opt/venv/bin/recycleguard recycleguard-investigator:local model probe --config /models/provenance/qwen3.5-9b-q8_0/local-model.json
```

### If the first start fails

Fix these inside `deploy/` or the `llama_cpp` branch of `src/recycleguard/local_model.py`. Do not change the MLX path
and do not loosen any check on the model's own output. Rebuild both `investigator` and `trials` after any source change.

| Symptom | Where to look |
| --- | --- |
| Reply refused for an unknown field | Name the field in `_LlamaCompletion`, after reading what it holds |
| `backend runtime fingerprint differs` | `system_fingerprint` is expected to start `b12033-`; check the actual reply |
| `does not serve the pinned model path` | `--alias` in `deploy/start_model.py` |
| Prompt echoes or special tokens look wrong | `/v1/completions` must parse `<\|im_start\|>` as a special token |
| Unknown server flag | `FLAGS` in `start_model.py` and `LLAMA_SERVER_FLAGS` must stay equal; a test checks this |

## Pipeline check without the GPU (5 minutes)

Run this if you want to separate a Docker problem from a model problem. It labels its output as not evidence.

```powershell
docker compose rm -sf model                                 # frees the name; volumes are kept
docker compose --profile fixture up -d --no-deps fake-model
docker compose --profile tools run --rm trials python scripts/run_trials.py docs/checkpoints/mg1/protocols/dry-run-all-variants.json /work/pipeline-check --config /models/provenance/fixture/local-model.json --docker
docker compose --profile fixture rm -sf fake-model
docker compose up -d model
```

## Full test suite: first run on this code

```powershell
docker compose --profile tools run --rm test
```

It runs ruff, the schema and API checks, pytest and the UI checks, continuing past failures. Fix what fails and rerun.

## Trials

Every run uses this command, with a new `<name>` per run:

```powershell
docker compose --profile tools run --rm trials python scripts/run_trials.py docs/checkpoints/mg1/protocols/<protocol>.json /work/<name> --config /models/provenance/qwen3.5-9b-q8_0/local-model.json --docker
```

Score and build tables for every trial output:

```powershell
docker compose --profile tools run --rm trials python scripts/score_trials.py /work/<name> benchmarks/hidden/pilot-0.1/oracle tests/fixtures/visible /work/<name>-scores
docker compose --profile tools run --rm trials python scripts/make_tables.py /work/<name> /work/<name>-scores /work/<name>-tables
```

To stop a schedule before its next trial, run this from a second window:

```powershell
docker compose --profile tools run --rm --no-deps trials touch /work/<name>/KILL
```

Remove that file the same way (`rm`), then rerun the same command to resume. **Do not rebuild images while a schedule runs**: runs pin the source, and every trial uses the current image.

Run in order:

| Step | Protocol | Notes |
| --- | --- | --- |
| A. Isolation and speed | `isolation-check`, then `smoke` | Both must pass isolation. Use `smoke` to measure speed and to estimate the later steps. |
| B. Tuning | `tuning-16` | The only set used to adjust prompts. Bump the prompt version per change and keep each result. No case-specific hints; do not loosen any check. |
| C. Constrained | `tuning-16`, new name | Skip if B reaches 95% schema-valid and shows no failure a schema could prevent; record that. Otherwise see below. |
| D. Checking | `checking-8` | Once, on the chosen setup. Never tune from it; if you do, say so, because it stops being a check. |
| E. Reliability | `reliability`, then `repeats` | No prompt change after D. |
| F. Failures | `smoke`, new name | See below. |
| G. Controls | `dry-run-all-variants` | V0 and SC must make no model call. Any `canaries.drifted` entry is a result to report, not a failure to fix. |

**Forced cap (after A).** Real-model runs refuse per-run budget overrides, so the cap comes from its own pinned
configuration. Each run must stop at 2 model calls or fewer with no third dispatch:

```powershell
docker compose --profile tools run --rm trials python scripts/configure_local_model.py --forced-cap 2 --llama-cpp /models/provenance/qwen3.5-9b-q8_0
docker compose --profile tools run --rm trials python scripts/run_trials.py docs/checkpoints/mg1/protocols/forced-cap.json /work/forced-cap-2 --config /models/provenance/qwen3.5-9b-q8_0/local-model-forced-cap.json --docker
```

**Constrained mode (C).** The server enforces the schema per request, and the flag records it in the pin:

```powershell
docker compose --profile tools run --rm trials python scripts/configure_local_model.py --constrained --llama-cpp /models/provenance/qwen3.5-9b-q8_0
$env:CONSTRAINED = "1"
docker compose up -d --force-recreate model
```

Use `local-model-constrained.json` as `--config`. Report speed against B, choose one setup for all later runs and
record why. To go back, run `Remove-Item Env:CONSTRAINED` and recreate the model the same way.

**Failures (F).** Each trial runs in a container labelled `recycleguard.trial=1`.

1. During a trial, kill the coordinator (`docker kill` the `trials` run container). Rerun the same command. Expect an
   `INTERRUPTED` row, the orphaned trial container removed, and that trial attempted again in a fresh root.
2. During a model call, `docker kill recycleguard-model`. Expect that trial to end `FAILED` with `PROVIDER_TIMEOUT` and
   exactly one POST for that operation in its trace. An uncertain dispatch is never retried. Later trials record
   `INFRA_FAILED`, and the schedule stops with `INFRASTRUCTURE_FAILURES` after three.
3. `docker compose up -d model`, rerun the same command. Expect it to resume and repeat no finished trial.

## Isolation evidence

There are two records per trial, both exported:

- `isolation-inspect.json`: what Docker was asked to run, checked **before it starts**. It must be read-only, with all
  capabilities dropped, nonroot, no binds or devices, only the allowed volumes, and on the running model's network.
  Any difference stops the schedule.
- `runtime/isolation-evidence-real.json`: from inside the container before the investigation starts. Evaluator paths and
  the Docker socket must be absent, the mount table must hold nothing else, writes to read-only mounts must fail, the
  network and `api` port must be unreachable, and `benchmarks` must not import. Every entry must have `denied: true`.

Never make a failing probe pass and never remove one. Real-model trials report backend `LOCAL_MODEL_DOCKER`.

**A limit to disclose:** the investigator shares a network namespace with the model server, so it can call the server's
other endpoints, and it is not protected against a hostile Docker host. `trials` holds the Docker socket, which is
effectively root on the host. Only your own evaluator code runs there.

## What to report

Report each MG1 criterion as measured per variant with its denominator, using the table in
[MODEL_TEST_HANDOFF.md](MODEL_TEST_HANDOFF.md#mg1-criteria-to-report). This is a **new setup**: 9B at Q8_0 on llama.cpp is not
comparable to the Mac's 4-bit MLX runs, which stay as history. Also report rejected proposals by reason, refused
actions and repairs, the largest prompt, V2 minus V1, GPU memory in use, and any F16 proposal acting on injected text.
A result showing no improvement is valid.

If 9B again produces no accepted finding on `tuning-16`, the next thing to try is Qwen3.5-27B at Q4_K_M. Edit
`deploy/model.env` (repository, revision, file, quantization, tokenizer, slug), rebuild `model-download`, download and
configure again. That is another new setup, and MG1 applies to whichever one is finally chosen.

```powershell
& $sh scripts/docker/export-results.sh <name> docs/checkpoints/mg1/runs/pc
```

This copies the ledger, results, protocol, backend label, scores, tables and isolation evidence. Bundles and data roots
hold dossier data and stay in the volume. Add results to `MODEL_TEST_RESULTS.md`. Do not commit data roots, bundles,
weights, `.env`, tokens or anything from `benchmarks/hidden`. Do not mark MG1 approved.

## Demo stack

```powershell
$env:RECYCLEGUARD_API_TOKEN = "<a long random value>"
docker compose --profile demo up -d
```

Open `http://127.0.0.1:8080`, and enter that same address as the API address. **Bring it down before any trial**
(`docker compose --profile demo down`, then `docker compose up -d model`). `run_trials.py` refuses to start while `api` is up.
