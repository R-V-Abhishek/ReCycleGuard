# Final report skeleton (IEEE style, 8-12 pages)

Status: **skeleton.** Structure follows `PROJECT_GUIDELINES.md` section 7. Prose marked *draft* comes
from the repository and must be rewritten by its owner. Every result cell is
`NOT YET MEASURED` until the CP6 tables exist; fill cells only from `tables/*.csv` produced by
`scripts/make_tables.py`, never by hand. Honest negative results are acceptable (guidelines section 8).

Suggested owners (an assumption, change freely): H methods and data, S results and figures,
V architecture and limitations. Numbers come from Abhishek's tables only.

## 1. Title, team, abstract
- Title, four names, team lead.
- Abstract (150-200 words): human-reviewed EPR e-waste reconciliation; a bounded agent with
  deterministic tools; V1 fixed retrieval vs V2 adaptive on 24 held-out synthetic cases with a local
  4-bit Qwen3.5-9B model; headline result: `NOT YET MEASURED`.

## 2. Problem and motivation (*draft*)
Producers, recyclers and auditors reconcile EPR obligations against certificates, transfers,
payments and portal balances. These facts are spread over PDFs, CSVs and JSON and disagree in
specific ways (overlapping exports, unpaid transfers, unit or period mistakes). The output is an
advisory working paper for a human reviewer, not a filing, a legal certificate or a fraud verdict.

## 3. Related work and existing practice
`TODO(H)`: spreadsheet reconciliation, rule-based audit tools, RAG/agent evaluation work. Cite only
sources read. State the gap: auditable, evidence-bound reasoning with refusal to guess.

## 4. Agent design and architecture
- Diagram from `docs/review_guides/01_OVERALL_ARCHITECTURE.md` and `docs/design/SYSTEM_DESIGN.md`.
- Components: intake, extraction, normalization, snapshots, index/retrieval, deterministic domain
  tools, LangGraph workflow, model gateway, audit kernel, reports/review, export/replay.
- Pattern: plan -> act (allow-listed tool) -> observe -> assess, bounded by budgets. Models propose;
  deterministic tools compute; a gate accepts or rejects finding proposals.

## 5. Agentic concepts demonstrated
Checklist with evidence pointers (trace event, test, doc) for: planning, tool use, observation,
adaptation (revised plan, reformulation), memory/state, guardrails, human in the loop, evaluation.

## 6. Implementation
Stack, data model (immutable originals, decimal quantities, pinned runs), loop bounds
(`evaluation_budgets`: 12 calls, 600 s, 32768 tokens/call), host sandbox for real-model runs.

## 7. Observability and evaluation
Traces and the UI timeline; metrics and denominators from `docs/evaluation/PROTOCOL.md`.

| Table | Source file | Status |
| --- | --- | --- |
| T1 primary success by variant | `t1_primary_success.csv` | NOT YET MEASURED |
| T2 exact reconciliation | `t2_exact_reconciliation.csv` | NOT YET MEASURED |
| T3 findings and abstention | `t3_findings_and_abstention.csv`, `t3_findings_micro.csv`, `t3_findings_macro.csv`, `t3_findings_per_family.csv` | NOT YET MEASURED |
| T3 model influence | `t3_model_influence.csv`, `t3_proposals_rejected.csv` | NOT YET MEASURED |
| T4 clean cases, abstention, unsupported claims, forbidden actions | `t4_clean_and_unsupported.csv`, `t4_forbidden_actions.csv` | NOT YET MEASURED |
| T5 rubric (citation, temporal, next action) | `t5_rubric.csv`, from blind sheets + `benchmarks/evaluation/rubric.py`; absent until scored | NOT YET MEASURED |
| T6 efficiency | `t6_efficiency.csv`, `t6_model_calls.csv` | NOT YET MEASURED |
| T7 reliability across repeats | `t7_reliability_across_repeats.csv` | NOT YET MEASURED |
| T8 failure taxonomy | `t8_failure_classes.csv`, `t8_outcome_taxonomy.csv` | NOT YET MEASURED |

Template for T1 (copy the CSV, do not type values):

| Variant | Scheduled | Scored | Successes | Success rate | Preflight blocks |
| --- | --- | --- | --- | --- | --- |
| V1 | NOT YET MEASURED | NOT YET MEASURED | NOT YET MEASURED | NOT YET MEASURED | NOT YET MEASURED |
| V2 | NOT YET MEASURED | NOT YET MEASURED | NOT YET MEASURED | NOT YET MEASURED | NOT YET MEASURED |

Report the paired case-level bootstrap interval for V2 minus V1, with and without the two preflight
cases. Undefined values are `NA`, never 0 or 1. Money is `NA` (local, not metered).

## 8. Experimentation
V1 vs V2 design, the decision it informs, repeat rule (PROTOCOL section 5), what changed before the
freeze (prompt v5 -> v6 on **development cases only**, v5 results kept as baseline). Say plainly that
one person built, ran and evaluated the system and how blind teammate scoring limits that.

## 9. Limitations, ethics, safety
Synthetic data and the limited separation of dev and held-out sets (same generator); small corpus
(2 sources); a single 4-bit local model; advisory output only; prompt-injection handling and
the sandbox; rights state of R02/R08 (`REVIEW_REQUIRED`).

## 10. Conclusion and future work
`NOT YET MEASURED`: conclusion depends on CP6. Future work: more sources, a second model, independent
dataset authors.

## 11. References and contribution table
Cite the models, libraries, datasets and rules used. Contribution table from
`docs/individual_contribution/`.
