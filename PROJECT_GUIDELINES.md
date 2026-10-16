# Agentic AI Mini-Project Guidelines

**Project-Based Cumulative Assessment (CIE)**

| Item | Details |
| --- | --- |
| Course | Agentic AI |
| Course code | 26CD7PEAAI |
| Programme | B.E. CSE (Data Science) |
| Semester / academic year | VII / 2026–27 |
| Department / institution | CSE (Data Science), BMSCE |
| Instructor | Dr. Kalyan Nagaraj |
| Assessment | Team project, assessed cumulatively |
| Final maximum marks | 10 (scaled from four reviews) |

> **Source note:** This is a formatting and organization of the instructor's guidelines supplied for this project. PDF page headers, footers, and line-wrap artifacts have been removed. Requirements, dates, marks, and distinctions between mandatory and bonus concepts are preserved.

## At a glance

In teams, design, build, observe, evaluate, and report a small but complete agentic AI system solving a non-obvious, niche-sector problem. Assessment is continuous across **four reviews, each out of 10**, averaged to a final score out of 10. Teams and the selected problem area are defended and locked at **Review 1 on Friday, 16 October 2026**. All reviews and presentations take place on Fridays or Saturdays. The final review is **Saturday, 7 November 2026**; all final artifacts are due by **Thursday, 12 November 2026**.

## 1. Objective and learning outcomes

Apply the course's agentic AI concepts end to end, rather than merely describing them. By completing the project, students should be able to:

- Frame a real niche problem as an agentic task and justify why an agent is appropriate rather than a plain script or single LLM call.
- Design and implement an agent using tools, agentic retrieval-augmented generation (RAG), a planning/reasoning loop, and ideally multi-agent collaboration.
- Demonstrate trustworthy, production-minded behavior through observability/tracing, evaluation, guardrails, human-in-the-loop review, and a basic experiment.
- Work as a team, defend design decisions, and communicate results through a clear technical report and demonstration.

## 2. What to build

Build a **small, working agentic system**, not a toy chatbot or a research thesis. Keep the scope focused enough to finish and demonstrate. The system must visibly **plan, act using tools, observe results, and adapt**. Instrument it so this behavior can be inspected through traces, logs, and evaluations, and report the full process.

> **Core requirement:** A reviewer must be able to watch the agent plan, call a tool, retrieve and use evidence, catch a mistake or weak result, and stop sensibly. A wrapper around one LLM prompt will not pass, however polished its interface.

## 3. Teams

- Form teams of **3–4 students**. Individual submissions are not permitted.
- Nominate a **Team Lead** responsible for coordination and submissions.
- Maintain a clear contribution split identifying the owner of each component.
- Every member must be able to explain the **whole system** in the viva, not only their own component.
- Finalize team composition and the selected problem area at Review 1 on **16 October 2026**. Later changes require instructor approval.

## 4. Choosing a niche problem

Choose a niche sector where agentic AI can make a meaningful difference. The problem should naturally require multiple steps, more than one knowledge source, tools or computation, and grounding and verification.

- If one prompt could answer it, the scope is too small.
- If it needs a research lab and a year, the scope is too large.
- Specify the exact sub-problem, data, tools, and **one decision** the agent supports.
- Original proposals are encouraged; the idea bank below is inspiration, not a menu to copy blindly.

### Discouraged themes and the alignment gate

Generic customer-support chatbots, résumé screeners, movie/product recommenders, plain “chat with your PDF,” generic code assistants, FAQ bots, and me-too personal assistants will not clear the Review 1 alignment gate unless a genuinely distinctive, defensible agentic problem is established.

### Curated niche idea bank

| # | Idea and sector | Problem | Natural agentic concepts |
| --- | --- | --- | --- |
| 1 | Seed/vaccine cold-chain compliance auditor — agri-logistics and regulatory | Inspect cold-storage sensor logs against seed-certification or cold-chain SOPs, flag breaches, and draft corrective-action notes. | Sensor queries, regulatory RAG, planning, human sign-off. |
| 2 | Handloom GI-tag provenance verifier — textiles and intellectual property | Cross-check authenticity claims against weaver registries, GI documents, and supply records; produce evidence-linked verdicts. | Multi-source retrieval, tools, grounded verification, abstention. |
| 3 | Shrimp-pond disease early-warning advisor — aquaculture | Reason over water-quality telemetry, a disease-symptom knowledge base, and farmer logs to raise warnings and graded interventions. | Monitor/diagnostician/advisor agents, tools, RAG, planning, memory across visits. |
| 4 | Parametric crop-insurance claims triage — insurance/fintech | Compare weather-index and satellite-rainfall data with policy wording to assess payout triggers with cited rationale. | Data APIs/files, policy RAG, corrective reasoning, human review of edge cases. |
| 5 | Mine-closure environmental-compliance tracker — mining/environment | Compare statutory obligations with site-monitoring data, flag lapses, and draft periodic compliance returns. | Statutory-plan RAG, tools, planning, persistent obligation memory. |
| 6 | Smallsat ground-station pass and anomaly triage — space operations | Plan downlink passes and triage telemetry anomalies against a fault knowledge base. | Scheduling, tools, fault-tree RAG, planner/triage collaboration. |
| 7 | Agricultural land-record dispute pre-diagnosis — legal-tech | Combine digitized land records, survey maps, and tenancy provisions to identify likely dispute types and required evidence. | Multi-source RAG, planning, grounding, abstention, human review. |
| 8 | Rooftop-solar net-metering interconnection screener — DISCOMs | Pre-screen applications using interconnection SOPs and feeder-capacity data; list missing information. | SOP RAG, capacity checks, planning, structured-output validation. |
| 9 | E-waste EPR compliance reconciliation — circular economy/environment | Reconcile producer EPR targets against recycler certificates under applicable rules and explain shortfalls. | Reconciliation tools, rule RAG, collector/auditor collaboration, evaluation. |
| 10 | Palm-leaf/epigraphy transcription QA — digital humanities/heritage | Check manuscript OCR/transcription against script dictionaries and palaeographic rules; flag uncertain glyphs. | OCR tools, reference RAG, reflection/self-correction, expert review. |
| 11 | MSME invoice-anomaly working-capital agent — supply-chain finance | Detect invoice/GST anomalies and reason over eligibility rules for auditable pre-qualification. | Anomaly tools, rule RAG, planning, financial-claim guardrails. |
| 12 | Post-disaster building-safety triage — disaster response/structural | Combine rapid inspections and safety codes into graded, cited recommendations for responders. | Code RAG, planning, strict human confirmation, abstention. |

**Make the idea your own:** Narrow it to a specific, defensible sub-problem. A sharply scoped agent with visible agentic behavior can outscore an ambitious system that only half works.

## 5. Agentic concepts to demonstrate

Cover **all mandatory concepts**. Bonus concepts can strengthen the assessment when justified.

| Tier | Concept | Required evidence of demonstration |
| --- | --- | --- |
| Mandatory | Tool/function use | Call at least one real tool—search, calculator, database, API, or code—and use its result. |
| Mandatory | Agentic RAG | The agent decides what to retrieve and grades, re-queries, or falls back when context is weak. |
| Mandatory | Planning and reasoning | An explicit ReAct, plan-and-execute, or reflection loop is visible in the trace; a single-shot response is insufficient. |
| Mandatory | Observability/tracing | Capture every run as an inspectable trace of steps. |
| Mandatory | Evaluation | Define output-quality assessment, such as rule-based metrics, an LLM judge with a rubric, or a small golden dataset. |
| Bonus | Multi-agent collaboration | Two or more specialized agents with clear conversation or supervisor coordination. |
| Bonus | Memory | Short-term working memory and/or persistent memory across runs. |
| Bonus | Human-in-the-loop and guardrails | Human approval for risky or irreversible steps, bounded loops, and input/output validation. |
| Bonus | Durable workflow | A checkpointed, resumable multi-step workflow, potentially with parallel steps. |
| Bonus | Experimentation | A small A/B test or offline-versus-online comparison with a reasoned decision. |

### Tooling

Any reasonable stack is allowed: LangChain/LangGraph, AutoGen/AG2, CrewAI, LlamaIndex, or custom orchestration; any LLM provider or local open model is acceptable. Assessment concerns behavior and evidence, not the framework brand. Keep costs manageable, mock external services where needed, and bound every loop.

**Production-thinking expectation:** Although deployment to real users is unnecessary, demonstrate tracing, evaluation, bounded loops, and at least one of human-in-the-loop approval, a durable workflow, or experimentation.

## 6. Assessment and schedule

There is no single final-day assessment. Marks accumulate across four reviews:

```text
Final CIE (out of 10) = (R1 + R2 + R3 + R4) / 4
Each Ri is between 0 and 10.
```

Steady progress matters. Missing or under-preparing for a review can reduce the marks earned across the assessment.

| Review | Focus | Present or submit | Date |
| --- | --- | --- | --- |
| R1 | Problem and area defense | Exactly 5-minute defense and 1-page Problem Charter | Friday, 16 October 2026 |
| R2 | Design and architecture | Architecture, patterns, data/tools, evaluation plan | Saturday, 24 October 2026 |
| R3 | Prototype and observability | Working core loop, tracing, one feedback loop; live demo | Saturday, 31 October 2026 |
| R4 | Final system, experiment, report | Full system, evaluation, experiment, report, demo | Saturday, 7 November 2026 |
| Final submission | All final artifacts | Report PDF, slides PDF, code repository link/archive with README and run instructions | Thursday, 12 November 2026 |

All reviews and presentations are on Fridays or Saturdays. **No review or presentation is scheduled after the final submission deadline.**

### Review 1 defense and alignment gate

Use exactly **5 minutes** to defend:

1. The selected niche area and why it matters.
2. The specific problem and the one decision the agent supports.
3. Why it is agentic, mapped to the concept checklist.
4. Feasibility: available data/tools and realistic scope.

An obvious, non-agentic, or infeasible topic must be revised and defended again. Prepare a strong primary idea and a backup. Team composition and the problem area are locked at Review 1.

### Review rubrics

#### R1 — Problem and Area Defense

| Criterion | Marks |
| --- | ---: |
| Niche-ness and originality: non-obvious, impactful area | 3 |
| Agentic fit: clear mapping to required concepts | 3 |
| Problem clarity and decision supported | 2 |
| Feasibility and team plan: scope, data/tools, roles | 2 |
| **Total** | **10** |

#### R2 — Design and Architecture

| Criterion | Marks |
| --- | ---: |
| Architecture soundness: agent/graph, components, data flow | 3 |
| Deliberate, correct mapping to agentic patterns: RAG, planning, multi-agent | 3 |
| Realistic, specified data sources and tool plan | 2 |
| Evaluation and metrics plan | 2 |
| **Total** | **10** |

#### R3 — Prototype and Observability

| Criterion | Marks |
| --- | ---: |
| Working core loop: live tool use, RAG, planning | 3 |
| Clear agentic behavior: visible reasoning/adaptation | 3 |
| Instrumented traces and at least one feedback loop | 2 |
| Code quality, repository hygiene, reproducibility | 2 |
| **Total** | **10** |

#### R4 — Final System, Experiment and Report

| Criterion | Marks |
| --- | ---: |
| Completeness and evaluation results: working, measured system | 3 |
| Experimentation and rigor: A/B or offline-to-online, honest analysis | 3 |
| Clear, complete, well-structured report | 2 |
| Final presentation and Q&A/viva: whole-team understanding | 2 |
| **Total** | **10** |

## 7. Deliverables

| Milestone | Required artifacts |
| --- | --- |
| R1 — 16 October | **1-page Problem Charter** covering area, problem, decision supported, agentic-concept mapping, data/tools, team, and roles; followed by the 5-minute defense. |
| R2 — 24 October | **3–5-page Design Document** with architecture diagram, selected patterns, tool/data plan, evaluation plan. |
| R3 — 31 October | Working prototype for a live demo, short trace walkthrough using screenshots or a recording, and code repository. |
| R4 — 7 November | Final system, evaluation and experiment results, final slides, report, demonstration. |
| Final — by 12 November | Report PDF, slides PDF, code repository link/archive containing README and run instructions. |

### Final report structure

Prepare an approximately **8–12-page concise technical report**, in IEEE style or the department template, containing:

1. **Title, team, abstract:** what was built, why the problem is niche, headline result.
2. **Problem and motivation:** sector, decision, value of agentic AI.
3. **Related work/existing practice:** current approaches and the gap.
4. **Agent design and architecture:** diagram, components, patterns, justification.
5. **Agentic concepts demonstrated:** explicit checklist mapping with evidence.
6. **Implementation:** stack, tools, data, key decisions, loop bounds.
7. **Observability and evaluation:** tracing, metrics, rubric, results in tables/plots.
8. **Experimentation:** variant comparison and the decision it informed.
9. **Limitations, ethics, safety:** failure modes, guardrails, responsible use.
10. **Conclusion and future work.**
11. **References and contribution table:** who did what.

## 8. Policies

### Tools and AI assistance

Agent frameworks, libraries, and AI coding assistants are permitted. Students must understand and explain every submitted component. Any member may be asked about any component in the viva. Cite external code, datasets, and models.

### Academic integrity

- **No fabricated results.** Report actual behavior; honest negative results are preferable to invented positive results and will be assessed fairly.
- **No unattributed reuse.** Cite reused code/text and distinguish the team's own contribution.
- **Each team's submission must be its own.** Sharing ideas is acceptable; sharing submissions is not.

### Responsible and safe scope

For sensitive domains such as health, law, disaster response, or finance, outputs must be **advisory and human-confirmed**, grounded in evidence, and able to abstain under uncertainty. Never present an agent output as a professional medical, legal, or financial decision.

## 9. Do's and don'ts

| Do | Don't |
| --- | --- |
| Choose a sharp, niche, defensible problem. | Choose an overdone, obvious theme. |
| Show behavior through traces. | Hide everything behind one prompt and chat box. |
| Bound loops and mock costly services where needed. | Allow unlimited loops on paid APIs. |
| Instrument evaluation early. | Judge quality only by the appearance of the demo. |
| Keep the scope small and finish it. | Over-promise a half-working giant system. |
| Share work fairly and ensure whole-system understanding. | Split work so no member can explain the complete system. |

## 10. Frequently asked questions

**Can we propose a problem outside the idea bank?** Yes. This is encouraged if it meets the agentic-problem criteria and is approved at Review 1.

**Do we need a paid LLM API?** No. Local/open models and free tiers are acceptable. Bound calls and costs; mock external services where appropriate.

**What if our topic is rejected?** Revise and arrange a prompt re-defense. Prepare a primary idea and a backup before Review 1.

**Is multi-agent collaboration mandatory?** No; it is a bonus. A well-instrumented single agent demonstrating every mandatory concept can score well. Add multiple agents only when justified.

**How production-ready must the project be?** It need not serve real users, but must show production thinking: tracing, evaluation, bounded loops, and at least one of human approval, durable workflow, or experimentation.

**What is the final deadline?** The final review/presentation is Saturday, 7 November 2026. All artifacts are due no later than Thursday, 12 November 2026. No extension or later review date is implied.
