# Slides outline (Review 4, Sat 7 Nov 2026)

Status: **outline.** Result slides stay `NOT YET MEASURED` until CP6; numbers are copied from
`tables/*.csv`. Target about 12 slides plus a live demo and a recorded fallback.

| # | Slide | Content | Source |
| --- | --- | --- | --- |
| 1 | Title and team | names, roles | report section 1 |
| 2 | Problem | EPR reconciliation, who decides, why it is hard | report section 2 |
| 3 | What it does | input dossier -> advisory working paper -> human review | UI screenshots |
| 4 | Architecture | components and the model/tool boundary | `docs/review_guides/01_*` |
| 5 | The agent loop | plan, act, observe, assess; budgets; stop reasons | `03_AGENT_HARNESS_*` |
| 6 | Safety | untrusted text, allow-listed tools, host sandbox, human approval | PROTOCOL, MG1 isolation |
| 7 | Data | synthetic pilot: 48 dossiers, 24 dev / 24 held-out, 16 fault families | `docs/data/dataset_card.md` |
| 8 | Experiment | V1 fixed vs V2 adaptive, same tools and budgets | PROTOCOL sections 2, 5 |
| 9 | Results | T1 and bootstrap interval: NOT YET MEASURED | `t1_*.csv` |
| 10 | Failures | taxonomy, reliability, what the model got wrong | `t8_*.csv`, `t7_*.csv` |
| 11 | Honest limits | one author, synthetic, small corpus, local 4-bit model | report section 9 |
| 12 | Conclusion and next steps | NOT YET MEASURED | report section 10 |

## Demo (about 4 minutes)
1. Connect, select a dossier, open the readiness view.
2. Start a run; show the live timeline with model-call latency and tokens.
3. Open the report: claims with support status, evidence chips opening the original page.
4. Open the review packet; submit a decision with the fixture reviewer (never call it a team approval).
Fallback: replay a recorded run (`RecordedReplayModelPort`), same screens, no model needed.

## Likely questions (every member may be asked about any component)
- Why can the model not approve evidence or compute amounts? (deterministic tools, finding gate)
- How do you know the held-out set was not used for tuning? (freeze manifest, ledger, dev-only v6)
- What happened to V2? (answer from T1, T8; negative results are valid)
- What does one person building and evaluating mean for validity? (blind scoring, disclosure)
