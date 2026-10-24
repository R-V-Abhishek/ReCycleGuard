# CP0 boundary publication

Protocol: **1.1**. Payload schema generation: **1.0**. This is the A02 review
candidate; four-member acceptance is recorded under `docs/checkpoints/checkpoint-0/`.
Do not infer CP0 approval from schemas being present or CI passing.

Generate with `uv run scripts/export_schemas.py`; check with
`uv run scripts/export_schemas.py --check`. Fifty schemas cover common context,
results, evidence, sources, receipts, extraction/coverage, the starter normalized
record subset, dossier manifests, pinned references, snapshot shape, audit and
calculation/finding interchange. Models are the source of truth. Cross-field and
calendar checks also run in Pydantic and cannot all be expressed in JSON Schema.

The scope is deliberately limited. Full calculation-profile policy, unsupported
record families, richer adapter-specific observation payloads and provider output/
usage/timing schemas require a reviewed publication before consumers use them.
`SnapshotRef`/`ProfileRef` and the operation envelopes are CP0 binding conventions;
they do not implement persistence, approval, authentication or C11 recovery.

Common nullable fields are required unless their model supplies an explicit default.
Defaults on optional domain payload fields implement the specification's optional
fields. The record discriminator rejects unknown record types. Generic service
results are illustrated for Quantity, ExtractionResult and CalculationResult.
