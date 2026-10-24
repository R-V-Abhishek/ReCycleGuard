# CP0 verification record

Technical candidate: `c8fb512` (full SHA in the boundary manifest).
Local environment: macOS arm64, Python 3.12.13. Verified 24 October 2026.
The technical evidence below is separate from approval. CP0 approval is recorded
in `approvals.json` using the lead's subsequent all-four acknowledgement.

## Results

| Check | Observed result |
| --- | --- |
| Combined contract/unit/integration suite | 118 passed |
| Ruff lint and format check | Passed |
| Generated schema consistency | 50 matched |
| Fresh locked development environment | Install, tests, lint/format and schema checks passed |
| Base-only, non-editable runtime install | Passed; package imports from site-packages |
| Runtime dependency separation | pdfplumber absent from the base-only environment |
| Build | Wheel and source distribution produced |
| Wheel contents | No tests, benchmark code, oracle fixtures, test adapter or config tree |
| Visible asset round trip | All 16 assets preserve exact bytes, lengths and digests |
| Source lineage | Every starter normalized-record observation ref resolves to an original |
| Starter rendering | Regenerated visible files match the committed candidate byte for byte |
| Audit prototype | Exact replay, reopen, hash chain, intent/attempt binding and atomic rollback passed |
| Original FAQ | Original hash retained; example answer checked against physical page 9 |
| Remote CI | [Checkpoint branch runs](https://github.com/R-V-Abhishek/ReCycleGuard/actions?query=branch%3Acheckpoint-0); remote results are separate from the local evidence above |

The V01 submitted PR has no original tests; the integration checks above were
added during A02. The submitted H01 suite added 16 tests, and S01 added seven.
The integrated total also includes the original 51 A01 tests and A02 additions.

## Reproduction

Run from the repository root:

```sh
uv sync --locked --python 3.12
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pytest -q
uv run --no-sync scripts/export_schemas.py --check
uv run --no-sync recycleguard doctor
uv build
```

Use a separate environment for a clean install:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/recycleguard-cp0-clean uv sync --locked --python 3.12
UV_PROJECT_ENVIRONMENT=/tmp/recycleguard-cp0-clean uv run --no-sync pytest -q
UV_PROJECT_ENVIRONMENT=/tmp/recycleguard-cp0-runtime \
  uv sync --locked --no-dev --no-editable --python 3.12
UV_PROJECT_ENVIRONMENT=/tmp/recycleguard-cp0-runtime uv run --no-sync recycleguard doctor
```

`uv run --no-sync python -m benchmarks.generator.starter_world` regenerates the
pre-freeze development pack. Do this in a copy or a temporary fixtures directory
when checking a frozen candidate; the reproducibility test already uses a temporary
root. Benchmark/reference code is development/evaluator-only.

The digest manifest records exact candidate inputs. Tests use no provider or
live regulatory acquisition. They do not demonstrate OCR accuracy, production
C08 reconciliation, legal applicability, multi-attempt recovery, power-loss
safety or evaluator sandbox isolation.

The boundary manifest retains its creation-time candidate label and stays byte
identical after acknowledgement. The separate approval ledger is authoritative
for the accepted status; changing a bound model/data file would require a new
manifest and renewed acceptance.
