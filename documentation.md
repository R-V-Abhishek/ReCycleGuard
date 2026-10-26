# ReCycleGuard — working documentation log

Append-only log of work done per session. Source of truth for execution state remains `implementation plan.md` §4.6/§4.7.

## 2026-10-24 22:47 IST — Vedantha — CP0 — V02

**Task state at start:** READY
**Predecessors verified:** CP0 APPROVED

### Done
- Diagnosed the pasted pytest failures as one environment issue: `TemporalValue` validation in `src/recycleguard/contracts/core.py` cannot resolve IANA zones on Windows without the `tzdata` runtime package.
- Confirmed the minimal fix is a shared dependency/config change (`pyproject.toml` plus `uv.lock`), outside V02 ownership.

### Evidence
- Commit/branch: uncommitted
- Tests run: NOT RUN in this session; pasted output shows 172 collected tests with timezone-related failures
- Fixtures/schema versions: none changed
- Gate(s) touched: none

### Limitations / open issues
- No code or dependency files were changed because the required files are owned by Abhishek and cross-owner authorization was declined.
- The pasted suite remains failing until `tzdata` is added to the runtime dependencies and the lockfile is refreshed.

### Updates required
- **implementation_plan.md:** no state change proposed
- **CONTRACTS.md / SYSTEM_DESIGN.md:** none
- **Other docs / fixtures / schemas / tests:** Abhishek should review the shared dependency fix
- **Other members affected:** Abhishek handoff required; re-run the full contract/integration suite after lock refresh

### Next permitted step
- Abhishek reviews and applies the minimal `tzdata` dependency/lockfile fix, then V02 resumes with its storage acceptance tests.

## 2026-10-24 23:05 IST — Vedantha — CP0 — V02

**Task state at start:** READY
**Predecessors verified:** CP0 APPROVED

### Done
- Added the cross-owner runtime dependency `tzdata>=2024.1` to `pyproject.toml` and refreshed `uv.lock`.
- Added [docs/EXECUTION_GUIDE.md](docs/EXECUTION_GUIDE.md) with Windows setup, locked environment, CLI, test, schema, lint and troubleshooting commands.
- Regenerated the five drifted boundary schemas; schema export verification now passes.

### Evidence
- Commit/branch: uncommitted
- Tests run: focused contracts/storage tests → `126 passed`; full suite → `169 passed, 3 failed`
- CLI/schema checks: `uv run recycleguard doctor` → `SCAFFOLD_READY`; `uv run scripts/export_schemas.py --check` → `Checked 50 boundary schemas`
- Fixtures/schema versions: CP0 visible fixtures unchanged; schemas regenerated from current runtime models
- Gate(s) touched: none

### Limitations / open issues
- Three existing byte-level fixture failures remain on this Windows checkout: visible text fixtures are converted to CRLF with `core.autocrlf=true`, and `doc_invoice_payment.pdf` does not match the digest/length recorded in `case_manifest.json`.
- The dependency/timezone failures are fixed; no V02 storage implementation files were changed by this session.

### Updates required
- **implementation_plan.md:** no state change proposed
- **CONTRACTS.md / SYSTEM_DESIGN.md:** none
- **Other docs / fixtures / schemas / tests:** use the execution guide; investigate the pre-existing PDF digest and repository line-ending policy before claiming a green full suite
- **Other members affected:** Abhishek should review `pyproject.toml`/`uv.lock`; fixture owner should repair or re-freeze the mismatched PDF asset

### Next permitted step
- Re-run `uv sync --locked` and the focused V02 tests; separately resolve the visible-fixture integrity baseline before full CP0 acceptance.

## 2026-10-24 23:20 IST — Vedantha — CP0 — V02

**Task state at start:** READY
**Predecessors verified:** CP0 APPROVED

### Done
- Fixed CP0 provenance writers in `benchmarks/generator/cp0_sources.py` to write UTF-8 text with explicit LF bytes on Windows.
- Preserved the existing blob-store behavior; blobs continue to hash and round-trip exact input bytes.

### Evidence
- Commit/branch: uncommitted
- Tests run: focused static diagnostics → no errors; pytest → NOT RUN after edit
- Fixtures/schema versions: visible fixture pack unchanged
- Gate(s) touched: none

### Limitations / open issues
- The checked-in visible fixture pack still needs regeneration or normalization so its on-disk bytes agree with its frozen manifest and artifact digests.

### Updates required
- **implementation_plan.md:** no state change proposed
- **CONTRACTS.md / SYSTEM_DESIGN.md:** none
- **Other docs / fixtures / schemas / tests:** regenerate the CP0 visible pack with the corrected LF writer, then run the four failing fixture/integration tests
- **Other members affected:** Sushanth owns S01/S05 fixture generation; handoff required for re-freezing the visible pack

### Next permitted step
- Re-freeze the visible CP0 fixture pack with S01/S05 ownership, then rerun the full pytest suite.

## 2026-10-26 IST — Sushanth — CP1 — S03

**Task state at start:** READY
**Predecessors verified:** CP1 APPROVED (qualified evidence foundation, lead acceptance 2026-10-26)

### Done
- Added the C08 package `src/recycleguard/domain/`: `universe.py` (server-side input universe + membership digest), `lots.py` (derived credit lots), `allocation.py` (validity + event/lot conservation, demote-only), `priority.py` (earlier-liability check at allocation time), `reconcile.py` (pure engine: required, supported, signed gap, shortfall, surplus, pending, portal comparison, dispositions, coverage), `service.py` (thin `compute_reconciliation`), `models.py`, `arith.py`.
- Strict no-promotion rule: PENDING allocations/events are never turned into supported quantity; checks can only exclude or leave pending.
- Callers cannot supply records: the API takes a pinned `SnapshotRef`; `bucket_ids` select outputs only; a mismatching `expected_input_membership_digest` is rejected with `STALE_SNAPSHOT`.
- Tests: `test_allocation_conservation.py` (G05), `test_reconciliation.py`, `test_c08_universe.py`, `tests/integration/test_s03_cp1_snapshot.py`; builders in `tests/support/c08.py`.

### Evidence
- Commit/branch: `S_branch`, uncommitted
- Tests run: `pytest` (full, Windows) → 293 passed, 12 failed, 3 skipped. The 12 failures are pre-existing and unrelated: `os.O_NOFOLLOW` in `intake/batch.py` (POSIX-only) and `os.getuid` in `local_session.py`; the same 12 failed before S03 (236 passed before, 57 new tests). With a local `O_NOFOLLOW` shim (not committed) the real CP1 pipeline test passes; 5 `getuid` failures remain.
- Real CP1 snapshot through C08 (shim run): required 100.0000, supported 0.0000, pending 80.0000 (55 PENDING allocation + 25 unlinked invoice), coverage QUALIFIED. Reviewed-state `case_001` reference records: required 100, supported 55, signed gap 45, pending 25, portal 55, delta 0.0000, matching `case_001_expected.json`.
- `ruff check` / `ruff format --check` clean; `scripts/export_schemas.py --check` → 77 boundary schemas (unchanged: no contract edits).
- Mutation check (in-process, not committed): disabling the lot cap, promoting pending, or removing the priority check each makes the gate tests fail.
- Gate(s) touched: G05 (new), G03 exercised.

### Limitations / open issues (this is a THIN implementation; raise in the PR)
- No audit/persistence: `storage/authority.py` has no `calculation.` event prefix, so a calculation cannot be committed as an audited operation. The service archives three blobs and writes no audit event (`audit_event_ids=[]`). Owner: Vedantha / Abhishek (A05).
- No CLI or dispatcher hook; `cli.py` untouched. Owner: Abhishek (A05).
- `QuantityDisposition` exists only as prose in CONTRACTS §6.2; S03 uses an internal model with no generated schema. Owner: Abhishek.
- `Allocation` has no allocation timestamp, so priority-at-allocation-time is `UNKNOWN` on real CP1 data; `FAIL`/`PASS` only with the explicit `allocation_order` input. Needs an `allocated_at` field or a reviewed ordering input. Owner: Abhishek / Sampreeth.
- No over-allocation `ErrorCode`; S03 uses `INTEGRITY_FAILED`. `UNSUPPORTED_FEATURE` is an `AbstentionReason`, not an `ErrorCode`, so the disabled purchase ceiling appears only in the derivation (`NOT_EVALUATED`). Owner: Abhishek.
- Real CP1 events/allocations stay PENDING, so there is no path to SUPPORTED in the real pipeline until a reviewed support assertion exists. Owner: Abhishek (review design).
- `CreditLot` is not a `Record`; lots are derived from `Certificate` + events (capacity = certificate face quantity). Needs confirmation of the C04/C08 split.
- Commercial handling is minimal (one unlinked INVOICE/PAYMENT per compatible bucket counts as pending; anything ambiguous is left unassigned). Full matching, F07/F08/F09 and lifecycle expiry are S04.
- Priority rule is stricter than the plan text: with an earlier owing bucket and no order, the result is UNKNOWN even when the earlier bucket ends fully met (end-of-year totals are not used).
- Windows: the 12 pre-existing failures above mean the CP1 pipeline cannot be verified on Windows without a shim; CI (Linux) is the real check for the integration test.

### Updates required
- **implementation_plan.md:** propose S03 READY → IN_REVIEW (needs an independent reviewer before DONE). V03 and A05 may start against `compute_reconciliation` / `CalculationResult` once merged.
- **CONTRACTS.md / SYSTEM_DESIGN.md:** none applied; proposals listed above (allocation timestamp, over-allocation code, QuantityDisposition schema, `calculation.` event prefix)
- **Other docs / fixtures / schemas / tests:** none
- **Other members affected:** Vedantha (persistence/prefix), Abhishek (A05 wiring, contract proposals), Sampreeth (applicability/deadlines keep results QUALIFIED)

### Next permitted step
- Independent review of S03, then S04 (unblocked by S03 acceptance). S05 is independently READY.
