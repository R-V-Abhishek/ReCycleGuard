# CP2 verification evidence

Local platform: macOS, Python 3.12.13. Source integration includes S03 `47c4482`
and V03 `ee2f64a`, based on approved CP1 commit `7797672`.

## Executed checks

- Full suite after integration repairs: **348 passed**. Windows-specific credential
  tests are being added; final platform counts and CI links are recorded below.
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

Pending: GitHub Actions runs the complete applicable suite, schema checks, lint,
format, doctor, fresh-root demonstration and package build on Windows/Linux with
Python 3.11 and 3.12. Native POSIX permission tests have Windows ACL counterparts;
functional pipeline tests are not skipped because of missing O_NOFOLLOW.
