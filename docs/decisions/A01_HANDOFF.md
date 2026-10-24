# A01: package and interface scaffold

Owner: R V Abhishek. State: **IN_REVIEW**. CP0 remains **WAITING**.
Independent reviewer: pending; no four-way interface acceptance is claimed.

## Delivered boundary

- Installable Python 3.11+ package, Typer CLI, Pydantic core proposal, committed
  `uv.lock`, and CI on Python 3.11/3.12.
- Strict protocol 1.1 context/result/error/blob/evidence/locator/quantity/time
  models and generated schemas. Extra fields, unsupported protocol versions,
  float quantities and incompatible dimensions fail validation. Required nulls
  remain distinct from omission. Signed quantities are permitted at this common
  boundary; later certificate/allocation payloads must enforce nonnegative values.
- Read-only `doctor` and `validate` commands. Preflight checks SQLite FTS5 using
  an in-memory database, displays resolved roots and reports gateway unavailable.
  Paths are configuration, not a claim of an implemented access-control sandbox.
- C10 `ModelPort` protocol and a scripted adapter under `tests/support` only.
  Explicit test mode/enablement is mandatory. Exhaustion fails; operation/attempt
  mismatches fail without consuming responses. Unknown usage remains null.
  This adapter does not perform provider calls, audit capture or retries.
- Local runtime/evaluation config rejects test-adapter enablement. Runtime wheels
  exclude tests, fixtures, benchmarks, hidden truth and OCR/model weights.

## Verification

From the repository root:

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run scripts/export_schemas.py --check
uv run recycleguard --version
uv run recycleguard doctor
uv run recycleguard validate command-context tests/fixtures/visible/a01/command_context.json
uv run recycleguard validate quantity tests/fixtures/visible/a01/quantity.json
uv build
```

Local verification on Python 3.12.13: **51 tests passed**, Ruff lint/format passed,
11 generated schemas matched, CLI smoke checks passed and `uv build` produced a
wheel and source distribution. A fresh separate environment passed `uv sync --locked`
and the same tests/checks. A non-editable install resolved from site-packages; wheel
inspection confirmed that tests, benchmarks and scripted adapters are excluded.
CI provides a separate Python 3.11/3.12 check, not assumed success.
Fixtures under `tests/fixtures/visible/a01` include successful, partial and rejected
`ServiceResult[Quantity]` examples. They are schema examples, not calculator results.

## A02 integration checklist

A02 stays blocked until A01, H01, S01 and V01 are accepted. Do not approve CP0
from A01 tests alone. Revalidate all producers/consumers, publish remaining models
and record four independent handoff acknowledgements before freeze.

Vedantha's [PR #2](https://github.com/R-V-Abhishek/ReCycleGuard/pull/2), inspected
at commit `3dc77fd9abd9281fef357655877b6682c5aeaac2`, adds a storage prototype and
also starter `pyproject.toml`, `__init__.py`, `cli.py`, `config.py`, `model_port.py`.
It is not merged by A01. During integration:

1. Retain A01's package/dependencies/lock/CLI and reconcile shared-file conflicts;
   do not replace the prototype storage implementation as part of this task.
2. Review storage's dataclass `BlobRef`/`AuditContext` and result shapes against
   Pydantic `BlobRef`/`CommandContext`/`ServiceResult`. Do not assume structurally
   similar classes enforce the same validation or authority semantics.
3. Replace or adapt prototype `RuntimeRoots` only with producer/consumer tests.
   Runtime configuration must not gain benchmark truth access. Inspect imports
   before removing the prototype type.
4. Incorporate V01's independent arithmetic and audit/metric handoff fixtures,
   H01's receipt/observation/source fixtures and S01's visible dossier/record
   fixtures. This PR does not supply their outputs or mark their reviews complete.
5. Resolve richer snapshot/profile, calculation, finding, audit, model-output,
   usage/timing schemas with their owners; this subset is deliberately not frozen.

## Dependency direction and local OCR

Base runtime dependencies are Pydantic and Typer. Developer tools are pytest
and Ruff. LangGraph is deferred to its workflow task; no inference, CUDA, Torch,
Paddle or OCR package/weights are installed by A01.

Abhishek's current extraction direction is to evaluate locally runnable, light
VLM/OCR options on 16 GB machines, including quantized Chandra-OCR or PaddleOCR
candidates. Neither has been selected or measured here. The extraction owner
should isolate backend-specific dependencies from the base package, preserve
original bytes/coverage/failed-page receipts and measure actual memory/accuracy
before enabling an adapter. A01 makes no OCR or 16 GB compatibility claim.
