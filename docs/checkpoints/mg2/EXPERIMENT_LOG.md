# Experiment log

Append-only. One entry per step: hypothesis, the one thing changed, the data used, the result
copied from the tables, the decision, and what it motivated. Never edit an earlier entry; a
correction is a new entry that cites it. This is the source for the report's progression chapter.
Entries 1 to 8 are carried from MG1 (`docs/checkpoints/mg1/FAILURE_ANALYSIS.md`,
`MODEL_ROLE_CHECKLIST.md`) so the story reads in order; their numbers are copied, not re-derived.

Data used is one of: **tuning-16** (16 development dossiers, tuned on), **checking-8** (8
development dossiers, looked at once and disclosed), **ablated** (tuning-16 with the deterministic
families off), **held-out** (24 sealed dossiers, never opened).

## MG1: from prompt tuning to a measured model contribution

### 1. Tune one prompt (v5 to v12) on tuning-16
- **Hypothesis.** A better prompt raises success on a 9B model.
- **Changed.** The single-agent prompt text (v8 to v12, each an ablation of v7).
- **Data.** tuning-16.
- **Result.** v7 stayed best at about 54% (69 of 128 trials across three sessions). Other versions
  traded one failure for another. The model contributed 3 findings in 128 trials.
- **Decision.** Stop tuning prompts; find why the same cases fail every time.
- **Motivated.** Entry 2.

### 2. Failure analysis of v7
- **Hypothesis.** The failures are not model noise.
- **Changed.** Nothing; each failing case was traced.
- **Data.** tuning-16, v7 runs.
- **Result.** Seven cases failed in every run, each for a deterministic cause: a check that did
  not exist (F02, F03, F04, F07, F10, F16, F01) or a gate that let a bad claim through.
- **Decision.** Fix the engine and the gate, not the prompt.
- **Motivated.** Entry 3.

### 3. Deterministic checks and a contradiction gate (`tuning16-v7-det1`)
- **Changed.** Added family checks, the `CONTRADICTED_BY_CALCULATION` rule and graceful
  degradation on invalid model output.
- **Data.** tuning-16, v7, 32 trials.
- **Result.** 30 of 32 (93.8%), against 53.9% before. The model proposed one finding, rejected.
  The gain is the engine, not the model.
- **Decision.** Fix the one remaining failure (`e8b5`).

### 4. `e8b5` fix, then checking-8 (`tuning16-v7-det2`, `checking8-v7`)
- **Result.** tuning-16 32 of 32. checking-8 14 of 16; `e64d` (F15 and F16) failed in both
  variants because preflight blocked on page loss and the scorer accepts a block only for F15 alone.
- **Disclosure.** checking-8 was looked at here. Nothing was tuned on its results, but the next
  step was prompted by it.

### 5. Model-free controls on checking-8 (`checking8-v7-controls`)
- **Hypothesis.** The model adds nothing the engine does not.
- **Result.** 7 of 8 for each of V0, SC, FIXED and ADAPTIVE. Model share of findings: 0.
- **Decision.** The model must be given a role where it can be measured against SC.

### 6. Improvement 1: page loss reported as F15, investigation continues
- **Changed.** Page loss becomes a deterministic F15 finding and the run continues.
- **Data.** tuning-16 and checking-8.
- **Result.** 32 of 32 on both, all REVIEWED. Model proposed no finding in either run.
- **Disclosure.** The change was prompted by checking-8; it is generic and was first checked on
  tuning-16 `c42a`.

### 7. Improvement 2: rule ablation, v7 against a thinking prompt
- **Hypothesis.** With the rules off, the model recovers faults the rules usually find.
- **Changed.** An evaluation-only setting that switches every family off, and a thinking prompt.
- **Data.** ablated (tuning-16).
- **Result.** SC 0 of 21. v7 0 of 21. Thinking 1 of 21 (F06, from a shown issue code) with 3 false
  F06 claims. None of the seven judgement families (F01, F03, F07, F11, F12, F14, F16) was found
  by any model variant. With the rules on, thinking scored 26 of 32 against v7's 32 of 32, doubled
  wall time and added 5 accepted false positives.
- **Decision.** v7 stays the baseline; the thinking prompt is not adopted. The gate accepts a
  model F06 the sweep found no sign of; logged as a known defect.
- **Motivated.** The model never saw document text, and it did not propose a finding even when an
  issue code was in front of it. Entry 8 and MG2.

### 8. Improvement 3: reviewer brief (implemented, not measured)
- **Changed.** An opt-in BRIEFING step, one audited model call per finding, gated by code.
- **Data.** None yet. The PC runs and the blind rubric are not done.

## MG2: retrieval and classification

### 9. First multi-agent attempt: chunked Reader, then Analyst (built, never run on the model)
- **Hypothesis.** A quarantined reader that sees text, plus an analyst that sees only kinds,
  recovers judgement families.
- **Changed.** Added phases READ and ANALYZE, a quote verifier and a claim-support filter. Branch
  `codex/multi-agent-mg2`, commits 86db5b2, ed203d4, 989eab5.
- **Data.** None. Scripted ports and the loopback fixture only; this is plumbing, not quality.
- **Finding on review.** The Analyst only maps each verified kind to its family through a fixed
  table, so the second call adds almost nothing, and the Reader is a classifier against a rubric
  the team wrote. Neither agent was given the problem it solves.
- **Decision.** Rebuild as a Retriever (agentic RAG with grading and re-query) and a Classifier
  that may use compute tools. Pre-register first.
- **Motivated.** `PREREGISTRATION.md` and entry 10.

### 10. Pre-registration and the queue (this commit)
- **Changed.** Wrote `PREREGISTRATION.md`; merged the MG1 integration branch into this branch
  (page loss, ablation, thinking, briefs); built the unattended queue.
- **Data.** None.

### 11. The Retriever and Classifier built (scripted ports only)
- **Hypothesis.** A retrieval loop that grades and re-queries, feeding a classifier that may run
  compute tools, recovers judgement families the single-agent loop and the first Reader never did.
  Not yet tested: no real model has run on it.
- **Changed.** Replaced the chunked Reader and Analyst with `agents/retriever.py` (bounded loop,
  tools `list_passages`, `read_passages`, `search_rules`, grade-then-change rule, verbatim quote
  check) and `agents/classifier.py` (at most three compute calls, then proposals). Both prompts are
  generated from `agents/registry.py` and each role is given only the problem and the definitions it
  needs. Added the arms `RETRIEVER_LOOKUP`, `RETRIEVER_CLASSIFIER` and `CLASSIFIER_ONLY`, prompt
  versions v1 to v3, per-arm protocols, and the queues. The ablation now reaches the agents' facts.
- **Data.** None. Unit tests and the loopback fixture server check plumbing, audit and the gate.
- **Decision.** Run the baselines first (they need none of this code), then the agent queue.
- **Next.** Entry 12 will be the baseline result, written when it exists.

### 11a. Harness defect found before any run: one-variant protocols (no data affected)
- **Found by.** A new read-only `run_queue.py --check`, run in the built `trials` image while
  writing the PC runbook. It was not found by the unit tests.
- **Defect.** `build_schedule` (`benchmarks/evaluation/trials.py`) required exactly two distinct
  variants, the shape of the MG1 pair. All ten MG2 per-arm protocols name one variant, so every
  session would have exited at start, been retried three times by the queue and marked `FAILED`.
- **Changed.** `build_schedule` accepts one or two distinct variants. Nothing else reads `variants`.
  The arms, protocols, prompts, controls and selection rule are unchanged. Added `--check` to
  `run_queue.py`, which validates a queue file and prints each session's trials, and a unit test for
  each change.
- **Data.** None. The 224 baseline and 784 agent trials counted by `--check` have not run.
- **Not covered.** On a laptop Docker host with 2 CPUs the per-trial container (`--cpus 8`) is
  refused, so a one-variant trial could not be run to the end against the fixture model there. The
  PC needs 8 CPUs visible to Docker; the runbook checks this first.
- **Decision.** Proceed with the registered design. The runbook was rewritten to be self-contained
  after team feedback that it did not work as intended and needed every command in order.

### 11b. A T4 series on free notebooks while the PC is unavailable (no data yet)
- **Why.** The PC cannot be reached for at least two days. The Retriever+Classifier arm has to run
  at least once before the review. Only free compute on our own accounts is available (one account
  per platform; Colab's FAQ disallows several accounts used to get around its limits).
- **Changed.** `run_queue.py --host` runs the same queue without Docker. Trials use the existing
  `--isolation-disclosed` backend, health is the server's `/health`, a restart runs the start
  script, and final or held-out jobs are refused. `RECYCLEGUARD_WORK` moves `/work` for a laptop dry
  run. `start_model.py` takes the binary path from `LLAMA_SERVER`. `scripts/cloud/` adds the
  bootstrap, a persist copy (ledgers last, a torn last line dropped) and `score.py`.
  `export-results.sh` copies from a local folder. `deploy/cloud/mg2_t4.ipynb` and
  `CLOUD_RUNBOOK.md` are the procedure. The three queues in `queue/t4/` hold the 18 PC sessions
  unchanged, at 3 slots: `mg2-t4-core` (v7 ADAPTIVE and Retriever+Classifier v1 in both arenas),
  `mg2-t4-ablated-rest` and `mg2-t4-rules-on-rest`.
- **Checked on the laptop, fixture model only (not evidence).** A host-mode queue of two shortened
  sessions ran, was scored and was exported. The v7 and SC trials ran through. The
  Retriever+Classifier trials ended in `PROVIDER_FAILURE` after one call, because the fixture model
  only answers v7-shaped prompts. Persist save and restore were tested with a torn ledger line.
- **Not checked.** Extracting the pinned llama.cpp binary on a notebook VM, VRAM headroom at 3 slots
  on a T4, and throughput.
- **Data.** None.
- **Decision.** Run `mg2-t4-core` on Kaggle and `mg2-t4-rules-on-rest` on Colab at the same time,
  then `mg2-t4-ablated-rest`. Label every result *T4, cooperative isolation, s3*. Never pool these
  results with PC runs. Entry 12 will be the first result.

### 12. First result: `mg2-t4-core` (T4, cooperative isolation, s3)
- **Hypothesis.** As entry 11: the Retriever+Classifier (M2, prompt `mg2_agents_v1`) recovers
  families in the ablated arena without a regression with the rules on.
- **Run.** Kaggle, Tesla T4 (driver 580.178.04), revision `7685b0c`, the pinned image's own
  llama-server (build 12033), 3 slots, 11,525 of 15,360 MiB used after the probe. 224 of 224 trials
  within about 2 h 05 min of the bootstrap start (03:25 to 05:30 UTC on 2026-11-10), one attempt
  per session, no restart and no `INFRA_FAILED`. Scored on the laptop (the notebook held no
  evaluator data; its own tables had 0 scored). Exported to `runs/t4/`, machine records in `runs/t4/mg2-t4-core/machine-kaggle-1/`.
- **Data.** ablated and rules on (tuning-16), 2 repeats per arm, SC and V0 controls per session.
- **Result, ablated (primary).** No arm succeeded on any case. v7 ADAPTIVE 0 of 32, proposed
  nothing, 39 of 39 expected findings missed. SC 0 of 16 cases and 0 of 21 findings, as in entry 7. Retriever+Classifier 0 of
  32: it proposed 60 findings, the gate accepted 42, and 1 was right (F16, 1 of 2) and 41 were false
  (F05 18, F07 11, F14 6, F16 4, F04 1, F11 1). Gate rejections: 12 `NO_VERIFIED_CLAIM`,
  3 `UNKNOWN_EVIDENCE_REF`, 2 `INVALID_ABSTENTION`, 1 `DUPLICATE_ISSUE_TYPE`. Schema-valid rate
  0.962, 5.4 model calls and 117 s per trial on average.
- **Result, rules on (gate).** v7 ADAPTIVE 31 of 32 (one `model-schema` failure), SC and V0 16 of
  16, no false positive. Retriever+Classifier 10 of 32 (95% CI 0.16 to 0.47; against SC −0.69, CI
  −0.84 to −0.53): every expected finding but one was found, by the rules, and the model added 38
  accepted false positives (F05 20, F14 11, F16 4, F03 2, F13 1). Repeats disagreed on 8 of 16 cases.
- **Decision.** M2 v1 fails the gate (false positives, below 32 of 32) and is not selected. In the
  ablated arena it is the only arm that proposes anything, but almost all of it is wrong. The
  gate accepted 79 model claims (41 + 38) across both arenas that the oracle marks false, most of
  them F05 and F14; why it accepted them has not been analysed yet and is the next step.
- **Not shown.** These are T4 runs with cooperative isolation and are not pooled with PC runs. M1,
  M2-nr and prompt versions v2 and v3 are in `mg2-t4-ablated-rest` and `mg2-t4-rules-on-rest`,
  still running or not yet run.

### 13. Ablated remainder: `mg2-t4-ablated-rest` (T4, cooperative isolation, s3)
- **Hypothesis.** As entry 11, for the other ablated arms: v7 FIXED, M2 with prompts v2 and v3,
  the Classifier alone (M2-nr, v1 and v3) and the Retriever with the deterministic lookup (M1, v1 and v2).
- **Run.** Kaggle, Tesla T4 (driver 580.178.04), revision `f792dc1`, the same llama-server build
  12033 from the pinned image, 3 slots, 11,525 of 15,360 MiB used after the probe. Started fresh
  (nothing restored). 336 of 336 trials; the first ledger line is at 08:11 and the last at 11:07
  UTC on 2026-11-10. One trial, `case_cab84413b4|CLASSIFIER_ONLY|r1` (classifier-only v3), ended
  `FAILED` after two `INFRA_FAILED` attempts with `child exit 1`; the same case also failed once
  under M2 v3 and passed on retry. The child log holds only the `wrapt` sitecustomize warning, so
  the cause is not known. Scored on the laptop; exported to `runs/t4/`, machine records in
  `runs/t4/mg2-t4-ablated-rest/machine-kaggle-2/`.
- **Data.** ablated (tuning-16), 2 repeats per arm, SC controls per session.
- **Result.** SC 0 of 16 cases and 0 of 21 findings in all seven sessions, as in entries 7 and 12.

  | Arm | Cases | True / false positives | Proposed / accepted | Calls, s per trial |
  | --- | --- | --- | --- | --- |
  | v7 FIXED | 0 of 32 | 0 / 1 (F07) | 2 / 1 | 6.1, 117 |
  | M2 v2 | 0 of 32 | 6 / 47 (F05 23, F14 12, F07 11, F04 1) | 65 / 53 | 5.7, 177 |
  | M2 v3 | 0 of 32 | 2 / 42 (F05 17, F07 11, F14 8, F16 6) | 55 / 44 | 5.7, 165 |
  | M2-nr v1 (Classifier alone) | 2 of 32 | 2 / 0 (found F10 2) | 39 / 2 | 1.1, 60 |
  | M2-nr v3 (Classifier alone) | 2 of 32 | 3 / 0 (found F10 2, F06 1) | 37 / 3 | 1.8, 71 |
  | M1 v1 (Retriever + lookup) | 1 of 32 | 6 / 36 (F05 17, F07 8, F14 7, F16 2, F11 1, F13 1) | 42 / 42 | 4.7, 120 |
  | M1 v2 (Retriever + lookup) | 0 of 32 | 3 / 28 (F05 14, F07 7, F14 6, F13 1) | 31 / 31 | 4.2, 101 |

  Most rejections of M2-nr claims were `NO_VERIFIED_CLAIM` (34 of 37 for v1, 33 of 34 for v3). The
  M2 gate rejected 12 (v2) and 11 (v3). M1 proposals were all accepted.
- **Reading (inference, not yet analysed).** Every arm that uses the Retriever produces the same
  false-positive families as M2 v1 in entry 12 (F05, F07, F14), and v2 and v3 do not reduce them.
  The Classifier alone makes no false positive because the gate rejects almost all of its claims.
  By the selection rule (fewest false positives, then ablated recall), M2-nr leads the ablated arena,
  with 2 of 32 cases (95% CI 0 to 0.19) and 2 of 42 (v1) or 3 of 40 (v3, one trial failed) findings. Neither can be selected
  without its rules-on gate result, which is in `mg2-t4-rules-on-rest`.
- **Not shown.** `mg2-t4-rules-on-rest` (Colab) ran but its records are not available. No
  `recycleguard-work` folder exists in the account's Drive, so the 10-minute copies did not reach
  it or went to another account. Not yet explained.

### 14. Rules-on remainder: `mg2-t4-rules-on-rest` (T4, cooperative isolation, s3)
- **Hypothesis.** As entry 11: the gate for every arm of entry 13, with the rules on.
- **Run.** Rerun on Kaggle in place of the lost Colab run (entry 13; none of its records are used).
  Tesla T4 (driver 580.178.04), revision `19cca05`, llama-server build 12033 from the pinned
  image, 3 slots, 11,525 of 15,360 MiB used after the probe. Started fresh. 448 of 448 trials, all
  `SUCCESS` on the first attempt, with ledger lines from 13:15 to 16:21 UTC on 2026-11-10. The
  10-minute copy stopped at 14:26: rsync exited 24 because a running trial's SQLite `-wal`/`-shm`
  file vanished mid-copy, and `persist.sh` runs under `set -e`. The notebook's final save copied
  everything, so nothing was lost here. `persist.sh` now accepts exit 24. The same failure would
  have stopped the Colab copies to Drive (inference: the Colab log was not kept). Scored on the
  laptop; machine records in `runs/t4/mg2-t4-rules-on-rest/machine-kaggle-3/`.
- **Data.** rules on (tuning-16), 2 repeats per arm, SC and V0 controls per session.
- **Result.** SC and V0 16 of 16 with no false positive in all seven sessions.

  | Arm | Cases (95% CI) | True / false positives | Proposed / accepted |
  | --- | --- | --- | --- |
  | v7 FIXED | 32 of 32 | 42 / 0 | 1 / 0 |
  | M2 v2 | 15 of 32 (0.31 to 0.63) | 42 / 25 (F05 16, F14 7, F16 2) | 38 / 25 |
  | M2 v3 | 12 of 32 (0.19 to 0.59) | 40 / 35 (F05 20, F16 7, F14 6, F08 1, F13 1) | 46 / 35 |
  | M2-nr v1 | 30 of 32 (0.81 to 1.00) | 42 / 2 (F03 2) | 26 / 2 |
  | M2-nr v3 | 31 of 32 (0.91 to 1.00) | 42 / 1 (F08 1) | 18 / 1 |
  | M1 v1 | 9 of 32 (0.13 to 0.47) | 41 / 37 (F05 22, F14 8, F16 5, F13 2) | 45 / 37 |
  | M1 v2 | 13 of 32 (0.25 to 0.59) | 41 / 31 (F05 19, F14 8, F16 3, F13 1) | 44 / 31 |

- **Decision (T4 series, entries 12 to 14).** No multi-agent arm passes the rules-on gate (32 of 32
  and no false positive), so none is selected and nothing is frozen. Only v7 FIXED passes, and it
  recovers nothing in the ablated arena (entry 13); v7 ADAPTIVE failed the gate at 31 of 32 (entry 12).
  M2-nr is the nearest: 1 or 2 accepted false positives with the rules on, none in the ablated arena,
  but only 2 of 32 ablated cases. Every arm with the Retriever has 25 to 37 accepted false
  positives with the rules on, mostly F05 and F14, as in the ablated arena.
- **Next.** Find out from the bundles why the gate accepts the Retriever's F05 and F14 claims, and
  M2-nr's F03 and F08 ones, before any v4 prompt; v4 must be logged before it runs.

### 15. Stop prompt iteration; declare the held-out run before it happens
- **Decision.** No v4 prompt is written and no MG2 arm is selected or frozen as a winner. Three
  prompt versions across the three multi-agent arms (entries 12 to 14) all fail the rules-on gate,
  and every arm that uses the Retriever produces the same accepted false-positive families (F05,
  F14, with F07 ablated and F16 with the rules on) whatever the prompt. The team accepts that prompting
  Qwen3.5-9B Q8_0 further is unlikely to change this. The gate analysis named in entry 14 is not
  done; it is reported as future work. Decided by Abhishek, with Sushanth's agreement.
- **Held-out run, declared here before it runs** (PREREGISTRATION.md held-out policy, with the
  deviations dated 2026-11-11):
  - Queue `queue/t4/queue-t4-heldout.json` (`mg2-t4-heldout`, 3 slots), rules on, the 24 sealed
    held-out cases (`held_out_case_ids()`), 2 repeats, V0 and SC controls in each session:
    - `heldout-baseline` with v7 (`u01_non_thinking_v7`): V1 FIXED_RETRIEVAL and V2 ADAPTIVE.
      This is the primary comparison of `docs/evaluation/PROTOCOL.md` (V2 vs V1).
    - `heldout-classifier-only` with `mg2_agents_v3`: M2-nr v3, the Classifier alone. By the
      selection rule it ranks first among the agent arms (0 ablated and 1 rules-on false
      positive, 3 ablated true positives, against 0, 2 and 2 for v1), but it failed the gate (31 of
      32), so it is reported **descriptively**, not as a selected arm.
  - 240 trials: 144 and 96 (`run_queue.py --check`).
  - R = 2, decided by Abhishek with Sushanth's agreement (PROTOCOL.md had proposed 3).
  - Where: a Kaggle T4, cooperative isolation (`--isolation-disclosed`), as in entries 12 to 14.
    The 24 visible dossiers go up once as a **private** Kaggle dataset, with the two freeze
    manifests; `benchmarks/hidden` (the answers) stays on the laptop, where the run is scored.
  - Freeze: one manifest per protocol (`benchmarks/heldout/freeze/`, untracked), built with
    `scripts/make_freeze.py` from a clean pushed commit. It pins that commit, the protocol, prompt
    and queue files, and the visible dossiers as a tree digest; the notebook checks out that commit
    and verifies both freezes before the queue starts.
- **Correction to entry 13.** Entry 13 first named the arms wrongly: it called the Classifier alone
  "M1" and the Retriever with the deterministic lookup "Lookup (Retriever only)". Commit `2a9c4ec`
  renamed them to the PREREGISTRATION names (M2-nr and M1). No number changed.
- **Expected.** Nothing is tuned after the freeze. The result is reported whatever it is,
  including a drop of the deterministic engine on cases it was not built from.
