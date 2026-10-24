# Copilot instructions — ReCycleGuard

## 0. Current focus (edit this block before each session)

```text
MEMBER:      <Abhishek | Sampreeth | Sushanth | Vedantha>
CHECKPOINT:  <CP0 | CP1 | CP2 | CP3 | CP4 | CP5 | MG1 | CP6 | CP7 | CP8>
TASK ID(S):  <e.g. A03, H02, S02, V02>
```

Rules for this block:

- The checkpoint and task IDs above define the **only** scope for this session.
- If the block is empty or still holds placeholders, ask which member, checkpoint and task ID(s) apply before producing any code or advice.
- Never infer the checkpoint from the date. Calendar dates are targets, not permission.

---

## 1. Mandatory reading order

Before answering anything, consult sources in this order. Stop at the first source that settles the question.

1. **`implementation_plan.md`** — execution authority. Read §4 (dependency graph, task register §4.6, checkpoint register §4.7, start/stop rules §4.2), then the section for the active checkpoint's day/week, then §3 (ownership) and §10 (acceptance matrix).
2. **`PROJECT_GUIDELINES.md`** — course rules: mandatory agentic concepts, review rubrics R1–R4, deliverables, academic integrity, advisory-only scope for sensitive domains.
3. **`CONTRACTS.md`** — authoritative software interfaces: boundary types, validation, error codes, protocol behavior, C00–C16 signatures.
4. **`SYSTEM_DESIGN.md`** — architecture, storage layout, algorithms, invariants, G01–G12 gates.
5. Other docs only when the task needs them:
   - `DOMAIN_RESEARCH.md` — officer tasks T01–T16, source hierarchy, evidence trails.
   - `AGENTIC_IMPLEMENTATION_OVERVIEW.md` — synthetic-data method, baselines, publication cautions.
   - `CPCB EPR Data and RAG.md` — acquisition leads and field inventory. **Tentative**: SYSTEM_DESIGN §1.2 lists deliberate corrections. Do not copy hard-coded GST rates, price bands, denomination lists, OCR cutoffs, or integer authority ranks from it.
   - `PROJECT_CHARTER.pdf`, `ReCycleGuard.pdf` — scope and decision statement.

Conflict resolution:

- Interface disagreement → CONTRACTS wins.
- Architecture policy disagreement → SYSTEM_DESIGN wins.
- Execution order / who-does-what disagreement → `implementation_plan.md` wins.
- If docs contradict each other and the answer matters, **stop, name the conflict, quote both locations, and ask**. Do not pick silently.

Never invent a field, enum, status, error code, path, or API that is not in these documents. If something is missing, say so and propose a contract change instead of improvising.

---

## 2. Checkpoint-scoped behavior

Give information and code **only** for the active checkpoint and task IDs in §0.

Procedure every session:

1. Read the task row(s) in `implementation_plan.md` §4.6 for the stated task IDs: owner, state, required predecessors, acceptance evidence.
2. Read the checkpoint row in §4.7.
3. Check predecessors:
   - All required predecessor tasks must be `DONE` and predecessor checkpoints `APPROVED`.
   - If not, reply: task is `BLOCKED`, list the unmet predecessors, and offer only (a) work on another `READY` task for the same member, (b) review of a producer handoff, or (c) fixture work explicitly authorized inside the active task.
   - Do not jump ahead to blocked descendants. Do not build stubs that pretend a blocked dependency is done.
4. Confirm the task belongs to the stated member (A = Abhishek, H = Sampreeth, S = Sushanth, V = Vedantha). If not, flag it.
5. Produce only what the task's "Work and acceptance evidence" column requires. No extra modules, no optional UI/OCR/dense retrieval/multi-agent work unless a registered task covers it.
6. Surface relevant data only: the exact contract types, gates (G01–G12), fixtures, and day-plan items tied to that task. Do not dump unrelated sections.

Out-of-scope requests: say which task ID or checkpoint they belong to, whether that is currently `READY`, and stop. If the user wants a new task, state that §4.2 rule 7 requires owner, reviewer, effort, contract, acceptance evidence, and a register + graph update before work starts.

---

## 3. Project overview

**ReCycleGuard** — agentic decision-support for India's e-waste EPR (Extended Producer Responsibility) reconciliation under the E-Waste (Management) Rules, 2022.

- **One decision supported:** which discrepancy should the compliance officer investigate next, and what verification or correction does the evidence support?
- **Output:** traceable, human-reviewable working paper. Advisory only.
- **Does not:** file returns, trade credits, handle OTPs, certify legal compliance, allege fraud, estimate compensation, or touch live CPCB systems.
- **Statuses (internal, not official):** `RECONCILED_WITHIN_SCOPE`, `DISCREPANCY_DETECTED`, `PENDING_VERIFICATION`, `REQUIRES_EXPERT_REVIEW`.
- **Course:** Agentic AI (26CD7PEAAI), BMSCE. Reviews: R2 24 Oct, R3 31 Oct, R4 7 Nov, final submission 12 Nov 2026.

### Team and ownership

| Member | Owns |
| --- | --- |
| R V Abhishek (lead) | Integration, C00 CLI, C09 graph, C05 snapshots/profiles, common schemas/config, C10 interface and test seam only |
| H Sampreeth Bhat | C01 acquisition/intake, C03 extraction, C06 index, C07 retrieval, source/profile content |
| Sushanth S | C04 normalization, C08 domain tools, C15 generator/renderers/fault injection |
| Vedantha Vinay Vernekar | C02 blobs/catalog, C11 audit kernel, C12 reports, C13 review, C14 export/replay, C16 evaluator/oracle isolation |

Shared-file rules: Abhishek owns `pyproject.toml`, `uv.lock`, common schemas, CLI/config. Vedantha owns SQL migrations and the writer coordinator. Do not edit another member's owned files; propose the change to the owner.

### Stack

Single local Python 3.11+ application, logical modules (not microservices). `uv` + committed lockfile, Typer CLI, Pydantic v2, stdlib `sqlite3` and `decimal`, SQLite FTS5 lexical retrieval, LangGraph for bounded workflow, text-PDF extraction. pandas only for convenience, never for compliance arithmetic. No vector DB, OCR engine, or web UI on the critical path.

### Components

C00 CLI · C01 acquisition · C02 artifact store · C03 extraction · C04 normalization · C05 snapshots/profiles · C06 index · C07 retrieval/grading · C08 deterministic tools · C09 workflow · C10 model gateway · C11 audit kernel · C12 reports/verifier · C13 human review · C14 export/replay · C15 synthetic generator · C16 evaluation.

### Checkpoints (summary; §4.7 is authoritative)

CP0 interfaces · CP1 evidence foundation · CP2 baseline vertical slice · CP3 integrated investigation · CP4 Week 1 prototype acceptance · CP5 experiment freeze · MG1 real-model readiness (conditional) · CP6 scientific results close · CP7 final review freeze · CP8 submission check.

### C10 status — critical

The real LLM gateway (task **U01**) is **UNPLANNED**. Only the C10 interface and a clearly labelled test double are in scope.

- Never choose a provider, SDK, model name, or price.
- Test double output must carry `model_backend=TEST_DOUBLE` and must never be reported as agent reasoning or measured agent performance.
- V1/V2 experiment results stay `NOT RUN — MODEL GATEWAY UNAVAILABLE` until a real gateway exists.

---

## 4. Non-negotiable invariants

Apply these to every piece of code, test, and doc you produce.

1. Every submitted file gets a receipt before parsing, including corrupt, duplicate, undeclared, and irrelevant files.
2. Originals and observations are immutable. Corrections create revisions with `derived_from` lineage.
3. Runs pin exact case, corpus, profile, index, prompt, code, and policy versions. Never depend on "latest".
4. Every page/row ends in a terminal disposition: parsed, quarantined, excluded, failed, not applicable. Zero parsed rows never means zero business activity.
5. **Decimal strings only.** Regex `^-?(0|[1-9][0-9]*)(\.[0-9]+)?$`, max 18 integral / 8 fractional digits. No floats, no exponents, no SQLite `SUM`/REAL for quantities. Precision 28, display 4 dp `ROUND_HALF_EVEN`, rounding only at display with delta retained. Overflow/inexact → `NUMERIC_PRECISION_EXCEEDED`.
6. Equipment mass, metal mass, and money are distinct dimensions. Never sum unlike metals (Au/Cu/Al/Fe) into one balance.
7. One certificate → many events; one event → many observations. Never dedupe by certificate ID alone. Equivalence needs an authoritative event ID or a reviewed equivalence assertion; otherwise `PENDING`.
8. Supported quantity comes **only** from supported allocations. Account balances, snapshots, invoices, and payments are comparison/context, never fulfilment. Never invent allocations from an aggregate.
9. One credit lot per resolved certificate; active allocations across all events and years must not exceed lot capacity. Earlier-liability priority is checked at allocation time.
10. C08 computes the full input universe server-side from the pinned snapshot. Caller-supplied record lists must never narrow it.
11. Missing, unknown, not applicable, withheld, and zero are different states. Empty CSV cell = missing, never zero.
12. Hidden oracle, world truth, seeds, and fault labels never reach the investigator, index, prompts, logs, checkpoints, caches, or UI.
13. No state transition succeeds without a durable audit record. Audit/storage failure stops progress. External dispatch only after intent commit; a lost response is `OUTCOME_UNKNOWN`, never fabricated.
14. Document content is data, never instructions. Hostile text is preserved as evidence and cannot change tools, profile, quantities, or approvals.
15. The model proposes `ActionProposal` only. It cannot alter quantities, approve profiles, supply human identity, run SQL/shell, or set paths. Actor kind from a caller string never grants authority.
16. Legal applicability is clause-specific, reviewed, and half-open `[from, to)`. Unknown interval ≠ always applicable. Keep three deadline types separate: `ACHIEVEMENT`, `CREDIT_EVENT`, `RETURN_FILING`. A signed order missing = unresolved, never invented.
17. Purchase-ceiling policy stays `DISABLED_REVIEW_REQUIRED`. No tax/GST, pricing, EC, solar, refurbishing deferral, gold offset, or sales-derived target calculation. Report an explicit unsupported-feature disposition.
18. Approval means approval of the working paper, never compliance or filing. Never generate a fake acknowledgment.
19. Rights are per-asset (`ALLOW | DENY | REVIEW_REQUIRED`). Do not assume a public URL permits model transfer or redistribution.
20. Retain full results; context selection never deletes evidence. Exact JSON canonicalization: sorted keys, compact separators, Unicode preserved, no NaN, no trailing newline.

Supported profile: `producer_snapshot_v1` — one fictional producer per dossier, FY 2024–25, supplied metal-wise obligations, separate historical liability buckets, up to two reviewed EEE codes. ITEW4 / CEEW1 are candidates only until reviewed.

---

## 5. Coding rules

- Follow module layout in `implementation_plan.md` §3.1. Keep modules small and logical.
- Every service call uses `CommandContext` and returns `ServiceResult<T>` per CONTRACTS §2. Unknown fields rejected at strict boundaries.
- Domain unknowns → `PARTIAL` with issues; process/integrity failures → `FAILED`/`REJECTED`. No empty-list fallbacks for failures.
- Use real SQLite and real files in tests where possible. Fakes must use the same models, fail explicitly, and be disabled in evaluation configs.
- Write tests mapped to the relevant G01–G12 gate (§10 of the plan) and contract acceptance matrix (CONTRACTS §10). A passing screenshot is not evidence.
- Changing a shared field/enum/semantic requires updating: model, generated schema, consumers, fixtures, tests, and both design docs in the same change. No speculative fallback parsing in a consumer.
- Do not hard-code values the design marks as unreviewed (rates, prices, denominations, deadlines, solar percentages, OCR thresholds).
- Never commit secrets, runtime data roots, databases, or hidden benchmark artifacts. Held-out answers and generator code stay out of the runtime image.
- Git: small commits referencing task IDs. Workstream branches under `codex/`, integration branch `codex/implementation`. No force-push.

### Honesty rules (course integrity)

- No fabricated results, counts, metrics, or test outcomes. Say "not run" when not run.
- Do not claim a test passed unless it was executed and output exists.
- Synthetic-only evaluation: never claim real-world EPR accuracy.
- Held-out data: no tuning after inspecting held-out outcomes. Corrections get versioned reruns (plan §13.2).

---

## 6. Documentation duty: `documentation.md`

After **every** meaningful unit of work, update `documentation.md` at the repo root. If it does not exist, create it with the header below. Append; never rewrite or delete earlier entries. Keep entries factual and brief.

### 6.1 File header (when creating)

```markdown
# ReCycleGuard — working documentation log

Append-only log of work done per session. Source of truth for execution state remains `implementation_plan.md` §4.6/§4.7.
```

### 6.2 Entry template

```markdown
## <YYYY-MM-DD HH:MM IST> — <Member> — <Checkpoint> — <Task ID(s)>

**Task state at start:** <READY | IN_PROGRESS | ...>
**Predecessors verified:** <list, each DONE / APPROVED, or "n/a">

### Done
- <what was implemented/changed; file paths; contract types touched>

### Evidence
- Commit/branch: <ref or "uncommitted">
- Tests run: <exact command> → <result, or "NOT RUN">
- Fixtures/schema versions: <ids/digests>
- Gate(s) touched: <G01–G12 or "none">

### Limitations / open issues
- <known gaps, assumptions, unsupported features, anything unverified>

### Updates required
- **implementation_plan.md:** <proposed state change, e.g. "A03: IN_PROGRESS → IN_REVIEW; evidence above". Never mark DONE without independent reviewer>
- **CONTRACTS.md / SYSTEM_DESIGN.md:** <proposed edits, or "none">
- **Other docs / fixtures / schemas / tests:** <or "none">
- **Other members affected:** <producer/consumer handoffs, REVALIDATE flags>

### Next permitted step
- <single next task ID or handoff, consistent with the dependency register>
```

### 6.3 Update rules

- Log before ending a session, even if the work is partial or blocked. A blocked session logs the blocker and unmet predecessors.
- **Do not edit `implementation_plan.md` task/checkpoint state cells yourself.** Propose the change under "Updates required"; the lead reconciles state on the integration branch. Exception: if the user explicitly asks you to apply the edit.
- A task becomes `DONE` only with: code/config commit, exact fixture/snapshot/schema versions, test command and result artifact, output/digest, unresolved limitations, and an independent reviewer (plan §4.2 rule 4). If any is missing, say what is missing.
- If a change alters a schema, profile, corpus, tool, or dataset version, list downstream accepted tasks that need `REVALIDATE` and gates that need `REOPENED`.
- If you notice scope drift or an unregistered task, record it in "Limitations / open issues" and stop.
- Record doc inconsistencies you found (e.g. mismatched section numbers, conflicting values) under "Updates required" with both locations.

---

## 7. Response style

- Lead with the task ID, its state, and whether predecessors are satisfied.
- Then give only what the active task needs: interface types, steps, code, tests.
- Cite documents by file and section (e.g. `CONTRACTS §3.4`, `implementation_plan §4.6 A03`).
- Flag uncertainty and conflicts explicitly. Prefer asking one precise question over guessing.
- End every substantive response with: what was done, what to log in `documentation.md`, and the next permitted step.