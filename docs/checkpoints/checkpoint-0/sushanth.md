# Sushanth S: S01

Normalization, deterministic tools and synthetic-data workstream. USN: 1BM23CD063.
Input: PR #4, commit `15c7dd6c389e8021e5aa79d7be1ac696485b55bd`.

## Submitted work

- One fictional producer dossier with entities/registrations, a supplied 100 kg
  copper obligation, one 55 kg supported allocation, two observations of its
  transfer, a 25 kg financial/pending record and a dated account comparison.
- Visible JSONL records, a CSV ledger, a synthetic invoice PDF and a measured
  asset manifest; expected reference amounts stored separately.
- Starter-world and PDF/invoice builders, seven deterministic invoice themes,
  a mandatory synthetic watermark and seven initial verification tests.
- Reference example: 100 required, 55 supported, 45 gap and 25 pending, with F02
  overlapping observations and F07 financial evidence lacking supported allocation.

## How A02 connected and repaired it

Eight normalized record families now validate against shared Pydantic consumers.
Date precision, ingestion timestamps and header-excluding CSV row numbering were
corrected. A02 supplied the missing portal JSON, visible source rows, remaining
observations, artifact references and synthetic receipt examples so every record's
source observations resolve to actual originals. The visible pack now has 16 assets.

Both transfer observations retain the same explicit external transaction ID;
sharing an instrument alone is not used as equivalence proof. Distinct lifecycle
IDs remain separate, and the 25 kg financial record does not create another
supported allocation. A typed derived CreditLot example remains developer-only.

The manifest is DRAFT with cut-offs, adapter versions and evidence expectations.
Its prior pre-freeze bytes remain in the submitted Git revision; no accepted
snapshot was mutated. Renderer reproducibility is tested against the integrated
pack. PDF checks use a development dependency; benchmark imports do not become
runtime package imports. Test formatting and numeric parsing were reconciled with CI.

## Handoff

S01 is DONE through the lead's reported all-four acknowledgement. With CP0
approved, S02 and S05 are READY; this record does not start either task. The initial expected JSON came from
the generator submission; A02's separate Fraction reference is an additional
check, not a production C08 result. Team acknowledgement was subsequently reported
by Abhishek and is recorded in the approval ledger.
