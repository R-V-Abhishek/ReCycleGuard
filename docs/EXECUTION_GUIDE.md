# ReCycleGuard execution guide

This guide describes the supported CP0 workflow from a clean checkout.

## Prerequisites

- Windows PowerShell
- Python 3.11 or newer
- `uv`
- Git

Check the tools from the repository root:

```powershell
python --version
uv --version
git --version
```

The visible fixtures include byte-level digests. On Windows, set Git to keep
those files byte-stable before cloning or refreshing a checkout:

```powershell
git config --global core.autocrlf false
```

For an existing checkout, re-clone after changing this setting rather than
relying on a line-ending conversion of already checked-out fixtures.

## Set up the environment

From `D:\Codespaces\ReCycleGuard` (or the root of your clone), create or
update the locked virtual environment:

```powershell
uv sync --locked
```

The runtime dependency `tzdata` is required on platforms where the operating
system does not provide IANA timezone data. It allows source values such as
`Asia/Kolkata` to pass the contract validation in
`src/recycleguard/contracts/core.py`.

If dependencies or `pyproject.toml` have changed and the lockfile is not
current, refresh it first:

```powershell
uv lock
uv sync --locked
```

Do not activate `.venv` manually when using `uv run`; `uv` selects the locked
environment for each command.

## Validate the project

Run the CP0 checks in this order:

```powershell
uv run recycleguard doctor
uv run pytest
uv run scripts/export_schemas.py --check
```

Run a focused test file while developing:

```powershell
uv run pytest tests/contracts/test_core.py
uv run pytest tests/unit/test_v02_storage.py
```

Run the formatter/linter check:

```powershell
uv run ruff check .
```

If the command reports an environment or dependency error, run `uv sync
--locked` again before changing application code.

## Run the CLI

List the available commands:

```powershell
uv run recycleguard --help
```

Run the read-only environment check:

```powershell
uv run recycleguard doctor
```

The current CP0 scaffold does not yet provide the complete ingestion,
reconciliation, or real-model workflow. Do not interpret a successful
`doctor` command as evidence that those later components are implemented.

## Development workflow

1. Read `implementation plan.md` sections 4.6 and 4.7 before starting a task.
2. Confirm that the task belongs to the active member and that all
   predecessors are complete.
3. Make the smallest change within the task's ownership boundary.
4. Run the narrowest relevant test command, then the full `uv run pytest`
   suite before handoff.
5. Run schema export checks when a contract model or schema changes.
6. Record the exact commands and results in the root `documentation.md`.

## Troubleshooting

### `timezone must be an IANA name`

Ensure the locked environment includes `tzdata`:

```powershell
uv sync --locked
uv run python -c "from zoneinfo import ZoneInfo; print(ZoneInfo('Asia/Kolkata'))"
```

If the check fails, run `uv lock` followed by `uv sync --locked`, then rerun
the test suite.

### `uv sync --locked` reports a lock mismatch

Regenerate the lockfile and sync again:

```powershell
uv lock
uv sync --locked
```

### A test fails after a local edit

Run the failing test file directly first, then rerun the full suite:

```powershell
uv run pytest path\to\test_file.py -q
uv run pytest
```

Do not commit generated runtime data, databases, secrets, hidden evaluation
artifacts, or local environment directories.
