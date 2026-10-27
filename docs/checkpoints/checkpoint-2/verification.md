# CP2 verification evidence

Local platform: macOS, Python 3.12.13. Source integration includes S03 `47c4482`
and V03 `ee2f64a`, based on approved CP1 commit `7797672`.

## Executed checks

- Full applicable suite passed on both supported operating systems and Python versions;
  exact native CI totals are recorded below.
- 94 generated schemas checked against actual runtime models.
- Ruff lint and format checks passed.
- Wheel and source distribution built successfully. The first sandbox build could
  not resolve PyPI DNS; the authorized network-enabled build succeeded.
- Doctor confirmed SQLite FTS5; model gateway remains UNAVAILABLE.
- Actual fresh-root reproduction completed without network/model/oracle access.
  It produced a qualified working paper and two baseline audit events.

## Fresh-root observations

17 case originals; 19 extraction outputs; 34 case observations with complete
normalization dispositions. The frozen calculation universe contains 13 revisions,
including all 3 superseded originals, and 13 matching calculation dispositions.
10 revisions remain active. Superseded records are explicitly excluded, not erased.

Before support review: required 100, supported 0, gap 100, pending 80 kg.
After review: required 100, supported 55, gap 45, pending 25 kg.
Both results are PARTIAL; report verification is QUALIFIED. The 25 kg invoice never
establishes a transfer or an allocation. The 55 kg account total is only comparison
evidence, never the origin of supported credit.

## Rejection and failure coverage

Tests exercise over-allocation at event/lot level; pending non-promotion; missing
history/order; unusable earlier targets; exact membership/profile pins; full-payload
and ordering digests; rejection of unaudited support flags; human capability and
stale review checks; payment/account/wrong-locator rejection; original preservation;
exact replay; audit commit failure; and persisted audit hash corruption.

Report tests reject changed numbers, embedded calculations, rendered text, claim
placeholders, exact citation locators/revisions, revision indexes, duplicate IDs and
prohibited claims. Empty findings render successfully; multiple findings retain
separate next actions. Source/legal semantic correctness is not inferred by these
structural checks.

## Platform matrix

All four jobs passed on technical candidate `a55138d541a35b227d36e09b71bb48f8c8a397bc`:
[GitHub Actions evidence](https://github.com/R-V-Abhishek/ReCycleGuard/actions/runs/40538495376).

| OS | Python | Full suite | Additional checks |
| --- | --- | --- | --- |
| Windows | 3.11 | 352 passed, 2 POSIX-only skips | Native ACL smoke, fresh-root demo, schemas, lint/format, doctor and build passed |
| Windows | 3.12 | 352 passed, 2 POSIX-only skips | Native ACL smoke, fresh-root demo, schemas, lint/format, doctor and build passed |
| Linux | 3.11 | 348 passed, 6 Windows-only skips | Fresh-root demo, schemas, lint/format, doctor and build passed |
| Linux | 3.12 | 348 passed, 6 Windows-only skips | Fresh-root demo, schemas, lint/format, doctor and build passed |

No functional pipeline test is skipped because O_NOFOLLOW is unavailable. Platform
primitive tests run against their actual OS: Windows ACL owner/inheritance/grants,
atomic creation and link refusal; POSIX owner/mode/symlink checks.

The first native runs exposed a PowerShell module-autoload collision and copied
fixture credential ownership. Direct .NET ACL operations plus a subprocess-local
module path resolved the former. Re-enrolling the reviewer when cloning evidence
fixtures resolved the latter. Ownership and permission checks were not weakened.

The lock documentation commit contains no source/test/config changes relative to
this passing technical candidate. The boundary manifest freezes 242 code/config,
fixture and schema files plus the checked-in demonstration evidence.
