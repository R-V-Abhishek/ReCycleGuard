# Runtime configuration

A01 reads `RECYCLEGUARD_DATA_ROOT`, `RECYCLEGUARD_INTAKE_ROOT`,
`RECYCLEGUARD_OUTPUT_ROOT`, `RECYCLEGUARD_MODE` and
`RECYCLEGUARD_ENABLE_TEST_ADAPTERS`. Default mode is `runtime`; test adapters
require both mode `test` and explicit enablement. Evaluation mode rejects them.
No provider/model is selected. Do not put credentials or benchmark truth roots
in this configuration. Root access enforcement and production handlers belong
to later tasks; `doctor` only resolves/displays roots and checks in-memory FTS5.
