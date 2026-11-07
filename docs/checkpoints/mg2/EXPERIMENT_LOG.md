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
