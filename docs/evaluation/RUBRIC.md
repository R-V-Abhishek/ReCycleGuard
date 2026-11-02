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
