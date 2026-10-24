# A01 visible contract fixtures

These hand-authored examples test serialization and explicit incomplete/error
states. They are not a synthetic dossier, hidden answers or production outputs.
`quantity.json` supplies a sample 100 kg quantity; result examples use 55 kg only
to exercise the envelope. No reconciliation algorithm ran to create them.

- `command_context.json`: pinned service context, no human approval credential.
- `quantity.json`: exact decimal JSON string with explicit dimension/metal.
- `result_success.json`: successful envelope.
- `result_partial.json`: 55 kg value with a blocking incomplete-coverage issue.
- `result_rejected.json`: typed schema failure, null output.

Validate them with `uv run pytest tests/contracts`. Runtime wheels exclude this
folder and all expected-answer, benchmark and test-adapter files.
