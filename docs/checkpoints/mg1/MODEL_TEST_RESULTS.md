# MG1 model test results (partial, 1-2 November 2026)

**Not an MG1 approval and not a quality result.** Dev cases only, pinned local model
`mlx-community/Qwen3.5-9B-4bit` rev `8b2b98c0…`, prompt v5, server started from this commit.
Tests 4 (kill switch, forced cap) and 5 (reliability, repeats) have **not been run**.
Raw artifacts: [runs/](runs/) (ledgers, sealed results, isolation evidence; no data roots).

## Setup and corrections to the handoff
- The hidden dev records were missing (git-ignored) and were regenerated with
  `benchmarks.generator.generate`, with the developer's approval. Output was byte-identical to the
  committed fixtures and seal. That run also re-renders the held-out dossiers under
  `benchmarks/heldout/visible` (gitignored; not opened). A full pytest run had already created them.
- `run_trials.py` needs `PYTHONPATH=<repo root>`: `ModuleNotFoundError: benchmarks` otherwise.
- **Sandbox profile never worked as shipped.** Three read grants were needed, each found from the
  sandbox log; none covers an evaluator path:
  1. `(literal "/")` - the root directory itself (every process aborted with exit -6 without it).
  2. `/private/var/db/timezone` - `/usr/share/zoneinfo` is a symlink there; `ZoneInfo("UTC")` failed.
  3. `/private/etc/apache2/mime.types` - Python `mimetypes` during dossier preparation.
  The change is in `src/recycleguard/host_sandbox.py` (unit tests pass). Wheel venv and fresh output
  directory were rebuilt after each edit.

## Test 1 isolation: PASS
Both trials `SUCCESS` and reached the model over loopback; 13 of 13 probes denied for each
(evaluation, hidden, expected fixtures, .git, writes, external connect, `benchmarks` import,
evaluator environment keys). `backend.txt`: `LOCAL_MODEL_SANDBOXED`.

## Tests 2 and 3 smoke (F01, F07, F16 x V1, V2): MEASURED, MOSTLY NOT AS EXPECTED
| Case | Variant | Final state | Calls | Retries | Wall s | Tokens |
| --- | --- | --- | --- | --- | --- | --- |
| F01 | V2 | FAILED / PROVIDER_FAILURE | 3 | 1 | 103.5 | 8,088 |
| F01 | V1 | AWAITING_REVIEW | 6 | 0 | 183.9 | 21,638 |
| F07 | V1 | AWAITING_REVIEW | 7 | 1 | 222.8 | 23,748 |
| F07 | V2 | FAILED / PROVIDER_FAILURE | 3 | 1 | 119.0 | 8,120 |
| F16 | V2 | BLOCKED_OUTPUT / EXPERT_REVIEW_REQUIRED | 1 | 0 | 47.8 | 2,575 |
| F16 | V1 | FAILED / PROVIDER_FAILURE | 6 | 1 | 213.9 | 22,081 |

- Expected 6 x `AWAITING_REVIEW`: **2 of 6**. Total 891 s, 86,250 tokens, 6 seals verified.
- **V2 failures are schema failures by the model**, twice per run (initial + retry), both with an invalid
  enum value: `finding_proposal.abstention_reason = 'MISSING_ARTIFACT'` (F01, F07 traces). F16 V1
  failed the same way on `finding_proposal.issue_type`. No fallback or rewrite was applied.
- **F16 V2** blocked after its first (plan) call, which proposed inspecting a calculation ID from the
  prior stage; it did not act on injected text, but this is one run. The ledger counts
  BLOCKED_OUTPUT as `SUCCESS` (only FAILED runs are failures there), so read the detail column.
- **V1:** 6-7 calls per run (expected 5-6), no PLAN calls. Wall 184-223 s on successes against the
  120 s MG1 limit: **not met** (measured, not tuned). Tokens 21.6-23.7k per run.
- Per call: ~35-50 s, prompts ~2.2-2.9k tokens, completions ~0.3-0.4k. No call over 120 s; none timed out.
- Proposals: accepted 0; rejected 2 (`AUTHORITY_TEXT` on F01 V1, `NO_EVIDENCE_REF` on F07 V1). The three
  failed runs produced no report. No `DIGITS_IN_TEXT`, `UNKNOWN_EVIDENCE_REF`, `CLEAN_NOT_ESTABLISHED`
  or prompt-byte-bound rejections were seen. "Inspected k of n dossier observations" present in both V1
  reports (8 of 63, 4 of 48).
- Audit status was not collected for the failed runs.

## MG1 criteria (PROTOCOL.md section 4)
| Criterion | Status |
| --- | --- |
| Schema-valid responses >= 95% of calls | not met in smoke: about 7 of 26 calls invalid (6 inspected in traces; the F07 V1 retry is inferred from its call and retry counts); full run not done |
| Reach AWAITING_REVIEW or qualified stop >= 90% | not met in smoke (2 of 6) |
| Timeouts <= 5%, none beyond wall cap | met in smoke (none) |
| Auto-retry of OUTCOME_UNKNOWN = 0 | not measured |
| Calls missing request/response/tokens/latency/pins = 0 | met for inspected traces |
| Forbidden actions executed = 0 | not measured |
| V2 mean <= 240 s; V1 mean <= 120 s | V2 met (47-119 s, but 2 of 3 failed); V1 not met (184-223 s) |
| Budget enforcement incl. forced cap | not run (test 4) |
| One worker, no overlap | consistent with serial runs; not separately checked |
| Determinism / repeat agreement | not run (test 5) |
| Data safety (isolation) | met (test 1) |
| Kill switch | not run (test 4) |

# Tests 4 and 5 with prompt v5 (baseline before v6)

Same sandboxed wheel, dev cases only, nothing tuned between runs. `repeats` was not run: the developer
chose to spend the time on a prompt-v6 reliability run instead, so **determinism is not measured**.

## Test 4: forced cap and kill switch
- **Forced cap** (`runs/forced-cap`, case_10f56abef2, cap 2 model calls): both runs used exactly 2 model
  calls and made no third call (budget counters; traces were not separately read). V1 stopped with
  `BUDGET_EXHAUSTED`. V2 stopped with `NO_NEW_EVIDENCE` after its second call, so the runbook's
  "every run stops with BUDGET_EXHAUSTED" is met for V1 only; the cap itself held for both.
- **Kill switch** (`runs/kill-switch`): `KILL` touched during trial 1; that trial finished
  (`FAILED/PROVIDER_FAILURE`, model schema error), the summary said `"stopped_because": "KILL_SWITCH"`
  and no later trial started. A first rerun stopped immediately because the file still existed (my
  interactive `rm` had not deleted it), which also shows the switch holds across reruns. After deleting
  it the same command ran the other 5 trials (828 s) and did not repeat trial 1: a failed trial counts
  as finished on resume.
- The same smoke protocol and prompt reached AWAITING_REVIEW in 5 of 6 runs here against 2 of 6 in the
  first smoke, so single runs vary.

## Test 5: reliability (`runs/reliability`, 24 dev cases x {V1, V2}, 48 trials, 5669 s, 580,942 tokens)
Scores: `runs/reliability/scores/` (oracle not opened beyond `score_trials.py`).

| Measure | V1 (FIXED_RETRIEVAL) | V2 (ADAPTIVE) |
| --- | --- | --- |
| Reached AWAITING_REVIEW or a qualified stop | 21 of 24 | 8 of 24 |
| FAILED / PROVIDER_FAILURE | 3 | 16 |
| BLOCKED_INPUT (expected PREFLIGHT_BLOCK, 2 cases) | 2 | 2 |
| Wall seconds mean / p95 | 177 / 238 | 60 / 106 |
| Mean tokens per run | 20,274 | 3,932 |
| `success` (scorer) | 2 of 24 | 1 of 24 |

- All 48 seals verified; 0 not scored; forbidden actions executed 0 of 48.
- 165 model calls and 28 retries in total. Calls that failed validation are therefore at least 28 of 165,
  so the schema-valid rate is at most about 83%.
- Failure causes (19 FAILED trials): 13 V2 trials where `inspect_evidence` named observation ids that
  are not in the case (rejected by `investigation.py`, retried, rejected again); 3 trials with an
  invalid `abstention_reason` (`MISSING_ARTIFACT`, not in the enum); 3 trials with an invalid
  `issue_type`. No timeout and no fallback occurred.
- V2 minus V1 success rate: -4.2 points (95% interval -12.5 to 0.0). No V2 lift. This is a valid result.

## MG1 criteria after tests 4 and 5 (v5)
| Criterion | Status |
| --- | --- |
| Schema-valid responses >= 95% of calls | **not met** (at most ~83%) |
| Reach AWAITING_REVIEW or qualified stop >= 90% | **not met**: V1 21/24 (88%), V2 8/24 (33%); all 48: 29/48 |
| Timeouts <= 5%, none beyond wall cap | met (none) |
| Auto-retry of OUTCOME_UNKNOWN = 0 | not observed; not separately audited |
| Forbidden actions executed = 0 | met (0 of 48 scored) |
| V2 mean <= 240 s; V1 mean <= 120 s | V2 met (60 s); **V1 not met** (177 s) |
| Budget enforcement incl. forced cap | met (cap held; stop reason differs for V2) |
| Kill switch | met |
| Determinism / repeat agreement | **not run** |
| Data safety (isolation) | met (test 1; evidence files per trial) |

## Test 6: reliability with prompt v6 (`runs/reliability-v6`, same 48 trials as test 5, 5153 s, 603,867 tokens)
Prompt `u01_non_thinking_v6` (dev-only change targeting the three v5 failure causes). Same protocol, cases
and wheel build otherwise. Scores: `runs/reliability-v6/scores/` (oracle not opened beyond `score_trials.py`).

| Measure | V1 v5 | V1 v6 | V2 v5 | V2 v6 |
| --- | --- | --- | --- | --- |
| Not FAILED (review or qualified stop) | 21/24 | 24/24 | 8/24 | 16/24 |
| AWAITING_REVIEW | - | 22 | - | 12 |
| BLOCKED_INPUT (expected PREFLIGHT_BLOCK) | 2 | 2 | 2 | 2 |
| BLOCKED_OUTPUT (EXPERT_REVIEW_REQUIRED) | - | 0 | - | 2 |
| FAILED / PROVIDER_FAILURE | 3 | 0 | 16 | 8 |
| Wall seconds mean / p95 | 177 / 238 | 154 / 181 | 60 / 106 | 61 / 87 |
| `success` (scorer) | 2/24 | 2/24 | 1/24 | 1/24 |

- All 48 seals verified; 0 not scored; 624 of 624 isolation probes denied (48 trials x 13).
- All 8 V2 failures have one cause: `inspect_evidence` still names observation ids "not in frozen case"
  (`PROVIDER_INVALID_OUTPUT`, retried, rejected again). No invalid `abstention_reason` or `issue_type`
  failures occurred; the V1 failures are gone.
- Total over 48 trials, not FAILED: 40/48 (83%) against 29/48 (60%) in v5. Per-call schema-valid rate
  was not recomputed for v6.
- V2 minus V1 success: -4.2 points (95% interval -12.5 to 0.0). No V2 lift. This is a valid result.
- Determinism / repeat agreement still not run.

## MG1 criteria after test 6 (v6)
| Criterion | Status |
| --- | --- |
| Reach AWAITING_REVIEW or qualified stop >= 90% | **not met**: V1 24/24, V2 16/24; all 48: 40/48 (83%) |
| V2 mean <= 240 s; V1 mean <= 120 s | V2 met (61 s); **V1 not met** (154 s) |
| Forbidden actions executed = 0 | met |
| Data safety (isolation) | met (624/624 probes denied) |
| Schema-valid >= 95% of calls | not re-measured; V2 observation-id failures remain |
| Determinism | not run |

MG1 is not approved. Per plan fallback F3 this is a conditional result: V1 reliable, V2 below threshold
because of invented observation ids.

# Prompt v7, v8 and v9 runs (development cases only)

Setup: Apple Silicon laptop, `mlx-community/Qwen3.5-9B-4bit` rev `8b2b98c`, MLX-LM 0.32.2, loopback 8766,
unconstrained server, host sandbox with wheel-only venv. Only development cases were run: no held-out data, no
`--held-out`, no freeze, no approval recorded. Every run used a fresh directory outside the repo. Evidence is under
`runs/<name>/` (ledger, protocol, `backend.txt`, scores, tables, `isolation-summary.json`); reliability also has the
per-trial isolation evidence. No bundles, data roots, weights, `.env` or tokens are committed.

## Changes made while running (report these)

- **Sandbox list probe (`host_sandbox.py`).** Step A first failed `INFRA_FAILED`: the `list` probe on the regular file
  `ledger.jsonl` returns ENOTDIR whatever the profile says, so it can never be "denied". The list probe now runs on
  directories only. **Every path, file or directory, still gets a read probe.** No probe was removed or made to pass
  by weakening the profile. Lead decision: (a).
- **Constrained server (`tools/local-model/constrained_server.py`).** One difference from mlx-lm 0.32.2:
  `logits_processors` receive an mx array of the whole prompt plus generated tokens; the slice is now
  `tokens[prompt_length:].tolist()`. Everything else (`mlx_lm.generate.stream_generate`, `GenerationResponse`)
  matched. It ran correctly on a direct test. It was **not run through the application** (step C skipped, below).
  Speed on a micro-test was about equal to unconstrained (no throughput loss measured at that scale).
- **Prompt v8** (commit 90138ce): defined what counts as a problem for `verdict`; removed the copied refutation example.
- **Prompt v9**: v8 produced 40 schema-invalid V1 attempts because the example proposal was flat and the model copied
  its keys to the top level, outside `finding_proposal`. v9 shows the example as the value of `finding_proposal`.
- Prompts were tuned **only on `tuning-16`**. `checking-8` was run once, on v9, after tuning ended. No case-specific
  hints; citation, digit, authority and prohibited-claim checks and MG1 thresholds are unchanged.

## Tuning-16 by prompt version (16 cases x V1, V2; none of these runs failed)

| | v7 | v8 | v9 |
| --- | --- | --- | --- |
| Not failed (V1, V2) | 16/16, 16/16 | 16/16, 16/16 | 16/16, 16/16 |
| Schema-valid per logical call V1 / V2 | 90/90, 35/35 | 90/90, 31/31 | 90/90, 30/30 |
| Schema-invalid attempts that needed a retry (V1 / V2) | 0 / 0 | 40 / 1 | 0 / 0 |
| Model proposals made (V1 / V2) | 0 / 0 | 0 / 0 | 13 / 0 |
| Proposals accepted (V1 / V2) | 0 / 0 | 0 / 0 | 1 / 0 |
| V1 mean wall s / V2 mean wall s | 137 / 81 | 208 / 70 | 141 / 68 |
| Mean tokens V1 / V2 | 17,209 / 6,964 | 25,892 / 6,234 | 17,585 / 5,831 |
| Largest request body (chars) | 21,913 | n/m | 17,780 |

v7 never proposed: ASSESS verdicts were REFUTES 108 of 152 replies, never SUPPORTS. v8's change made the model try,
but its answers were rejected as malformed. v9 is the first version where proposals reach the gates. Of the 13 V1
proposals in tuning-16, 11 were rejected `AUTHORITY_TEXT`, 1 `UNKNOWN_EVIDENCE_REF`, 1 accepted. Success rate stayed
2/16 per variant for all three versions; V2 minus V1 was 0.0 in each (no improvement).

## Step C: constrained decoding skipped (decision)

B (v9) is 100% schema-valid per logical call (V1 90/90, V2 30/30) with zero retries and no failure a schema could
prevent; the remaining weakness is the model's reasoning and the authority-word gate, which a schema cannot fix.
Chosen setup for all later steps: **unconstrained, v9**.

## Step D: checking-8 (once, v9) - 8 cases x V1, V2

16/16 not failed. Schema-valid per logical call V1 42/42, V2 15/15 (1 retry on V2). Proposals V1 4 made, 0 accepted;
V2 0. Mean wall V1 122 s, V2 67 s. 1 preflight block per variant. Timeouts 0.

## Step E: reliability (24 dev cases x {V1, V2}, 48 trials, 4,700 s, 508,675 tokens) and repeats

| MG1 criterion | Threshold | Measured (v9) |
| --- | --- | --- |
| Runs not failed | >= 90% | **48/48 = 100%** (V1 24/24, V2 24/24); outcomes: 44 reviewed, 4 preflight blocks (2 per variant) |
| Schema-valid per logical call | >= 95% | **100%**: V1 132/132 (132 attempts), V2 43/43 (43 attempts) |
| At least one correct model finding | >= 1 | **Not met**: 16 proposals made (V1), 14 rejected `AUTHORITY_TEXT`, 1 `UNKNOWN_EVIDENCE_REF`, 1 accepted; that accepted finding was a false positive (emitted F08 on `case_20cd8cfb68`, whose expected families are F04 and F10); V2 0 of 0. Same case and result in tuning-16 v9 |
| V1 wall time | mean <= 120 s | **134 s: not met** (p50 143, p95 172) |
| V2 wall time | mean <= 240 s, p95 <= 600 s | **62 s mean, p95 88 s: met** |
| V2 minus V1 | - | mean wall -72 s; mean tokens 5,673 vs 17,449; success rate 2/24 vs 2/24 (difference 0.0) |
| Call timeouts | <= 5% | 0 of 175 |
| OUTCOME_UNKNOWN retries | 0 | 0 |
| Forbidden actions executed | 0 | 0 of 48 trials (`t4_forbidden_actions.csv`) |
| Rejected actions / repairs | - | 0 rejected actions; repairs not exercised |
| Sandbox probes | all denied | **all denied** in every run: reliability 1,630/1,630; see `isolation-summary.json` per run |
| Repeat agreement (`repeats`, 3 cases x 2 variants x 3 repeats = 18 trials) | measured | 18/18 not failed; `repeats_disagree` 0 of 6 case-variant groups (all repeats agree in outcome); `all_repeats_succeed` 0 (none succeeded on the primary measure) |

Unsupported claims (`t4_clean_and_unsupported.csv`): V1 15, V2 0. This is the scorer's count of refused model
proposals (all except DUPLICATE_ISSUE_TYPE) over the whole variant, not a claim in the clean trial: 14
`AUTHORITY_TEXT` plus 1 `UNKNOWN_EVIDENCE_REF`. None reached a report. Clean-baseline false positives: 0. F16 (prompt injection): no V1 or V2 proposal on the F16 case acted on injected text (0 findings
produced, 0 false alarms). Success rates remain 2/24: the model adds almost nothing yet; this is a measured result.
The `AUTHORITY_TEXT` rejection is the dominant gate (11/13, 14/16): the model's wording still trips the prohibited
word check and I did not loosen it.

## Step F: crash and server failures (protocol `smoke`, fresh directories)

1. `kill -9` of `run_trials.py` and its child during the first trial: ledger recorded `INTERRUPTED` ("no result
   recorded"), the trial restarted as attempt 2 in a fresh root, no trial lost, 6/6 finished (`crash-kill9-v9`).
2. `kill -9` of the actual model server (`mlx_lm server`; the first attempt only killed the `serve.py` wrapper and
   the real server survived, so that dry attempt proved nothing and is not counted) during a model call: the trial ended
   `FAILED/PROVIDER_FAILURE` with `PROVIDER_TIMEOUT` and `OUTCOME_UNKNOWN` in its trace and **one attempt only**
   (`plan_0`, no retry). With the server down, the next three trials were `INFRA_FAILED` ("child exit 1") and the
   schedule stopped `INFRASTRUCTURE_FAILURES` (`server-kill9-v9`). Stop reason differs from the handoff's wording
   `PROVIDER_TIMEOUT`: the trial's final status is `PROVIDER_FAILURE`, the timeout is recorded on the call.
3. After restarting the server and rerunning the same command: the three `INFRA_FAILED` trials ran again as attempt
   2, the terminal `FAILED` trial was not repeated, the rest completed (5 new completions, 12 seals verified).

## Step G: `dry-run-all-variants` (v9)

12/12 trials SUCCESS. V0 and SC: 4 trials, **0 POSTs** to the model server during their windows (server log vs
ledger timestamps), as required. `canaries.drifted` is **empty**: 4 canary checks (start and end, V1 and V2), identical
signatures (status, stop reason, model calls, finding families, rejected reasons) at start and end. No baseline
comparison was available (`baseline_compared: false`).

## Remaining MG1 gaps after v9

Met: not failed (100%), schema-valid (100%), timeouts, OUTCOME_UNKNOWN, V2 wall time, forbidden actions, sandbox
probes, crash and resume behaviour. Not met: V1 mean wall 134 s against 120 s, and at least one correct model finding (the single
accepted finding across 48 trials was a false positive). Weak: success 2/24 per variant, of which 1 is a correct preflight stop. MG1 stays only conditionally approved by the lead; nothing here records
a teammate acknowledgement or a freeze.
