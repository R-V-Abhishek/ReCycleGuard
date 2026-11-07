# Human scoring rubric (DRAFT, frozen at CP5)

Scorers (Sampreeth, Sushanth, Vedantha) judge three things per report. They never see which variant
produced it. The automatic scorer already checks exact balances, finding families, abstentions and
forbidden actions; this rubric covers what code cannot decide.

## Your materials
- `scorer_a.csv` (or `scorer_b.csv` if you are the second scorer), one row per item.
- The visible dossier for each `case_label`, given to you by the evaluator (the label-to-case map
  stays with the evaluator). Read the original PDF/CSV/JSON cited by the report.
- Do not try to guess the variant, repeat or model behaviour. Do not discuss items with the other
  scorer until both sheets are submitted.

## Labels (fill the three columns for every row)
Use exactly `PASS`, `PARTIAL` or `FAIL`.

| Dimension | PASS | PARTIAL | FAIL |
| --- | --- | --- | --- |
| `citation_support` | Every cited reference exists in the dossier and says what the claim says | Some cited references support the claim, others are missing, vague or only loosely related | A cited reference does not support the claim, or a claim has no citation |
| `temporal_correctness` | Dates, periods and ordering the report relies on are correct and tied to the right document | Mostly correct but one date or period is unclear or unstated | A wrong date, period or ordering is used, or an expired/cancelled item is treated as valid |
| `next_action_quality` | The recommended action is specific, feasible for a reviewer and fits the evidence | Reasonable but vague, or missing one obvious step | Irrelevant, unsafe (for example files or certifies something) or contradicts the evidence |

If a report has no findings, judge `next_action_quality` on whether stating "no action" is justified
by the evidence, and `citation_support` on the report's claims.

## Rules
1. Judge the report text only, not how impressive it sounds. Uncertain wording is correct when the
   evidence is uncertain.
2. A confident claim with no support is `FAIL` for citation even if it happens to be true.
3. When unsure between two labels choose the lower and write one line in your notes.
4. Leave nothing blank. If you cannot open a cited reference, label `FAIL` and say why.

## Known limit (disclose in the report)
Variant details can leak through the report text, for example "Inspected k of n dossier
observations" differs in pattern between V1 (fixed sample) and V2. Blinding is therefore partial.

## Agreement and disputes
At least 20% of items are scored twice. The evaluator computes raw agreement and Cohen's kappa per
dimension (`benchmarks/evaluation/rubric.py`; kappa is undefined, shown as `NA`, when every label is
identical). Any item where the two scorers differ goes to the third scorer, who sees both labels.
The builder, runner and primary evaluator are the same person; this is disclosed.

## Evaluator commands
```sh
PYTHONPATH=. uv run scripts/make_rubric_sheets.py <trial-output> <sheets-dir> --seed <seed> \
  --fraction 1.0 --double-fraction 0.2
```
Choose the seed once, record it in the freeze, and keep `key.json` and `case_map.json` private.

## Reviewer briefs (Improvement 3)
A brief helps a reviewer check one finding. It never changes the finding, its numbers or the
decision. Each brief sheet row shows one finding and two briefs, `brief_1` and `brief_2`. One was
drafted by the model and checked by code; the other is the template built from the finding alone.
Their order is seeded per row and only `key.json` says which is which. Figures in both are filled
by code from the calculation, so judge the wording, the citations and the request, not the numbers.

Label each brief `PASS`, `PARTIAL` or `FAIL` on three dimensions, then fill `preferred` with `1`,
`2` or `SAME`: which brief would help you more to review the finding.

| Dimension | PASS | PARTIAL | FAIL |
| --- | --- | --- | --- |
| `citation_support` | Every cited reference exists and supports what the brief says | Some citations fit, others are loose or missing | A citation does not support the brief, or the brief relies on something it does not cite |
| `next_action_quality` | The evidence request is specific, feasible and fits the finding | Reasonable but vague, or missing one obvious item | Irrelevant, unsafe or contradicts the finding |
| `usefulness` | It tells you what to check and why, in plain words, and saves you reading time | Partly useful, or repeats the finding without adding guidance | Misleading, confusing or no help |

Rules 1-4 above apply. Only accepted model briefs are scored. Rejected and dropped model briefs are
counted in `brief_outcomes.json` and reported as the acceptance rate; for those findings the
reviewer already sees the template. Agreement uses the same 20% double-scoring:
`agreement(a, b, BRIEF_SCORES)` per brief slot, `preference_agreement(a, b)` for `preferred`, and
`brief_comparison(scores, key)` unblinds the pass rates and preferences by source.

**Known limit.** The template is recognisable: its "what to check" line is a fixed family
sentence and its evidence request repeats the finding's next action. Blinding is therefore partial;
disclose it with the results.

**Timed review (crossover).** Pick about 6 findings from the brief run, stratified by family. Each of
two scorers reviews half of them with the model brief and the other half with the template, and the
second scorer gets the opposite halves. Record minutes per finding from opening it to a written
review note, and whether the note asks for the right evidence. Report the median minutes per source
next to the rubric pass rates. With so few findings this is indicative, not a measured effect.

```sh
PYTHONPATH=. uv run scripts/make_rubric_sheets.py <brief-trial-output> <sheets-dir> --seed <seed> \
  --briefs 1 --fraction 1.0 --double-fraction 0.2
```
