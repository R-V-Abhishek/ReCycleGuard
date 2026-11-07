# Model role checklist: four improvements, in order

The deterministic engine now decides every scored finding. On checking-8, the model-free controls
(V0, SC) scored the same as the model on every case. These four improvements give the agent roles
where it can add value, and measure that value. This file keeps the work from drifting.

## Rules

- **Order.** Strictly 1 → 4. An improvement starts only when the one before it has all its boxes ticked.
- **One plan each.** Every improvement gets its own plan, approved before any code is written.
- **Required tests only.**
  - On the laptop: static checks, plus the focused tests named in that improvement's plan.
  - On the PC: the runs that plan names, in Docker.
- **v7 stays frozen** as the baseline prompt. A new prompt is a new version file; v7 never changes.
- **checking-8 discipline.** It has been looked at once. Any change it prompted is disclosed in
  `FAILURE_ANALYSIS.md`, and nothing is tuned on its results.
- **No benchmark knowledge in runtime.** Runtime code never imports or reads `benchmarks/`, a
  recipe or a case ID.
- **Honest reporting.** Every result shows deterministic-only success (SC) next to model success.
  A gain that SC also gets is not a model gain.

## 1. Page loss: keep investigating instead of blocking

- [x] Plan approved
- [x] Implemented. The offline sweep gives `c42a` F15 alone; the other 15 tuning cases are unchanged.
- [ ] Required tests pass (PC). No test log was committed with the runs; record the pytest output here.
- [x] PC runs done: `tuning16-v7-pl1` 32/32 and `checking8-v7-pl1` 32/32 (V0, SC, FIXED, ADAPTIVE).
- [x] Results recorded in `FAILURE_ANALYSIS.md`.

**Goal.** A dossier with a lost or missing page is reported as F15 and still investigated, so every
other fault in it is found.

**Why.**
- Preflight blocks the whole run on any page loss. The scorer accepts a block only when F15 is the
  only family (`benchmarks/evaluation/scoring.py:343`), so every combined case fails:
  - checking-8 `e64d` (F15+F16);
  - the held-out F15+F11 case.
- The block also stops the model from ever running on these dossiers.

**Scope.**
- A deterministic F15 finding from PDF page coverage issues:
  - status `REQUIRES_EXPERT_REVIEW`;
  - abstention `MISSING_EVIDENCE`;
  - scope `lost_document_page`;
  - an `ARTIFACT` reference to the affected document.
- Preflight returns QUALIFIED for page loss, not BLOCKED.

**Non-goals.** Prompt changes. Guessing what a lost page held. CSV row coverage.

**Acceptance.**
- `c42a` (F15 alone) passes as a reviewed report.
- `e64d` passes, disclosed as a change prompted by checking-8.
- Nothing else changes on tuning-16.

**Measurement.**
- tuning-16 and checking-8 success.
- SC still matches the model here: this improvement is deterministic. It makes the next three
  possible on these dossiers.

## 2. Rule ablation: what the model finds when a rule is off (v7 vs a thinking prompt)

- [x] Plan approved
- [x] Implemented.
  - The offline probe of tuning-16 with every family off leaves no deterministic finding and no contradiction on any case.
  - Five settled cases would otherwise have received a false deterministic F01.
  - Non-thinking pins and the v7 prompt digest are unchanged.
- [ ] Required tests pass (PC). No test log was committed with the runs.
- [x] PC runs done: `tuning16-v7-abl1`, `tuning16-think-abl1`, `tuning16-think-pl1`.
- [x] Results recorded in `FAILURE_ANALYSIS.md`.
  - With the rules off, the model found 1 of 21 families (thinking: F06 only, plus 3 false F06). v7 found 0 of 21; SC found 0.
  - With the rules on, thinking scored 26/32 against v7's 32/32. v7 stays the baseline.

**Goal.** Measure, per fault family, how often the model finds the fault when that family's
deterministic check is switched off.

**Why.** It is the honest test of "cases no rule covers", using existing dossiers and the existing
scorer.

**Scope.**
- An evaluation-only `ablated_families` setting, pinned in the run spec. It disables those
  families' computed findings and their contradiction rule.
- Ablation protocols on tuning-16 only, with SC as the zero baseline.
- A new thinking prompt version with a larger output budget, run next to v7.

**Non-goals.** Changing default runs. Tuning a prompt on checking-8.

**Acceptance.**
- A per-family recovery table for v7, the thinking prompt and SC.
- Default (unablated) runs are unchanged.

**Measurement.** The recovery rate per family, model minus SC, with intervals.

**Decisions (plan approved).**
- **One condition:** all families are switched off at once, in one protocol (`tuning-16-ablated.json`) that serves both prompts.
- **No deterministic clean finding** under ablation; the gate's safety checks all stay.
- **Tool outputs are unchanged.** Results are reported in two groups:
  - *signal* families, where a tool shows a matching issue code;
  - *judgement* families (F01, F03, F07, F11, F12, F14, F16), where none exists.
- **Thinking makes two requests within one model call:** think up to 1024 tokens, then answer up to 1024. The server and v7 pins are unchanged.
- **The thinking prompt** is v7 with one sentence changed.
- **Intervals:** per-family n is 1–2, so there are no per-family intervals. Aggregate success uses the existing paired bootstrap against SC.

## 3. Reviewer brief: speed up the compliance review

- [x] Plan approved
- [x] Implemented.
  - A `BRIEFING` run step after verification and before review, turned on per model config (`--brief`). Plain v7 configurations and their pins and prompt digest are unchanged.
  - Each brief is a separate `ReviewerBrief` record, bound to the report and finding revisions. The report, its verification and the review packet are untouched.
  - The UI shows each brief under its finding, with the advisory or template label. Rejected and dropped briefs show their reason, followed by the template.
  - Blind brief sheets: `make_rubric_sheets.py --briefs 1`.
- [ ] Required tests pass (PC). This includes the Improvement 1–2 tests that have no log yet.
- [ ] PC runs done
- [ ] Results recorded

**Deviation from the plan (disclosed).** Brief calls are not limited by the investigation's model-call, action and token caps, so a run that used its whole investigation budget still gets briefs. They are still counted in the run's model calls and reserved tokens, so the run budget's `model_calls` now includes them. Their own bound is 16 findings, each with one call plus its retries; beyond 16 a brief is dropped as `BRIEF_LIMIT`. The wall clock still applies.

**Goal.** For each finding, a model-drafted brief that shortens the review: what to check, the
cited evidence, and a draft evidence request. Numbers are filled in by code, never written by the
model.

**Scope.**
- A BRIEF model phase after the draft stage.
- The brief text passes the gate's text checks and cites only the finding's own references.
- The report marks it "advisory, model-drafted".
- SC gets a deterministic template brief.

**Non-goals.** The brief never changes a finding, a status, a number or a reviewer decision.

**Acceptance.**
- Every brief passes the gate, or is dropped and the drop is recorded.
- The report verifier still passes.

**Measurement.**
- The blind human rubric (`docs/evaluation/RUBRIC.md`: citation support, next-action quality),
  model brief against template brief.
- A timed review of a few cases by the scorers.

## 4. Documents-only dossiers (later phase)

- [ ] Plan approved
- [ ] Implemented
- [ ] Required tests pass (PC)
- [ ] PC runs done
- [ ] Results recorded

**Goal.** With no typed records, the model proposes record facts and links from PDF/CSV text,
quoted exactly. Deterministic checks verify them, a reviewer confirms them, and the reconciliation
then matches the typed-record result.

**Why.**
- Real dossiers have no typed JSON.
- `normalization/service.py` hard-codes `linked_credit_refs=[]` on the extracted path, so real
  invoices never link.

**Needs.** New documents-only dev cases. Its plan is written when this step is reached.

**Measurement.**
- Bucket-number and family agreement with the typed-record runs.
- Proposal acceptance and rejection rates.
