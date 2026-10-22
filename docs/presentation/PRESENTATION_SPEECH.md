# ReCycleGuard presentation speech

Target: **8–10 minutes**. The main talk uses slides **1–13**. Slides **14–15 are hidden backup slides** for questions. The speech below is also embedded in the PowerPoint Presenter Notes.

## How to present it

Spend most of your time on architecture (3), the adaptive graph (4), the worked example (6), and evaluation (11–12). Explain why you chose the patterns (5) and how the evidence/tools work (7–9). Cover scope (2), operational safeguards (10) and ownership (13) briefly.

Do not read component IDs, API names, team IDs or reference titles aloud. Use the diagrams to explain the flow. Treat the timings as rehearsal guides rather than a stopwatch requirement. Say **we propose**, **we plan** or **we will measure** for application behavior and experiments. Do not claim implementation or performance results.

At about 130–145 words per minute, the main script leaves room for the diagram pauses within an 8–10 minute slot.

## Main speech

### Slide 1: ReCycleGuard

**Time:** about 15 seconds. **Priority:** Brief opening.

*Presenter cue: Look at the audience. Start without reading the names on the slide.*

Good morning. We are presenting ReCycleGuard, our proposed agentic system for e-waste EPR reconciliation. It helps a compliance officer investigate discrepancies and identify the action that the available evidence supports. Today, we will focus on the architecture and how we plan to evaluate it.

### Slide 2: Decision and scope

**Time:** about 25 seconds. **Priority:** Mention briefly.

*Presenter cue: Emphasize the decision. Move through the scope quickly.*

Our central question is: which discrepancy needs investigation, and what evidence supports the next action? We start with one synthetic producer, one closed reporting year and supplied metal-wise obligations. Historical liabilities stay separate. The output is a working paper for human review. Live filing, certificate trading and automatic legal certification are outside our scope.

### Slide 3: Architecture and data flow

**Time:** about 80 seconds. **Priority:** Core explanation.

*Presenter cue: Point to the two inputs, then the evidence foundation, the investigator and the report. Do not read component IDs aloud.*

The architecture has two input paths: official regulatory material and the producer dossier. Both enter the evidence foundation. We retain the original files, extract their content, normalize the records and freeze the inputs for the run. Every calculated figure must remain traceable to an original row or page.

The investigator sits at the center. On one side, retrieval supplies relevant clauses and their amendments. On the other, deterministic tools check quantities, certificate history and allocations. The model gateway handles structured model requests and responses. The investigator chooses the next check, while the tools establish the numerical result.

Findings then pass through report verification and human review. Audit capture spans the entire workflow, including failed operations and evidence the model never used.

The generator and evaluator sit outside the runtime. Hidden benchmark answers remain inaccessible to the investigator. We propose these as logical modules in one local application, which keeps the initial implementation manageable.

### Slide 4: Agent graph and adaptation

**Time:** about 60 seconds. **Priority:** Core explanation.

*Presenter cue: Follow the arrows. Pause at the loop from revised investigation back to planning.*

This graph explains the agent's role. First, deterministic preflight checks the inputs and computes provisional findings. The investigator then forms a hypothesis, such as whether a pending item has valid allocation evidence. It proposes a tool call, and the dispatcher checks the arguments, permissions and remaining budget before execution.

After the result arrives, the investigator records whether it supports the hypothesis, contradicts it or provides weak evidence. Weak results can trigger a revised plan or a reformulated retrieval query. This feedback loop is the adaptive part of the design.

The run stops when the finding is supported, evidence remains insufficient or a budget limit applies. Uncertainty remains visible in the report. The final stage verifies the report and requests a human decision.

### Slide 5: Selected agentic patterns

**Time:** about 40 seconds. **Priority:** Explain choices and reasons.

*Presenter cue: Stress tool use, RAG and persisted planning. Give the optional multi-agent experiment one sentence.*

We selected tool use because joins, units and allocation arithmetic require exact code. Agentic RAG lets the investigator choose a query and investigate again when the retrieved evidence is inadequate. Planning and reflection preserve the hypothesis, observation and reason for changing direction.

Human review controls the final decision, and checkpoints support recovery. We begin with one bounded investigator. A collector and auditor pair remains an optional experiment because collaboration must demonstrate enough quality improvement to justify its extra cost and complexity.

### Slide 6: Worked investigation

**Time:** about 60 seconds. **Priority:** Core example.

*Presenter cue: Point to 55 kg first. Pause before introducing the 25 kg. Finish on the remaining 20 kg gap.*

Consider this synthetic example for one metal. The supplied target is 100 kilograms. The dossier supports a 55-kilogram allocation, and two records describe that same allocation. We count it once. A separate 25-kilogram item has payment evidence but still lacks supported transfer or allocation evidence.

Initially, supported fulfillment stays at 55 kilograms, the apparent gap is 45 kilograms and the 25 kilograms remain pending. The investigator traces the certificate and allocation history to determine what evidence is missing.

Only after a later evidenced and reviewed allocation can a new run support 80 kilograms, leaving a 20-kilogram gap. A payment or newer account snapshot alone cannot produce that change. If the evidence never arrives, the correct response is to abstain on the unresolved amount and identify the next evidence needed.

### Slide 7: Data sources and evidence intake

**Time:** about 35 seconds. **Priority:** Important foundation.

*Presenter cue: Explain the three source roles. Avoid reading individual document titles.*

We separate three types of data. Official Gazette instruments and CPCB guidance provide the regulatory basis. Synthetic producer dossiers provide operational evidence, such as obligations, certificate events, allocations and account snapshots. Public aggregate statistics provide context only.

During intake, we preserve original files and account for their pages and rows. A corrupt file or missing page must remain an explicit evidence problem. It cannot silently become zero activity. We also retain applicability, source locators and rights-review status.

### Slide 8: Retrieval and memory

**Time:** about 40 seconds. **Priority:** Explain trust in RAG.

*Presenter cue: Trace the retrieval sequence, then summarize the two memory types in one sentence.*

Retrieval begins with the frozen, authorized corpus. We filter for the relevant role, regime and period, then use a lexical search baseline. Retrieved clauses expand to include necessary headers, footnotes and amendments.

We assess authority, temporal applicability, direct support, completeness and contradiction separately. If support remains weak, the investigator can reformulate the query within its budget. Dense retrieval will be an experiment rather than an assumed improvement.

Working memory stores the current plans, observations and checkpoints. Persistent history stores evidence and decisions. A previous interpretation still needs support in the current run.

### Slide 9: Deterministic tool plan

**Time:** about 40 seconds. **Priority:** Explain representative tools.

*Presenter cue: Explain certificate tracing and reconciliation. Mention the other tools without reading every API name.*

The tool plan exposes a small set of typed operations. Evidence inspection returns source values and locators. Locator lookup resolves a provision against a particular applicability basis. Certificate tracing reconstructs observations, lifecycle events and allocation history.

Reconciliation then calculates the required, supported and pending quantities using exact decimals. Return comparison checks figures and section readiness. Each tool returns structured results, provenance and explicit errors. The investigator cannot hide a liability by selecting a convenient subset of records, and it cannot edit the original evidence.

### Slide 10: Execution limits and human review

**Time:** about 25 seconds. **Priority:** Mention safeguards briefly.

*Presenter cue: Emphasize bounded autonomy and human authority. Do not explain every review transition unless asked.*

Autonomy remains bounded. The default is eight investigative tool actions per finding and two query reformulations, with additional limits on retries, time and cost. The model proposes checks and findings through controlled interfaces. Human decisions bind to the exact report and inputs, so approval never transfers to changed evidence. Audit failure stops progress.

### Slide 11: Evaluation design

**Time:** about 60 seconds. **Priority:** Core evaluation explanation.

*Presenter cue: Point to 48 and the development/held-out split. Explain what the comparison isolates.*

Our planned pilot contains 48 synthetic dossiers, split into 24 development cases and 24 held-out cases. They cover all sixteen fault families, including clean controls, duplicate observations, legitimate certificate stages, expired or cancelled instruments, missing evidence and prompt injection.

We compare deterministic reconciliation, fixed retrieval with tools, the bounded investigator and optionally the collector and auditor variant. Every variant receives the same visible inputs. This lets us test whether adaptive investigation adds value beyond calculation and fixed retrieval.

Expected results come from independent reviewed calculations and fixtures. The investigator cannot access oracle files or hidden labels. The oracle also distinguishes what happened in the synthetic world from what visible evidence actually justifies, so a correct abstention can score better than an unsupported guess.

### Slide 12: Quality metrics

**Time:** about 55 seconds. **Priority:** Core success criteria.

*Presenter cue: Explain arithmetic, detection and evidence support. Mention efficiency metrics at the end.*

We will judge quality at several levels. Exact balance agreement checks each eligible bucket against an independent decimal reference. Precision measures how many reported discrepancies are correct, while recall measures how many reference discrepancies the system detects.

We also assess whether resolutions are supported and whether the system abstains appropriately when evidence is insufficient. Citation checks ask both whether a source supports the claim and whether it applies to the correct role and date. Unsupported claims, prohibited verdicts and forbidden action attempts are recorded explicitly.

Alongside quality, we will report investigative steps, latency, cost and repeated-run reliability. Complete evidence accounting and audit coverage are acceptance gates. These are planned measurements. We are not claiming accuracy or performance results yet.

### Slide 13: Acceptance and ownership

**Time:** about 25 seconds. **Priority:** Brief close.

*Presenter cue: State the acceptance gates clearly. Mention the division of work quickly, then look up for the closing line.*

Our acceptance gates are exact supported arithmetic, complete evidence and audit accounting, and zero prohibited verdicts in released reports. Abhishek leads orchestration and correctness, Sushanth handles data generation and RAG, Vedanth builds the tools, and Sampreeth handles the remaining evidence, audit and review work. The intended outcome is a traceable, human-reviewed investigation, with uncertainty kept explicit. Thank you.

## If you are running short

Keep the main explanations on slides 3, 4, 6, 11 and 12. On slide 5, give one sentence each for tools, RAG and planning, then mention that multi-agent collaboration is optional. On slides 7–9, summarize the evidence roles, applicability checks and exact tools without listing each row. Give slide 10 one sentence about budgets and human approval. Close on the three acceptance gates on slide 13.

Do not skip the evaluation plan or present configuration limits as measured results.

## Backup slide speech

### Slide 14: Operating metrics

*Use only if asked about efficiency, repeatability or audit completeness.*

For operating performance, we will report average investigative steps, latency percentiles and provider cost per task. Repeated trials test reliability. Evidence coverage and audit coverage use explicit inventories rather than final citations alone. Unknown cost or coverage remains unknown, and failed trials remain in the report.

### Slide 15: Sources and limitations

*Use only if asked about source authority, legal scope or remaining decisions.*

Our planned corpus uses official Gazette instruments and CPCB materials, with reviewed applicability. Technical references support the retrieval and checkpoint choices. The pilot remains synthetic-only. Exact equipment codes, source permissions, profile activation and model selection still require review and evaluation.

## Likely questions and short answers

**What makes this agentic?**

The investigator selects the next check, assesses its result and revises the investigation. We preserve plans, observations and revisions. The calculations remain deterministic.

**Why begin with a single investigator?**

It gives us a clear baseline with simpler integration and lower coordination overhead. We will compare the optional collector/auditor variant under the same evidence and budget rules before adopting it.

**Why is payment insufficient for the 25 kg?**

A payment supports a commercial fact. Supported fulfillment needs eligible allocation evidence. We retain the paid amount as pending until the evidence supports that allocation.

**Can a newer portal balance establish the allocation?**

It can show a reported account position and support a comparison. Our initial calculation profile uses the allocation ledger, so an aggregate balance cannot create missing allocation history.

**How will you obtain realistic data?**

We plan original synthetic dossiers with connected evidence and controlled faults. We have not verified a public producer transaction dataset for this project. Authorized real cases would require permission and separate evaluation.

**How do you prevent benchmark leakage?**

The runtime cannot access oracle files, generator seeds, hidden labels or answer-bearing filenames. The evaluator scores only after run artifacts close. Independent reference calculations establish expected results.

**How do you handle outdated or contradictory rules?**

Freeze the source corpus, expand relevant amendments and assess clause-specific temporal applicability. Missing or conflicting authority triggers an unresolved finding or expert review.

**Which model are you using?**

No provider/model has been selected yet. We need reliable structured responses, validated tool proposals, suitable context, usage reporting and bounded failure handling. Selection requires representative evaluation.

**Can the LLM change quantities or approve its own report?**

No. The dispatcher exposes typed, capability-scoped checks and new derivations. Original records and trusted review actions remain protected. Human decisions bind to exact report and input hashes.

**What are your results so far?**

This is a design and evaluation plan. Accuracy, latency and cost remain unmeasured. The next milestone is the data foundation and deterministic baseline, followed by retrieval and bounded investigation.

**What does “zero prohibited verdicts” mean?**

Released reports must not contain agent-authored legal-compliance verdicts, intent/fraud/concealment allegations or compensation amounts. Rejecting a generated candidate is recorded, and the report cannot publish that prohibited conclusion.

## Rehearsal checklist

- Rehearse the architecture by pointing to inputs, evidence foundation, investigator, tools and human review in that order.
- Say the example without looking at the slide: 100 target, 55 supported, 25 pending, 45 gap. Only supported allocation changes fulfillment to 80 and the gap to 20.
- Explain precision as “how many flagged findings are correct” and recall as “how many reference issues we found.”
- Finish within the time limit once with normal pauses. Shorten secondary sections before speeding up the core explanation.
- End on slide 13. Keep the two backup slides available for questions rather than presenting them automatically.
