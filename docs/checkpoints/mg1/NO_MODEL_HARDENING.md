# Hardening done without the model (2 November 2026)

Built and tested on Windows with a loopback fake. **No real-model result changed and none is claimed.**
`MODEL_TEST_RESULTS.md` still describes prompt v6. The next model run is in
[MODEL_TEST_HANDOFF.md](MODEL_TEST_HANDOFF.md). MG1 stays conditional; CP5 is not started and the freeze is
undecided.

## Evidence that drove the changes

Committed runs only; no new data was gathered.

- All 8 v6 V2 failures were invented observation ids. The tool retried with the same arguments, which could
  not help.
- Model findings accepted: 0 in 64 reports. The 20 retained v5 rejections were 12 `NO_EVIDENCE_REF`,
  3 `UNKNOWN_EVIDENCE_REF`, 2 `AUTHORITY_TEXT`, 2 `DIGITS_IN_TEXT`, 1 `CLEAN_NOT_ESTABLISHED`. v6 made no
  proposals at all, cause unconfirmed because its traces were not committed.
- Most prompt bytes were double-escaped evidence JSON, null locator fields and blob references.

## Changes

| Area | Change |
| --- | --- |
| Invented ids | `ToolBinding.reject_arguments` refuses them before dispatch. The refusal is retained as `graph.action_rejected`, and the model is asked once more with the reason (`plan_repair`). A second refusal fails the run. Nothing is auto-corrected, and the handler's own check remains. |
| Copyable ids | PLAN prompts list up to 20 `inspectable_observation_ids`, in V1's order. |
| Retry prompt | Names where a reply failed, by field and error type. It never echoes model text. |
| Prompt v7 | Rewritten finding rules: propose when a problem is shown, null when there is nothing to cite, which ids can be cited, words only, and a shape with placeholders that hints at no case. |
| F01 gate | Needs a reconciliation from this run with nothing pending and no other finding. A shortfall alone no longer blocks it, and the finding states it does not establish the target was met. |
| Prompt size | Fixture worst case, 24 dev cases: 29,731 to 23,874 of 31,744 bytes, with longer rules. Evidence is sent as JSON, null locator fields and blob references are dropped, and V1's ASSESS omits its fixed plan. Retrieval evidence keeps its 6,000-character disclosed cut. |
| Constrained decoding | Optional and off by default: `tools/local-model/constrained_server.py` with a tested matcher. The flag is in the pin. **Its server has never run.** |
| Runner | No `PYTHONPATH` needed. `BLOCKED_OUTPUT` is ledger `BLOCKED`, not `SUCCESS`. |
| Sandbox | Configuration and runtime lock are granted as single files instead of their directories. Each evaluator tree, plus the session's ledger, results and bundles, gets its own probe. A grant overlapping an evaluator path is refused. |
| Controls | V0 and SC run through the coordinator. Only they get test adapters, and they get no model configuration. |
| Held-out mode | `--held-out <freeze.json>` needs a verified freeze at the exact commit, real-model scope, the exact protocol digest and the visible root. Tested with stubs only. **No held-out case was opened or run.** |
| Scoring and tables | All four variants, V2−V1, each real variant − SC, T1 intervals, T2, T3 micro, macro and per family, T4, T5 when scored, T6 call metrics, T8 classes per PROTOCOL section 7. |
| Evaluation support | Committed 16/8 dev split, canaries, and sealed trial bundles that `recorded_port` can load. |
| UI | The run screen explains failed, blocked and budget-stopped runs, and shows elapsed time and a note on long runs. |

## Verification on Windows

Focused tests only, by agreement; the full suite was not run.

- `tests/unit`: `test_finding_gate`, `test_local_model`, `test_constrained_json`, `test_trial_tooling`,
  `test_tables`, `test_host_sandbox`.
- `tests/integration`: `test_failure_paths` (server death mid-call, malformed reply, full disk during a call and
  on the ledger, repeated infrastructure failures), `test_invariants` (hostile text, secrets on disk and in prompts,
  no binary floats), `test_v1_fixed_plan`, `test_a06_control_records`, `test_model_investigation`, `test_run_trials`.
- UI: `tsc --noEmit`, `lifecycle.test.tsx`.
- Fixture dry run of V0, SC, V1 and V2 with canaries through runner, scorer, tables and bundle replay:
  12 of 12 trials, audit chains verified, no canary drift. Backend `FIXTURE_NOT_EVIDENCE`.

## Open decisions

- **`AUTHORITY_TEXT` rejected the word "certificate". Decided 3 November 2026.** The pattern `certif\w+` also matched the
  domain's own noun: 2 of the 20 v5 rejections, and all 3 proposals on the PC's `tuning-16` v7 run. Sushanth and Abhishek
  agreed to narrow it to the verb forms and "certification" (`certify`, `certifies`, `certified`, `certifying`,
  `certification(s)`). Claims of certification are still rejected; "certificate" is not.
- **Model findings cannot cite rule passages.** A search result gives no evidence reference to cite. Allowing the
  grader's selected passages would be a behaviour change, so it was not made.
- **R and the freeze** are undecided (`docs/evaluation/PROTOCOL.md` section 5).
- **The 120 s call timeout** in the plan differs from the 180 s configured. Unchanged; reported in the handoff.

## Prompt sweeps (3 November 2026)

Prompt versions are now data in `docs/checkpoints/mg1/prompts/`, carried to the investigator inside the pinned
configuration. v7 stays the built-in text, so its pins are unchanged. `scripts/run_sweep.py` runs several versions at
once against one llama-server started with `SLOTS=N`; each trial container carries its session's label, so parallel
coordinators never remove each other's containers.

- **Limit to disclose:** batched decoding with several slots can change greedy outputs slightly against one slot. A
  sweep therefore always includes v7, and versions are compared only inside one sweep. The chosen version gets one
  confirming `tuning-16` run at one slot before `checking-8`.
- A sweep refuses any protocol holding a `checking-8` case, and refuses to resume if a prompt file or configuration
  changed since it started.
- First versions: v8a (do not stop while an allowed check has not run), v8b (propose a finding, abstaining if support
  is incomplete, whenever cited ids exist), v8c (both). Generic rules only; no gate was changed.
- Checked on Windows: compile, `ruff check`, `ruff format --check`, schema export, and a load of every prompt file and
  of variant configurations. **Tests were not run here, by agreement**; they run on the PC.

## Deterministic findings and the decision trace (4 November 2026)

Branch `cp-5_findings_fix`. `cp-5_windows_model` stays as it was for the report, holding the `sweep-v8` results.

**Evidence.** In `sweep-v8` on `tuning-16`, no prompt version beat v7. Every variant reached 2/16 or less, and
v8c's 10 accepted V1 findings were all false positives. The misses were then split by whether the
reconciliation had computed a signal for the missed family:

- 55 of 138 missed families had a signal in the report. The calculation had established the fact, and the run
  turned it into a finding only if the model proposed it.
- 83 of 138 had no computed signal. These are judgement families, or signals not computed.
- 19 trials failed only because of duplicate F14 findings. Each unsupported-offset claim became its own finding
  (case `189b1c`, F1 0.9, `duplicate_count` above 0).

Only F11, F12 and F14 were emitted without the model.

**Changes.**

- **Duplicates.** Claim checks of one kind now produce one finding citing every matching claim, not one finding
  per claim.
- **Findings from computed checks.** New `reporting/calculation_findings.py` turns structured reconciliation checks
  into findings, at most one per family, with source `DETERMINISTIC_CALCULATION`. It reads the stored derivation's
  checks, not issue codes alone, because one code can mean several things: `DIMENSION_MISMATCH` also marks a wrong
  metal.

  | Family | Emitted when | Status |
  | --- | --- | --- |
  | F04 | a BLOCKING `DIMENSION_MISMATCH` issue | discrepancy |
  | F05 | entity eligibility FAIL | discrepancy |
  | F06 | a `STALE_SNAPSHOT` issue | withheld: `TEMPORAL_UNCERTAINTY`, `stale_portal_statement` |
  | F08 | an earlier-liability priority check FAIL or UNKNOWN | discrepancy; withheld (`INCOMPLETE_HISTORY`) if any check is UNKNOWN |
  | F09 | a lifecycle allocation check FAIL | discrepancy |
  | F10 | a capability check FAIL, or registration eligibility FAIL | discrepancy |

  UNKNOWN entity, lifecycle and capability states give no finding. The existing gate still applies: a
  deterministic finding takes its family, and a model proposal for that family is rejected as a duplicate.
- **Decision trace.** Each result now holds `decisions`, one row per model call. A row records what was shown
  (tool, citable id counts, whether the evidence was cut at 6000 characters, the issue codes still visible) and the
  reply (verdict, proposal summary, stop reason, `finish_reason`, tokens), with no evidence text.
  `runtime/model-calls.jsonl` keeps the exact request and response bodies in the volume. It is not sealed and not
  exported.
- **Funnel.** `scripts/funnel.py` assigns each miss to a stage, from `S5_REJECTED` down to `S0_JUDGEMENT_ONLY`, and
  labels each false positive with its source. Its signal table is evaluator-side only. Run on `sweep-v8` v8b
  (before the trace existed), each variant shows FALSE_POSITIVE 2, S0 3, S1 6 and S3_COMPUTED_NO_TRACE 6.
- **Reasoning replay.** `scripts/replay_reasoning.py` resends recorded prompts with thinking open. Its output is
  labelled `DIAGNOSTIC_NOT_EVIDENCE`; it is never scored and never changes a run.

**To disclose.**

- The detectors raise V0, V1 and V2 alike, since none of them uses the model. After this change, V2 minus V1
  measures the model on the judgement families only.
- The detectors were checked against `tuning-16` only. `checking-8` stays the honest check of whether they
  generalise.
- No citation, digit, authority or prohibited-claim check was changed. No prompt was changed.

**Waiting for funnel evidence.** These changes are decided only after a traced run shows where misses are lost:
evidence truncation, the observation window, stopping early, and the 1024-token output cap.

Checked on Windows: compile, `ruff check`, `ruff format --check`, `sh -n` on the export script, schema export check,
and imports. **Tests were not run here, by agreement.**
