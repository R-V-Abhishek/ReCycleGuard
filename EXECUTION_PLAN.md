# ReCycleGuard execution plan: from CP4 to CP8 (real-model evaluation)

*(Once approved, saved to the repo root as `EXECUTION_PLAN.md`. This is a plan only: no code
change, experiment or model call has been made.)*

## Context

CP4 was approved on 1 Nov 2026 for candidate `b5a9831` on the pushed `checkpoint-4`
branch (`e3b59fc`). This checkout (`codex/s-ui-api-review`, `12db29f`) is behind it and
still shows CP4 as WAITING. `main` is still at the Review 2 docs.

**Decision already made:** every evaluation includes the real model. MG1 is a required
gate, and CP5 must be recorded as `INCLUDES_REAL_MODEL`. Scripted C10 runs are kept only
as a control.

**Fixed dates** (`PROJECT_GUIDELINES.md:20,116-117`):
- Review 4 is **Sat 7 Nov**.
- Final artifacts are due **Thu 12 Nov**.
- Today is Sun 1 Nov. There are **six nights** before Review 4.

### Decisions from your answers

Items marked **[A]** are assumptions taken from my best guesses, which you accepted.

| # | Decision |
| --- | --- |
| Model **[A]** | Only `mlx-community/Qwen3.5-9B-4bit`, revision `8b2b98c00a6b4d291155e4890773ca8f769aee53`, MLX-LM 0.32.2 / MLX 0.32.4, served locally on `127.0.0.1:8766`. No external provider and no API keys. |
| Money **[A]** | ₹0 in provider spend. Compute and energy are recorded as *not measured*, never as zero. |
| Hardware | One Apple Silicon Mac (Abhishek's) with one serial model worker. **Long runs happen overnight only**, because you are at work in the daytime. Evening work is setup, review and fixes. |
| Data safety **[A]** | Nothing leaves the machine. The model endpoint is loopback only. The R02/R08 sources stay `REVIEW_REQUIRED` for redistribution. |
| Sandbox **[A]** | MLX cannot run in the Linux Docker sandbox. Real-model runs instead get host-level restriction (macOS `sandbox-exec` profile, loopback-only network, no evaluator or held-out paths) plus probe evidence. If `sandbox-exec` proves unworkable, the fallback is cooperative isolation, disclosed as such. |
| Variants **[A]** | V0 deterministic; **V1** fixed retrieval + real model; **V2** bounded adaptive real model (the primary comparison is V2 vs V1); **SC** scripted-C10 control. V3 is dropped. |
| Trial count | Reduced from 144. **24 held-out × {V1, V2} × 2 repeats = 96 real-model runs**, plus 24 V0 and 24 SC runs. A pre-declared reduction rule applies (see CP5). |
| Scoring | Teammates do blind human double-scoring of at least 20% of trials while other work continues. Results go to a separate `results/cp6` branch. |
| Ownership | **Abhishek executes every remaining technical code** (A, H, S and V codes, and U01). **Sampreeth, Sushanth and Vedantha** do the report, slides and pitch, plus blind human scoring. The split between the three is an assumption **[A]**. The original code owners stay listed as reviewers where possible. |
| Acknowledgement | You report the all-four acknowledgement, with each member named, as at CP4. |
| UI | Include the uncommitted `Readiness.tsx` change and `docs/review_guides/` after fixing errors. Improve the UI for pitches as needed; this is not a gate blocker. |
| Base branch **[A]** | `checkpoint-5` is created from `checkpoint-4`. CP3's ledger is closed retroactively as a records-only step. |

**Independence caveat (disclose it in the report).** One person builds the system,
writes the evaluator and runs the trials. To limit that conflict:
- Human rubric labels come from teammates, blind to variant.
- Vedantha adjudicates disputes **[A]**.
- The scorer and oracle run in a separate process with a separate root.

---

## Phase 0 — Immediate consolidation (Sun 1 Nov evening; Mon 2 Nov evening)

| Code | Goal / tasks | Files | Evidence → how verified | Effort | Risks |
|---|---|---|---|---|---|
| **A08-close** (A) | Make the approved state the base. Create `checkpoint-5` from `checkpoint-4`. Tag `checkpoint-4-approved-2026-11-01` on `e3b59fc`. Open a PR from `checkpoint-4` to `main`. | Git only | Tag and PR URL → `git tag --contains b5a9831`; the PR is open with green CI | S | CI on the final CP4 candidate was never asserted, and it may fail on Windows |
| **V09-durable** (A) | Copy `/private/tmp/recycleguard-cp4-evaluator/` and `tmp/cp4-*` into a private, durable root outside the repo (`~/recycleguard-private/cp4/`). Write `SHA256SUMS` and record its digest in `docs/checkpoints/checkpoint-4/`. | Docs | `sha256sum -c` passes, and the digest is committed | S | Answer-bearing files must not enter Git |
| **REC-1** (A) | Fix the records:<br>• Close `docs/checkpoints/checkpoint-3/approvals.json` with lead acceptance (needs your explicit instruction).<br>• Reconcile `docs/checkpoints/model-gateway/README.md`: mark the v1–v3 failures as history and v4 as current.<br>• Commit a v4 summary JSON built from `tmp/s06_run_*` / `tmp/local-smoke-v4`.<br>• Update `docs/checkpoints/README.md`, `checkpoint-4/README.md`, `API_HANDOFF.md` and `S_contribution.md`. | `docs/checkpoints/**` | The register, ledgers and READMEs agree → `git grep -n "WAITING"` review | S | Rewriting history: append only, never edit old evidence |
| **UI-1** (A) | Fix and include `ui/src/screens/Readiness.tsx` and `docs/review_guides/`:<br>• Replace `file:///Users/...` links with repo-relative ones.<br>• Correct the "hand-reviewed oracle" claim.<br>• Add a pitch-friendly run view showing model calls, tokens and latency per turn, using existing API trace fields only (`api/trace.py`, `ui/src/state`). | `ui/src/**`, `docs/review_guides/*` | `npm run typecheck`, `npm test`, `npm run build` pass | M | The UI must not compute compliance numbers (`AGENTS.md`) |
| **ENV-1** (A) | Real-model environment check: run `uv sync --project tools/local-model --locked`. The weights manifest is verified by `serve.py`, and `recycleguard model probe` must pass. Record the macOS, chip and RAM versions. | `tools/local-model/`, `scripts/configure_local_model.py` | Probe output saved → `docs/checkpoints/mg1/environment.json` | S | Weights drift or missing cache |

Phase 0 can run in parallel: REC-1 and UI-1 are independent; A08-close comes first.

---

## Phase 1 — MG1: real-model readiness (Mon 2 → Tue 3 Nov evening)

MG1 needs U01, A07 (done), V07 extended to real-model runs, and V10.
**MG1 approves the setup only, not result quality.**

### Engineering steps (evenings of 1–2 Nov)

| Code | Goal / tasks | Files / modules | Evidence → verify | Effort | Risks |
|---|---|---|---|---|---|
| **V10a** (A; V reviews) | Protocol v0.1: variants, endpoints, metrics, denominators (N/A where undefined), repeats, invalid-trial policy, failure taxonomy, stop rules, MG1 criteria (below). | New `docs/evaluation/PROTOCOL.md` | Document committed → reviewed by Vedantha | M | Changing it after held-out runs start → version it instead |
| **U01-log** (A) | Make sure every call records: prompt pin, exact request and response blobs (already in `local_model.py`), prompt/completion tokens (from the server `usage` field, otherwise byte-bound estimate with the flag `ESTIMATED`), latency, model revision, weights-manifest digest, server-session digest (`server-session.json`), and money cost (`null`, with the reason "local; not metered"). | `src/recycleguard/local_model.py`, `contracts/workflow.py` (TurnManifest) | Unit test: each `ModelCallResult` has all fields → `pytest tests/unit/test_local_model.py` | S | Usage fields from MLX-LM may be missing → keep `null`, never invent |
| **U01-det** (A) | Determinism. `temperature=0.0` is already set. Add `seed` to the request body if MLX-LM 0.32.2 honours it; otherwise record "unseeded greedy". Set `--prompt-cache-size 0` (or record the setting) so cache state cannot change outputs. Pin `max_tokens`, `stop` and the server flags inside the config pin. | `tools/local-model/serve.py`, `local_model.py` | Config pin covers the server flags; a repeat-agreement measurement exists (smoke) | S | Metal nondeterminism → *measured* rather than assumed |
| **U01-rel** (A) | Reliability:<br>• Choose JSON-schema-constrained decoding (Outlines-MLX, isolated in `tools/local-model` only) **or** pin prompt v4 plus one validation retry. Decide from smoke results.<br>• Timeout of 120 s per call, with a retry count from `BudgetLimits.retries_per_operation` (1).<br>• A malformed output counts as one failed attempt and is retained. | `tools/local-model/`, `local_model.py`, `workflow/runner.py` | Malformed/timeout tests using the existing loopback-server test pattern (`tests/unit/test_local_model.py`) | M–L | Outlines adds a dependency; keep it out of the base package |
| **V1-impl** (A) | Implement the V1 fixed-retrieval variant. Deterministic plan: `search_rules` (fixed query set from H09) → `compute_reconciliation` → `trace_certificate` for flagged certificates → `inspect_evidence` for cited observations. The model does only ASSESS and drafting. It runs under the same `BudgetLimits` as V2. `experiment_variant="V1_FIXED_RETRIEVAL_REAL_MODEL"`; V2 = `"V2_ADAPTIVE_REAL_MODEL"`. | `workflow/runner.py`, `investigation.py:260-300`, `contracts/workflow.py` | Integration tests with the scripted port, plus a live smoke | M | The variant must not quietly use fewer evidence sources than V2 |
| **V07-rm** (A) | Isolation for real-model runs:<br>• Run the investigator from the **installed wheel** in a fresh root containing only the visible case.<br>• Wrap it in a `sandbox-exec` profile: deny reads outside the visible, runtime and venv paths; deny network except `127.0.0.1:8766`.<br>• Strip the environment.<br>• Reuse the probe and key-scan approach from `isolation.py` / `isolated_runtime.py` and the 45-probe set. | New `src/recycleguard/host_sandbox.py` (or a `scripts/` launcher), `isolation.py` | All probes denied; key scan finds 0 evaluator keys → `isolation-evidence-real.json` | M | `sandbox-exec` is deprecated → fallback is disclosed cooperative isolation |
| **C16-run** (A) | Trial coordinator, evaluator-only. It:<br>• reads a frozen protocol JSON;<br>• builds the counterbalanced schedule (case × variant × repeat, with V1/V2 order alternating per case);<br>• launches each trial with a fresh data root through the CLI;<br>• writes an append-only `ledger.jsonl` with one row per attempt;<br>• seals outputs by digest;<br>• resumes safely;<br>• checks a **kill switch** file before each trial;<br>• enforces night caps on wall time and tokens. | New `benchmarks/evaluation/trials.py`, `scripts/run_trials.py` | Dry run with the scripted port on 3 dev cases → ledger and seals verified | L | Most important new code: test resume after `kill -9` |
| **SCORE-fix** (A) | Scorer fixes:<br>• Undefined precision/recall become `None`/N/A (`benchmarks/evaluation/scoring.py:173-174`).<br>• Add a BucketResult → scorer projection.<br>• Add `scripts/score_trials.py`, run in a separate process with the oracle root.<br>• Add a paired case-level bootstrap (seeded stdlib, resampling cases with all their repeats) in `benchmarks/evaluation/analysis.py`. | `benchmarks/evaluation/*` | `tests/unit/test_v04_oracle.py`, plus new scorer and analysis tests | M | Scorer bugs become laundered results → hand-check 3 scored trials |

**Status (2 November 2026):** MG1 engineering is complete and has run on the real model. MG1 is **conditionally approved,
setup only** ([approval](docs/checkpoints/mg1/APPROVAL.md), [results](docs/checkpoints/mg1/MODEL_TEST_RESULTS.md)). Open: no model
finding has reached a report in any run, and determinism was not run. Next gate: CP5, not started.

**Authority:** Sushanth and Abhishek own every task and make every approval, whatever owner or reviewer this plan names.
No other acknowledgment is awaited at any gate.

### MG1 pass/fail criteria (all must pass; measured on **dev cases only**)

1. **Smoke first (night of 1–2 Nov, ~30 min).** 3 dev cases (F01 clean, F07 paid-no-transfer,
   F16 injection) × V2, and V1 once V1-impl lands, × 1. **Pass:** every run reaches a terminal or
   AWAITING_REVIEW state with a complete trace; there are no unhandled exceptions; the kill
   switch, triggered once mid-run, cancels cleanly (`investigation cancel`) with no orphan
   operation.
2. **Reliability run (night of 2–3 Nov).** 24 dev × {V1, V2} × 1 = 48 runs, plus 3 dev cases ×
   3 repeats for determinism.

   | Criterion | Pass threshold |
   |---|---|
   | Schema-valid model responses (after ≤1 retry) | ≥ 95% of calls |
   | Runs ending AWAITING_REVIEW or an explicit qualified stop (not FAILED) | ≥ 90% |
   | Call timeouts | ≤ 5% of calls; 0 hung runs beyond `max_wall_seconds` |
   | OUTCOME_UNKNOWN auto-retries | 0 |
   | Calls missing request, response, tokens, latency or pins | 0 |
   | Forbidden actions executed (approval, mutation, unsupported verdict) | 0 (attempts are reported) |
   | Per-run wall time | V2 mean ≤ 240 s, p95 ≤ 600 s; V1 mean ≤ 120 s |
   | Budget enforcement | Per-run caps stop the run before excess dispatch (existing test, plus one live forced-cap run) |
   | Rate limit / concurrency | One worker; no overlapping requests in the server log |
   | Determinism | Repeat agreement (action sequence and final dispositions) is **measured and reported**; every run's pins match. Pass = pins verified, not identical outputs. |
   | Data safety | Isolation evidence: all probes denied, 0 non-loopback connections, 0 evaluator/held-out keys found in prompts, 0 secrets in logs (scan for `RECYCLEGUARD_API_TOKEN`, password files) |

3. **Advisory, not a gate.** Degenerate behaviour, meaning the same tool and verdict in more than
   80% of dev runs, the same pattern seen in the U01 v4 table. If it occurs, prompt and plan
   tuning goes to A09 on dev only.
4. **Fail handling.** If the schema-valid rate is below 95% after U01-rel, switch the decoding
   strategy and repeat step 2 on night 3. If it still fails, see Fallbacks F3.

**MG1 exit checklist.** The reviewer needs `docs/checkpoints/mg1/`, containing:
- `environment.json`
- the weights manifest digest and runtime lock digest
- the server flags pin
- the smoke ledger
- the reliability ledger and its summary table against the criteria above
- the determinism measurement
- `isolation-evidence-real.json`
- the kill-switch test transcript
- the logging completeness check
- `approvals.json`, stating scope `REAL_MODEL_SETUP_ONLY` and the lead-reported acknowledgement, with the explicit note "no quality claim"

---

## Phase 2 — CP5: experiment freeze (Tue 3 → Wed 4 Nov evening)

A09, H09, S08 and V10 run in parallel on 3 Nov evening, using the night-2 dev results.

| Code | Goal / tasks | Files | Evidence → verify | Effort | Risks |
|---|---|---|---|---|---|
| **A09** (A) | Dev-only tuning: prompt v5 if needed (from the advisory metrics), graph stop criteria, one frozen `BudgetLimits` for both variants:<br>`max_model_calls=12`, `tokens_per_model_call=32768`, `max_total_tokens=393216`, `max_wall_seconds=600`, `tools_per_finding=8`, `reformulations=2`, `retries=1`, `report_repairs=1`.<br>Make evaluation mode **reject per-run budget overrides** (`api/app.py:115-118`, `:713-723`). | `local_model.py` (prompt), `contracts/workflow.py`, `api/app.py` | Regression tests; prompt pin digest | M | Tuning on held-out = invalid → only dev ledgers are read |
| **H09** (A; H reviews) | Freeze the corpus, index and retrieval policy: R02/R08 membership digest, index manifest, V1's fixed query set, applicability policy. The corpus is still 2 sources; disclose it. | `indexing/`, `knowledge/`, `configs/` | `audit_frozen_corpus_profile` returns `VERIFIED_INTEGRITY` | S | Small corpus limits RAG claims |
| **S08** (A; S reviews) | Fix dev tool and generator defects found in the night-2 runs. Freeze C08 version, profile, generator revision and `pilot-0.1`. Regenerate the held-out set into the evaluator root and check it against `benchmarks/pilot/heldout_seal.json`. | `domain/`, `benchmarks/generator/` | `generate --check` passes; seal matches | S–M | Any generator change means a new dataset version → avoid |
| **V10b** (A; V reviews) | Final protocol v1.0. Dev dry run of the full pipeline (coordinator → scorer → analysis) on 4 dev cases. Throughput measurement decides the repeat count (rule below). Human-scoring rubric `docs/evaluation/RUBRIC.md` and blind sheet generator (`benchmarks/evaluation/rubric.py`, which hides variant labels). | `docs/evaluation/*`, `benchmarks/evaluation/*` | Dry-run ledger, scores and tables regenerate end-to-end | M | Rubric ambiguity → adjudication rules written in advance |
| **V09-h** (S, H teammates; 30–60 min) | Human spot-check of all 24 held-out numeric references (no model involved), recorded with reviewer names. It is a separate attestation; the status stays `INDEPENDENT_REFERENCE_VALIDATED`. | Private evaluator root, plus aggregate seal in docs | Signed spot-check record digest | S | Exposes held-out answers to teammates → they do not tune anything |

**Proposal, 2 November 2026:** R = 3, because schedule no longer drives decisions. The value
and the freeze itself remain undecided; Sushanth and Abhishek decide them together. The rule below stands
until they do. Held-out runs now need `run_trials.py --held-out <freeze.json>`, and V0, SC, canaries and
trial bundles run through the same coordinator (`docs/evaluation/PROTOCOL.md`).

**Pre-declared repeat rule (decided at CP5 from the dev throughput, before any held-out run):**
- If the dev V2 mean is ≤ 240 s, use **R = 2** for all 24 held-out cases (96 runs).
- Otherwise use **R = 1** for all 24 (48 runs), plus a second repeat on a fixed 8-case
  family-stratified subset (16 runs), listed in the protocol.

### CP5 freeze manifest

Everything below is hashed into `docs/checkpoints/checkpoint-5/freeze.json`:
- **Code and dependencies:** commit SHA and tag `cp5-freeze`; `uv.lock`, `tools/local-model/uv.lock`, `ui/package-lock.json` digests; wheel SHA-256; Python version.
- **Model:** model ID, revision `8b2b98c…`, quantization, weights-manifest SHA-256, MLX-LM/MLX versions, server flags, `temperature=0.0`, seed or "unseeded", `max_output_tokens=1024`, `max_total_tokens=32768`, stop tokens, endpoint, **provider = "local MLX-LM on <machine id>"**, freeze date.
- **Prompt:** template ID and prompt pin digest (`LocalModelConfig.prompt_pin()`), and the response-schema digests.
- **Budgets:** `BudgetLimits` JSON digest; night caps (wall 7 h, 2 M tokens); kill-switch path.
- **Corpus/index/profile:** corpus snapshot, index manifest and profile digests; V1 query-set digest.
- **Tools:** C08 version (`c08-s04-0.x`), tool schema digest (`InvestigationService.tool_schemas()`).
- **Dataset:** `pilot-0.1` seal aggregate `90e2c5c3…`, split policy, held-out case list, V09 reference seal `b93c4173…`, spot-check record digest. Seeds and templates stay private, with only their digest recorded.
- **Scorer:** scorer, analysis and rubric versions and digests; bootstrap seed and resample count (10,000).
- **Protocol:** `PROTOCOL.md` v1.0 digest; schedule JSON (case, variant, repeat, order); invalid-trial policy; failure taxonomy; stop rules.
- **Scope:** `"evaluation_scope": "INCLUDES_REAL_MODEL"`, with `MG1` approval referenced.

**CP5 exit checklist:**
- MG1 APPROVED.
- `freeze.json` present, with every digest recomputable by `scripts/verify_freeze.py` (new, read-only).
- Dev dry-run tables regenerate.
- The evaluator root is separated from the investigator root (isolation evidence).
- The held-out regeneration matches the seal.
- The repeat-rule decision is recorded.
- No held-out outputs exist yet; this is checked through the ledger.
- `approvals.json` with scope and acknowledgement.

---

## Phase 3 — CP6: trials, scoring and results (night of 4–5 Nov → Fri 6 Nov evening)

| Code | Goal / tasks | Evidence → verify | Effort | Risks |
|---|---|---|---|---|
| **V11** (A) | V0 deterministic (24) and SC scripted control (24) on held-out, in the same coordinator. Runs in minutes. | Ledger rows sealed | S | — |
| **V12** (A) | Real-model trials, **night of 4–5 Nov**. Each night starts and ends with a **canary** dev case, and its outputs are compared to the night-2 baseline (drift check). Order: all repeat-1 pairs first, then repeat 2. Night of 5–6 Nov is reserved for unfinished schedule rows and pre-declared invalid-trial reruns only. | Ledger complete; every scheduled row ends SUCCESS, FAILED or NOT_RUN with a reason | L (unattended) | Overnight crash → resume-safe coordinator; kill switch |
| **S09** (A runs automatic scoring; S human-labels) | Automatic scoring of exact balances and findings with `scripts/score_trials.py`. Errors are classified using the failure taxonomy: infrastructure / parser / tool / retrieval-applicability / model-schema / model-reasoning / verifier / budget-stop / timeout / oracle. | `scores.jsonl` | M | — |
| **H10** (H, S, V humans; A prepares sheets) | Blind rubric scoring of citation support, temporal correctness and next-action quality on **100% of real-model trials, if feasible, or at least 40%** **[A]**. At least 20% of trials are double-scored, plus every critical or disputed item. Agreement is reported as raw % and Cohen's κ. | Signed sheets with digests | M (people) | People's daytime limits → runs in parallel |
| **V13** (A computes; V adjudicates) | Adjudication; per-case and per-family tables; paired case-level bootstrap 95% CI for V2−V1 and for each real-model variant − SC; all-repeats success; usage and latency p50/p95. | `results/cp6` branch: ledger, scores, adjudications, `tables/*.csv`, `scripts/make_tables.py` | M | Scored subset bias → denominators always shown |

**Handling non-determinism.**
- Repeats are not independent samples: report the per-trial mean and the "all-repeats success".
- Report within-case disagreement between repeats as its own metric.
- Bootstrap resamples cases, carrying all repeats of a case together.
- No significance claims are chosen after the fact; with n = 24 the results are a pilot.

**Final results tables:**
- **T1 primary:** supported-case success by variant (V0, SC, V1, V2), with counts, denominators and CIs.
- **T2:** exact reconciliation per bucket.
- **T3:** finding precision, recall and F1, micro/macro/per family (N/A where undefined).
- **T4:** clean-case false positives, appropriate abstention, unsupported claims, forbidden-action attempts.
- **T5:** citation, temporal and next-action rubric results with agreement.
- **T6:** efficiency (calls, tokens, latency, timeouts, money = null).
- **T7:** reliability across repeats.
- **T8:** failure taxonomy counts.

**CP6 exit checklist:**
- Every scheduled row is accounted for.
- The canary drift check passes, or drift is documented and the affected rows are versioned.
- Scores are recomputable from the ledger (`make_tables.py` gives byte-identical CSVs).
- Agreement and adjudication records exist.
- Failures are classified.
- No post-freeze code change touched the held-out runs (diff of `cp5-freeze`..trial commit = none).
- `approvals.json`.

---

## Phase 4 — CP7: final review freeze (Thu 5 → Sat 7 Nov morning)

| Code | Goal / tasks | Owner | Evidence | Effort |
|---|---|---|---|---|
| **S10** | Dataset and generator card: pilot design, families, split, synthetic limits, limited internal separation (`benchmarks/generator/README.md:148-150`), rights. | A drafts; S reviews | `docs/data/dataset_card.md` | S |
| **H11** | Source rights, attribution and limitations for R02/R08 (manifest plus acquisition instructions; no redistribution unless cleared). | A drafts; H reviews | `docs/data/source_data_card.md` updated | S |
| **A10** | 8–12-page report and slides built from the CP6 tables only. Report sections and slides are drafted from 5 Nov, with result cells left as `NOT YET MEASURED` until CP6. | **H, S, V** (assumed split: H methods and data, S results and figures, V architecture and limitations); A supplies numbers and figures | PDF drafts | L |
| **V14** | Reproducible package (details below). Clean-checkout reproduction on a fresh root. | A | `docs/release/REPRODUCE.md`, package digest | M |
| **A11** | Freeze the demo build (UI + API on a dev case with a live model, plus a **recorded fallback**: replay of a saved run), and hold a four-person rehearsal (evening of 6 Nov). | A runs it; all rehearse; pitch by H, S, V | Rehearsal record, demo recovery copy | M |

**Reproducing results without the Mac or the weights:**
1. **Saved outputs.** Every real-model trial's exact request and response blobs are in its
   COMPLETE_LOCAL bundle (`recycleguard audit export`). They are verified with
   `audit verify-package` and inspected with `replay-package`, with no DB or model needed.
2. **Recorded-response replay (new, small).** A `RECORDED_REPLAY` model port serves saved
   responses keyed by exact request digest and fails on any mismatch. Re-running the graph
   with it reproduces each trace and report deterministically, without a model. The files
   are `src/recycleguard/model_port.py` (protocol) and a new adapter beside
   `tests/support/model_port.py`; it is test-mode gated like the scripted port.
3. **Tables.** `make_tables.py` rebuilds every table from the ledger and scores.
4. **Fresh model run (optional).** On Apple Silicon, follow the documented download and serve
   steps with the pinned weights. A new run is a **new trial**, not a reproduction.
5. **Held-out data.** The held-out set is regenerated by
   `python -m benchmarks.generator.generate --check` against the seal. No keys are needed
   anywhere, because the model is local.

**CP7 exit checklist:**
- Report and slides PDFs whose numbers match the CP6 CSVs (spot-check 10 numbers).
- Dataset and source cards.
- `REPRODUCE.md` executed on a clean clone, with the transcript retained.
- Recorded-replay reproduces 3 sampled trials byte-identically.
- Demo build tag, a demo recovery copy, and the rehearsal record.
- `approvals.json`.

---

## Phase 5 — CP8: submission check (Sun 8 → Thu 12 Nov)

| Code | Goal / tasks | Owner | Evidence | Effort |
|---|---|---|---|---|
| **A12** | Fix Review 4 feedback (presentation and packaging only; no result replacement); final README run instructions; licence decision for code and synthetic data. | A (report fixes: H, S, V) | Final tag `submission-2026-11-12` | M |
| **H12** | Final rights and attribution audit against the actual archive contents; no restricted originals inside a public archive. | A; H reviews | Audit checklist | S |
| **S11** | Independent regeneration of the pilot and baseline from the tagged commit. | A; S reviews | Transcript | S |
| **V15** | Archive (`git archive` of the tag + results bundle + PDFs); `SHA256SUMS`; manifest of included and omitted items; a permissions statement (code licence, data licence, R02/R08 manifest-only, weights not included, with a pin). Verify on a fresh machine or directory. | A | `submission/MANIFEST.json`, `SHA256SUMS` | S |

**CP8 exit checklist:**
- Report PDF and slides PDF.
- Code archive and repo link with README and run instructions.
- `SHA256SUMS` verified twice.
- Rights, permissions and omission list.
- Secrets scan clean (no `.env`, tokens or passwords).
- No held-out answers, seeds or weights in the public archive.
- Final approvals.

---

## Dependencies, parallelism and critical path

```text
P0: A08-close → (REC-1 ∥ UI-1 ∥ ENV-1 ∥ V09-durable)
P1: V10a ∥ U01-log ∥ U01-det ∥ U01-rel ∥ V1-impl ∥ V07-rm ∥ C16-run ∥ SCORE-fix
    → smoke (night 1) → reliability run (night 2) → MG1
P2: (A09 ∥ H09 ∥ S08 ∥ V10b ∥ V09-h) → CP5 (needs MG1)
P3: V11 ∥ V12 (night 4; night 5 spare) → S09 ∥ H10 → V13 → CP6
P4: S10 ∥ H11 ∥ A10 drafts (from 5 Nov) → A10 final (after CP6) → V14 → A11 → CP7 (7 Nov morning)
P5: A12 ∥ H12 ∥ S11 → V15 → CP8 (≤ 12 Nov)
```

**Critical path:** C16-run + V1-impl + U01-rel → reliability night (2–3 Nov) → MG1 → A09
freeze → CP5 (4 Nov) → V12 night (4–5 Nov) → scoring and adjudication (5–6 Nov) → CP6
(6 Nov) → report and slide numbers → CP7 (7 Nov) → V15 → CP8.

**Slack:** one spare night (5–6 Nov). Any slip past 4 Nov at CP5 squeezes CP6 into the day of Review 4.

---

## Cost plan

All figures are estimates **[A]**. The measured basis is U01 v4: about 1,800 tokens per call and
about 20 s per call (2 calls / ~3,600 tokens / ~40 s per run).

| Item | V1 | V2 | Notes |
|---|---|---|---|
| Expected calls per run | 6 | 5 | V1 makes one ASSESS call per fixed check: 3 queries, reconciliation, certificate trace, inspection (fewer if a case has no certificates). Reports are drafted by deterministic code. |
| Expected tokens per run | ~13k | ~11k | ~2.2k per call |
| Expected wall time per run | ~150 s | ~125 s | ~25 s per call. V1 exceeds the MG1 V1 mean ≤ 120 s threshold on this estimate; keep the threshold and report the measured result. |
| Hard cap per run | 12 calls / 393,216 reserved tokens / 600 s | same | Identical budgets; `evaluation_budgets()` |
| Held-out runs (R = 2) | 48 | 48 | |
| Expected total | ~0.62 M tokens, ~2.0 h | ~0.53 M tokens, ~1.7 h | **~1.15 M tokens, ~3.7 h** |
| With 1.5× safety margin | | | **~1.7 M tokens, ~5.5 h** (fits the 2 M / 7 h stop rule, with little slack) |
| Theoretical worst case | | | ~37.7 M reserved tokens / 16 h (prevented by the stop rule) |
| Dev reliability night | 24 + 9 | 24 + 9 | ~0.35 M tokens, ~1.5 h |
| Money | ₹0 provider spend | | Energy and compute not metered: recorded as `null` |

**Stop rule (coordinator-enforced, at run boundaries):**
- Halt the night if cumulative wall time exceeds 7 h, tokens exceed 2 M, 3 consecutive
  infrastructure failures occur, or the kill-switch file exists.
- Resume the next night in schedule order.
- Unfinished rows at the CP6 deadline become `NOT_RUN` and are counted; they are never dropped.
- Nothing stops early because a result looks good.

---

## Fallbacks

| ID | Situation | Response |
|---|---|---|
| **F1** | Model or server down | The coordinator marks the row `INFRA_FAILED` and retries once after `serve.py` restarts and the manifest is re-verified. If down for the night, resume next night (spare night 5–6). Never substitute another model or the scripted port. |
| **F2** | Too costly in time | Apply the pre-declared reduction (R = 1 + 8-case subset) **only if it is decided before held-out runs**. After that, only the stop rule applies. |
| **F3** | Too unreliable at MG1 | (a) Constrained decoding; (b) prompt v5 on dev; (c) if MG1 still fails on 3 Nov, proceed with an **honest MG1 "conditional pass"**: setup controls pass but reliability falls below threshold, recorded explicitly, and report real-model failure rates as results (a negative result is valid, plan §15). (d) A second local model needs new weights, a new MG1 and your approval; not planned. |
| **F4** | Behaviour changes mid-evaluation | Weights and runtime are hash-verified at each start (`serve.py`, `LocalModelConfig`). If the canary drifts: stop, keep the rows, investigate (cache, flags, OS update), version the protocol, and rerun **all** affected comparable rows. Disable macOS auto-updates during evaluation nights **[A]**. |
| **F5** | Mac unavailable | Recorded runs remain; Review 4 demo uses recorded replay. |

---

## Risk register

| # | Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| 1 | Coordinator bugs corrupt a trial night | M | H | Dev dry run, resume test, append-only ledger | A |
| 2 | Real model below the MG1 reliability threshold | M | H | U01-rel, F3 | A |
| 3 | Degenerate model policy (same action for every case) | H | M | A09 dev tuning; report it if it persists | A |
| 4 | Schedule slip past 4 Nov | M | H | One spare night; reduction rule | A |
| 5 | Self-evaluation conflict (one person builds and evaluates) | H | M | Blind teammate labels, separate scorer process, disclosure | A, V |
| 6 | Held-out contamination (regenerable from code) | M | H | Held-out kept only in the evaluator root; access log; no tuning after CP5 | A |
| 7 | `sandbox-exec` unusable | M | M | Disclosed cooperative isolation + probes | A |
| 8 | Evidence lost from `/private/tmp` | M | H | Phase 0 durable copy | A |
| 9 | macOS update or thermal throttling changes behaviour or timing | L | M | Disable updates; canary check | A |
| 10 | Teammates' scoring is late | M | M | Separate `results/cp6` branch; 40% minimum coverage | H, S, V |
| 11 | Report numbers diverge from the tables | M | H | Generated CSVs; spot-check at CP7 | H, S, V |
| 12 | Rights: redistributing R02/R08 | L | M | Manifest-only release | A |
| 13 | Small corpus (2 sources) weakens V1/V2 contrast | H | M | Disclose; no broad RAG claims | A |
| 14 | Windows CI fails on new code | M | L | Keep real-model code out of the portable tests | A |

---

## Verification approach (for executing this plan)

- **Per step:** focused `uv run pytest` on the touched modules, then `ruff check`,
  `ruff format --check`, `export_schemas.py --check`, `export_openapi.py --check`.
- **UI:** `npm run typecheck && npm test && npm run build`.
- **Before each gate:** full `uv run pytest`, with CI on the PR.
- Real-model runs happen only at the explicitly planned smoke, reliability and trial nights,
  each on fresh data roots.
- Every gate's exit checklist is verified from committed files only.

## First 5 actions today (Sun 1 Nov evening)

1. Create `checkpoint-5` from `checkpoint-4` (`e3b59fc`); tag `checkpoint-4-approved-2026-11-01`; open the PR from `checkpoint-4` to `main`.
2. Copy `/private/tmp/recycleguard-cp4-evaluator/` and the `tmp/cp4-*` evidence to `~/recycleguard-private/cp4/` with `SHA256SUMS`; commit the digest.
3. REC-1: close the CP3 ledger (with your explicit instruction), reconcile the model-gateway README, commit the v4 summary, and update the checkpoint index.
4. Write `docs/evaluation/PROTOCOL.md` v0.1 with the MG1 criteria above (V10a), and start U01-log, U01-det and the C16 coordinator skeleton.
5. Overnight: MG1 smoke step 1. That is 3 dev cases with the existing V2 path, plus a kill-switch test, on fresh roots, with the server started via `tools/local-model/serve.py`.
