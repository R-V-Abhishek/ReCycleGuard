# A01 schema proposal

Generated from Pydantic boundaries using `uv run scripts/export_schemas.py`.
Check drift using `uv run scripts/export_schemas.py --check`.

These schemas implement the common subset of protocol 1.1, not a CP0 freeze.
The directory name describes payload-schema generation; it is not protocol 1.0.
All nullable fields are required unless the model explicitly supplies a default.
Higher-level receipt/observation, calculation, finding, snapshot/profile and audit
models must be reconciled with H01/S01/V01 in A02. No placeholder models claim
those services exist. `ServiceResult_Quantity` demonstrates the generic envelope;
other consumers parameterize it with their approved output model.

C10 usage/timing and validated-output schemas remain proposals: the seam retains
JSON values without inventing a provider schema, usage or execution history.
Strict output-schema validation belongs to the eventual C10 implementation.
