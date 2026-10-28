# A06 verification

Local verification on 28 October 2026:

- Complete suite: **430 passed, 6 skipped**. The skipped tests require Windows.
- A06 contributes **82 tests**, covering graph control, storage and crash recovery.
- Ruff lint and formatting passed. All **112** exported boundary schemas matched.
- CLI diagnostics reported SQLite FTS5 available and the real model gateway
  unavailable. Source distribution and wheel builds passed.
- The [fresh-root scripted demo summary](evidence/a06-summary.json) records four
  scripted model calls, two tool actions, one reformulation and six committed
  turns. Final state: `AWAITING_REVIEW`; review: `PENDING`. Measured usage and cost
  remain unavailable. Its source and dependency-lock digests identify the run.

The CI workflow runs the full suite, schema checks, diagnostics, CP2/A06 fresh-root
demonstrations and packaging on Windows/Linux with Python 3.11/3.12. See
[A06 branch CI](https://github.com/R-V-Abhishek/ReCycleGuard/actions/workflows/ci.yml?query=branch%3Acodex%2Fa06)
for the published matrix result. Local checks alone do not establish native Windows
execution; use the Windows jobs as that evidence.

These are correctness and recovery checks over synthetic fixtures and scripted
ports. They measure neither model quality nor production service performance.
They do not approve CP3. Reproduction commands and remaining boundaries are in
the [A06 handoff](a06.md).
