# CP1 verification

Date: 26 October 2026. Scope: qualified evidence foundation.

- Full suite: **250 passed**, including real dossier/source integration, exact
  replay, interrupted-stage manual recovery, source hash/locator checks, numeric
  safety, conservative equivalence and authenticated version-bound final approval.
- Ruff lint: passed. Formatting: 118 files checked.
- Generated schema check: **77 boundary schemas**.
- Wheel and source distribution: built successfully; PDF parser is a runtime dependency.
- Read-only doctor: passed; model gateway remains unavailable.
- Final runtime check: approved case/corpus/profile resolved, every original blob
  hash verified, final case pins approved profile/corpus, profile provision and
  applicability references resolve inside the final corpus.
- Original PDF page-context QA: physical R02 pages 24/27 and R08 page 9 rendered
  and visually inspected. No generated replacement PDF was used.
- No hidden oracle/expected-answer data was loaded into the A04 runtime.

Task PRs #5 and #6 are retained through merge ancestry. GitHub CI is recorded after
push. Approval evidence and accepted qualifications are in approvals.json; this
record does not assert independent four-person acknowledgement.
