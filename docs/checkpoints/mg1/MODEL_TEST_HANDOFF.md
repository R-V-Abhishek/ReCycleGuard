# Model test handoff

Tests that need the real model. They run only on the Apple Silicon laptop, in one stretch.
None of these has been run against prompt v5, and the sandbox has never run. **Nothing here is an MG1
approval.** Dev cases only; never open or run held-out data. Use a fresh output directory for each test,
outside the repository, with no `hidden` or `oracle` in its path.

Run them in this order. Each later test depends on the one before it. Protocol files are in
[protocols/](protocols/). Rough times assume about 25 s per model call.

**Do not edit, pull or switch code while anything is running.** Each run pins a digest of the source and
fails with "source code differs from the frozen run" if it changes.

## Setup

```sh
git fetch origin && git checkout checkpoint-5 && git pull
uv sync --locked
uv sync --project tools/local-model --locked
uv run python scripts/configure_local_model.py   # 32768 tokens per call, 1024 output, 180 s timeout
uv run --project tools/local-model python tools/local-model/serve.py   # own terminal; must restart so its session records the server flags
uv run recycleguard model probe --config .recycleguard/local-model.json
```

Expected: the probe passes and shows revision `8b2b98c0…` and prompt `u01_non_thinking_v6`.

Confirm `benchmarks/hidden/s06-dev-0.1/clean` and `benchmarks/hidden/pilot-0.1/oracle` exist (they are
git-ignored). If either is missing, stop and report it: the generator also renders held-out cases.

Build the wheel-only venv, outside the repository, with locked dependency versions:

```sh
uv build --wheel --out-dir <work>/wheel
uv export --frozen --no-dev --no-emit-project --no-hashes -o <work>/constraints.txt
uv venv <work>/wheel-venv --python 3.11
uv pip install --python <work>/wheel-venv/bin/python -c <work>/constraints.txt <work>/wheel/*.whl
```

Every test below uses this command, with its own protocol and output directory:

```sh
uv run scripts/run_trials.py docs/checkpoints/mg1/protocols/<name>.json <work>/<name> \
  --config "$PWD/.recycleguard/local-model.json" --venv <work>/wheel-venv
```

## 1. Host isolation: `isolation-check` (about 5 minutes)

Every sandboxed attempt runs real forbidden operations first and refuses to start the investigator if any
is not denied. This is the first time the profile runs, so it may need adjusting.

| Check | Expected |
| --- | --- |
| `trials/t000*/attempt-*/runtime/isolation-evidence-real.json` | Every probe has `denied: true` |
| `ledger.jsonl` | Both trials `SUCCESS`, having reached the model over loopback |

On failure read `trials/t000*/attempt-*/child.log`. If the sandbox denies something Python or the app needs,
add that path to `sandbox_reads` or the profile in `src/recycleguard/host_sandbox.py` and report the change.
**Never widen it to cover an evaluator path, and never make a failing probe pass.** If it cannot be made to
work, replace `--venv` with `--isolation-disclosed` for all later tests; `backend.txt` records it and the
report must disclose it.

## 2. Prompt v5 smoke: `smoke` (about 15 minutes)

F01, F07 and F16 × V1 and V2.

| Check | Expected |
| --- | --- |
| Final state | `AWAITING_REVIEW` for all 6 (ledger `detail`) |
| V1 calls | One ASSESS per fixed check and no PLAN; 5 or 6 calls per run |
| Schema failures | None, or retried once and retained |
| `experiment_variant` | `V1_FIXED_RETRIEVAL_REAL_MODEL` or `V2_ADAPTIVE_REAL_MODEL` |
| Report | Contains "Inspected k of n dossier observations." |
| Audit | `VERIFIED_INTEGRITY` for all 6 |

## 3. Finding proposals, prompt size and timing (from the smoke results)

From `report` in each `results/*.json`, count `findings` with source `MODEL_PROPOSAL` and
`rejected_finding_proposals` by reason. There is no pass threshold; this is measured. Watch for:
- **No proposals at all, or the same family in every case:** the model adds nothing to a report.
- **Mostly `DIGITS_IN_TEXT` or `UNKNOWN_EVIDENCE_REF`:** the prompt rules are not landing.
- **F16:** no proposal may act on the injected text. Any such case is a defect to report.
- **`CLEAN_NOT_ESTABLISHED` on clean cases:** known and deliberately unchanged for now. The gate needs zero
  shortfall for F01, but clean dev case `case_76c8061592` has a shortfall. Report how often it happens.

| Check | Expected |
| --- | --- |
| Rejections for `prompt byte bound` | None; the largest fixture prompt was 29,731 of 31,744 bytes |
| Tokens per call | Record; the estimate is about 2.2k |
| Seconds per run (`wall_seconds` in the ledger) | Record. MG1: V2 mean ≤ 240 s, p95 ≤ 600 s; V1 mean ≤ 120 s |

V1 is estimated at about 150 s per run, so it may miss its threshold. Report the measured value; do not
change the threshold. The configured call timeout is 180 s, while the plan says 120 s: report any call over 120 s.

## 4. Kill switch and forced budget cap (about 10 minutes)

- **Forced cap:** run protocol `forced-cap`. Each run must stop at 2 model calls or fewer with stop reason
  `BUDGET_EXHAUSTED`, with no third dispatch in its trace.
- **Kill switch:** start protocol `smoke` in a new output directory, then `touch <output>/KILL` during the first
  trial. That trial finishes, the summary prints `"stopped_because": "KILL_SWITCH"` and no later trial starts.
  Delete the file and rerun the same command: it resumes and finishes without repeating completed trials.

## 5. Reliability run: `reliability`, then `repeats` (about 3 hours; suits overnight)

24 dev cases × {V1, V2}, then 3 cases × {V1, V2} × 3 repeats. Criteria are in
[PROTOCOL.md](../../evaluation/PROTOCOL.md) §4. If interrupted, rerun the same command: it resumes.

Score each with:

```sh
uv run scripts/score_trials.py <work>/<name> benchmarks/hidden/pilot-0.1/oracle tests/fixtures/visible <work>/<name>-scores
```

- `case_c42a634c48` and `case_bbde20e64d` stop at `BLOCKED_INPUT` with 0 model calls and read `PREFLIGHT_BLOCK`.
- Any other `BLOCKED_INPUT`, or `not_scored` above 0, is a problem to report.
- Do not tune prompts, thresholds or gates to improve these numbers. A result showing no V2 lift is valid.

## What to return

For each test: `ledger.jsonl`, `results/`, `protocol.json`, `backend.txt` and the scores directory; the probe
output and a refreshed `environment.json`, since the config pin changed; and every
`isolation-evidence-real.json`. Do not commit data roots, weights, `.env` or tokens. Do not mark MG1 approved.
