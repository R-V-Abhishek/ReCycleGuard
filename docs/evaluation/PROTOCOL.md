# Evaluation protocol (DRAFT v0.1)

Status: **DRAFT, not frozen.** Written 1 November 2026 under task V10a. It is frozen
only by the CP5 freeze record. Governing plan: `EXECUTION_PLAN.md`. Every statement
about measurements below is a rule or target, not a result.

## 1. Scope

All evaluation includes the real model: `mlx-community/Qwen3.5-9B-4bit`, revision
`8b2b98c00a6b4d291155e4890773ca8f769aee53`, MLX-LM 0.32.2, served on loopback.
Scripted-C10 runs are a **control only**. CP5 scope will be recorded as
`INCLUDES_REAL_MODEL`; MG1 is a required gate. Data stays on the machine.

## 2. Variants

| ID | Description |
| --- | --- |
| V0 | Deterministic pipeline, no model. |
| SC | Scripted C10 control (`REAL_SERVICES_SCRIPTED_C10`). Never reported as model performance. |
| V1 | Fixed retrieval + real model: predeclared check sequence; model assesses and drafts only. |
| V2 | Bounded adaptive real model through the graph (`REAL_SERVICES_LOCAL_MODEL`). |

Primary comparison: **V2 vs V1** on the same held-out cases, same tools, same corpus, same
budgets. V1 is not yet implemented (see `EXECUTION_PLAN.md`, V1-impl).

## 3. Metrics and denominators

Primary: supported case success = successful eligible case-trials / all scheduled
eligible case-trials. Failures, timeouts and invalid model output count as unsuccessful.
Secondary: exact reconciliation, finding precision/recall/F1 (undefined denominators are
reported **N/A, never 1.0**), clean-case false positives, appropriate abstention,
unsupported claims, next-action correctness, citation/temporal support (human rubric),
forbidden-action attempts and executions, efficiency (calls, tokens, latency, timeouts;
money = null, "local, not metered"), reliability across repeats.

Open item: `benchmarks/evaluation/scoring.py` also produces a weighted composite
(0.5 exact buckets + 0.3 finding component + 0.2 abstention accuracy). It is **not** the primary
metric unless the freeze record says so. Undefined finding precision/recall/F1 are now `None`
(N/A); the composite uses `composite_component` (1.0 only for a correct empty result).

## 4. MG1 criteria (dev cases only)

Setup gate, not a quality claim. Smoke first (3 dev cases, kill-switch test), then a
reliability run (24 dev x {V1, V2}, plus 3 cases x 3 repeats).

| Criterion | Pass threshold |
| --- | --- |
| Schema-valid model responses (after at most 1 retry) | >= 95% of calls |
| Runs reaching AWAITING_REVIEW or an explicit qualified stop | >= 90% |
| Call timeouts | <= 5% of calls; no run beyond `max_wall_seconds` |
| OUTCOME_UNKNOWN automatic retries | 0 |
| Calls missing request, response, tokens, latency or pins | 0 |
| Forbidden actions executed | 0 (attempts reported) |
| Wall time | V2 mean <= 240 s, p95 <= 600 s; V1 mean <= 120 s |
| Budget enforcement | Caps stop before excess dispatch, including one live forced-cap run |
| Concurrency | One worker; no overlapping requests |
| Determinism | Pins verified every run; repeat agreement measured and reported |
| Data safety | Loopback only; 0 evaluator/held-out keys in prompts; 0 secrets in logs; isolation probes all denied |
| Kill switch | Mid-run cancel stops the run cleanly with no orphan operation |

Advisory only: the same tool and verdict in more than 80% of dev runs is degenerate
behaviour and goes to A09 (dev-only tuning).

## 5. Trials (to be fixed at CP5)

24 held-out cases x {V1, V2} x R repeats, plus V0 and SC. R = 2 if the dev V2 mean is
<= 240 s, otherwise R = 1 plus a second repeat on a fixed 8-case family-stratified
subset. The rule is applied before any held-out run. V1/V2 order alternates per case.
Repeats are not independent samples; bootstraps resample cases with all their repeats.

## 6. Invalid trials and stop rules

A trial is invalid only for evaluator or infrastructure failure before investigator
launch, recorded with a reason; a replacement is run and both are kept. Model failures
are not invalid. Nightly stop: 7 h wall, 2 M tokens, 3 consecutive infrastructure
failures, or the kill-switch file. Unfinished rows become NOT_RUN and are counted.

## 7. Failure taxonomy

infrastructure, parser, tool, retrieval/applicability, model-schema, model-reasoning,
verifier, budget-stop, timeout, oracle.

## 8. Scoring independence

Automatic scoring runs in a separate process with the evaluator root. Human rubric
scoring (citation, temporal, next action) is blind to variant; at least 20% of trials
are double-scored; disputes are adjudicated by a third scorer. The builder, runner and
primary evaluator are the same person; this is disclosed in the report.
Reference status is `INDEPENDENT_REFERENCE_VALIDATED` (agent-reviewed), not
`HAND_REVIEWED`.
