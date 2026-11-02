# Held-out numeric reference spot-check (V09-h)

Purpose: a human confirms the generator's reference arithmetic for the 24 held-out dossiers. It is a
**separate attestation**; the reference status stays `INDEPENDENT_REFERENCE_VALIDATED`
(agent-reviewed) unless a record below says otherwise. No model is involved.

## Who and when
Two teammates (not the person who ran the trials), done **after the CP5 freeze and before the first
held-out model run**. They see the held-out dossiers and reference numbers, so they must not change
code, prompts or the generator afterwards.

## Procedure
1. The evaluator exports, for each held-out case, the visible dossier path and the reference
   numbers per bucket (required, supported, signed gap, shortfall, surplus, pending, portal, delta)
   into a private sheet outside Git.
2. For each case the teammate recomputes the bucket numbers by hand or spreadsheet from the visible
   files, using exact decimals and the rules in `docs/design/CONTRACTS.md`.
3. Record agreement per bucket: `AGREE`, `DISAGREE` (with the value found) or `CANNOT_CHECK`
   (with the reason). Do not edit the reference.
4. Any `DISAGREE` stops the held-out run for that case until the evaluator decides whether it is a
   generator defect. A defect after the freeze means a new dataset version and a new seal.

## Record (copy, fill, keep private; commit only the digest of the signed file)
```json
{
  "record_version": "v09h-1",
  "dataset_version": "pilot-0.1",
  "seal_aggregate_sha256": "90e2c5c3a430f95ebca609f88da1616c070ecd383bf5cb3b45dc6a2c3a54619d",
  "reviewers": [{"name": "", "date": ""}, {"name": "", "date": ""}],
  "cases_checked": 0,
  "cases": [{"case_id": "", "buckets_agree": 0, "buckets_disagree": 0, "cannot_check": 0, "notes": ""}],
  "outcome": "NOT_YET_DONE"
}
```
Allowed outcomes: `ALL_AGREE`, `DISAGREEMENTS_RESOLVED`, `OPEN_DISAGREEMENTS`, `NOT_YET_DONE`.
