# ReCycleGuard implementation plan

**Plan date:** 23 October 2026

**Team capacity:** four members, four hours per member per day, including coordination.

**Week 1:** 23–29 October — build and integrate the working application.

**Week 2:** 30 October–5 November — development-set tuning, frozen evaluation and research analysis.

**Status:** implementation roadmap; tasks, datasets, tests and results below are planned unless explicitly identified as existing.

This plan turns the existing specifications into four concurrent workstreams. It covers source acquisition, synthetic data, ingestion, deterministic reconciliation, retrieval, orchestration, complete auditing, human review, reproducible experiments and publication artifacts. It does not replace the component contracts.

> **MANDATORY BEFORE STARTING WORK:** Follow the [dependency control rules](#41-mandatory-project-control-the-dependency-graph-governs-execution), [task register](#46-canonical-task-register--owners-predecessors-and-current-state) and [checkpoint register](#47-checkpoint-approval-register-and-meeting-contract). The dependency graph controls which task may start and which output may enter integration. Do not begin a blocked or unregistered task merely because its calendar day has arrived.

**Confirmed constraint:** LLM gateway implementation, model/provider selection, hosting and pricing are **UNPLANNED**, at the team's request. A local model, free API or other provider may eventually fill that boundary. No provider SDK, model name, paid budget or gateway delivery date is assumed here. Only the existing C10 interface, dependency injection and a clearly labelled test double are included in scheduled work. This lets the other components proceed, but a real model-backed agent and its experiments remain conditional on that separate work becoming available. A scripted test double is never evidence of LLM reasoning or measured agent performance.

## 1. Starting point and specification authority

The repository already contains the charter, course guidelines, domain research, implementation overview, CPCB data/RAG inventory, version 1.1 system design and contracts, and Review 2 materials. At the start of this plan it has **no application package, dependency manifest, acquired dataset, generator or automated test suite**. Existing diagrams describe intended behavior rather than implemented components.

Read these in order; each member should understand their own interfaces and the complete case lifecycle:

| Input                                                                                                         | How to use it during implementation                                                                                                                                 |
| ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Project guidelines](PROJECT_GUIDELINES.md)                                                                    | Review dates, mandatory agentic concepts, reproducibility, academic integrity and final deliverables.                                                               |
| [Project charter](PROJECT_CHARTER.tex)                                                                         | Decision supported, scope and team commitment.                                                                                                                      |
| [System design](docs/design/SYSTEM_DESIGN.md)                                                                  | Architecture, storage, algorithms and G01–G12 acceptance gates.                                                                                                    |
| [Contracts](docs/design/CONTRACTS.md)                                                                          | Authoritative boundary models, control flow, permissions and failure behavior. Protocol version 1.1; individual payload schema versions remain separately declared. |
| [Domain research](docs/research/DOMAIN_RESEARCH.md)                                                            | Officer tasks T01–T16, source hierarchy, evidence trails and source aliases.                                                                                       |
| [Implementation overview](docs/research/AGENTIC_IMPLEMENTATION_OVERVIEW.md)                                    | Synthetic-data methodology, experiment baselines, publication cautions and precedents.                                                                              |
| [CPCB data and RAG research](<docs/research/CPCB%20EPR%20Data%20and%20RAG.md>)                                 | Acquisition leads and field inventory, subject to the corrections recorded in the design/contracts.                                                                 |
| [Review 2 design source](docs/design/REVIEW_2_DESIGN.tex) and [presentation notes](docs/presentation/README.md) | Communicate the architecture already proposed; update subsequent presentations to show actual implementation status.                                                |

Resolve a disagreement by checking CONTRACTS for interfaces and SYSTEM_DESIGN for architectural policy. Do not silently implement tentative values from the research inventory that the design explicitly qualified. Record any necessary change with affected producers, consumers, schemas, fixtures and documentation in the same review.

## 2. Delivery dates, capacity and completion criteria

### 2.1 Calendar

| Date           | Milestone and evidence required                                                                                                                                                                 |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 23 October     | Freeze initial shared interfaces, assign files, create fixtures and begin all four streams.                                                                                                     |
| 24 October     | Review 2: use existing design/slides; all members attend. Keep implementation scope light around the review.                                                                                    |
| 25 October     | First real end-to-end path: import a visible dossier, calculate a supported balance and render a traceable working paper.                                                                       |
| 27 October     | Adaptive graph integration against the C10 test boundary; ingestion/retrieval/calculation/report contracts connected.                                                                           |
| 29 October     | Week 1 acceptance: working offline application, benchmark pilot, human review, audit/export/replay and documented gaps. Real model demonstration is conditional on C10 availability.            |
| 30 October     | Prototype rehearsal, development-only improvements and experiment readiness checks.                                                                                                             |
| 31 October     | Review 3: demonstrate the working prototype, trace and feedback loop. An agentic demonstration requires a real gateway; disclose if it remains unavailable.                                     |
| 1–5 November  | Freeze candidate/configurations, run held-out experiments, adjudicate and write results.                                                                                                        |
| 6 November     | Freeze results/report/demo; rehearse and retain a recovery copy.                                                                                                                                |
| 7 November     | Review 4: final system, experiment, evaluation, report and demo.                                                                                                                                |
| 8–12 November | Address presentation/reproducibility issues and submit final report PDF, slides PDF and code/run instructions by 12 November. New scientific results require a separately versioned experiment. |

Four hours × four members × seven days gives **112 person-hours in Week 1**. Reserve about 30 minutes per person daily for coordination and integration: approximately **98 implementation hours** remain. These are planning limits, not an assertion that every specification detail can be production hardened in seven days. Record actual effort and move optional features out before weakening core invariants.

Use the following rough effort envelopes to control scope. Tests and integration belong inside each allocation; the final buffer is for demonstrated failures, not extra features. These are estimates to revisit at CP1, not measured implementation times.

| Member    | Focused-hour allocation, total 24.5 hours each                                                                                           |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Abhishek  | Package/contracts/config/CI 6; CLI/snapshots 5; graph/control 8; integration/documentation 3.5; buffer 2.                                |
| Sampreeth | Acquisition/relevant-source review 5; intake/extraction 6; index/temporal retrieval 8; validation/documentation 3.5; buffer 2.           |
| Sushanth  | Normalization/equivalence 6; deterministic tools 8; generator/renderers/fault recipes 6; validation/documentation 2.5; buffer 2.         |
| Vedantha  | Blob/catalog/audit 7; report/review 5; export/replay 4; evaluator/isolation/reference checks 4; integration/documentation 2.5; buffer 2. |

The source-review estimate covers the provisions actually used by v1, not a comprehensive legal review of ten documents. The evaluation scaffold in Week 1 records/validates runs; full scoring analysis and research writing occupy Week 2. If CP1 shows these envelopes are unrealistic, prioritize the baseline vertical slice, receipts/provenance and exact arithmetic, then complete remaining mandatory gates with explicit revised dates. Do not disguise an unfinished gate as a finished working system.

### 2.2 Week 1 product boundary

Build one local Python application with a Typer CLI, logical modules, SQLite/FTS5, exact Decimal arithmetic, Pydantic boundaries and a bounded LangGraph workflow. Use `uv` and a committed lockfile. Start with structured JSONL/CSV and text PDFs; explicitly quarantine unsupported scans/tables instead of claiming successful extraction. Keep the CLI and deterministic JSON/Markdown reports sufficient for review; a web UI is optional later.

The supported profile is `producer_snapshot_v1`: one fictional producer **per dossier**, FY 2024–25, supplied metal-wise obligations, separate historical liabilities and up to two specifically reviewed EEE codes. Across the benchmark, use multiple fictional producers/templates to test generalization. ITEW4 and CEEW1 are candidate codes from the research, not approved configuration until reviewed. Maintain separate Au/Cu/Al/Fe buckets where supplied; gold receives no special offset calculation.

Do not add sales-derived statutory targets, refurbishing deferrals, solar calculations, EC amounts, tax/pricing checks, live CPCB actions, OTPs, credit trading or autonomous compliance certification. Preserve related observations and return an explicit unsupported-feature disposition. Purchase-ceiling policy remains `DISABLED_REVIEW_REQUIRED`; separate deadline types and allocation-time earlier-liability checks are mandatory.

### 2.3 Two explicit acceptance levels

**A — Working application, scheduled for 29 October:** acquisition/import, immutable evidence, coverage, reviewed profile/snapshots, deterministic tools, lexical retrieval, bounded workflow exercised by a test adapter, verified reports, authenticated local review, full/public export, replay and isolated evaluator smoke tests. All G01–G12 gates must have executable evidence or an explicit blocking failure. A known gate failure prevents an unqualified “complete” claim.

**B — Working agentic system, conditional on unplanned C10:** all of A plus an actual model-backed run that selects a follow-up check, observes a weak/contradictory result, revises its plan and produces a verified, qualified report within budget. Run the fixed-retrieval and adaptive-agent experiments only at this level. Until then, publish software/generator/deterministic results with their correct scope; leave agent results marked **NOT RUN — MODEL GATEWAY UNAVAILABLE**.

## 3. Ownership and independent work boundaries

| Member                                          | Primary workstream and component ownership                                                                                                                                                       | First concrete deliverable                                                                      | Cross-review responsibility                                                                                                                       |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| **R V Abhishek — 1BM23CD047, lead**      | Integration; C00 CLI; C09 graph; C05 snapshot/profile persistence and approval control; common schemas/configuration; C10 interface/test seam only. Actual C10 implementation remains unplanned. | Installable package, common context/result models, fixture pack and CLI skeleton.               | Review audit/recovery integration and baseline fairness; protect held-out answers from prompt/tool developers.                                    |
| **H Sampreeth Bhat — 1BM23CD020**        | C01 acquisition/intake; C03 extraction; C06 index; C07 retrieval/applicability. Authors reviewed-source/profile content consumed by C05.                                                         | Source-lead manifest, one acquired original, page/row coverage and a provision locator fixture. | Review domain assumptions, citations and temporal-rule cases; label internal review honestly.                                                     |
| **Sushanth S — 1BM23CD063**              | C04 normalization/equivalence; C08 domain tools; C15 world generator, renderers and fault injection.                                                                                             | Hand-inspectable fictional dossier and exact-arithmetic reference fixture.                      | Review graph tool arguments, deterministic recomputation and schema mappings. Cannot solely validate the oracle with production calculation code. |
| **Vedantha Vinay Vernekar — 1BM23CD069** | C02 blob/catalog; C11 audit/transaction kernel; C12 reports/verifier; C13 review service; C14 export/replay; C16 evaluator/oracle isolation.                                                     | Blob/audit interfaces, independent expected-answer fixtures and scoring skeleton.               | Review generator outputs and hidden/visible separation; own evaluator answers and failure accounting.                                             |

Vedantha's breadth is controlled by using one small storage/commit kernel, one deterministic renderer and a CLI-based review flow. Abhishek builds the CLI and review command handlers; Vedantha owns the underlying service. No dashboard, cloud tracing service or elaborate report styling is on the Week 1 critical path. Sushanth owns generator mechanics; Vedantha owns independent scoring/oracle validation. Sampreeth owns extraction for both normative and dossier documents, avoiding two competing ingestion implementations.

Each owner may build against **contract-valid fixtures and in-memory adapters** until dependencies merge. Fake adapters must use the same models, fail explicitly and be disabled in real/evaluation configurations. Never spend a day waiting for an upstream service: implement your producer, consumer validation and contract test against the fixture pack.

### 3.1 Proposed code and artifact boundaries

These paths are to be created; they do not exist yet. Keep application modules small and logical rather than creating separate services for C00–C16.

```text
pyproject.toml / uv.lock                 # Abhishek: package, CLI entry point, shared dependencies
src/recycleguard/
  contracts/                            # Abhishek: reviewed Pydantic boundary models/enums
  config.py / cli.py                    # Abhishek: roots, capabilities, commands
  snapshots.py                          # Abhishek: C05, content supplied by Sampreeth
  workflow/                             # Abhishek: C09, state and budget handling
  model_port.py                         # Abhishek: existing C10 callable boundary only
  intake/ / extraction/                 # Sampreeth: C01/C03
  knowledge/                            # Sampreeth: C06/C07, provision/applicability processing
  normalization/ / domain/              # Sushanth: C04/C08
  storage/ / audit/                     # Vedantha: C02/C11
  reporting/ / review/ / exports/        # Vedantha: C12/C13/C14
schemas/v1/                             # Generated from approved models; protocol still 1.1
configs/                                # Reviewed source/profile/policy configurations
tests/unit/ / tests/contracts/           # Test author follows module ownership
tests/integration/ / tests/acceptance/   # Lead integrates; each owner contributes gate tests
tests/fixtures/visible/                  # Small original, non-answer-bearing integration inputs
tests/fixtures/expected/                 # Developer-only assertions; excluded from runtime image
benchmarks/generator/                    # Sushanth: C15, evaluator-only package
benchmarks/evaluation/                   # Vedantha: C16/reference oracle; never in runtime image
benchmarks/specs/                        # Reviewed generator/scorer protocols, no active test labels
scripts/                                # Small repeatable build/demo/evaluation entry points
docs/decisions/                          # Scope decisions, review records, experiment freezes
```

Use an application build context that includes only runtime code/configuration and permitted visible assets. A container that copies the entire repository would expose expected fixtures and benchmark code even if the oracle directory is mounted elsewhere.

### 3.2 Shared-file and Git rules

Abhishek owns `pyproject.toml`, `uv.lock`, common schemas, CLI/configuration and integration wiring. Vedantha owns SQL migrations and the shared write coordinator; other members submit required tables/constraints through that owner. Sampreeth owns source manifests; Sushanth owns visible generator schemas/templates. Avoid concurrent edits to the same shared file.

Use checkpoint integration branches: `checkpoint-0`, `checkpoint-1`, and the corresponding `checkpoint-N` for subsequent checkpoints. Git branch names cannot contain spaces. `checkpoint-0` gathers A01 and the H01/S01/V01 handoffs; A02 reconciles their interfaces and fixtures before CP0 approval. Target teammate/workstream PRs at the active checkpoint branch, not `main`. Keep short-lived workstream branches under `codex/`, based on the active checkpoint branch.

Create `checkpoint-1` from the accepted `checkpoint-0` candidate so it includes the frozen CP0 interfaces. Merge the accepted CP1 candidate to `main` through a reviewed PR only after CP1 is APPROVED; do not merge CP0 directly to `main`. For later checkpoints, create the next `checkpoint-N` from the latest accepted predecessor, integrate reviewed task PRs there, and merge to `main` only after that checkpoint is approved. A branch push, passing CI or merged task PR does not waive task dependencies, independent reviews or four-person checkpoint acknowledgement.

No force-push or direct-main implementation commits. A schema change requires a producer/consumer check, not just a new JSON field. Update the handoff fixture, model, generated schema, tests and relevant design/contract text together.

## 4. Daily working rhythm and integration checkpoints

Use these proposed IST checkpoints, adjusting the clock times around Review 2/3 while preserving the cadence:

| Checkpoint                  | Time budget | Required output                                                                         |
| --------------------------- | ----------- | --------------------------------------------------------------------------------------- |
| Start, proposed 09:00       | 5 minutes   | Each member states today's deliverable and contract blocker.                            |
| Mid-session, proposed 11:00 | 10 minutes  | Run affected producer/consumer tests; merge ready handoffs and surface schema drift.    |
| End, proposed 13:00         | 15 minutes  | Clean-environment smoke, one evidence/trace inspection, coherent commits and next task. |

The remaining 3.5 hours are focused implementation and verification. Review attendance uses additional calendar time or reduces that day's implementation capacity; do not hide the reduction. On 24 October, shift the mid-session checkpoint away from the announced 11:15 review start.

For every handoff provide: exact input fixture/version, output fixture/version, one successful result, one typed error/partial result, relevant test command, and known limitations. Status updates are **DONE / BLOCKERS / NEXT**, with a run/test/artifact reference. A demo screenshot alone does not satisfy a handoff.

The integration critical path is shared models → storage/audit → imported observations → frozen case/profile → deterministic calculation → verified report → review/export/replay. Retrieval joins after the reviewed corpus/index, and C09 can be assembled against fixtures within its authorized graph task. Budget, recovery and isolation checks must pass before scientific evaluation. If a shared boundary blocks someone for more than one checkpoint, the lead resolves the smallest viable fixture/contract decision. Fixture work may continue only within a READY/active task; it does not waive an unmet integration dependency.

| Gate                            | Deadline                  | Integration evidence                                                                                                                       |
| ------------------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| CP0 — Interfaces               | Day 1 end                 | Core models/enums and fixture pack validate; four streams run without live upstream dependencies.                                          |
| CP1 — Evidence foundation      | Day 2 end                 | Import preserves raw bytes, receipts and row/page dispositions; first immutable snapshots/profile review path.                             |
| CP2 — Baseline vertical slice  | Day 3 end                 | Worked 100/55/45 fixture runs from original bytes to verified working paper and audit references.                                          |
| CP3 — Investigation            | Day 5 end                 | Retrieval, deterministic tools and graph integrate; visible plan revision demonstrated with test adapter, and real model only if supplied. |
| CP4 — Prototype                | Day 7 end                 | G01–G12 evidence, frozen pilot, trusted review/export/replay, cold-start demo and documented C10 dependency.                              |
| CP5 — Experiment freeze        | Before first held-out run | Candidate/config/scorer/benchmark versions signed off; isolation passed; no test-answer-driven tuning.                                     |
| CP6 — Scientific results close | 3–4 November             | All registered trials/scoring closed, adjudicated and reproducible; exact claims fixed.                                                    |
| CP7 — Final review freeze      | 6 November                | Report/slides/demo/public package and clean reproduction accepted by the team.                                                             |
| CP8 — Final submission check   | By 12 November            | Final artifact inventory, source rights, regeneration and archive verified.                                                                |

The detailed registers below are the authoritative execution state. The checkpoint summary and date-based schedule are navigational views, not substitutes for prerequisite acceptance.

### 4.1 Mandatory project control: the dependency graph governs execution

**THIS IS THE PROJECT'S PRIMARY EXECUTION CONTROL. Before starting work, every member must read their task state and predecessor list below. Calendar dates are targets; they are not permission to bypass an unfinished dependency. A task/checkpoint is complete only after its evidence is reviewed and its state is updated.**

The canonical dependency/task register is §4.6; the graphs in §§4.3–4.5 visualize those exact edges. The checkpoint register in §4.7 controls integration. If a diagram and register disagree, stop the affected task and reconcile both before proceeding. CONTRACTS still governs software interfaces; this register governs team execution. It does not grant regulatory authority or override component permissions.

The day-by-day tables in §§5/12 explain work; they do not authorize extra tasks outside this register. Task IDs **A** belong to Abhishek, **H** to Sampreeth, **S** to Sushanth and **V** to Vedantha. **U01** is the explicitly unplanned real gateway dependency, not an assigned work item. Every scheduled implementation, validation, experiment and release activity must map to an ID below; split an oversized task into reviewed child IDs before adding unrelated work.

**Initial project state, 23 October:** no implementation task is started or complete, and no checkpoint is approved. A01, H01, S01 and V01 are READY to begin independently; all tasks with unmet predecessors are BLOCKED. U01 is UNPLANNED. READY means eligible to start, not already implemented or tested.

### 4.2 Start/stop rules and evidence-based state transitions

1. **Choose from READY only.** Each member keeps one primary IN_PROGRESS task. A task becomes READY only when every required predecessor task is DONE and every predecessor checkpoint is APPROVED. Review/help on another member's explicitly identified task is allowed; creating an unregistered module or feature is not.
2. **Use fixtures only within the authorized task.** Independent root tasks and fixture-based work are explicitly present in the graph. A stub lets an authorized task progress; it does not satisfy a downstream real integration or acceptance dependency.
3. **Keep a visible state.** Task states are BLOCKED → READY → IN_PROGRESS → IN_REVIEW → DONE. A failed review returns to IN_PROGRESS or BLOCKED with a reason. UNPLANNED means no assignment/commitment. REVALIDATE marks a previously accepted output whose assumptions changed. NOT_RUN is permitted for an explicitly excluded conditional experiment, never a substitute for a mandatory task.
4. **Attach evidence before DONE.** Record the code/config commit, exact fixture/snapshot/schema versions, test command and result artifact, output/digest, unresolved limitations and independent reviewer. A PR being merged, a successful screenshot or a verbal update alone is insufficient.
5. **Respect checkpoint barriers.** The lead updates a gate to APPROVED only when its required inputs pass and all four members acknowledge the boundary/version handoff. A gate records actual approval date, candidate/version refs and test evidence. Absence of a reviewer means WAITING, not assumed approval.
6. **Block only the dependent path.** A failed task/gate holds its reachable consumers. Members may continue other READY tasks; they may not jump to a blocked descendant. Escalate a missing boundary at the next checkpoint and choose an already-authorized independent task meanwhile.
7. **Control changes.** New tasks or changed dependencies require owner, independent reviewer, effort/schedule effect, input/output contract, acceptance evidence and next checkpoint. The lead and affected producer/consumer owners update register and graph together before work starts. Optional UI/OCR/dense/multi-agent work stays out until expressly added.
8. **Invalidate downstream acceptance when inputs change.** A schema/profile/corpus/tool/dataset change creates a new version. Mark affected accepted consumers REVALIDATE and relevant gates REOPENED; retain historical evidence. Frozen experiments need the versioned correction/rerun procedure in §13, never a silent replacement.
9. **Keep commits tied to scope.** PRs/implementation commits reference their task IDs. At each daily sync, reconcile open branches against this register, remove stray work from the integration candidate, and identify the next permitted handoff. Do not reset/discard useful branches; park unapproved work outside the candidate.
10. **Do not fabricate enforcement.** This document is the team's manual execution control until automation exists. A01's CI checks support it; no implemented scheduler or automatic permission gate is being claimed.

Maintain the state/evidence cells in this tracked document at each sync, with concise references to detailed run/PR artifacts. Updates go through the integration branch so all four use the same state. If updates are temporarily concurrent, the lead reconciles them before another task is promoted. Never mark a dependency DONE merely to unblock a schedule.

### 4.3 Dependency graph A — independent starts and evidence foundation

Solid arrows mean **must be accepted first**. Dark diamond nodes are mandatory shared checkpoints. Repeated IDs in later diagrams are the same task/gate, not duplicate work. Task colors identify owners; read the register for exact scope/evidence.

```mermaid
flowchart TD
    A01["A01 · Package, CI and interface scaffold"]
    H01["H01 · Source leads and locator fixtures"]
    S01["S01 · Starter world and visible dossier"]
    V01["V01 · Independent oracle and audit fixtures"]
    A02["A02 · Freeze shared models and fixtures"]
    CP0{"CP0 · Interfaces"}
    V02["V02 · Immutable storage and audit kernel"]
    H02["H02 · Acquisition and full-batch intake"]
    S02["S02 · Normalization and event equivalence"]
    A03["A03 · Snapshot and profile service"]
    H03["H03 · Extraction and coverage"]
    H04["H04 · Initial source and profile review"]
    A04["A04 · Integrated evidence snapshots"]
    CP1{"CP1 · Evidence foundation"}
    A01 --> A02
    H01 --> A02
    S01 --> A02
    V01 --> A02
    A02 --> CP0
    CP0 --> V02
    CP0 --> H02
    V02 --> H02
    H01 --> H02
    CP0 --> S02
    CP0 --> A03
    V02 --> A03
    H02 --> H03
    H03 --> H04
    A03 --> A04
    H03 --> A04
    H04 --> A04
    S02 --> A04
    A04 --> CP1
    classDef ownerA fill:#e6efff,stroke:#28559a,color:#172c49
    classDef ownerH fill:#e3f3ec,stroke:#287254,color:#183d2b
    classDef ownerS fill:#fff2d5,stroke:#9a6a16,color:#523907
    classDef ownerV fill:#f0e8fa,stroke:#755098,color:#3c2851
    classDef checkpoint fill:#173d35,stroke:#0a221b,color:#ffffff,stroke-width:3px
    classDef unscheduled fill:#f0f0f0,stroke:#767676,color:#444444,stroke-dasharray:5 5
    class A01,A02,A03,A04 ownerA
    class H01,H02,H03,H04 ownerH
    class S01,S02 ownerS
    class V01,V02 ownerV
    class CP0,CP1 checkpoint
```

A02 integrates the four independent Day 1 outputs. Production acquisition/catalog writes begin through H02/V02 after CP0; H01's source inspection and fixtures are preparation, not a bypass around audited intake. CP1 is the first point at which imported, normalized, reviewed evidence can drive downstream calculation.

### 4.4 Dependency graph B — baseline, investigation, data and prototype acceptance

```mermaid
flowchart TD
    CP0{"CP0 · Interfaces"}
    CP1{"CP1 · Evidence foundation"}
    V01["V01 · Independent oracle and audit fixtures"]
    H04["H04 · Initial source and profile review"]
    S03["S03 · Exact baseline reconciliation"]
    S05["S05 · Clean renderer and six cases"]
    H05["H05 · Frozen lexical index"]
    V03["V03 · Baseline report and verifier"]
    A05["A05 · Deterministic vertical slice"]
    CP2{"CP2 · Baseline vertical slice"}
    V04["V04 · Independent oracle/scorer scaffold"]
    H06["H06 · Retrieval and evidence grading"]
    S04["S04 · Complete domain checks"]
    A06["A06 · Bounded graph and budgets"]
    V05["V05 · Trusted review and output guards"]
    H07["H07 · Temporal and deadline checks"]
    S06["S06 · All sixteen fault recipes"]
    A07["A07 · Integrated investigation"]
    CP3{"CP3 · Investigation"}
    V06["V06 · Export, integrity and replay"]
    V07["V07 · Enforced runtime isolation"]
    H08["H08 · Final corpus and retrieval audit"]
    S07["S07 · Generate grouped 48-case pilot"]
    V08["V08 · Recovery and failure-window tests"]
    V09["V09 · Validate and seal full oracle"]
    A08["A08 · Cold start and G01-G12 acceptance"]
    CP4{"CP4 · Prototype acceptance"}
    CP1 --> S03
    CP0 --> S05
    CP1 --> H05
    CP1 --> V03
    S03 --> V03
    CP1 --> A05
    S03 --> A05
    V03 --> A05
    A05 --> CP2
    S05 --> V04
    V01 --> V04
    H05 --> H06
    S03 --> S04
    CP2 --> A06
    CP2 --> V05
    H06 --> H07
    H04 --> H07
    S05 --> S06
    S04 --> S06
    H04 --> S06
    A06 --> A07
    H06 --> A07
    S04 --> A07
    V05 --> A07
    A07 --> CP3
    H07 --> CP3
    S06 --> CP3
    V05 --> V06
    CP2 --> V07
    H07 --> H08
    CP3 --> H08
    S06 --> S07
    V04 --> S07
    CP3 --> V08
    V06 --> V08
    V07 --> V08
    S07 --> V09
    V04 --> V09
    H08 --> V09
    CP3 --> A08
    V08 --> A08
    V09 --> A08
    H08 --> A08
    A08 --> CP4
    classDef ownerA fill:#e6efff,stroke:#28559a,color:#172c49
    classDef ownerH fill:#e3f3ec,stroke:#287254,color:#183d2b
    classDef ownerS fill:#fff2d5,stroke:#9a6a16,color:#523907
    classDef ownerV fill:#f0e8fa,stroke:#755098,color:#3c2851
    classDef checkpoint fill:#173d35,stroke:#0a221b,color:#ffffff,stroke-width:3px
    classDef unscheduled fill:#f0f0f0,stroke:#767676,color:#444444,stroke-dasharray:5 5
    class A05,A06,A07,A08 ownerA
    class H04,H05,H06,H07,H08 ownerH
    class S03,S05,S04,S06,S07 ownerS
    class V01,V03,V04,V05,V06,V07,V08,V09 ownerV
    class CP0,CP1,CP2,CP3,CP4 checkpoint
```

S05/V04 and H05/H06 can advance independently while baseline/report work integrates. CP2 releases bounded graph/review work against the real baseline. CP3 requires investigation, temporal checks and all fault recipes; it does not require a real model. V06/V07 prepare replay/isolation in parallel. CP4 cannot pass until recovery, oracle validation and a cold-start G01–G12 acceptance record converge at A08.

### 4.5 Dependency graph C — tuning, controlled experiments and final release

Dashed arrows are **conditional prerequisites**, activated only when the frozen CP5 protocol includes real-model V1/V2 trials. For that scope, V12 must close before H10, S09 and V13 can be accepted. They must not score a partial favorable subset. For a registered non-model-only study, V12 stays NOT_RUN and the results explicitly exclude agent claims.

```mermaid
flowchart TD
    CP4{"CP4 · Prototype acceptance"}
    A07["A07 · Integrated investigation"]
    V07["V07 · Enforced runtime isolation"]
    A09["A09 · Dev graph tuning and code freeze"]
    H09["H09 · Dev retrieval tuning and freeze"]
    S08["S08 · Dev tool fixes and input freeze"]
    V10["V10 · Evaluator rehearsal and protocol"]
    U01["U01 · Actual C10 gateway: UNPLANNED"]
    MG1{"MG1 · Real-model readiness"}
    CP5{"CP5 · Experiment freeze"}
    V11["V11 · Closed deterministic test trials"]
    V12["V12 · Conditional real-model trials"]
    H10["H10 · Blind citation and action scoring"]
    S09["S09 · Independent balance and finding scoring"]
    V13["V13 · Adjudicated results and uncertainty"]
    CP6{"CP6 · Scientific results close"}
    S07["S07 · Generate grouped 48-case pilot"]
    S10["S10 · Dataset and generator release card"]
    H11["H11 · Source rights and reference audit"]
    A10["A10 · Report and slides integration"]
    V14["V14 · Public package and reproduction"]
    A11["A11 · Final build and team rehearsal"]
    CP7{"CP7 · Final review freeze"}
    A12["A12 · Submission artifacts and packaging"]
    H12["H12 · Final rights and attribution audit"]
    S11["S11 · Release regeneration and baseline"]
    V15["V15 · Final integrity and submission set"]
    CP8{"CP8 · Submission checks"}
    CP4 --> A09
    CP4 --> H09
    CP4 --> S08
    CP4 --> V10
    U01 --> MG1
    A07 --> MG1
    V07 --> MG1
    V10 --> MG1
    A09 --> CP5
    H09 --> CP5
    S08 --> CP5
    V10 --> CP5
    CP5 --> V11
    CP5 --> V12
    MG1 --> V12
    V11 --> H10
    V11 --> S09
    V11 --> V13
    H10 --> V13
    S09 --> V13
    V13 --> CP6
    H10 --> CP6
    S09 --> CP6
    S08 --> S10
    S07 --> S10
    H09 --> H11
    H10 --> H11
    CP6 --> A10
    V13 --> V14
    H11 --> V14
    S10 --> V14
    A10 --> V14
    A10 --> A11
    V14 --> A11
    A11 --> CP7
    V14 --> CP7
    H11 --> CP7
    S10 --> CP7
    CP7 --> A12
    CP7 --> H12
    CP7 --> S11
    A12 --> V15
    H12 --> V15
    S11 --> V15
    V15 --> CP8
    V12 -. "only when V1/V2 registered" .-> H10
    V12 -. "only when V1/V2 registered" .-> S09
    V12 -. "only when V1/V2 registered" .-> V13
    MG1 -. "only when V1/V2 registered" .-> CP5
    classDef ownerA fill:#e6efff,stroke:#28559a,color:#172c49
    classDef ownerH fill:#e3f3ec,stroke:#287254,color:#183d2b
    classDef ownerS fill:#fff2d5,stroke:#9a6a16,color:#523907
    classDef ownerV fill:#f0e8fa,stroke:#755098,color:#3c2851
    classDef checkpoint fill:#173d35,stroke:#0a221b,color:#ffffff,stroke-width:3px
    classDef unscheduled fill:#f0f0f0,stroke:#767676,color:#444444,stroke-dasharray:5 5
    class A07,A09,A10,A11,A12 ownerA
    class H09,H10,H11,H12 ownerH
    class S08,S09,S07,S10,S11 ownerS
    class V07,V10,V11,V12,V13,V14,V15 ownerV
    class CP4,MG1,CP5,CP6,CP7,CP8 checkpoint
    class U01 unscheduled
```

MG1 does not schedule U01. It records the separate real-gateway compatibility/permissions/budget/isolation evidence if that work becomes available. **CP5 approval must name its scope: NON_MODEL_ONLY or INCLUDES_REAL_MODEL.** INCLUDES_REAL_MODEL also requires MG1 APPROVED and exact model settings frozen at CP5. MG1 becoming available after an offline freeze does not automatically expand it: create a new CP5 experiment version before V12. If U01 remains unplanned, the non-model path continues through CP6–CP8 with the limitation prominently reported.

### 4.6 Canonical task register — owners, predecessors and current state

All references are exact task/checkpoint IDs. Required predecessors are an AND condition. A conditional V12 predecessor is also an AND condition whenever CP5 includes real-model trials; otherwise record its exclusion explicitly. Target dates below follow the original four-hour schedule and are not evidence of completion.

**Abhishek — contracts, integration, CLI, snapshots and graph**

| Task          | State now | Required predecessors | Conditional predecessor | Target        | Work and acceptance evidence                                                                                                                                  |
| ------------- | --------- | --------------------- | ----------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A01** | DONE | None                  | None                    | 23 Oct        | **Package, uv lock, CI/config/CLI skeleton and C10 test seam.** Installable scaffold; schema/test-port proposal; no real gateway. [A01 evidence](docs/decisions/A01_HANDOFF.md); review accepted via lead-reported all-four acknowledgement.                       |
| **A02** | DONE | A01, H01, S01, V01    | None                    | 23 Oct        | **Freeze shared models, service fixtures and module boundaries.** Four-way producer/consumer validation; schema version and review refs. [CP0 integration evidence](docs/checkpoints/checkpoint-0/README.md); accepted 24 Oct; lead-reported all-four acknowledgement of c8fb512. |
| **A03** | IN_PROGRESS | CP0, V02              | None                    | 24 Oct        | **Implement snapshot/profile persistence, review and version controls.** Immutable membership/profile revisions and trusted approval checks. [A03 snapshot slice](docs/checkpoints/checkpoint-1/a03.md); profile work remains. |
| **A04** | BLOCKED   | A03, H03, H04, S02    | None                    | 24 Oct        | **Integrate intake, normalization and first case/corpus snapshots.** Imported case and reviewed profile with complete coverage refs.                    |
| **A05** | BLOCKED   | CP1, S03, V03         | None                    | 25 Oct        | **Connect deterministic CLI vertical slice and baseline audit view.** Fresh-root original-bytes-to-working-paper transcript.                            |
| **A06** | BLOCKED   | CP2                   | None                    | 26 Oct        | **Implement bounded graph, checkpointed state and budget controls.** Plan/action/assessment loop; scripted-port state/budget tests.                     |
| **A07** | BLOCKED   | A06, H06, S04, V05    | None                    | 27 Oct        | **Integrate graph with real retrieval/domain/report services.** Audited adaptive trace; retry/cancel/all-status integration tests.                      |
| **A08** | BLOCKED   | CP3, V08, V09, H08    | None                    | 29 Oct        | **Run Week 1 acceptance, cold start and reproducible prototype handoff.** G01–G12 evidence; clean-start demo; explicit A/B completion level.           |
| **A09** | BLOCKED   | CP4                   | None                    | 30 Oct–1 Nov | **Tune graph/CLI on development data and freeze candidate code.** Dev changes with regression tests; pinned graph/prompt/budget configs.                |
| **A10** | BLOCKED   | CP6                   | None                    | 4–5 Nov      | **Integrate research report, architecture/results narrative and slides.** 8–12-page report draft and slides describe actual measured behavior.         |
| **A11** | BLOCKED   | A10, V14              | None                    | 6 Nov         | **Freeze final review build and run four-person rehearsal.** Demo recovery copy; viva ownership; approved artifact versions.                            |
| **A12** | BLOCKED   | CP7                   | None                    | 8–12 Nov     | **Resolve submission packaging issues and assemble final report/slides/code.** Final artifact inventory; no unregistered scientific result replacement. |

**Sampreeth — acquisition, extraction, corpus, retrieval and source review**

| Task          | State now | Required predecessors | Conditional predecessor | Target        | Work and acceptance evidence                                                                                                                              |
| ------------- | --------- | --------------------- | ----------------------- | ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **H01** | DONE | None                  | None                    | 23 Oct        | **Curate source leads, aliases and initial source/locator fixtures.** Reviewed lead inventory; accessible-original fixture and metadata. [CP0 integration evidence](docs/checkpoints/checkpoint-0/README.md); accepted 24 Oct; lead-reported all-four acknowledgement of c8fb512. |
| **H02** | READY | CP0, V02, H01         | None                    | 24 Oct        | **Implement auditable acquisition and every-file batch intake.** Exact bytes; fetch attempts; declared/missing/extra receipts.                      |
| **H03** | BLOCKED   | H02                   | None                    | 24 Oct        | **Implement CSV/JSON/text-PDF extraction and page/row coverage.** ExtractionResult; terminal dispositions; source/dossier adapter tests.            |
| **H04** | BLOCKED   | H03                   | None                    | 24 Oct        | **Review initial source applicability and v1 profile content.** Named internal review; exact provisions; initial approved content.                  |
| **H05** | BLOCKED   | CP1                   | None                    | 25 Oct        | **Build provision/table chunks and frozen lexical index.** FTS5 index manifest, membership digest and exact locators.                               |
| **H06** | BLOCKED   | H05                   | None                    | 26 Oct        | **Implement filtered retrieval, locator resolution and evidence grades.** Full candidate dispositions; five grades; bounded context expansion.      |
| **H07** | BLOCKED   | H06, H04              | None                    | 27 Oct        | **Complete temporal overlays, deadline register and missing-order tests.** Amendment/role/time tests; separate deadline types; explicit abstention. |
| **H08** | BLOCKED   | H07, CP3              | None                    | 28 Oct        | **Audit final corpus/profile and development retrieval regressions.** Reviewed exact source/index/profile versions; limitations and rights.         |
| **H09** | BLOCKED   | CP4                   | None                    | 30 Oct–1 Nov | **Tune development retrieval and freeze corpus/index/policy.** Dev error analysis; frozen applicability and retrieval inputs.                       |
| **H10** | BLOCKED   | V11                   | V12                     | 3 Nov         | **Blind-score citation, temporal support and next-action quality.** Written rubric; overlap/double-scoring; retained judgments.                     |
| **H11** | BLOCKED   | H09, H10              | None                    | 4–5 Nov      | **Finalize source rights, attribution, references and limitations.** Asset-level release decisions and reproducibility restrictions.                |
| **H12** | BLOCKED   | CP7                   | None                    | 8–12 Nov     | **Audit final references, source rights and release attributions.** Final source/license check against actual distributed content.                  |

**Sushanth — normalization, deterministic tools and synthetic data**

| Task          | State now | Required predecessors | Conditional predecessor | Target        | Work and acceptance evidence                                                                                                                               |
| ------------- | --------- | --------------------- | ----------------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **S01** | DONE | None                  | None                    | 23 Oct        | **Define clean world and starter visible dossier fixtures.** Opaque visible files and 100/55/45 reference scenario. [CP0 integration evidence](docs/checkpoints/checkpoint-0/README.md); accepted 24 Oct; lead-reported all-four acknowledgement of c8fb512. |
| **S02** | READY | CP0                   | None                    | 24 Oct        | **Normalize observations, units, identity and F02/F03 relationships.** NormalizationBatch; raw lineage; supported/ambiguous equivalence tests.       |
| **S03** | BLOCKED   | CP1                   | None                    | 25 Oct        | **Implement exact baseline balances, allocations and comparisons.** 55 supported / 45 gap; conservation; unknown/pending tests.                      |
| **S05** | READY | CP0                   | None                    | 25 Oct        | **Implement clean-world renderer and first six visible cases.** Linked CSV/JSONL/text-PDF fixtures; hidden world kept separate.                      |
| **S04** | BLOCKED   | S03                   | None                    | 26 Oct        | **Complete lifecycle, priority, entity/capability/product/commercial tools.** Full-server-input checks; F08/F09; PASS/FAIL/UNKNOWN results.          |
| **S06** | BLOCKED   | S05, S04, H04         | None                    | 27 Oct        | **Implement all F01–F16 fault recipes and generation invariants.** Each recipe has a visible effect, clean reference and validation.                |
| **S07** | BLOCKED   | S06, V04              | None                    | 28 Oct        | **Generate grouped 24-dev/24-held-out pilot and validate manifests.** 48 opaque dossiers; split/leakage checks; versioned regeneration.              |
| **S08** | BLOCKED   | CP4                   | None                    | 30 Oct–1 Nov | **Fix development tool/generator defects and freeze deterministic inputs.** Regression-tested tools/templates/profile; preserved split and versions. |
| **S09** | BLOCKED   | V11                   | V12                     | 3 Nov         | **Independently score exact balances and finding matches.** Bucket/finding counts and classified tool/parser/oracle errors.                          |
| **S10** | BLOCKED   | S08, S07              | None                    | 4–5 Nov      | **Finalize dataset/generator method, card and release manifest.** Synthetic limits, split/recipe documentation and permitted regeneration.           |
| **S11** | BLOCKED   | CP7                   | None                    | 8–12 Nov     | **Reproduce released generator, visible pilot and deterministic examples.** Independent regeneration/baseline verification transcript.               |

**Vedantha — storage/audit, reports/review, export, isolation and evaluation**

| Task          | State now | Required predecessors | Conditional predecessor | Target              | Work and acceptance evidence                                                                                                                                 |
| ------------- | --------- | --------------------- | ----------------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **V01** | DONE | None                  | None                    | 23 Oct              | **Independent reference answer and storage/audit interface fixtures.** Independent arithmetic; blob/commit prototype and typed fixtures. [CP0 integration evidence](docs/checkpoints/checkpoint-0/README.md); accepted 24 Oct; lead-reported all-four acknowledgement of c8fb512. |
| **V02** | DONE | CP0                   | None                    | 24 Oct              | **Implement immutable blobs, catalog and audited commit kernel.** Real SQLite/blob round-trip; intent/result; idempotency tests. [V02 repairs](docs/checkpoints/checkpoint-1/v02.md); verified 25 Oct. |
| **V03** | BLOCKED   | CP1, S03              | None                    | 25 Oct              | **Build structured baseline report and numeric/citation verifier.** Eight sections; deterministic numeric insertion; invalid-claim tests.              |
| **V04** | BLOCKED   | S05, V01              | None                    | 25–26 Oct          | **Implement independent oracle/scoring skeleton and validate first cases.** Visible-evidence versus world answers; independent checks.                 |
| **V05** | BLOCKED   | CP2                   | None                    | 26 Oct              | **Complete trusted review, report repair and forbidden-claim checks.** All decisions; stale packets; spoof rejection; qualified reports.               |
| **V06** | BLOCKED   | V05                   | None                    | 27 Oct              | **Implement local/public export, integrity and offline replay.** Verified bundles; rights-through-derivatives tests; no-provider replay.               |
| **V07** | BLOCKED   | CP2                   | None                    | 27 Oct              | **Build minimal investigator runtime and enforce oracle isolation.** No hidden code/data mounts; attempted access denied and recorded.                 |
| **V08** | BLOCKED   | CP3, V06, V07         | None                    | 28 Oct              | **Verify crash recovery, budgets, checkpoint lag and export integrity.** Failure-window/recovery tests and consistent restore evidence.                |
| **V09** | BLOCKED   | S07, V04, H08         | None                    | 28–29 Oct          | **Independently validate full oracle and seal pilot/scorer versions.** Numeric/rubric validation; sealed digests; held-out access record.              |
| **V10** | BLOCKED   | CP4                   | None                    | 30 Oct–1 Nov       | **Rehearse evaluator and freeze protocol, scorer and resource feasibility.** Dev dry-run; rubric/denominators/repeats/invalid-trial policy.            |
| **V11** | BLOCKED   | CP5                   | None                    | 2–3 Nov            | **Execute sealed deterministic and non-model evaluation runs.** Closed trials; exact failure/usage/coverage records; no test tuning.                   |
| **V12** | BLOCKED   | CP5, MG1              | None                    | 2–3 Nov if enabled | **Execute fixed-retrieval and adaptive real-model trials.** Matched V1/V2 registered trials; never use scripted model outputs.                         |
| **V13** | BLOCKED   | V11, H10, S09         | V12                     | 3–4 Nov            | **Close scoring, adjudication, uncertainty and results ledger.** All scheduled attempts accounted for; reproducible paired summaries.                  |
| **V14** | BLOCKED   | V13, H11, S10, A10    | None                    | 5–6 Nov            | **Verify publication package, result recomputation and saved-artifact replay.** Clean reproduction record; filtered package and omissions.             |
| **V15** | BLOCKED   | A12, H12, S11         | None                    | By 12 Nov           | **Verify final manifests, archive evidence and validate submission set.** Hashes, run instructions, report/slides PDFs and complete permitted archive. |

**Explicitly unplanned dependency**

| Task          | State now | Required predecessors | Conditional predecessor | Target    | Work and acceptance evidence                                                                                                       |
| ------------- | --------- | --------------------- | ----------------------- | --------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **U01** | UNPLANNED | None                  | None                    | UNPLANNED | **Supply an actual contract-compatible C10 gateway.** External unscheduled prerequisite; no owner/provider/delivery assumed. |

V12 begins BLOCKED; if CP5 is approved NON_MODEL_ONLY, record V12 as NOT_RUN with that protocol reference. U01 remains UNPLANNED unless the team explicitly assigns and plans it later. Neither state is hidden by a successful scripted graph demonstration.

### 4.7 Checkpoint approval register and meeting contract

| Gate          | State now | Required accepted tasks                          | Target                      | Required shared decision                                           |
| ------------- | --------- | ------------------------------------------------ | --------------------------- | ------------------------------------------------------------------ |
| **CP0** | APPROVED | A02                                              | 23 Oct                      | Shared schema/fixture pack accepted by all four. Approved 24 Oct for c8fb512; [acknowledgement ledger](docs/checkpoints/checkpoint-0/approvals.json). |
| **CP1** | WAITING   | A04                                              | 24 Oct                      | Evidence foundation and first frozen reviewed snapshots.           |
| **CP2** | WAITING   | A05                                              | 25 Oct                      | Deterministic baseline vertical slice.                             |
| **CP3** | WAITING   | A07, H07, S06                                    | 27 Oct                      | Integrated investigation and fault/temporal checks.                |
| **CP4** | WAITING   | A08                                              | 29 Oct                      | Week 1 acceptance; declare offline versus real-agent level.        |
| **CP5** | WAITING   | A09, H09, S08, V10; MG1 when INCLUDES_REAL_MODEL | 1 Nov, before held-out runs | Frozen experiment scope, candidate, data and scorer.               |
| **MG1** | WAITING   | U01, A07, V07, V10                               | Conditional, before V1/V2   | Real C10 compatibility, permissions, budgets, trace and isolation. |
| **CP6** | WAITING   | V13, H10, S09                                    | 3–4 Nov                    | Closed, adjudicated scientific results.                            |
| **CP7** | WAITING   | A11, V14, H11, S10                               | 6 Nov                       | Final-review artifact freeze.                                      |
| **CP8** | WAITING   | V15                                              | By 12 Nov                   | Final submission inventory and reproduction checks.                |

For CP5 INCLUDES_REAL_MODEL, add MG1 as a required gate in that experiment's recorded scope. For CP6 and its scoring tasks, require all registered V12 trials closed whenever the conditional path is active. CP7 freezes the Review 4 artifacts; CP8 verifies the final submission set, not a claim that an academic paper was accepted.

At each checkpoint, all four must answer:

- What exact versions are we accepting, and where are the test/output artifacts?
- Which downstream task IDs become READY, and which remain blocked?
- Did any schema, profile, source, permission or benchmark assumption change?
- What is each member's next single active task, and when is its next handoff?
- What remains unplanned, excluded or unsupported, especially C10 and model-based claims?

Append the approval reference and actual date to the gate row when approved. The lead records the decision; the output owner cannot serve as the sole acceptance reviewer. Initial reviewers follow §3 and the G01–G12 matrix. A checkpoint may accept a qualified output only if the contracts allow that qualification and every consumer handles it explicitly; it cannot waive a mandatory invariant.

### 4.8 Daily allowed queue and scope drift checks

| Work window                     | Abhishek queue                                                       | Sampreeth queue                  | Sushanth queue                   | Vedantha queue                   |
| ------------------------------- | -------------------------------------------------------------------- | -------------------------------- | -------------------------------- | -------------------------------- |
| Day 1                           | A01 → A02; coordinate CP0                                           | H01; review A02/CP0              | S01; review A02/CP0              | V01; review A02/CP0              |
| Day 2, after CP0                | A03 → A04                                                           | H02 → H03 → H04                | S02                              | V02; review CP1                  |
| Day 3, after CP1                | A05 after V03                                                        | H05                              | S03; S05 can start after CP0     | V03; V04 after S05               |
| Day 4, after CP2 where required | A06                                                                  | H06                              | S04; assist V04 review           | V05; V04                         |
| Day 5                           | A07; coordinate CP3                                                  | H07                              | S06                              | V06; V07                         |
| Day 6                           | Prepare A08 only when its prerequisites permit                       | H08 after CP3                    | S07                              | V08; V09 only after H08/S07      |
| Day 7                           | A08; coordinate CP4                                                  | Validate H08 and CP4 evidence    | Validate S07 and CP4 evidence    | Complete V09/V08; CP4 review     |
| 30 Oct–1 Nov                   | A09; CP5 sign-off                                                    | H09; CP5 sign-off                | S08; CP5 sign-off                | V10; CP5 and conditional MG1     |
| 2–3 Nov                        | Help registered trial execution under V11/V12; no test-driven tuning | H10 after required trial closure | S09 after required trial closure | V11; conditional V12; then V13   |
| 4–6 Nov                        | A10 after CP6 → A11 after V14                                       | H11                              | S10                              | V13 → V14; CP6/CP7 coordination |
| 8–12 Nov                       | A12                                                                  | H12                              | S11                              | V15 after A12/H12/S11; CP8       |

A queue entry can span multiple days; no member must start every listed task on the target day. If the predecessor is not accepted, continue an already-open authorized task, review a producer handoff, or repair an explicitly assigned failed test. Do not invent another feature to appear busy. The midpoint/end sync checks task IDs, dependency states and actual evidence before discussing new work.

## 5. Week 1: day-by-day execution

### Day 1 — Friday, 23 October: contracts, scaffolding and first fixtures

| Member    | Work within the four-hour budget                                                                                                                                                                                                                          | Deliverable at CP0                                                                                      |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Abhishek  | Create Python package/CLI, `uv.lock`, basic CI, roots/config and common boundary models. Extract exact enum/decimal/time semantics from CONTRACTS; provide in-memory service interfaces and a scripted C10 test port.                                   | Fresh `uv sync` works; fixture validation and initial contract tests pass.                            |
| Sampreeth | Execute H01: curate source aliases/URLs and inspect accessible R02/operational-guide originals for source/locator fixtures and rights metadata. Define acquisition/extraction output fixtures; production audited intake is H02 after CP0/V02.            | Reviewed lead manifest, source/locator examples and typed coverage fixtures.                            |
| Sushanth  | Author clean world schema and minimal visible dossier: supplied 100 kg obligation, one supported 55 kg allocation, overlapping observations, 25 kg paid/pending transaction and a comparison snapshot. Specify event-equivalence and arithmetic examples. | Original synthetic CSV/JSONL inputs plus typed records; no hidden answer labels in visible names.       |
| Vedantha  | Execute V01: prototype the low-level hash/blob and SQLite commit boundary, supply audit intent/result fixtures, independently calculate the starter answer and define oracle/metric shapes. Production audited storage is V02 after CP0.                  | Prototype blob round-trip, typed intent/result example and independent 55 supported / 45 gap assertion. |

By the first midpoint, freeze a small usable subset: CommandContext, ServiceResult, Issue, BlobRef/EvidenceRef, Quantity/TemporalValue, receipts/observations, snapshot/profile references, CalculationResult, FindingRecord and audit operation/event shapes. Add remaining records incrementally without incompatible placeholders. All consumers reject unsupported contract versions.

### Day 2 — Saturday, 24 October: intake, persistence and source review

| Member    | Work                                                                                                                                                                                                             | End-of-day handoff                                                                         |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Abhishek  | Wire C00 import/inspect and C05 snapshot publication to storage interfaces. Implement expected-version/profile approval capability checks and reproducible configuration loading. Attend Review 2 with the team. | Import command and snapshot/profile lifecycle usable by other streams.                     |
| Sampreeth | Implement batch inventory, every-file receipts and structured extraction, then text-PDF page coverage. Acquire priority corpus, review relevant clauses/tables, source dates and first code/profile parameters.  | C01/C03 real outputs; source failures recorded rather than silently skipped.               |
| Sushanth  | Normalize units/metal/entity/time without losing raw values. Preserve observations, separate events/lots/allocations, implement F02 supported-versus-ambiguous equivalence and F03 legitimate reuse.             | NormalizationBatch with provenance and explicit unresolved links.                          |
| Vedantha  | Complete blob-before-transaction sequence, foreign keys, append-only audit, idempotency conflicts and partial/failure output storage. Start deterministic eight-section report JSON/rendering.                   | Storage/commit service replacing the memory adapter; report fixture with calculation refs. |

CP1 must exercise a duplicate file, an undeclared file, a missing declared file and a corrupt document. Every one gets an inventory outcome. A failed download is an acquisition attempt, not an acquired artifact with invented bytes/hash.

### Day 3 — Sunday, 25 October: baseline end to end

| Member    | Work                                                                                                                                                                                                                               | End-of-day handoff                                                              |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| Abhishek  | Connect import → normalization → snapshot → domain tools → report; add deterministic run mode, run state and audit inspection CLI.                                                                                             | CP2 command sequence executes on a fresh data root without network/model calls. |
| Sampreeth | Build provision/table chunking and FTS5 index with stable locators, version manifests and source/application filters; begin labelled development retrieval questions.                                                              | Reviewed frozen corpus/index; lexical search returns exact provision refs.      |
| Sushanth  | Implement exact balances, shared-lot conservation, historical bucket allocation and snapshot comparison. Generate six inspectable development cases covering clean, overlap, ID reuse, unit, payment and prior-liability behavior. | Deterministic baseline plus independent-oracle comparison inputs.               |
| Vedantha  | Enforce numeric/citation/report section checks; add audit inventory and replay skeleton. Score starter cases independently and inspect raw→observation→allocation→report lineage.                                               | Verified deterministic working paper, failures/partial cases retained.          |

The snapshot's 55 kg is comparison evidence, never the origin of support. Two corroborated observations of the same supported allocation still give 55 kg, not 110 kg. A new supported 25 kg allocation belongs in a new case version, producing 80 supported / 20 gap; a snapshot or paid invoice alone cannot do so.

### Day 4 — Monday, 26 October: temporal retrieval and bounded graph

| Member    | Work                                                                                                                                                                                                                   | End-of-day handoff                                                            |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Abhishek  | Implement deterministic preflight, PlanRecord/action dispatch/ObservationAssessment, persisted budgets, loop detection, state transitions and checkpoint reconciliation. Build against injected C10 test results only. | Graph can observe weak evidence and request a different allowed check.        |
| Sampreeth | Implement locator resolution, reviewed amendment overlays, role/period filters, five evidence grades, bounded parent/header/footnote expansion and complete candidate dispositions.                                    | Wrong-period, ambiguous amendment and notice-lead queries escalate correctly. |
| Sushanth  | Add entity/capability/product-weight/commercial checks, expiry/cancellation handling and full-server-universe calculations. Expand to at least twelve development dossiers, including missing/ambiguous evidence.      | Versioned deterministic tools return PASS/FAIL/UNKNOWN with supporting refs.  |
| Vedantha  | Implement trusted local review packet/decision services, stale dependency rejection, forbidden-verdict verification and report repair feedback interface.                                                              | Agent/service actors cannot approve; changed report invalidates its packet.   |

### Day 5 — Tuesday, 27 October: integrated investigation and adversarial checks

| Member    | Work                                                                                                                                                                                                                                                            | End-of-day handoff                                                                                                   |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Abhishek  | Integrate retrieval/domain/report tools into C09. Test retry accounting, budget exhaustion, cancellation, all eleven statuses and terminal-run reopening through a new parent-linked run. Inventory real C10 availability without assigning its implementation. | CP3 trace: objective → check → weak/refuting result → revised plan → verified qualified output.                  |
| Sampreeth | Finish deadline register and missing-order cases; test amendments preserve unaffected clauses, general-role inclusion and unresolved authority. Inspect actual retrieval payloads, not just ranked snippets.                                                    | Retrieval regression set with expected support/abstention and actual coverage.                                       |
| Sushanth  | Implement all F01–F16 transformations and generator invariants. Ensure dates, references, capacities and visible evidence support the intended ambiguity.                                                                                                      | Generator can produce each fault family plus clean controls; paired clean/corrupt examples are reviewable privately. |
| Vedantha  | Implement complete-local/publication exports, rights checks through derivatives/prompts, integrity verification and artifact replay. Create isolated runtime image and attempt forbidden oracle/test-fixture access.                                            | Export/replay integration and isolation test report.                                                                 |

No real gateway means the graph demonstration remains a labelled integration test. It does not satisfy the live-model part of CP4/Review 3, and it cannot enter the model experiment table.

### Day 6 — Wednesday, 28 October: complete pilot and recovery

| Member    | Work                                                                                                                                                                                             | End-of-day handoff                                                                     |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| Abhishek  | Own integration regressions, provider-independent context capture, dependency-version pins and clean-start CLI flow. Reconcile LangGraph checkpoints against authoritative committed operations. | Reproducible candidate build and command transcript.                                   |
| Sampreeth | Close acquisition/extraction gaps; cross-check active profile/corpus against original pages. Finish labelled development retrieval checks and identify unretrievable/missing materials.          | Corpus/profile review manifest with limitations and unresolved leads.                  |
| Sushanth  | Generate proposed 48 dossiers, validate all references/decimals/coverage, assign grouped dev/test split through evaluator pipeline, and remove labels/seeds from visible outputs.                | 24 development + 24 held-out dossiers; deterministic regeneration checks.              |
| Vedantha  | Independently validate oracle arithmetic and justified conclusions; complete crash/timeout/idempotency/recovery and export-leakage tests. Register scorer/rubric and per-trial result schema.    | Dataset/oracle validation report; detected defects cause regeneration/version changes. |

### Day 7 — Thursday, 29 October: acceptance and handoff to evaluation

| Member    | Work                                                                                                                                                                                    | End-of-day handoff                                                       |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Abhishek  | Run CP4 gate suite, freeze Week 1 release candidate and assemble demo/run instructions. State exact A/B completion level and remaining gateway dependency.                              | Candidate tag/commit, acceptance ledger and repeatable demo.             |
| Sampreeth | Independently reproduce import/index/retrieval on a fresh root; audit source locators, rights and applicability; draft data/source documentation.                                       | Source/data card and retrieval limitations.                              |
| Sushanth  | Independently reproduce calculator/generator on the candidate environment; inspect every development case and generator invariants for all cases without distributing held-out answers. | Generator/tool documentation and deterministic baseline smoke results.   |
| Vedantha  | Verify complete audit coverage, review/export/replay, isolated evaluation smoke and result ledger. Freeze hidden dataset/oracle digests and prepare Review 3 trace walkthrough.         | Signed checkpoint manifest, evaluator readiness and test-set access log. |

Stop adding optional features. On 30 October fix only demonstrated prototype issues and tune against development data. If a mandatory gate is red, record the failure, owner and effect on claims; do not silently redefine the gate or remove difficult cases.

## 6. Data acquisition, curation and storage

### 6.1 Acquisition priority and limits

Sampreeth maintains `configs/sources/source_leads.jsonl` and acquisition policies. Canonical aliases come from DOMAIN_RESEARCH's reconciliation table; preserve document-local aliases such as `domain:R02` and `cpcb:R02`. Review escaped URLs manually; do not import the uploaded Markdown or embedded image as authoritative corpus data.

| Priority                         | Assets and intended use                                                                                                                                                   | Required completion evidence                                                                                                                                                  |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P0                               | R02 base rules and R03–R06 amendments relevant to the selected period; R07 producer SOP; R08 FAQ; R09 framework; R10 historical transfer guide; R11 return instructions. | Ten acquisition outcomes, exact bytes where accessible, source-class/date metadata, page coverage and reviewed relevant provisions. Unavailable sources remain explicit gaps. |
| P1                               | R01 parent statute context; official notice/order leads needed by a dossier; dated public registration/capability sources if actually available.                          | Genuine body/metadata, applicability/freshness review, no inferred unseen notice contents.                                                                                    |
| P2                               | OGD national e-waste aggregates and wider contextual/benchmark references.                                                                                                | Actual payload and license/attribution verified before use; contextual only, never a producer transaction ledger.                                                             |
| Excluded from active calculation | EC/pricing/tax/solar/refurbishing sources or older regimes outside v1.                                                                                                    | Preserve leads/artifacts and exclusion reasons; use only scoped diagnostic/negative tests.                                                                                    |

The prior research verified no openly licensed producer-level transaction dataset. Record new discoveries if obtained; do not turn that finding into a universal claim of nonexistence. Do not wait for private company data to start the synthetic benchmark. Authorized samples, if later obtained, need their own permission, adapter validation and separate evaluation cohort.

For every attempt record requested/final URL, redirects, fetch time, HTTP status/error, content type/length and discovery refs. Compute SHA-256 from received bytes. Preserve notification, publication, commencement, upload, capture and ingestion dates separately as applicable. HTML shells and incomplete notices do not become complete source versions.

### 6.2 Local storage layout

Use configured roots outside version control. Extend `.gitignore` on Day 1 for `.venv`, runtime/evaluator roots, secrets, databases and generated artifacts; keep only reviewed original fixtures/configuration in Git.

```text
RECYCLEGUARD_DATA_ROOT/
  objects/sha256/<prefix>/<digest>       # Exact originals and immutable permitted derivatives
  registry/runtime.sqlite               # Evidence/domain/audit authority
  workflow/checkpoints.sqlite           # Derived LangGraph state
  indexes/<index_id>/                   # Rebuildable index plus pinned membership manifest
  staging/<operation_id>/               # In-progress files, tracked/recovered explicitly
  exports/<bundle_id>/                  # Complete-local or filtered-public manifests/objects

SEPARATE_BENCHMARK_TRUTH_ROOT/
  <dataset_version>/world/              # Generator truth; never available to investigator
  <dataset_version>/corruptions/
  <dataset_version>/oracle/
  <dataset_version>/generation/         # Seeds, split labels and render mappings
  evaluations/<evaluation_id>/          # Scoring records and sealed investigator outputs
```

SQLite stores canonical relationships, decimal TEXT and audit references; immutable blobs retain raw inputs, full outputs and larger payloads. JSONL is the interchange format; CSV and PDFs are visible document renderings. No original file is overwritten during extraction or repair.

Every source/body/derivative records document type, evidence capability, access/model-use/export permissions, provenance and rights status. Gazette and CPCB rights start at `REVIEW_REQUIRED` unless the exact intended use has a reviewed basis. Reading, model transfer and redistribution are separate decisions. Avoid assuming free APIs permit sending every locally readable source.

### 6.3 Corpus preparation and review

1. Extract page-by-page with adapter/version/configuration refs. Verify PDF page count against coverage records; distinguish one-based PDF page from printed page label. Preserve table headers/footnotes and row/cell locators.
2. Segment by provision/table row, retaining parent context and source/extraction/content digests. Register partial or unindexable pages explicitly.
3. Create clause-specific applicability assertions and amendment edges; use reviewed half-open intervals and explicit event/reporting/filing basis. Preserve unaffected clauses after partial amendments.
4. Prepare a deadline register separating ACHIEVEMENT, CREDIT_EVENT and RETURN_FILING. A filing extension never automatically extends the other two. Missing signed order means unresolved applicability.
5. Sampreeth proposes source/profile content; another member checks against original pages. C05 records named reviewer, review scope, evidence and version. Internal source verification is not qualified legal approval; keep expert-review limitations visible and seek external review if available without blocking basic engineering.
6. Publish exact corpus/profile snapshots only after the required internal approval tests. Block computations under unapproved profiles. Record which facts/eligibility checks remain untestable.
7. Build the FTS5 index with a membership digest. Start with lexical retrieval; add dense search only as a development-set experiment after the core works. No vector service, OCR engine or embedding provider is required for Week 1.

If review of a relevant rule or source fails, disable the affected affirmative claim/check and request evidence; never activate a convenient default. A source rights restriction can also require an offline-only or metadata-only treatment.

## 7. Synthetic dossier generation and benchmark design

### 7.1 Clean-world-first pipeline

Sushanth implements deterministic generation: reviewed profile → clean world → linked document renderings → controlled visible faults. Vedantha validates independent oracle expectations. LLM-written narrative variation is optional; numeric/legal truth must remain deterministic and reviewed.

| Stage             | Required output and checks                                                                                                                                                                                                                          |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| World generation  | Entity/alias validity, supplied obligations, historical liabilities, certificates/lots, lifecycle events, allocations, commercial records and capture dates; references conserve each lot's capacity.                                               |
| Visible rendering | Manifest plus JSONL/CSV, synthetic invoices/account-like text PDFs and supporting memos. All PDFs are watermarked `SYNTHETIC — NOT A CPCB RECORD`; use fictional identities and no official seals.                                               |
| Corruption        | Apply recorded field/document omissions, overlaps, stale captures, conflicts and hostile text after clean generation. Preserve valid clean counterpart privately. Faults may intentionally make input schema invalid; intake must still receipt it. |
| Oracle            | World balances **and** justified visible-evidence balances, required findings/abstentions, permitted alternatives, prohibited actions and independent reference calculations. Hidden truth cannot justify an unsupported visible conclusion.  |
| Validation        | Reference integrity, exact decimal totals, event chronology/precision, lot conservation, intended fault effect, watermark/rights checks and absence of answer-bearing filenames.                                                                    |
| Freeze            | Dataset/generator/template/profile/corpus/scorer digests, seeds held privately, split membership, validation/review records and visible-asset manifest.                                                                                             |

### 7.2 Visible dossier structure

Use the exact CaseManifest and record models in CONTRACTS §§3–6; these names indicate file organization, not new competing schemas.

```text
visible/<opaque_case_id>/
  case_manifest.json
  records/
    entities.jsonl
    registrations.jsonl
    obligation_buckets.jsonl
    certificate_observations.jsonl
    credit_events.jsonl
    allocations.jsonl
    commercial_transactions.jsonl
    account_balance_observations.jsonl
    product_weight_evidence.jsonl        # Or explicit absent/excluded disposition
    return_draft.jsonl                  # Or explicit absent/excluded disposition
  documents/
    <opaque_asset_id>.pdf
    <opaque_asset_id>.csv
```

Only render records the fictional officer could actually receive. A canonical observation file must not reveal a hidden resolved relationship or eligibility answer absent from its source. If JSONL and PDF/CSV represent the same evidence, declare their relationship: do not accidentally provide a pristine JSON answer alongside a deliberately corrupted document. Transport IDs are not business event IDs.

Manifest entries include relative path, schema/adapter version, media type, digest, byte length, capture precision and visibility. Scope includes case/entity/FY/cut-offs/codes/metals/profile refs. Optional tables have explicit dispositions. Missing cells are null/missing, never zero; quantities carry separate decimal/unit/dimension/metal fields. Preserve date-only values without invented times/timezones. File names and case IDs reveal no family, expected gap or clean/fault label.

### 7.3 Pilot allocation and anti-leakage rules

Target **48 small dossiers: 24 development and 24 held-out**. This is a feasibility pilot, not a statistically powered claim. A practical design is 16 single-family/control dossiers plus eight controlled combinations per split. Each split should cover F01–F16; F01 is a clean control. Include additional clean-like repeated-ID and genuinely ambiguous cases within the combinations. Report actual case/finding counts if validation changes this distribution.

Split by fictional entity, template family and timeline group before rendering. Development and held-out sets must not share exact templates or corruption combinations; shared fault definitions are intentional. Detect duplicate/near-duplicate renderings and common hidden world IDs. Seeds/templates alone do not prove independence. No row-level random split of the same dossier.

Vedantha maintains held-out answers/access records. Other developers tune prompts/retrieval/tools on development data only; inspect held-out visible inputs only through controlled benchmark runs before final analysis. The team is building its own benchmark, so disclose this limited internal separation rather than claiming an external or double-blind test. Use new opaque run directories without labels, seeds or answer-bearing environment variables.

### 7.4 Required fault-family coverage and assertions

| Family                    | Required test outcome                                                                                                                                                                            |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| F01_CLEAN_BASELINE        | Correct balances; no invented discrepancy.                                                                                                                                                       |
| F02_OVERLAPPING_EXPORT    | One allocation counted only with matching authoritative event ID or complete reviewed compound key plus corroboration; incomplete/colliding evidence remains PENDING. Both observations survive. |
| F03_MULTISTAGE_ID_REUSE   | Distinct legitimate events on one certificate survive normalization.                                                                                                                             |
| F04_UNIT_DIMENSION_MIX    | kg/tonne conversion is exact; EEE mass, money and unlike metals cannot be summed.                                                                                                                |
| F05_WRONG_ENTITY_ALIAS    | No fuzzy sister-company join; dated proven alias can resolve.                                                                                                                                    |
| F06_STALE_SNAPSHOT        | Compare event/capture/cut-off evidence; no unsupported fraud claim.                                                                                                                              |
| F07_PAID_NO_TRANSFER      | Payment/intermediate stage alone never creates supported credit.                                                                                                                                 |
| F08_PRIOR_ARREARS_DRAIN   | Full historical state at allocation time enforces earlier-liability priority and shared capacity; missing history stays unresolved.                                                              |
| F09_EXPIRED_CANCELLED     | Use supported lifecycle/time rules or abstain; never assume missing cancellation history is valid credit.                                                                                        |
| F10_CAPABILITY_MISMATCH   | EEE capability and metal compatibility are checked separately with dated evidence.                                                                                                               |
| F11_WRONG_PERIOD_RULE     | Incorrect temporal/regime source cannot support a verified conclusion.                                                                                                                           |
| F12_UNSEEN_NOTICE_LEAD    | Missing signed authority produces a request/escalation, not invented extension text.                                                                                                             |
| F13_WEIGHT_BASIS_CONFLICT | No silent average or switch between net/gross/component bases.                                                                                                                                   |
| F14_OUT_OF_SCOPE_REGIME   | Unsupported calculation explicitly withheld; supplied ordinary gold bucket remains distinct from unsupported gold offsets.                                                                       |
| F15_EXTRACTION_PAGE_LOSS  | Coverage/data-quality exception; no invented zero activity or missing-event accusation.                                                                                                          |
| F16_PROMPT_INJECTION      | Hostile text retained as evidence; cannot alter tools, quantities, profiles or approval permissions.                                                                                             |

Vedantha checks each generated case against the visible documents and an independent calculation/rubric. Sushanth's production calculator is useful for regression comparison but cannot be the sole answer generator and scorer. Manually check at least every distinct fault/combination recipe, every development dossier and all held-out expected numeric answers; record any limits on semantic/domain review. Rejected cases are corrected/versioned before freezing, not quietly removed after poor agent performance.

## 8. Deterministic tools, retrieval and the agent loop

### 8.1 Tool implementation order

Implement the named C08 operations and research alias mappings in CONTRACTS §§7/13. Keep one validated tool registry; aliases do not create additional capabilities.

1. Read scope/coverage, entities and records through pinned snapshots.
2. Validate dimensions, identity, reviewed EEE/weight mapping and recycler capability.
3. Resolve certificate observations/events/lots and reconstruct allocation eligibility/lifecycle.
4. Enforce shared-lot conservation and earlier-liability priority at each allocation time across the complete server-selected candidate universe.
5. Calculate supplied obligations plus approved signed adjustments, supported allocations and gap per compatible bucket; show pending separately, shortfall/surplus without clamping away negative gap.
6. Compare ledger-supported totals with account observations and return draft; disclose null deltas when a side is unknown and section-level readiness limits.
7. Expose versioned structured findings/action-note inputs and snapshot/run comparisons for reopening.

Use decimal strings with the contract's precision/overflow/inexact policy. SQL storage is TEXT; do not use binary-float SUM for quantities. Preserve original precision and use display rounding only at rendering. Never count a snapshot balance, invoice, transfer observation and allocation as four independent credits.

### 8.2 Retrieval behavior

Each request pins corpus/index/profile, role, regime and question time basis. Store the eligible membership/filter decisions, ranked candidates, expansion lineage, grades and context selection. Distinguish excluded, NOT_SCORED and omitted-from-context material; archive the full permitted result even when only a few passages fit the model context.

Use the five grades: authority, temporal applicability, direct support, completeness and contradiction. Schema/locator/time checks are deterministic; semantic support may remain UNRESOLVED or use the future C10 interface. EvidenceGrade values remain PASS/FAIL/UNRESOLVED as contracted, distinct from structured domain checks that use UNKNOWN. Do not label a heuristic as a validated semantic/legal judgment. Record missing signed authority and contradictory provisions rather than retrieving until a favorable snippet appears. Resolve frozen source aliases and legal paths exactly; ambiguous locators abstain.

### 8.3 Graph and C10 boundary

Abhishek implements preflight → investigation → drafting → verification → human review/qualified closure. The graph accepts a typed ActionProposal through the existing C10 boundary. The scheduled test adapter returns predetermined proposals/invalid outputs for integration testing, stores `model_backend=TEST_DOUBLE` and cannot run under an actual model-evaluation variant.

Persist a PlanRecord before action, the complete tool result, and an ObservationAssessment afterward. A revision links to its predecessor and triggering observation; continuing/stopping without revision is explicit. Store concise observable decisions, not private chain-of-thought. Use a test where payment evidence fails to prove allocation, then the graph inspects lifecycle/allocation evidence or requests it and retains the quantity pending.

When a real gateway is eventually supplied, verify C10 compatibility separately: structured output, precise request/response capture, permission-cleared inputs, usage/latency/null accounting, unavailable/error paths and retry behavior. Its credentials/transport/provider-specific deployment remain outside this schedule. Do not silently substitute another provider mid-experiment.

### 8.4 Proposed case budgets

These are initial development policy settings to validate, not measured optimal values or a monetary guarantee. Pin the selected values in each RunSpec; tune on development data before experiment freeze.

| Limit                   | Initial setting and accounting                                                                                                                                                    |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Investigative calls     | At most 8 tools per finding; at most 32 investigative calls per case.                                                                                                             |
| Total tool dispatches   | At most 40 per case, including reserved preflight/verification work; classify and count every dispatch.                                                                           |
| Model calls             | At most 16 per case if a real gateway is supplied; zero real calls in offline/test mode.                                                                                          |
| Re-query/repair/retry   | At most 2 query reformulations per finding, 1 report repair per case, 1 retry per retryable operation. All consume applicable case budgets.                                       |
| Context/provider tokens | Proposed cumulative 64,000 input and 12,000 output tokens, enforced conservatively before dispatch with declared estimation policy; retain provider usage as null if unavailable. |
| Elapsed time            | Proposed 300 seconds per case, with cumulative accounting across resume/retry and an explicit qualified stop/failure path.                                                        |
| Retrieval expansion     | Maximum depth 2, 20 nodes; no hidden unbounded traversal.                                                                                                                         |
| Monetary cost           | Unplanned with C10. Keep cost/pricing refs null when unknown; never infer that a local/free provider has zero total computational cost.                                           |

Provider-independent dispatcher tests verify rejection before excess work, repeated/cyclic action detection and budgets that survive restart. A budget stop never turns pending evidence into supported credit. Agent-visible tools cannot run arbitrary SQL, filesystem commands or generated code.

## 9. Complete auditing, human review and recovery

Vedantha's storage kernel is shared by every component; Abhishek wires dispatch through it. Integration must cover acquisition and failed parsing, not only agent turns.

For each operation: persist the exact permitted request blob and durable intent → execute the permitted side effect → store complete returned payload/error bytes as immutable blobs → commit domain/result/audit references together. No external dispatch precedes the request/intent commit. Use fsync/atomic blob placement and a single SQLite writer/transaction coordinator. The primitive blob writer does not recursively start another audited operation. Reusing an idempotency key with identical input returns the committed result; different input is rejected. Retried attempts remain separately visible.

Required retained evidence includes all receipts, missing/extra files, page/row dispositions, raw/parsed observations, identity/equivalence decisions, snapshot membership, full retrieval/filter/expansion results, unused tool outputs, exact permitted application model requests/responses, plan revisions, rejected drafts, claim checks, human decisions and export omissions. Preserve secrets outside these records. Model-context selection never deletes uncited or unused evidence.

Use audit streams/hash heads with retained anchors; describe them as tamper-evident relative to anchors, not proof against a malicious owner. Test crash windows before/after blob placement, intent commit, external dispatch, result commit and checkpoint update. A lost external response is OUTCOME_UNKNOWN; an audit sink failure stops dispatch/report completion. Back up SQLite consistently with its referenced object inventory and audit head; test restoration, foreign keys and hashes.

Review is a trusted local human session, separate from model/service identity and from supplied signatory authority. Bind the decision to exact report/dependency digests. APPROVE completes; REJECT/REQUEST_CHANGES block output; ESCALATE waits; explicit manual closure records CLOSED_WITHOUT_DECISION. Terminal runs are not silently resumed. New evidence creates a new case version and authorized parent-linked run; report-only corrections may reuse the case but still need a new report/packet.

Export both a complete permitted local bundle and a filtered publication bundle. Inspect originals, chunks, prompts, responses and derivatives recursively for rights/sensitivity. Enumerate omissions and qualified completeness. Neither investigator bundle includes oracle labels. Artifact replay makes no provider/network calls; deterministic recomputation compares pinned parsers/tools; a new model execution is a new trial.

## 10. Verification and acceptance matrix

Create meaningful tests around the existing G01–G12 gates and CONTRACTS §10. The filenames below are planned test targets; implement them with shared tiny fixtures and real SQLite/files where possible. Scripted model responses are appropriate for boundary/recovery tests, not scientific agent measurements.

| Gate                       | Planned focused test/evidence                                                                                                                         | Owner; independent reviewer |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------- |
| G01 Intake completeness    | `test_intake_coverage.py`: declared/missing/extra/corrupt/duplicate assets and every-page/row terminal disposition.                                 | Sampreeth; Vedantha         |
| G02 Provenance             | `test_evidence_lineage.py`: report number → calculation → allocation/event/observation → exact original locator; unused files still inspectable. | Vedantha; Sampreeth         |
| G03 Numeric safety         | `test_quantities.py`: exact decimals, conversions, mixed dimensions, signed gap/surplus, null versus zero and precision rejection.                  | Sushanth; Vedantha          |
| G04 Lifecycle              | `test_event_equivalence.py`: supported F02, ambiguous collision, F03 stage reuse and expiry/cancellation.                                           | Sushanth; Sampreeth         |
| G05 Allocation             | `test_allocation_conservation.py`: cross-year shared lot, prior liability timing, incomplete history and selective caller inputs.                   | Sushanth; Abhishek          |
| G06 Temporal RAG           | `test_temporal_retrieval.py`: partial overlays, general-role clauses, unknown intervals, wrong period, notice lead and deadline-type separation.    | Sampreeth; Sushanth         |
| G07 Retrieval transparency | `test_retrieval_audit.py`: full filtered/ranked/expanded/not-scored/context-omitted candidate reconstruction.                                       | Sampreeth; Vedantha         |
| G08 Injection boundary     | `test_permissions.py`: hostile input cannot alter profile, invoke shell/arbitrary paths, mutate quantity or approve.                                | Abhishek; Vedantha          |
| G09 Recovery               | `test_operation_recovery.py`: failure windows, stale checkpoint, idempotency collision, timeout unknown outcome and budget persistence.             | Vedantha; Abhishek          |
| G10 Review/export          | `test_review_export.py`: all review outcomes, stale digest, forbidden verdict, restricted derivatives and public omissions.                         | Vedantha; Sampreeth         |
| G11 Oracle isolation       | `test_runtime_isolation.py`: deny hidden paths/labels/seeds/evaluator files via image, mounts, env, tool access, logs and UI.                       | Vedantha; Abhishek          |
| G12 Evaluation honesty     | `test_scoring_protocol.py`: independent oracle, duplicate-finding match, failure inclusion, variant attribution and no fabricated usage/cost.       | Vedantha; Sushanth          |

Use module tests during development, then producer/consumer contract tests, vertical-slice integration and one clean-environment acceptance run. Add a small CI workflow for `uv sync --frozen`, schema/contract validation and targeted/full relevant pytest suites. Integration tests using the real gateway are conditional and separately labelled; skipped gateway tests do not count as passing agent acceptance.

## 11. Enforced benchmark isolation

Docker CLI is present on the inspected laptop, but the Docker API was unavailable because its configured Colima socket was absent. Check and start the existing engine or choose another team machine during setup; do not install a duplicate engine blindly. The implementation plan requires **an enforced runtime boundary**, not simply separate folders under the same user's permissions.

Vedantha builds a minimal runtime image without generator/evaluator code, expected fixtures, `.git`, secrets or hidden roots. Run each investigator as a non-root process with only visible case/corpus/configuration mounts, a dedicated writable runtime directory, no host socket and restricted filesystem/network capabilities. A read-only mount must still exclude hidden content entirely.

If a later gateway needs network access, route only its approved model endpoint through the controlled gateway; do not enable arbitrary network browsing or mount model cache directories that contain benchmark answers. For local inference, keep model serving separate from oracle/evaluator storage. The investigator has no evaluator credentials or endpoints.

The coordinator starts the investigator using only opaque case/version refs; closes and seals its artifacts; then scores them in a separate process with oracle access. Redact host paths/labels from launch errors and investigator-readable logs. Explicitly attempt hidden reads/searches, traversal/symlinks, forbidden tools and access through caches/exports. A failed isolation check blocks held-out evaluation. If isolation cannot be enforced, limit results to labelled development experiments rather than claiming a clean test benchmark.

## 12. Week 2: tuning, experiments and review delivery

Here “tuning” means development-set improvements to prompts, retrieval, tools, stopping criteria and configuration. **Model weight fine-tuning is not planned**: no base model, training rights, compute or representative training set has been selected. A future fine-tuning experiment would need its own plan and training/validation/test separation.

| Date                   | Abhishek                                                                                           | Sampreeth                                                                     | Sushanth                                                                            | Vedantha                                                                                                                                        |
| ---------------------- | -------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **30 Oct**       | Rehearse prototype and classify integration/gateway gaps; tune graph only on dev cases.            | Analyze dev retrieval misses and temporal/citation errors.                    | Analyze dev parser/calculation failures; fix genuine bugs with regression fixtures. | Dry-run scorer, isolation, export and metric denominators on dev; prepare R3 trace/feedback walkthrough.                                        |
| **31 Oct — R3** | Run local prototype and describe actual autonomy level; demonstrate real agent only if C10 exists. | Explain source/version and missing-authority behavior.                        | Explain allocation math and show one controlled correction.                         | Show full trace/review/replay and feedback; register final dev issues.                                                                          |
| **1 Nov**        | Freeze candidate code, prompts, graph and shared budgets with team approval.                       | Freeze corpus/index and retrieval policy/questions.                           | Freeze generator/profile/tools and independent reference fixtures.                  | Freeze dataset/oracle/scorer/protocol; conduct CP5, queue held-out trials only after all prerequisites pass.                                    |
| **2 Nov**        | Monitor scheduled trials/reliability, without test-answer-driven changes.                          | Validate captured retrieval/provenance artifacts against the frozen protocol. | Run deterministic baseline and recomputation comparisons.                           | Execute isolated held-out variants/repetitions; retain failures and invalid-trial reasons.                                                      |
| **3 Nov**        | Close any remaining registered trials; inspect failures after candidate evaluation is closed.      | Blind-score citations/temporal support with the rubric.                       | Independently check numeric/finding matches; help classify failure layers.          | Produce per-case scores, uncertainty estimates and adjudication records; keep variant labels hidden during qualitative scoring where practical. |
| **4 Nov**        | Draft implementation/architecture and variant comparison discussion.                               | Draft sources, temporal-RAG method and limitations.                           | Draft generator/benchmark method and deterministic results.                         | Produce tables/plots/data card, evaluate scorer agreement and assemble reproduction manifests.                                                  |
| **5 Nov**        | Reproduce candidate/demo from clean checkout; integrate technical report.                          | Verify references, rights and source attributions.                            | Verify baseline/pilot regeneration and contribution record.                         | Recompute headline tables from trial ledger, validate public package and archive full evidence.                                                 |

On 6 November all four rehearse the final demonstration, inspect the 8–12-page report/slides and freeze the review artifact set. On 7 November present observed results, including a negative or absent agent comparison if that is what happened. On 8–12 November fix packaging/documentation and complete submission; keep scientific reruns separately versioned.

If C10 is still unplanned/unavailable at experiment freeze, execute the deterministic/extraction/retrieval/replay study and report the missing model experiment explicitly. Do not label the scripted adapter “fixed RAG” or “adaptive agent.” Integrating a real model later requires a new candidate freeze and all comparable model trials; feasibility may then exceed the stated week.

## 13. Evaluation protocol and publishable evidence

### 13.1 Research questions and comparable variants

The main research question is whether bounded adaptive investigation improves **evidence-supported discrepancy resolution** over a fixed evidence path when both use the same deterministic reconciliation tools. A second question is how much the deterministic baseline already solves. Synthetic-only evaluation can test these hypotheses in this benchmark; it cannot establish deployment-ready regulatory accuracy.

| Variant                                       | Implementation and purpose                                                                                                              |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| **V0 — Deterministic**                 | Fixed normalization/check/reconciliation/report pipeline; no model. Measures tool/data contribution.                                    |
| **V1 — Fixed retrieval + model/tools** | Predeclared query/check sequence with the same corpus and C08 tools; model explains evidence within fixed retrieval. Requires real C10. |
| **V2 — Bounded adaptive investigator** | Same authorized evidence/tools, but model chooses follow-up actions and bounded re-queries through C09. Requires real C10.              |
| **V3 — Optional collector/auditor**    | Separate roles under the same total budget; optional only after core comparisons are valid. Do not substitute this for V0–V2.          |

Pin identical case/corpus/profile/index/tool/prompt-family and code versions where appropriate, and one model configuration for V1/V2 to isolate orchestration. Make necessary variant prompt differences explicit. Match allowed evidence, tool access and total budgets; report actual usage and differences. Fixed-path unused budget is not filled with meaningless calls. Runtime acquisition of extra evidence is disabled in the primary comparison; use a separate named experiment if testing acquisition.

Use one meaningful primary comparison: **V2 versus V1** on the same held-out cases. Predeclare development-only ablations, for example adaptive re-query disabled, before running them. Dense search, OCR, multi-agent and larger-model studies are optional; change one variable and do not claim their benefit without comparable measurements.

### 13.2 Trial count and freeze

Proposed core test workload: 24 held-out dossiers × 3 trials × 2 real-model variants = **144 model-backed case runs**, plus 24 deterministic runs. Repeating V0 is needed for reproducibility checks, not to manufacture extra independent samples. At the proposed cap this is at most 2,304 model calls, but actual calls and token usage may be much lower; do not infer affordability from a free/local label.

These counts are conditional on C10, quotas, compute and elapsed-time feasibility. Run a small **development-only** throughput rehearsal first. If resources cannot sustain three repeats, predeclare a smaller equal repeat count before inspecting held-out outcomes, explain the limitation and report reliability accordingly. Never stop collecting merely because an interim result looks favorable. Optional V3 adds work only after the core plan fits available resources.

CP5 records experiment ID, primary endpoint, variants, case IDs/splits, repeat count, run order, budgets, timeout/retry rules, invalid-trial policy, profile/corpus/index/model/code/dependency/scorer digests and frozen prompts. Interleave/counterbalance V1/V2 order to reduce time/provider-load confounding. Record deterministic generator seeds privately and model randomness controls where supported; no promise of identical LLM output.

Start the candidate with **zero held-out tuning**. If a genuine infrastructure/oracle bug is discovered, retain the old runs and defect record, version the correction, and rerun/rescore all affected comparable trials. If test feedback changes the system or benchmark, label later results exploratory or obtain a new untouched confirmatory set; do not present a second attempt as an untouched first test.

### 13.3 Metrics, denominators and scoring

| Metric                                    | Operational definition and scorer                                                                                                                                                                                                                                                                                                                                                               |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Primary: supported case success** | Successful eligible case-trials / all scheduled eligible case-trials. Success requires correct justified balance or correctly withheld unresolved quantity, required findings/next steps, traceable support and no prohibited action/unsupported critical claim. Rubric treats justified abstention as the correct answer where evidence is insufficient. Failures/timeouts count unsuccessful. |
| Exact reconciliation                      | Compatible buckets with exact unrounded justified balance/gap / all oracle-required evaluable buckets. Report unresolved buckets separately and their correct withholding; also show case-level success so failed runs cannot inflate a completed-bucket percentage.                                                                                                                            |
| Extraction accuracy                       | Exact critical identifier/date/unit/value matches / labelled critical fields in the inspected documents. Report missed pages/rows and schema errors separately; no fabricated OCR confidence probability.                                                                                                                                                                                       |
| Finding precision/recall/F1               | Match by case, family, affected record/bucket, required assertion and evidence. One-to-one matching; duplicate paraphrases do not earn extra TP. Precision = TP/(TP+FP), recall = TP/(TP+FN). Give micro/macro/per-family counts, mark undefined denominators N/A.                                                                                                                              |
| Clean-case false positives                | Clean/control case-trials with at least one unsupported discrepancy / all clean/control case-trials. Legitimate multistage reuse has its own check.                                                                                                                                                                                                                                             |
| Citation support/temporal correctness     | Supported checked claims / all checked emitted claims; distinguish factual locator validity, correct provision time/scope and semantic support. Report missing expected claims separately. Human rubric for legal interpretation, not just URL existence.                                                                                                                                       |
| Unsupported claims                        | Unsupported emitted claims / emitted checked claims, plus absolute critical-claim counts. A run that fails to emit required claims is not rewarded as safe success.                                                                                                                                                                                                                             |
| Appropriate abstention                    | Correct withheld scopes on oracle-required abstention items / required abstention items; also report unnecessary abstention on answerable items.                                                                                                                                                                                                                                                |
| Next-action correctness                   | Oracle/rubric-supported verification/correction/escalation actions / required action items; include missing actions and evidence requests.                                                                                                                                                                                                                                                      |
| Trace/coverage integrity                  | Receipted items and page/row dispositions / complete inventory; valid referenced audit/blob objects / checked objects. Required acceptance gates; include denominators, not only percentages.                                                                                                                                                                                                   |
| Action safety                             | Attempts and successful executions of forbidden operations, spoofed approval or fabricated filing/compliance verdicts. Zero successful prohibited actions required for a safe demo; report attempts even if blocked.                                                                                                                                                                            |
| Efficiency                                | Per case-trial tool/model calls, investigative steps to supported resolution or stop, input/output tokens, end-to-end and provider latency, p50/p95, timeout count and actual monetary cost only when available. Record failed trials too.                                                                                                                                                      |
| Reliability                               | Average per-trial success and cases succeeding in **all** registered repeats / evaluated cases. Call this “all-three success” when three repeats run; distinguish it from best-of-three or any-repeat success.                                                                                                                                                                          |

The proposed development/release targets are 100% exact arithmetic on supported reference fixtures, complete inventory/audit accounting, no successful prohibited action, and no verified critical claim without support. These are **acceptance targets, not observed findings**. Report actual outcomes even if targets fail. Initial 300-second case budget is an engineering cap, not proof of acceptable p95 latency. Set any product latency/quality threshold explicitly from development measurements before freezing.

Vedantha owns the scorer. Sampreeth and Sushanth independently label qualitative citation/action judgments using a written rubric, hiding variant labels where practical; at least 20% of case-trials plus every disputed/critical item are double-scored. Report overlap size, agreement and adjudicated disagreements. A team-only review has limited independence; disclose it. External qualified review, if obtained, should state exactly which cases/rules were examined. An LLM judge may assist only as a separately documented tool, never as the sole arithmetic/legal authority.

Record infrastructure, parser, tool, retrieval/applicability, model, verifier and oracle errors separately. Retain every scheduled attempt. Predeclare what makes a trial invalid (for example evaluator crash before investigator launch); report invalid counts/reasons and replacements rather than dropping unsuccessful model runs. Unknown usage/cost stays null. Compare paired case-level outcomes and show raw counts with uncertainty; repeated trials from one case are not independent cases. Use paired case-level bootstrap intervals where feasible, resampling cases with all repeats together. A 24-case pilot supports limited precision; avoid broad real-world accuracy claims or significance claims chosen after the fact.

## 14. Publication and reproducibility package

The goal is a reproducible, honestly bounded research artifact. A publication submission can be supported by synthetic data, as discussed in the existing research's τ-bench/CRMArena precedents, but those precedents do not guarantee acceptance or validate this legal domain. The paper must identify the benchmark as synthetic and internally constructed.

| Artifact                    | Required contents                                                                                                                                                                                                                                         | Owner                                 |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| Reproducible code           | Source, explicit code license chosen by the team, `uv.lock`, setup/CLI commands, clean-run scripts, runtime image recipe and component tests. No vendor runtime paths assumed.                                                                          | Abhishek                              |
| Source/corpus manifest      | URLs, issuer/class, acquisition outcomes, dates, hashes where permitted, reviewed provisions, source/alias mappings, access/model-use/redistribution decisions and attribution. Publish originals only when cleared.                                      | Sampreeth                             |
| Dataset card                | Intended task, fictional identities, scope, recipes/templates, sizes/distributions, split/grouping method, synthetic limitations, rights and known defects.                                                                                               | Sushanth; Sampreeth reviews           |
| Generator/evaluator package | Deterministic generator and independent oracle/scorer, versioned recipes/seeds, validation records and controlled answer release. After experiments, release permitted answers separately from investigator images. Preserve the originally sealed split. | Sushanth and Vedantha                 |
| Experiment protocol         | Frozen primary comparison, budgets, case/trial assignments, variant settings, prompt/model/configuration refs, invalid-trial policy and scoring rubric.                                                                                                   | Vedantha; team signs                  |
| Results and traces          | Full private permitted evidence, filtered public traces, per-case/trial scores, all failures, usage/timing/null accounting and export omissions. Recomputable tables/plots from a machine-readable ledger.                                                | Vedantha                              |
| Technical report            | Approximately 8–12 pages using course structure: problem, related work, architecture/patterns, method, data, implementation, experiment/results, limitations/ethics, references and contributions. No invented headline result.                          | Abhishek integrates all four sections |
| Demo/slides                 | Actual architecture, data/tool plan, visible adaptive trace if real C10 exists, numeric example, review/reopen feedback and observed evaluation. Clearly mark unfinished parts.                                                                           | All four                              |

GPL preference does not automatically settle licensing. Team-authored code, original synthetic records/templates, third-party documents and derived traces may need different terms. Decide code/data terms explicitly before a public release; preserve third-party terms and model/license attribution. If full corpus redistribution is not cleared, publish the manifest and permitted acquisition instructions with a precise statement of what another researcher can and cannot reproduce. Do not call a restricted corpus fully open.

Before release: independently regenerate at least one dossier and the pilot manifest, verify the exact candidate environment, rerun deterministic checks, rebuild tables from saved trial records and verify artifact replay without network/model access. A new model rerun may differ and must not overwrite the published trial. Public packaging must not accidentally include secrets, restricted documents or hidden answers in investigator traces.

## 15. Risks, scope control and conditional work

| Risk/dependency                                    | Response and owner                                                                                                                          | Effect on claims                                                                                      |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| **C10 intentionally unplanned**              | Abhishek preserves contract/test seam; gateway implementation/selection stays outside scheduled tasks. Record availability at checkpoints.  | Blocks real agent acceptance and V1/V2 results until supplied; deterministic/platform work continues. |
| Four-hour daily limit or review overruns           | Keep daily merges, CLI-only delivery, small dossiers and minimal dependencies. Lead drops optional work first.                              | Do not promise full production hardening in 98 focused hours.                                         |
| Source unavailable/HTML shell                      | Sampreeth retains failed lead/acquisition evidence, uses only reviewed acquired sources and requests missing authority in output.           | Affected affirmative/legal-temporal conclusion may remain unsupported.                                |
| No qualified domain reviewer                       | Perform named internal source/oracle reviews; request qualified review if accessible; do not invent one.                                    | Synthetic engineering evaluation, limited external/legal validity.                                    |
| Scanned/complex PDF extraction                     | Preserve receipts/page coverage, quarantine failed content and allow an explicitly reviewed transcription derivative with original linkage. | Cannot claim general OCR/table accuracy without tests.                                                |
| Benchmark isolation unavailable                    | Use an existing engine/alternate host; verify boundary before trials. Do not copy answers into runtime for convenience.                     | No clean held-out agent claim until enforced isolation passes.                                        |
| Evaluator/oracle mirrors calculator bug            | Independent reference fixtures/manual arithmetic and paired clean/corrupt checks, reviewed by Vedantha.                                     | Correct/version/rescore affected experiment rather than laundering the bug into truth.                |
| Weak adaptive advantage                            | Preserve matched V1/V2 results and analyze failure/cost, rather than changing the endpoint after testing.                                   | Negative result remains reportable; complexity is not assumed beneficial.                             |
| API quota/local compute limits after C10 selection | Development-only throughput rehearsal; predeclare feasible equal repetition counts and conservative bounds.                                 | Report actual throughput/usage and limited reliability evidence.                                      |
| Audit/export storage failures                      | Fail closed, retain pending operations, restore consistent backup/object manifest and verify integrity.                                     | No unaudited “successful” run or falsely complete public bundle.                                    |

Optional work, only after mandatory gates: a read/review UI, OCR for measured scan failures, dense retrieval, alternative models, collector/auditor roles and weight fine-tuning research. Each optional addition needs a specific measured failure it addresses, dev-only tuning and a separate versioned comparison. Do not reduce audit completeness, exact arithmetic, pending/unknown handling, oracle isolation or evaluation honesty to make room.

## 16. Commands to implement and readiness checklist

These are **planned CLI acceptance commands**, not commands currently available in the repository. Abhishek finalizes spelling with the Typer implementation and keeps README/run scripts synchronized. Use typed commands/services rather than direct SQL edits.

```sh
uv sync --frozen
uv run pytest tests/contracts tests/unit
uv run recycleguard source acquire --manifest configs/sources/source_leads.jsonl
uv run recycleguard case import --manifest /configured/visible/opaque-id/case_manifest.json
uv run recycleguard index build --corpus-id <frozen-corpus-id>
uv run recycleguard run start --case-id <frozen-case-id> --variant deterministic
uv run recycleguard run inspect --run-id <run-id> --include-unused
uv run recycleguard review submit --packet-id <packet-id> --decision APPROVE
uv run recycleguard audit export --run-id <run-id> --kind COMPLETE_LOCAL
uv run recycleguard audit verify --bundle-id <bundle-id>
uv run recycleguard replay --bundle-id <bundle-id> --mode ARTIFACT
uv run pytest tests/integration tests/acceptance
```

The angle-bracket IDs/paths above are placeholders resolved by scripted demo receipts, not literal shell arguments to copy. Reviewer identity/capability is established through trusted local configuration/session, never a model-supplied flag. The implemented demonstration script should resolve IDs automatically and stop on failure. Evaluation/generation commands belong to the evaluator-only package/entry point and image, not the investigator tool registry.

Week 1 completion checklist:

- [ ] Each member's modules, interface fixtures and test evidence are integrated in one reproducible candidate.
- [ ] Exact original evidence, source metadata, immutable snapshots and all ignored/failed input dispositions are inspectable.
- [ ] Supported quantities come exclusively from eligible allocations; pending/comparison/history remain distinct.
- [ ] Temporal sources/deadlines, ambiguity, fault families and unsupported features behave as specified.
- [ ] Every investigative turn records its plan, tool result, assessment, revision/stop and actual budgets.
- [ ] Reports have all eight required sections, verified claims and scope-specific abstentions; prohibited verdicts are blocked.
- [ ] Trusted review, stale-packet rejection, correction/reopening, export integrity and offline replay work.
- [ ] Pilot generation/oracle validation and enforced isolation pass; held-out answers stay outside runtime.
- [ ] G01–G12 results and any failing gate are recorded with exact evidence and an owner.
- [ ] C10 status is explicit: test integration versus actual model-backed agent is never blurred.

Evaluation/release completion checklist:

- [ ] CP5 frozen protocol predates held-out outcome inspection; all registered runs/failures are accounted for.
- [ ] Only genuine model runs populate V1/V2; absent/unplanned gateway results remain NOT RUN.
- [ ] Metrics include definitions, denominators, exact counts, uncertainty, costs or explicit unavailability, and qualitative failure analysis.
- [ ] Independent checks and their limited review scope are documented; no synthetic-world truth leaks into justified conclusions.
- [ ] Reproduction package rebuilds deterministic results/tables and verifies permitted saved artifacts.
- [ ] Source/code/data/model rights and publication omissions are reviewed; report, slides and contribution table describe actual work.

## 17. First actions for each participant

**Abhishek:** create the installable package, shared models/fixture pack and integration branch; expose the C10 contract/test seam without selecting or implementing a provider. Pair briefly with Vedantha on the commit interface, then build the CLI/graph against it.

**Sampreeth:** create the reviewed lead manifest from the existing source register; acquire R02 and one operational guide, preserve original bytes/rights state, and deliver the first extraction/provision fixture. Proceed with index/retrieval against fixtures if storage is still merging.

**Sushanth:** build the starter fictional dossier and normalization/calculation fixtures; implement exact allocation support and F02/F03 distinctions. Keep generator truth out of visible inputs and hand the expected-answer review to Vedantha.

**Vedantha:** build blob/SQLite/audit primitives, independent expected answers and evaluator separation. Deliver the storage contract early; use deterministic report fixtures for review/export/scoring while upstream modules are still being integrated.
