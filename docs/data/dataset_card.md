# Dataset card: synthetic pilot `pilot-0.1`

Owner: Sushanth (S10). Status: **draft.** Facts come from `benchmarks/generator/README.md`,
`benchmarks/pilot/heldout_seal.json` and `docs/evaluation/PROTOCOL.md`. It makes no claim about
real-world prevalence of the faults or about model quality.

## What it is
48 synthetic EPR dossiers (visible PDFs, CSVs, JSON), rendered from a typed world model with exact
decimal quantities. Firms, identifiers and documents are fictional and watermarked
"SYNTHETIC - NOT A CPCB RECORD" (identity policy in the generator README).

| Part | Dossiers | Location | In Git |
| --- | --- | --- | --- |
| Development | 24 | `tests/fixtures/visible/case_<tag>/` | yes |
| Held-out | 24 | `benchmarks/heldout/visible/case_<tag>/` | no (seal only) |
| Hidden records and oracle | all | `benchmarks/hidden/` | no (regenerated) |

Each split has one dossier per fault family F01-F16 and eight combinations. The splits are grouped by
entity, template and timeline group and assigned before rendering (`GROUPED_DEV_HELDOUT_V1`).
Further hand-built and S06 development dossiers (`s04-dev-0.1`, `s05-dev-0.1`, `s06-dev-0.1`) and the
frozen `case_001` are separate dataset versions used for development and tests.

## Held-out seal
`benchmarks/pilot/heldout_seal.json` holds opaque held-out case ids and a SHA-256 per visible file
tree, aggregate `90e2c5c3a430f95ebca609f88da1616c070ecd383bf5cb3b45dc6a2c3a54619d`. It carries no labels,
families, seeds or templates. `python -m benchmarks.generator.generate --check` compares regenerated
bytes with it.

## Construction checks
Generation fails if the splits share an entity, template, combination, timeline group or world id, if
a visible name or file carries a family/recipe/seed word, if two dossiers are exact duplicates, or if a
dev/held-out pair reaches a word 5-shingle Jaccard of 0.85 (current maximum about 0.31).

## Labels and reference status
Expected buckets and findings come from the generator's world model, not from a human audit. The
reference answers are `INDEPENDENT_REFERENCE_VALIDATED` (reviewed by an agent), **not**
`HAND_REVIEWED`; a human spot-check of the held-out numeric references is a separate attestation
(`docs/evaluation/SPOT_CHECK.md`). Report the status as stated.

## Known limits (state these in the report)
- **Limited internal separation.** Templates and seeds are in the repository, so anyone with the code
  can regenerate the held-out dossiers. This is not an external or double-blind benchmark.
- Same author built the generator, the system and the evaluator.
- 24 held-out cases: results are a pilot, not a statistically powered study.
- Synthetic prices and a labelled GST assumption (`GST_RATE_ASSUMED = 18`) are for realism only.
- Two held-out cases are expected preflight stops (`F15_EXTRACTION_PAGE_LOSS`) and cannot separate
  the variants; report results with and without them.
- Synthetic dossiers cannot show how the system behaves on real producer data.

## Rights and use
Synthetic data and generator code are the team's own. Licence for the final archive is decided at
CP8 (A12). The two regulatory source documents used for retrieval are described in
`docs/data/source_data_card.md` and are not redistributed here.
