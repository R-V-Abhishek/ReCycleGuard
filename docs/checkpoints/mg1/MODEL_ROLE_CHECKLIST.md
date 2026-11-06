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
- [ ] Required tests pass (PC)
- [ ] PC runs done: `tuning16-v7-pl1`, `checking8-v7-pl1`
- [ ] Results recorded in `FAILURE_ANALYSIS.md`

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

- [ ] Plan approved
- [ ] Implemented
- [ ] Required tests pass (PC)
- [ ] PC runs done
- [ ] Results recorded

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

## 3. Reviewer brief: speed up the compliance review

- [ ] Plan approved
- [ ] Implemented
- [ ] Required tests pass (PC)
- [ ] PC runs done
- [ ] Results recorded

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
