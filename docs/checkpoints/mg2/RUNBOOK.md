# MG2 runbook (PC, real model)

Status: written and not yet run. Nothing here is a result. The laptop has no model, so every
quality number comes from these steps on the PC. Follow `docs/checkpoints/mg1/DOCKER_RUNBOOK.md`
for the container and the model server; only the differences are listed here.

## What is compared

| Arm | How it runs | Where its result appears |
|---|---|---|
| D0 deterministic only | the `V0` control, no model, report from the deterministic pipeline | `by_variant.V0` and the control rows of each session |
| S1 single agent | `sweep-mg2-single`: prompt v7, `FIXED_RETRIEVAL` and `ADAPTIVE` on the current code | `sweep-mg2-single-u01_non_thinking_v7` |
| M2 Reader + Analyst | `sweep-mg2-agents`: variant `READER_ANALYST` | `sweep-mg2-agents-mg2_reader_analyst_v1` |
| M2-nr Analyst only | same sweep: variant `ANALYST_ONLY` | same session |

Both protocols use the 16 tuning cases and 2 repeats. The arms differ only in architecture and
prompt: same weights, same slots, same code revision. Run both sweeps from one commit. The
source pin makes a run fail if the code changes mid-run, by design.

## Steps

1. Pull `codex/multi-agent-mg2` on the PC and note the commit. Run
   `uv run pytest tests/unit/test_agents.py tests/integration/test_agents_workflow.py` first.
2. Start the model server with `SLOTS=3` as in the MG1 runbook.
3. `python scripts/run_sweep.py docs/checkpoints/mg2/sweeps/sweep-mg2-single.json`
4. `python scripts/run_sweep.py docs/checkpoints/mg2/sweeps/sweep-mg2-agents.json`
   (`KILL` in `/work/<sweep name>/` stops a sweep, as in MG1; rerunning resumes.)
5. Commit the run folders under `docs/checkpoints/mg2/runs/` as MG1 did. Do not commit weights,
   tokens or `.env` values.

## What to read, and how to report it

- `success`, with intervals, per arm. Report every number twice: full success, and
  deterministic-only success from `t3_model_influence`. The agents' contribution is the gap.
- False positives per case and proposals rejected, by reason. `NO_VERIFIED_CLAIM` counts
  Analyst proposals no verified claim backed; `CONTRADICTED_BY_CALCULATION` counts the rest.
- Invalid-output rate, calls, tokens and wall time per case. M2 should use at most 7 calls
  (6 Reader chunks plus 1 Analyst call). A case that reaches the chunk cap is stated in the
  report as "Inspected k of n", and its stop reason is `NO_NEW_EVIDENCE`, not resolved.
- Per-claim behaviour from the trial traces: claims proposed, verified, dropped (and why).

## Decision rule

M2 counts as an improvement only if it beats the better of D0 and S1 on tuning-16 in both
repeats, and then does not regress on checking-8. If D0 is at or near the ceiling on tuning-16,
there is no headroom: say so, and judge M2 by false-positive reduction and by checking-8.
A "no lift" result is a valid result and is reported as one.

## checking-8

Run once, at the end, for the winning arm only, through the frozen held-out path
(`--held-out <freeze.json>`). Do not read its cases, tune on it, or rerun it after a failure.
`run_sweep.py` refuses a sweep that includes a checking case.

## Known limits

- Reader quality on a non-thinking 9B model is unmeasured. M2-nr isolates its effect.
- The deterministic text checks (F11, F12, F14, F16) already read document text with regexes and
  win their families. The Reader can add only what they miss, such as paraphrases.
- n=16 with one or two cases per family: intervals are wide.
- The deterministic engine is frozen for this experiment. Any engine bug found by the baseline
  is logged and fixed for every arm, never for one.
