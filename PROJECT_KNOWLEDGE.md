# ReCycleGuard — project knowledge and checkpoint gap analysis

Prepared 1–2 November 2026 by a read-only review of the repository. Nothing was
modified except this file. No tests, scripts, experiments or model calls were run;
every statement below comes from reading files and Git history. Where the repo
is silent or contradicts itself, this document says so.

> **Read this first: there are two relevant code states.**
>
> - This checkout is on `codex/s-ui-api-review` at `12db29f` (plus one uncommitted
>   change to `ui/src/screens/Readiness.tsx` and the untracked `docs/review_guides/`).
>   Its plan register still shows **CP4 WAITING**, V06–V09 not integrated.
> - The pushed branch **`checkpoint-4`** (`e3b59fc`, also checked out as a separate
>   worktree at `/private/tmp/recycleguard-cp4`) adds V06–V09, A08, isolation and
>   CP4 approval records. HEAD is an ancestor of it (`git log HEAD..checkpoint-4`
>   shows 7 commits, 51 files, ~5.7k lines). **CP4 was approved there on 1 Nov for
>   candidate `b5a9831`** (`docs/checkpoints/checkpoint-4/APPROVAL.md` on that branch).
>
> All CP5+ work must start from `checkpoint-4`, not from this checkout. Files that
> exist only on `checkpoint-4` are marked **[cp4]** below and were read with
> `git show checkpoint-4:<path>`.

---

## 1. Project summary

### 1.1 The problem, as the repo defines it

ReCycleGuard supports a **compliance officer investigating discrepancies in an
e-waste Extended Producer Responsibility (EPR) case** under India's E-Waste
(Management) Rules 2022 and CPCB guidance (`README.md:3-5`,
`docs/research/DOMAIN_RESEARCH.md`, `docs/design/SYSTEM_DESIGN.md` §1).

In this repo's model, a producer has **metal-wise recycling obligations** (Au, Cu, Al,
Fe buckets, in kg) for a reporting period, including separate historical
liabilities. Recyclers generate **EPR certificates** (credit lots). Lots move through
lifecycle events (generated, transferred, allocated, cancelled, expired) and are
**allocated** to the producer's obligation buckets. Supporting evidence arrives as a
messy dossier: portal-like statements, ledgers, invoices, payments, memos and notes.

"Reconciliation" means computing, per compatible bucket, **required vs. supported vs.
gap**, keeping **pending** quantities separate, and comparing against portal balances
or return drafts. Core rules the repo insists on (`implementation plan.md` §2.2, §7.4;
`AGENTS.md` invariants):

- Supported achievement comes **only from eligible, supported allocations**. A
  payment, invoice, transfer observation, portal balance or certificate alone never
  creates supported credit (F07); duplicated observations count once (F02).
- Shared lots are conserved; earlier liabilities have priority at allocation time (F08).
- Missing, unknown, not-applicable and zero are distinct. Exact decimals only.
- Unsupported regimes (sales-derived targets, refurbishing deferrals, gold offsets,
  EC/penalty amounts, live CPCB actions, credit trading) are explicitly withheld.

The canonical worked example is **100 kg required, 55 kg supported, 45 kg gap, 25 kg
pending** (`README.md:19-21`, CP2 record).

### 1.2 What the system is meant to achieve

A **local, human-reviewed** application that produces an **advisory, qualified working
paper** — never a legal certification, filing, credit trade or fraud verdict
(`AGENTS.md` "Architecture"). The research question (plan §13.1) is whether a
**bounded adaptive agent (V2)** resolves evidence-supported discrepancies better than a
**fixed retrieval + model path (V1)**, both over the same deterministic tools, with a
**deterministic pipeline (V0)** as the baseline. Course context: Agentic AI
(26CD7PEAAI), BMSCE, four members (`README.md:108-117`).

### 1.3 Where the project stands (from the repo)

| Gate | Repo status | Source |
| --- | --- | --- |
| CP0 | APPROVED 24 Oct | `docs/checkpoints/checkpoint-0/approvals.json` |
| CP1 | APPROVED 26 Oct (lead exception) | `checkpoint-1/approvals.json`, tag `checkpoint-1-approved-2026-10-26` |
| CP2 | APPROVED 27 Oct (lead acceptance + Win/Linux CI) | `checkpoint-2/approvals.json`, tag `checkpoint-2-approved-2026-10-27` |
| CP3 | **Contradictory**: README says "closure", ledger says `VERIFICATION_IN_PROGRESS`, plan register says WAITING | `checkpoint-3/README.md`, `checkpoint-3/approvals.json`, `implementation plan.md:525` |
| CP4 | APPROVED 1 Nov on `checkpoint-4` (lead-reported all-four acknowledgement) | [cp4] `docs/checkpoints/checkpoint-4/APPROVAL.md` |
| MG1, CP5–CP8 | WAITING | `implementation plan.md:527-531` |

Released by CP4: **A09, H09, S08, V10 are READY** (not started per any record).

---

## 2. Architecture and data flow

### 2.1 Stack and layout

Single local Python package (`pyproject.toml`): Python ≥3.11, Pydantic v2, Typer CLI,
FastAPI/uvicorn API, LangGraph + `langgraph-checkpoint-sqlite`, pdfplumber, SQLite/FTS5,
stdlib `decimal`; `uv.lock` committed. React/Vite UI in `ui/` (`package-lock.json`).
Isolated Apple-Silicon MLX runtime in `tools/local-model/` with its own `uv.lock`.
Components C00–C16 are logical modules, not services (`SYSTEM_DESIGN.md` §2).

| Component | Code |
| --- | --- |
| C00 CLI / API / UI | `src/recycleguard/cli.py`, `api/app.py`, `ui/src/` |
| C01 Acquisition/intake | `intake/acquisition.py`, `intake/batch.py`, `configs/sources/source_leads.jsonl` (29 leads) |
| C02 Blob store/catalog | `storage/blob_store.py`, `storage/catalog.py` |
| C03 Extraction | `extraction/{csv,json,pdf}_extractor.py`, optional `extraction/vlm_parser.py` seam |
| C04 Normalization | `normalization/units.py` (incl. Indian lakh grouping), `normalization/equivalence.py` |
| C05 Snapshots/profiles | `snapshots.py`, `profiles.py`, `foundation.py`, `foundation_review.py`, `support_review.py` |
| C06 Index | `indexing/` (provision chunker, FTS5 index) |
| C07 Retrieval/grading | `retrieval/service.py`, `grader.py`, `expansion.py`, `claim_checks.py`; `knowledge/` (temporal, deadline register, corpus audit) |
| C08 Domain tools | `domain/` (allocation, lots, lifecycle, priority, identity, products, commercial, reconcile) |
| C09 Workflow | `workflow/runner.py` (LangGraph), `workflow/store.py`, `investigation.py` (A07 composition) |
| C10 Model gateway | `model_port.py` (protocol only), `local_model.py` (MLX loopback adapter), `tests/support/model_port.py` (scripted) |
| C11 Audit kernel | `storage/audit_kernel.py`, `storage/commit_boundary.py`, `storage/authority.py` |
| C12 Report/verifier | `reporting/baseline.py`, `reporting/repair.py` |
| C13 Review | `review/service.py`, `local_session.py` (password reauth, POSIX mode / Windows ACL) |
| C14 Export/replay | [cp4] `exports/service.py`, `contracts/bundles.py` |
| C15 Generator | `benchmarks/generator/` |
| C16 Evaluation | `benchmarks/evaluation/` (oracle, scoring; [cp4] validation, visible_reference, reference_review) — **no trial coordinator** |
| Isolation | [cp4] `isolation.py`, `isolated_runtime.py`, `tools/investigator-runtime/Dockerfile` |

Contracts: `src/recycleguard/contracts/*` → 151 JSON schemas in `schemas/v1/`
(159 on [cp4]), checked by `scripts/export_schemas.py --check`; OpenAPI in
`docs/api/openapi.json`.

### 2.2 End-to-end data flow

```text
Normative corpus:  source leads → acquisition attempt (bytes, SHA-256) → C02 original
                   → C03 page/clause coverage → reviewed provisions/applicability (C05)
                   → frozen corpus snapshot → C06 FTS5 index (membership digest) → C07

Case dossier:      case_manifest.json + records/*.jsonl|csv + documents/*.pdf
                   → C01 receipts (declared/missing/extra/duplicate/corrupt)
                   → C02 immutable originals → C03 observations + page/row coverage
                   → C04 typed records, event equivalence (pending when ambiguous)
                   → DRAFT foundation → authenticated foundation review → approved case snapshot
                   → explicit authenticated support review (record-level, with evidence refs)
                   → C08 preflight reconciliation
                   → C09 investigation: PLAN → tool action → ASSESS (loop, budgeted)
                   → C12 draft + numeric/citation verification (≤1 repair)
                   → AWAITING_REVIEW → C13 human decision bound to exact report/input digests
                   → C14 COMPLETE_LOCAL / QUALIFIED_PUBLIC bundle → integrity verify → artifact replay

Benchmark:         C15 world → invariants → visible render → faults → visible dossier (normal path)
                   C15 hidden record / V09 references → evaluator only, after run is sealed
```

**Per-action order** (`CONTRACTS.md` §9.4): record proposed action → validate
allowlist/args/pins/budget → commit intent + exact request → execute, write outputs to
blobs → commit result + audit event atomically → update graph checkpoint. A lost
outcome becomes `OUTCOME_UNKNOWN` and is **not** blindly retried
(`workflow/ports.py:24-28`).

**Run states** (`SYSTEM_DESIGN.md` §7.2): CREATED → PREFLIGHT → INVESTIGATING ⟲ →
DRAFTING ⇄ VERIFYING → AWAITING_REVIEW → COMPLETED / BLOCKED_INPUT / BLOCKED_OUTPUT /
FAILED / CANCELLED. Approve completes; reject/request-changes block output (correction
is a new parent-linked run); escalate stays in review; manual closure is
`CLOSED_WITHOUT_DECISION`, never fake approval.

### 2.3 The agent and its tools

The agent is one bounded investigator inside the LangGraph runner. Each turn the model
returns a typed **PlanProposal** (choose one allowed action or a stop reason) and,
after the tool result, an **AssessmentProposal** (verdict + disposition). Tools exposed
to the model (`src/recycleguard/investigation.py:283-293`, `:894-902`):
`inspect_evidence`, `lookup_locator`, `trace_certificate`, `compute_reconciliation`,
`compare_return`, `search_rules`. Note: `compare_return` is bound to the same
`reconcile` handler as `compute_reconciliation` (`investigation.py:899-900`).
The runner rejects any tool outside `_ALLOWED` (`workflow/runner.py:42`, `:91`).
Models cannot approve, mutate evidence, or run SQL/shell.

### 2.4 Review, recovery, export, UI/API

- **Review:** local reviewer enrolled via `recycleguard reviewer init` or
  `POST /api/v1/reviewer`; every decision re-authenticates and binds exact report and
  input digests; stale packets are rejected (`docs/checkpoints/checkpoint-3/a07.md`).
- **Recovery:** LangGraph checkpoints are derived state; the application ledger is
  authority. [cp4] recovery rejects checkpoint/ledger sequence mismatches and resumes
  interrupted turns from committed reservations without re-dispatch
  ([cp4] `A08_INTEGRATION.md`).
- **Export/replay** [cp4]: `audit export`, `audit verify-package`, `replay-package`.
  Artifact replay reconstructs references offline; it does **not** recompute reports
  or model results. Public export is deliberately **PARTIAL** (withholds uncleared
  derivatives).
- **API:** single-process demo (`docs/api/README.md`). Bearer token ≥24 chars,
  constant-time compare (`api/app.py:130`, `:149`); ZIP upload capped at 25 MB
  compressed / 100 MB expanded (`api/app.py:466-475`); model config, prompts and actors
  are server-owned. Only development fixtures (`tests/fixtures/visible`) are served.
- **UI:** React app consuming the OpenAPI contract; 78 tests reported passing
  (`docs/checkpoints/checkpoint-4/S_UI_REVIEW.md`).

### 2.5 Scripted sandbox vs. real model

| Aspect | Scripted (what CP3/CP4 demonstrate) | Real model (U01) |
| --- | --- | --- |
| Gate | `RECYCLEGUARD_MODE=test` **and** `ENABLE_TEST_ADAPTERS` (`config.py:21-25`) | Explicit `--model-config` / `RECYCLEGUARD_LOCAL_MODEL_CONFIG` |
| `execution_kind` / variant | `SCRIPTED_TEST` / `REAL_SERVICES_SCRIPTED_C10` | `MODEL_BACKED` / `REAL_SERVICES_LOCAL_MODEL` (`investigation.py:271-274`) |
| Proposals | Predetermined exchanges (`tests/support/model_port.py`) | `mlx-community/Qwen3.5-9B-4bit`, revision `8b2b98c0…`, via loopback `127.0.0.1` `/v1/completions` |
| Tools/services | Real A07 services | Same |
| Sandbox | [cp4] Docker: nonroot, read-only root, `--network none`; image hard-sets `MODE=test` (`tools/investigator-runtime/Dockerfile`) | **Not sandboxed**; [cp4] isolation evidence states "real-model isolation not claimed" |
| Fallback | None | None ("no automatic fallback", `workflow/runner.py:185-187`) |

**Model, prompt and budget configuration:**

- `LocalModelConfig` (`local_model.py:63-78`): model id/revision literal-pinned,
  weights-manifest and runtime-lock digests, MLX-LM `0.32.2`, prompt
  `prompt:u01_qwen_non_thinking_v4`, `max_output_tokens=768`,
  `max_total_tokens=16384`, `timeout_seconds=120`. Prompt pin = SHA-256 over system
  text, phase rules, format and both response schemas (`local_model.py:111-127`).
  Requests use `temperature: 0.0`, no seed field (`local_model.py:360-366`).
- Weight hashes: `docs/checkpoints/model-gateway/evidence/weights-manifest.json`
  (5,977,071,733 bytes; weights not in Git).
- **Budgets exist in three different places with different values:**

| Source | Model calls | Actions | Tokens | Wall time |
| --- | --- | --- | --- | --- |
| Plan proposal (`implementation plan.md:801-814`) | 16 | 32 investigative / 40 total | 64k in + 12k out | 300 s |
| Contract defaults `BudgetLimits` (`contracts/workflow.py:59-70`) | 24 | 64 | 49,152 total | 300 s |
| API defaults for MODEL_BACKED (`api/app.py:713-723`) | 12 | 64 | 16,384 × 12 | 600 s |

  Clients can also override budgets per run (`RunRequest.budgets`, `api/app.py:115-118`).

### 2.6 Dataset, corpus/index, scorer and trial protocol

| Item | Exists? | Evidence |
| --- | --- | --- |
| Visible dev fixtures | Yes: `case_001` (S01) + 6 S05 + 6 S04 + 21 S06 dossiers + 24 pilot dev dossiers in `tests/fixtures/visible/` | `benchmarks/generator/README.md` |
| Pilot `pilot-0.1` | Yes: 48 dossiers, 24 dev / 24 held-out, grouped by entity/template/timeline; one per family F01–F16 + 8 combinations per split | `benchmarks/generator/pilot_cases.py`, `pilot.py` |
| Held-out storage | Seal only: `benchmarks/pilot/heldout_seal.json` (24 tree digests, aggregate `90e2c5c3…`). Held-out bytes regenerated into gitignored `benchmarks/heldout/` — **not present in this checkout** | `.gitignore:35-38` |
| Separation strength | "Internal only. Templates and seeds are in this code, so anyone with the repository can regenerate the held-out dossiers." | `benchmarks/generator/README.md:148-150` |
| Corpus | Fixture corpus of **two originals**: R02 (Rules 2022, 38 pp) and R08 (CPCB FAQ, 13 pp); selected provisions R02 Rule 6(4), 15(1)-(3), R08 §C | `docs/data/source_data_card.md` |
| Index | FTS5 with membership digest; immutable-bytes recovery | `indexing/`, `checkpoint-3/a07.md` |
| Oracle | `benchmarks/evaluation/oracle.py` (OracleCase). [cp4] V09 independent visible-reference calculator; 48/48 agree; status `INDEPENDENT_REFERENCE_VALIDATED`, **0 human reviews** | [cp4] `reference-evidence.json` |
| Scorer | `benchmarks/evaluation/scoring.py`: reconciliation, findings P/R/F1, abstentions, forbidden actions | — |
| Citation / temporal / next-action scoring (H10) | **Not implemented** | no code found |
| Trial runner, variant definitions V0/V1/V2, repeats, results ledger, bootstrap | **Not implemented** | `git grep` for variant/trial/bootstrap finds only the `experiment_variant` string |
| Trial protocol | **Only as planned prose** (plan §13): 24 held-out × 3 repeats × V1/V2 = 144 model runs + 24 V0 | `implementation plan.md:900` |

---

## 3. Work-item code glossary

Primary definition source for every code is the canonical task register in
`implementation plan.md` §4.6 (lines ~440–515) and the dependency graph §4.5
(lines ~337–432). "Status" is the register on **`checkpoint-4`**; where this checkout
differs it is noted. Owner letters: A = R V Abhishek, H = H Sampreeth Bhat,
S = Sushanth S, V = Vedantha Vinay Vernekar (`implementation plan.md:174`).

| Code | Definition (register) | Owner | Predecessors | Status / evidence |
| --- | --- | --- | --- | --- |
| **A07** | Integrated investigation: real services, scripted C10, audited adaptive trace, authenticated review recovery | A | A06, H06, S04, V05 | **DONE** — `docs/checkpoints/checkpoint-3/a07.md`, `evidence/a07-*.json` |
| **A08** | Week-1 acceptance, cold start, reproducible prototype handoff; G01–G12 evidence; explicit A/B level | A | CP3, V08, V09, H08 | **DONE** on [cp4] (this checkout: BLOCKED) — [cp4] `COMPLETION.md`, `gate-regressions.json` |
| **A09** | Tune graph/CLI on dev data and freeze candidate code; pinned graph/prompt/budget configs | A | CP4 | **READY** [cp4]; no work recorded |
| **A10** | Integrate research report, architecture/results narrative and slides (8–12 pp) | A | CP6 | BLOCKED |
| **A11** | Freeze final review build; four-person rehearsal; demo recovery copy | A | A10, V14 | BLOCKED |
| **A12** | Submission packaging; final report/slides/code; artifact inventory | A | CP7 | BLOCKED |
| **H09** | Tune dev retrieval; freeze corpus/index/policy | H | CP4 | **READY** [cp4] |
| **H10** | Blind-score citation, temporal support, next-action quality; written rubric; ≥20% double scoring | H | V11 (+V12 if real-model) | BLOCKED |
| **H11** | Finalize source rights, attribution, references, limitations | H | H09, H10 | BLOCKED |
| **H12** | Final references/rights/attribution audit against distributed content | H | CP7 | BLOCKED |
| **S08** | Fix dev tool/generator defects; freeze deterministic inputs; preserve split | S | CP4 | **READY** [cp4] |
| **S09** | Independently score exact balances and finding matches; classify errors | S | V11 (+V12) | BLOCKED |
| **S10** | Dataset/generator card and release manifest | S | S08, S07 | BLOCKED |
| **S11** | Reproduce released generator, visible pilot and deterministic examples | S | CP7 | BLOCKED |
| **U01** | Local C10 gateway development (Qwen/MLX) | A | None | **IN_PROGRESS (paused)** — `docs/checkpoints/model-gateway/README.md`; see §5 contradiction |
| **V07** | Minimal investigator runtime; enforced oracle isolation; denied access recorded | V | CP2 | **DONE** on [cp4] (scripted investigator only) — [cp4] `isolation-evidence.json`, `checkpoint-3/v07.md` |
| **V10** | Rehearse evaluator; freeze protocol, scorer, rubric, denominators, repeats, invalid-trial policy, resource feasibility | V | CP4 | **READY** [cp4] |
| **V11** | Execute sealed deterministic and non-model evaluation runs | V | CP5 | BLOCKED |
| **V12** | Fixed-retrieval and adaptive real-model trials (V1/V2); never scripted outputs | V | CP5, MG1 | BLOCKED; must be recorded NOT_RUN if CP5 is NON_MODEL_ONLY (`implementation plan.md:516`) |
| **V13** | Close scoring, adjudication, uncertainty, results ledger | V | V11, H10, S09 (+V12) | BLOCKED |
| **V14** | Verify publication package, result recomputation, saved-artifact replay | V | V13, H11, S10, A10 | BLOCKED |
| **V15** | Final manifests, archive evidence, hashes, run instructions, PDFs, submission set | V | A12, H12, S11 | BLOCKED |

Related codes that gate the table (also in §4.6): V06 export/replay, V08 recovery,
V09 oracle seal (all **DONE** on [cp4]); MG1 requires U01, A07, V07, V10
(`implementation plan.md:528`). Every code in your table is defined; none were
missing. They also appear in `docs/individual_contribution/S_contribution.md:120-124`
(S07–S11, which still shows S08 "BLOCKED on CP4" — stale).

---

## 4. Checkpoint readiness table

| Checkpoint | Readiness | Evidence present | Missing / unverified |
| --- | --- | --- | --- |
| **CP4 – Approved** | **Ready (approved, qualified)** — on `checkpoint-4` only | [cp4] `APPROVAL.md`, `COMPLETION.md`, `VERIFICATION.md`, `gate-regressions.json` (437 tests, 0 failed), `isolation-evidence.json` (45/45 probes denied), `reference-evidence.json` | Not in this checkout; not merged to `main`; no `checkpoint-4-approved` tag. G12 is `INCOMPLETE_EVIDENCE` (24 skipped) in the ledger. No clean final full-suite run ("Do not describe this as a clean final full-suite run", [cp4] `VERIFICATION.md`). No Windows/Linux CI asserted for the final candidate. Rests on CP3, whose ledger is still `VERIFICATION_IN_PROGRESS`. Acknowledgement is lead-reported, not signed. |
| **MG1 – Real-model readiness** | **Partial** | U01 adapter, pins, weights manifest, tokenizer bound check (`model-gateway/evidence/`); v1–v3 failure summaries; claimed v4 21/21 workflow completion (`model-gateway/README.md:60-79`); A07 DONE; V07 DONE for scripted mode | V10 not started (MG1 requires it). Real-model execution is **not** inside the sandbox. v4 evidence summary not committed (only v1–v3 JSON). README contradicts itself (§5 R1). No constrained decoding. No real-model failure/retry/timeout characterization across a run set. No MG1 approval record. |
| **CP5 – Experiment freeze** | **Not started** | Pinned prompt/model config; pilot seal; V09 reference seal; scorer module | A09/H09/S08/V10 not started. No trial runner, no V0/V1/V2 definitions in code, no frozen budgets (three conflicting sets), no protocol document, no invalid-trial policy, no scope declaration (NON_MODEL_ONLY vs INCLUDES_REAL_MODEL), no experiment ID. Corpus has 2 sources. |
| **CP6 – Results close** | **Not started** | Scorer for balances/findings/abstentions/forbidden actions | No trials, no citation/next-action rubric or scorer (H10), no adjudication or double-scoring workflow, no uncertainty/bootstrap code, no results ledger. |
| **CP7 – Final review freeze** | **Not started** | Review 2 report/slides (`output/`), `docs/data/source_data_card.md`, generator README | No final report, slides, dataset card (S10), rights audit (H11), clean reproduction package (V14), or rehearsal record. |
| **CP8 – Submission check** | **Not started** | — | No submission inventory, archive, hashes, licence decision, or verified final package. |

### Per-checkpoint detail: risks and next actions

**CP4.** Risks: (a) work exists on a branch not yet in `main` or this checkout, and
its worktree and its private evaluator evidence live under `/private/tmp`, which
macOS can clear; (b) CP3 never formally closed; (c) G12 incomplete and
"independent" review was a coding agent, not a human. Actions:
1. Tag `b5a9831`/`e3b59fc` and merge `checkpoint-4` to `main` via reviewed PR
   (plan §3.2 requires merge after approval).
2. Move `/private/tmp/recycleguard-cp4-evaluator/` and `tmp/cp4-*` evidence to a durable
   private location outside the repo and record its digests.
3. Close the CP3 ledger (`checkpoint-3/approvals.json`) or record why CP4 supersedes it.
4. Reconcile the stale CP4 docs in this checkout (`checkpoint-4/README.md`,
   `API_HANDOFF.md` say WAITING) by working from `checkpoint-4`.

**MG1.** Risks: unreliable structured output (the README's own blocker,
`model-gateway/README.md:131-136`); every v4 run chose the same tool and the same
`REFUTES/ABSTAIN` verdict, including the clean F01 baseline (`:65-79`), which suggests
a degenerate policy rather than investigation; real model not isolated; `temperature
0.0` without a seed means reproducibility is only best-effort; Mac-only runtime.
Actions (order matters):
1. V10 must exist first (MG1 depends on it).
2. Commit the v4 summary evidence and fix the README contradiction.
3. Decide whether real-model runs need the sandbox; if yes, extend the isolated
   runtime to allow only the loopback model endpoint (plan §11).
4. Run a dev-only reliability characterization (schema-valid rate, timeouts, retries,
   tool diversity) on the 24 dev dossiers, not held-out.
5. Write an MG1 approval record that approves setup only, not quality.

**CP5.** Risks: unfrozen budgets; client-overridable budgets; no runner means trials
could be run ad hoc; held-out regenerable from code; tiny corpus makes V1-vs-V2
retrieval differences hard to observe; no scope decision. Actions:
1. **Scope decision first:** NON_MODEL_ONLY or INCLUDES_REAL_MODEL (`implementation plan.md:434`).
2. In parallel: A09 (freeze graph/prompt/budget into one pinned config),
   H09 (freeze corpus/index/policy and retrieval question set), S08 (freeze tools/
   generator/profile, preserve split), V10 (protocol, rubric, denominators, repeats,
   invalid-trial policy, dev dry-run, throughput rehearsal).
3. Build the C16 trial coordinator: variant definitions, case×repeat×order schedule,
   isolated launch, sealing, per-trial ledger.
4. Freeze record listing every digest (code commit, `uv.lock`, prompt pin, model
   config pin, weights manifest, corpus/index/profile, pilot seal, V09 seal, scorer
   version, budgets) and the scope.
5. If INCLUDES_REAL_MODEL: MG1 APPROVED before freeze.

**CP6.** Risks: scorer currently returns precision 1.0 / recall 1.0 for empty sets
(`scoring.py:173-174`) instead of N/A; scorer was relaxed to accept agent-validated
references (§5 R7); no blind scoring tooling. Actions: V11 → (V12) → H10 + S09 in
parallel → V13 (adjudication, paired case-level bootstrap, all attempts accounted).

**CP7 / CP8.** Depend entirely on CP6. Risks: licence for code/data undecided
(plan §14); public export is PARTIAL; sources default to `REVIEW_REQUIRED` rights.
Actions: H11 and S10 can begin drafting once H09/S08 freeze; A10 after CP6; V14, A11;
then A12/H12/S11 → V15 with hashes.

### Dependency order (critical path)

```text
[now] merge/tag CP4 ─┬─ A09 ─┐
                     ├─ H09 ─┼─ (scope decision) ─ CP5 ─ V11 ─┬─ H10 ─┐
                     ├─ S08 ─┤                     ▲          ├─ S09 ─┼─ V13 ─ CP6 ─ A10 ─ V14 ─ A11 ─ CP7 ─ A12/H12/S11 ─ V15 ─ CP8
                     └─ V10 ─┘                     │          └───────┘
   U01 + A07 + V07 + V10 ─ MG1 ────────────────────┘ (only if real model) ─ V12 ─ (gates H10/S09/V13)
   S10 after S08+S07;  H11 after H09+H10
```

---

## 5. Risks and open questions (including quality review)

### 5.1 Governance and record integrity

- **R1 — Contradictory U01/MG1 record.** `model-gateway/README.md:3` says compatibility
  demonstrated and `:60` reports v4 "100% … passed cleanly", while `:104` says "All three
  runs ended FAILED" and `:131-136` says the blocker remains and nothing was implemented.
  The register still says "paused" (`implementation plan.md:514`). Only v1–v3 summaries
  are committed. *Open question: is U01 paused or active, and where is the v4 evidence?*
- **R2 — CP3 never closed.** `checkpoint-3/approvals.json` `"status":
  "VERIFICATION_IN_PROGRESS"`; plan register line 525 WAITING even on [cp4]. A08 requires
  CP3. *Open question: was CP3 approved?*
- **R3 — Branch drift.** `main` is still at the Review 2 docs (`c9cc375`). CP1/CP2 have
  tags; CP3/CP4 do not. This checkout lacks the approved candidate.
- **R4 — Volatile evidence.** CP4 worktree (`/private/tmp/recycleguard-cp4`) and the
  private evaluator outputs (`/private/tmp/recycleguard-cp4-evaluator/`) cited by
  [cp4] `COMPLETION.md` are in `/private/tmp`; repository `tmp/` is gitignored.
- **R5 — Acknowledgements are lead-reported.** CP1, CP2 and CP3 explicitly lack
  four-person acknowledgement; CP4's is lead-reported via conversation. Acceptable if
  disclosed, but it weakens "independent reviewer" claims.
- **R6 — Stale/inaccurate docs.** `checkpoint-4/README.md` and `API_HANDOFF.md` in this
  checkout say WAITING; `docs/checkpoints/README.md` index stops at CP3;
  `S_contribution.md:121` stale. The untracked `docs/review_guides/` use machine-local
  `file:///Users/rva/...` links and describe "hand-reviewed ground-truth Oracle Cases"
  (`05_EVALUATIONS_AND_BENCHMARKS.md`), but no oracle is `HAND_REVIEWED`.

### 5.2 Evaluation validity

- **R7 — Scorer gate weakened.** This checkout's scorer requires `HAND_REVIEWED`
  (`scoring.py:64-65`); [cp4] changes it to reject only `UNVERIFIED_WORLD_PROJECTION`,
  so agent-validated references (`INDEPENDENT_REFERENCE_VALIDATED`, 0 human reviews) are
  scoreable. This must be declared in the CP5 protocol.
- **R8 — Undefined denominators score as perfect.** `scoring.py:173-174` returns 1.0
  precision/recall when there are no expected findings, contrary to plan §13.3 ("mark
  undefined denominators N/A"). Clean F01 cases would inflate macro scores.
- **R9 — Held-out contamination risk.** Generator code and seeds are in the repo
  (`benchmarks/generator/README.md:148-150`); anyone can regenerate held-out dossiers.
  There is no held-out access log in this checkout (V09 was to own it).
- **R10 — Oracle independence.** The hidden reference was written by the generator
  author (`documentation.md:479`); [cp4] V09 adds an independent calculator but semantic
  review was by a coding agent.
- **R11 — No experiment machinery.** No V0/V1/V2 variants, no trial runner, no ledger, no
  uncertainty code, no citation/next-action scorer. V1 ("fixed retrieval + model") has no
  implementation at all.
- **R12 — Small, narrow corpus.** Two source documents (`source_data_card.md`) limit
  temporal-RAG and adaptive-retrieval claims.
- **R13 — Pilot power.** 24 held-out cases; the plan itself says it is a feasibility pilot
  (`implementation plan.md` §7.3).
- **R14 — Model behaviour.** The U01 v4 table shows identical action and verdict for all
  21 dossiers; "workflow completion" ≠ investigation quality (the README says so too).

### 5.3 Reproducibility

- **R15 — Budgets not frozen** (three value sets, client override; §2.5).
- **R16 — Non-deterministic model output.** Greedy decoding but no seed; MLX/Metal
  numeric nondeterminism unmeasured. Plan already says "no promise of identical LLM
  output" (`implementation plan.md:904`).
- **R17 — Platform split.** Real model is Apple-Silicon only; the sandbox is
  Docker/Colima; CI is Windows/Linux. A single reproducible real-model environment does
  not exist.
- **Positive:** `uv.lock` and `ui/package-lock.json` committed; CI uses `uv sync
  --locked` on Win/Linux × 3.11/3.12 and replays CP2/A06/A07/API from fresh roots
  (`.github/workflows/ci.yml`); runs pin config, source, lock, snapshots and index
  (`checkpoint-3/a07.md`); [cp4] wheels embed the build lock.
- `pyproject.toml` dependency ranges are loose (`pdfplumber>=0.11.10` has no upper bound),
  harmless while the lock is used.

### 5.4 Security and data handling

- **Positive:** test adapters gated by mode (`config.py:21-25`); loopback-only model
  endpoint validator (`local_model.py:80-95`); constant-time token compare
  (`api/app.py:149`); ZIP size limits; reviewer reauthentication with POSIX/Windows ACL
  checks (`configs/README.md`); weights and `.recycleguard/` gitignored; hidden and
  held-out roots gitignored.
- **Risk:** API docs example binds `--host 0.0.0.0` over plain HTTP on a LAN
  (`docs/api/README.md`); the doc itself says HTTPS is required on untrusted networks.
- **Risk:** isolation covers only the scripted investigator (Dockerfile hard-sets
  `MODE=test`); ordinary API and real-model runs have no enforced boundary.
- **Minor:** `.gitignore:33` ignores `CLAUDE.md`, but it is tracked.
- The model-gateway README mentions an OpenRouter key "supplied in chat" was not used;
  confirm it is not stored anywhere (not checked: secrets were not inspected).

### 5.5 Failure and recovery behaviour

- **Positive:** OUTCOME_UNKNOWN is never auto-retried (`workflow/ports.py:24-28`); budget
  stop never promotes pending to supported; uncertain UI mutations lock to read-only
  (`S_UI_REVIEW.md`); [cp4] recovery rejects checkpoint/ledger mismatch.
- **Risk:** API is single-process with no idempotency-key protocol (`S_UI_REVIEW.md`);
  a crashed API leaves recovery to manual inspection.
- **Risk:** a real model's timeouts/invalid outputs at scale are uncharacterized; v1–v3
  ended `FAILED/PROVIDER_FAILURE`.

### 5.6 Test coverage

- 78 test files on [cp4]; mapped gate ledger 437 executed, 0 failed, 24 skipped in G12
  ([cp4] `gate-regressions.json`). Frontend 78 tests.
- The planned per-gate files `test_intake_coverage.py`, `test_evidence_lineage.py`,
  `test_temporal_retrieval.py`, `test_retrieval_audit.py`, `test_permissions.py`,
  `test_operation_recovery.py`, `test_scoring_protocol.py` (plan §10) do not exist;
  gates are mapped onto other modules ([cp4] `scripts/verify_cp4.py` `GATES`).
- One stray test file sits outside the test tree layout: [cp4] `tests/test_v06_export_replay.py`.
- No last clean full-suite run is recorded for the approved candidate.

### 5.7 Open questions for the team

1. Is CP3 approved? Should its ledger be closed before CP5?
2. Is the real model in scope for CP5 (INCLUDES_REAL_MODEL)? If yes, who owns making
   structured output reliable and sandboxing the model?
3. Which single budget set will be frozen?
4. Is agent-performed reference review acceptable for scoring, or must V09 add human review?
5. Where is the v4 U01 evidence, and which part of the model-gateway README is current?
6. What code and data licences will the release use (plan §14)?
7. What does the uncommitted `ui/src/screens/Readiness.tsx` change belong to?

---

## 6. Recommended next steps (priority order)

1. **Consolidate the approved state.** Work from `checkpoint-4`; tag the CP4 candidate;
   open a reviewed PR to `main`; copy `/private/tmp` evaluator and isolation evidence to a
   durable private location and record digests. Decide what to do with the uncommitted
   `Readiness.tsx` edit.
2. **Fix records before freezing.** Close or explain CP3; reconcile the
   model-gateway README and commit the v4 summary; update `docs/checkpoints/README.md`.
3. **Make the CP5 scope decision** (NON_MODEL_ONLY vs INCLUDES_REAL_MODEL). The
   non-model path is achievable now; the real-model path adds MG1 and engineering risk.
4. **Start A09 / H09 / S08 / V10 in parallel** (all READY). V10 is on the critical path for
   both CP5 and MG1, so start it first.
5. **Build the missing evaluation machinery** (owned by V with A): trial coordinator,
   variant definitions (at least V0; V1/V2 only with a real model), per-trial ledger,
   invalid-trial policy; fix N/A denominators in `scoring.py`; add citation/next-action
   rubric tooling for H10.
6. **Freeze one budget set** in a pinned configuration, and make API runs reject budget
   overrides under evaluation mode.
7. **If the real model is in scope:** constrained decoding or equivalent; dev-only
   reliability characterization; sandbox the model run; MG1 record. Otherwise record V12
   as NOT_RUN with the CP5 reference.
8. **Write the CP5 freeze record** with every digest listed in §4, then run V11 (and V12)
   on held-out cases with no further tuning.
9. **CP6:** H10 and S09 scoring with ≥20% double scoring, V13 adjudication and paired
   bootstrap; retain every attempt.
10. **CP7–CP8:** S10 dataset card, H11 rights, A10 report/slides on measured results only,
    V14 clean reproduction, A11 rehearsal; then A12/H12/S11 and V15 hash-verified
    submission set.
